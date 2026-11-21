# Rutina de publicación de TikTok — @firstpaycheckmath (First Paycheck Math)

**Por qué existe esta rutina:** GitHub Actions genera cada video (corridas 15:30 y
23:30 UTC), pero TikTok rechaza la subida desde la IP de datacenter de Actions
(`error_subida` en el historial). El workflow guarda el video renderizado como
artefacto `video-fallido`. Romo sube cada video desde su navegador, en el perfil
«TikTok» (`pc7057f97d86f`), donde viven la sesión de @firstpaycheckmath y la
sesión de GitHub de David. Probado de punta a punta el 2026-11-21 con el tema 2.

## Ciclo por video (en orden)

1. **Detectar.** Leer `historial.json` y `estrategia.json` del repo
   `daviddnk13/tiktok-auto` (API de GitHub). Hay trabajo solo si la última
   entrada del historial tiene `estado: "error_subida"` y su tema sigue
   `pendiente` en la `cola` de estrategia. Si no hay nada así, terminar en
   silencio.
2. **Bajar el video.** En el perfil «TikTok» del navegador: Actions del repo →
   corrida más reciente de «Auto First Paycheck Math» → descargar el artefacto
   `video-fallido` → descomprimir → `final_video.mp4`. Verificar con ffprobe:
   1080×1920 y duración 55–95 s. Si la sesión de GitHub está caída, NO pedir
   credenciales: reportar a David en el chat principal que hay que volver a
   iniciar sesión en ese perfil.
3. **Caption.** Reconstruir: la descripción guardada en el campo `error` de la
   entrada del historial (viene truncada al final) se completa con el `cta` del
   tema en estrategia; se añade la línea de cifras clave del `visual` del tema
   (p. ej. `$1,400 needs · $840 wants · $560 future you`), los hashtags del
   nicho (los del video 1: #personalfinance #budgeting #firstpaycheck
   #moneytips #paycheck #financialliteracy #moneytok #firstjob
   #budgetingtips, más uno específico del tema si aplica) y la línea final
   `Educational only — not financial advice.`
4. **Portada.** Local, con el código del repo:
   `visuals.render_cover(tema["visual"], tema["gancho"], "cover.jpg")`.
   Verificar visualmente que la cifra clave y el gancho se leen bien.
5. **Subir en TikTok Studio** (mismo perfil del navegador): caption exacto;
   Editar portada → Cargar portada con la generada; **etiqueta «Contenido
   generado por IA» ACTIVADA**; comentarios permitidos; visibilidad pública.
   **Programar al siguiente hueco (15:30 o 23:30 UTC) estrictamente posterior
   a ahora + 20 min** (el selector de Studio muestra hora local GMT-5: 15:30
   UTC = 10:30, 23:30 UTC = 18:30). Si la programación no está disponible,
   publicar al momento y decirlo en el reporte. Si TikTok pide una
   verificación de identidad o un rompecabezas que no se resuelve, detenerse
   y reportar a David.
6. **Corregir el estado en el repo** (push-files): en `estrategia.json`, el
   tema pasa a `estado: "publicado"` con `url`, `programado_para` (ISO UTC) y
   `publicado_via: "Romo desde el navegador (artefacto de Actions)"`. En
   `historial.json`, la entrada pasa a `estado: "publicado"` con `url` y
   `programado_para`; el texto del error de Actions se conserva en
   `error_actions` y se añade `via` explicando la ruta.
7. **Reportar** a David en el chat principal: tema, URL del video y hora UTC
   de salida. Reportar solo cuando hubo subida o cuando algo necesita su
   mano; si no había nada pendiente, terminar sin mensaje.

## Reglas que no se rompen

- Nunca subir un tema que ya figure `publicado` en estrategia.
- Una sola subida por ciclo; si la corrida de Actions aún no terminó, esperar
  al siguiente ciclo en vez de reintentar en caliente.
- El video 1 (Roth IRA, publicado a mano el 2026-11-21) y el tema 1 de la cola
  (`en_produccion`) son el mismo: no volver a subirlo.
- Las cookies y los secrets no intervienen en esta rutina: la sesión del
  navegador es la única llave. Si la sesión de TikTok muere, David vuelve a
  iniciar sesión en el perfil «TikTok» y la rutina sigue.
