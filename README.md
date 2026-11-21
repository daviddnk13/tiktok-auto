# First Paycheck Math — TikTok automático

Pipeline de GitHub Actions que **genera y sube solo** los videos del canal
de TikTok **@firstpaycheckmath** (finanzas personales explicadas en inglés
para jóvenes de EE. UU. con su primer salario). Es el tercer pipeline de la
casa, con la misma arquitectura probada de `yt-shorts-auto` (TrucoCero) y
`sharpcents-auto` (SharpCents): guion con IA y fallbacks, voz Kokoro,
subtítulos con tiempos reales de faster-whisper, avisos por Telegram e
historial versionado por el propio bot.

Diferencias clave frente a los canales de YouTube:

- **Sin Pexels ni stock.** TikTok penaliza como «no original» el formato
  video de stock + texto, así que los visuales se **generan por código**
  para cada tema (`visuals.py`): curva de interés compuesto animada, tabla
  tipo hoja de cálculo que se llena fila a fila y barras comparativas. Las
  cifras del gráfico las calcula el código, nunca el modelo de IA.
- **La subida usa la sesión real de la cuenta** (ver «El paso manual»),
  porque la API oficial de TikTok mantiene privados los videos de cuentas
  sin auditar.

## Cómo funciona una corrida

1. Lee el siguiente tema con estado `pendiente` de `estrategia.json`.
2. Genera el guion con IA (Gemini → NVIDIA NIM, modelos en `config.json`
   clave `modelos`). El prompt lleva el cumplimiento financiero dentro:
   solo explicar cómo funcionan las cosas, nada de consejo personalizado,
   tickers ni productos concretos; y la regla de oro de la casa: el video
   entrega exactamente las cifras que promete el gancho.
3. Sintetiza la voz por escenas con **Kokoro** (`am_michael`, en-us, ×1.08);
   si una escena falla, cae a **edge-tts** (`en-US-AndrewNeural`) solo en
   esa escena. Los tiempos por palabra salen de **faster-whisper**
   alineando lo escuchado con el texto del guion (el texto mostrado es
   siempre el del guion); si whisper falla, reparto proporcional.
4. Renderiza el visual animado del tema (1080×1920) y compone el video
   final con ffmpeg: visual + voz + subtítulos ASS (WrapStyle 0, grupos de
   ~3 palabras, verde lima sobre oscuro, siempre dentro del cuadro) +
   banner del gancho los primeros segundos.
5. Genera la portada del video (`cover-<id>.jpg`, con el gancho y la cifra
   del tema) y lo sube a TikTok con `upload_tiktok.py` (si
   `subida.activada` está en `true` en `config.json`): si aún falta más
   de media hora para el slot de publicación (23:30 UTC), el post queda
   **programado** con la programación nativa de TikTok para ese slot;
   si no, se publica de inmediato.
6. Marca el tema como `publicado`, añade la entrada a `historial.json`
   y avisa por Telegram. El workflow commitea `historial.json` y
   `estrategia.json`.
7. Al final de la corrida, si `config.json` trae `"analitica": true`,
   `analitica.py` intenta rellenar el `metricas_48h` de las entradas
   que ya cumplieron 48 h (ver la sección siguiente). Es best-effort:
   si falla, la corrida ni se entera.

Horario (`.github/workflows/publish.yml`): **15:30 y 23:30 UTC** — mañana
y tarde-noche en EE. UU. —, un video por corrida, dos al día. El workflow
`model_health.yml` prueba los modelos de IA cada lunes, igual que en los
otros repos.

## Analítica a las 48 h y tendencias (solo lectura)

