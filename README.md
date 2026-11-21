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
5. Sube el video a TikTok con `upload_tiktok.py` (si `subida.activada`
   está en `true` en `config.json`) y lo publica de inmediato.
6. Marca el tema como `publicado`, añade la entrada a `historial.json`
   (con el campo `metricas_48h` reservado para el snapshot de métricas a
   las 48 h, como el `views_48h` de YouTube) y avisa por Telegram. El
   workflow commitea `historial.json` y `estrategia.json`.

Horario (`.github/workflows/publish.yml`): **15:30 y 23:30 UTC** — mañana
y tarde-noche en EE. UU. —, un video por corrida, dos al día. El workflow
`model_health.yml` prueba los modelos de IA cada lunes, igual que en los
otros repos.

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

El mismo código funciona fuera de Actions: clona el repo en el servidor,
crea un venv con `requirements.txt`, instala Playwright
(`python -m playwright install --with-deps chromium`), deja el
`cookies.txt` junto al repo (o exporta `TIKTOK_COOKIES_FILE` con su ruta)
y programa `python main.py` en cron a las mismas horas. Sin cambios de
código.

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
  TTS (`tts`), velocidad, rango de duración objetivo y el interruptor
  `subida.activada`. Con `subida.activada: false` el pipeline renderiza
  sin subir (útil para pruebas).
- Los videos ya publicados no se re-renderizan: cualquier arreglo aplica
  desde la siguiente corrida, como en los canales de YouTube.
- La pregunta para comentarios que genera la IA (`pregunta`) se añade al
  final del caption, porque `tiktok-uploader` no puede fijar comentarios.