Dos piezas de **solo lectura** basadas en
[davidteather/TikTok-Api](https://github.com/davidteather/TikTok-Api)
(MIT, fijado en `requirements.txt` como `TikTokApi==7.3.5`). Ninguna de
las dos publica, comenta ni toca la cuenta: solo leen.

### `analitica.py` — snapshot `metricas_48h`

Igual que el `views_48h` de los canales de YouTube: cuando una entrada
de `historial.json` cumple **48 h desde que el video salió** (su
`programado_para` si el post quedó programado; si no, su `fecha` de
subida) y aún no tiene `metricas_48h`, se traen los videos propios de
la cuenta con TikTok-Api (sesión creada desde el mismo `cookies.txt`
de la subida, parseado a dict) y se empareja cada entrada con su video:

1. **Por descripción:** el caption guardado empieza por el gancho y es
   la descripción del video en TikTok; si el inicio coincide, es ese.
2. **Por fecha:** el video cuya `createTime` esté más cerca del
   instante de publicación, dentro de ±36 h.

Al emparejar, `metricas_48h` queda como
`{vistas, likes, comentarios, compartidos, capturado_en}`.
`main.py` lo invoca al final de cada corrida (en un `finally`, tras el
aviso de Telegram) solo si `config.json` trae `"analitica": true`, y el
paso de commit del workflow recoge el `historial.json` actualizado.
**Best-effort por diseño:** todo va envuelto en try/except; si
TikTok-Api falla se registra en el log y la corrida termina como si
nada. También se puede correr a mano: `python analitica.py
[cookies.txt]`.

### `tendencias.py` — insumo para elegir temas

CLI independiente (`python tendencias.py`): trae los videos en
tendencia, se queda con los adyacentes a finanzas personales /
presupuesto / nómina / trabajo en EE. UU. (filtro por palabras clave
sobre descripción y hashtags) y escribe **`tendencias.json`** con
`{generado_en, videos: [{descripcion, vistas, likes, hashtags}],
hashtags_top: [{hashtag, menciones}]}`. Es un insumo para elegir los
próximos temas de `estrategia.json` **a mano**: no modifica la cola ni
lo invoca `main.py`.

### Riesgos honestos de la lectura

- **Bloqueo por IP de datacenter.** TikTok suele bloquear estas
  lecturas desde IPs de datacenter, y los runners de GitHub Actions lo
  son. En Actions la analítica puede fallar a menudo (sin afectar a la
  publicación, que va por otra ruta); el sitio fiable para
  `tendencias.py` — y para la analítica si se quiere puntual — es el
  **servidor de David**, con su IP y sesión estables.
- **Cookies que caducan.** La sesión de TikTok-Api usa las mismas
  cookies que la subida; si vencen, la lectura falla igual que fallaría
  la subida, y toca re-exportarlas (ver «El paso manual»).
- **Es scraping no oficial** (la API oficial no da estas métricas sin
  auditoría). Se usa solo en lectura, a ritmo humano (al final de cada
  corrida, una pasada), el mismo criterio que con la subida.

## Secrets necesarios (GitHub → Settings → Secrets → Actions)

| Secret | Para qué |
|---|---|
| `GEMINI_API_KEY` | Guion (principal) — la misma de los otros repos |
| `NVIDIA_API_KEY` | Guion (respaldo NIM) — la misma de los otros repos |
| `TG_BOT_TOKEN` / `TG_CHAT_ID` | Avisos de Telegram — los mismos |
| `TIKTOK_COOKIES` | **El contenido del `cookies.txt` de la sesión de TikTok** (ver abajo) |

## ⚠️ El paso manual: las cookies de TikTok

La subida usa el paquete `tiktok-uploader`, que automatiza la web de
TikTok con las cookies de la sesión iniciada. Hay **un único paso manual**
y hay que repetirlo cuando las cookies venzan (TikTok las invalida cada
cierto tiempo o al cerrar sesión en todos los dispositivos):

1. Con la sesión de **@firstpaycheckmath** abierta en el navegador, instala
   la extensión **«Get cookies.txt LOCALLY»** y exporta las cookies de
   `tiktok.com` (formato Netscape; lo importante es que incluya la cookie
   `sessionid`).
2. En GitHub: repo → Settings → Secrets and variables → Actions →
   `TIKTOK_COOKIES` → pega **todo el contenido** del archivo exportado.
3. Listo: la siguiente corrida ya sube sola. Si las cookies vencen, la
   corrida falla con un aviso de Telegram que dice exactamente esto, y el
   tema queda en `pendiente` para reintentarse en la siguiente corrida.

El archivo `cookies.txt` está en `.gitignore`: **nunca** se commitea.

### Riesgos honestos de esta ruta

- **Es una ruta no oficial.** La oficial (Content Posting API) deja los
  videos en privado hasta que la app pasa una auditoría de TikTok, así que
  para publicar en público sin auditar, esta es hoy la vía práctica.
- **Las cookies vencen** y tocará re-exportarlas de vez en cuando (el bot
  avisa por Telegram cuando pase).
- **TikTok puede pedir CAPTCHA o bloquear IPs de datacenter** (los runners
  de GitHub Actions lo son). Si eso se vuelve frecuente, la alternativa es
  correr el mismo código en el servidor de David (abajo), cuya IP y sesión
  son estables.
- Automatizar subidas puede violar los términos de TikTok si se abusa;
  este pipeline publica 2 videos/día originales, el ritmo acordado.

### Alternativa: correrlo en el servidor de David

El mismo código funciona fuera de Actions, sin cambios: hay un kit
completo en `servidor/` (instalador, envoltorio de corrida y unidades
systemd con timer a las mismas horas). Ver la sección «Modo servidor
(sin GitHub Actions)» más abajo.

## Puesta en marcha (una sola vez)

1. Crea el repo en GitHub (p. ej. `tiktok-auto`) y sube esta carpeta.
2. **Los workflows se pegan a mano:** la app de GitHub de Muse no tiene
   permiso «Workflows» (pasa igual que en los repos de YouTube), así que
   crea `.github/workflows/publish.yml` y `.github/workflows/model_health.yml`
   desde la web de GitHub o desde tu clon local, con el contenido de esta
   carpeta.
3. Crea los cinco secrets de la tabla (las claves de IA y Telegram son las
   mismas de los otros repos; solo `TIKTOK_COOKIES` es nuevo).
4. Lanza una corrida manual (Actions → Auto First Paycheck Math → Run
   workflow) y verifica el aviso de Telegram y el video en el perfil.

## Modo servidor (sin GitHub Actions)

**Por qué:** la primera corrida real en Actions (2026-11-21) generó
todo perfecto — guion, voz Kokoro, video, portada y analítica — pero
TikTok **rechazó la subida desde la IP de datacenter de GitHub
Actions** (tiktok-uploader reportó el video como no subido; el tema
quedó en `error_subida`, pendiente de reintento). La salida: correr el
mismo pipeline en el servidor de David, con su IP y su sesión estables.
El kit vive en `servidor/`:

- `instalar.sh` — instalación idempotente: clona/actualiza el repo en
  `/opt/tiktok-auto`, crea el venv, instala dependencias y el Chromium
  de Playwright, crea el `.env` (permisos 600) e instala las unidades
  systemd.
- `run.sh` — el envoltorio de cada corrida: espeja el workflow (mismas
  variables de entorno; `TIKTOK_COOKIES` se materializa en un temporal
  que se borra al salir; commit del bot de `historial.json` +
  `estrategia.json` siempre, con el mismo mensaje, y push a GitHub).
- `tiktok-auto.service` / `tiktok-auto.timer` — systemd, 15:30 y
  23:30 UTC (`Persistent=true`: si el servidor estaba apagado a la
  hora, la corrida sale al arrancar).
- `env.ejemplo` — las 5 variables con comentarios de dónde sale cada
  valor. **Nunca** lleva valores reales.

**Comandos exactos en el servidor** (una sola vez):

```bash
# 1. Clona el repo en /opt con tu URL/alias SSH habitual (la misma
#    forma con la que clonas cuba-bots en este servidor):
cd /opt && git clone git@github.com:daviddnk13/tiktok-auto.git

# 2. Instala todo (venv, Chromium, unidades systemd, .env):
sudo bash /opt/tiktok-auto/servidor/instalar.sh

# 3. Rellena las 5 variables (claves nuevas de este repo, Telegram y
#    el contenido completo de tu cookies_tiktok.txt):
nano /opt/tiktok-auto/.env

# 4. Primera corrida, a mano:
sudo systemctl start tiktok-auto.service

# 5. Mírala en vivo:
journalctl -u tiktok-auto -f
```

El timer queda activado (`enable`) con el paso 2; compruébalo con
`systemctl list-timers tiktok-auto.timer`.

**Cómo conviven ambos modos:** Actions y el servidor hacen exactamente
lo mismo a las mismas horas — si los dos quedan activos, **publicarían
duplicado** (y se pisarían los commits del historial). Si el servidor
queda como ejecutor, desactiva los crons de Actions **a mano en la web
de GitHub**: repo → Actions → workflow «Auto First Paycheck Math» → ⋯ →
**Disable workflow**. (La app de GitHub de Muse no puede tocar los
workflows; es un paso tuyo de dos clics.)

**Nota honesta:** la IP del servidor también es de datacenter (Oracle
Cloud). Es estable y es la misma desde la que ya operan otros servicios
de David, pero si TikTok también la rechazara en la subida, el
siguiente paso es correr `servidor/run.sh` en su PC con WSL — la red
donde vive la sesión del navegador — con el mismo `.env`.

## La cola de temas (`estrategia.json`)

14 temas para la primera semana, cada uno con su `gancho` (primera línea
del guion), su `visual` (tipo + datos que el código convierte en cifras) y
su `cta`. El tema 1 (Roth IRA) está `en_produccion` — se está produciendo
a mano la primera noche — así que el pipeline empieza por el tema 2.
Para añadir temas: copia un bloque, cambia `titulo`, `gancho`, `visual` y
`cta`, y déjalo en `pendiente`. Si la cola se vacía, el bot avisa por
Telegram en vez de inventarse un plan.

Tipos de visual disponibles: `growth_curve` (mensual/tasa_anual/anios),
`budget_table` (columnas/filas) y `comparison_bars` (barras directas o
`calculo` con tipo `deuda`, `match401k` o `interes` — las cifras se
calculan en código).

## Prueba local (dry-run)

Sin claves de IA ni subida, para validar voz + visual + subtítulos:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Reutiliza los modelos Kokoro ya descargados en la maquina de pruebas:
export TT_KOKORO_DIR=~/workspace/kokoro-test
```

En esta carpeta ya hay un ejemplo generado así: `dryrun-topic2.mp4`
(tema 2, guion de muestra escrito a mano con la misma voz y extensión
que produciría la IA, porque en la máquina local no hay claves de IA).

## Notas

- `config.json` concentra lo ajustable: modelos de IA, voz y proveedor
  TTS (`tts`), velocidad, rango de duración objetivo, el flag
  `analitica` (`true` activa el snapshot de métricas a las 48 h de
  `analitica.py` al final de cada corrida) y el bloque
  `subida`: `subida.activada` (con `false` el pipeline renderiza sin
  subir, útil para pruebas), `subida.portada` (portada personalizada
  por video, `true` por defecto), `subida.programar` (programación
  nativa de TikTok, `true` por defecto) y `subida.hora_slot_utc` (hora
  UTC del slot al que se programa el post cuando la corrida llega con
  más de media hora de antelación; por defecto `23.5`, es decir,
  23:30 UTC).
- Los videos ya publicados no se re-renderizan: cualquier arreglo aplica
  desde la siguiente corrida, como en los canales de YouTube.
- La pregunta para comentarios que genera la IA (`pregunta`) se añade al
  final del caption, porque `tiktok-uploader` no puede fijar comentarios.
