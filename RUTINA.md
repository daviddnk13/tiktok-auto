# Rutina de publicación de TikTok — @firstpaycheckmath (First Paycheck Math)

**Por qué existe esta rutina:** dos cosas fallan fuera de nuestro control:
(1) TikTok rechaza la subida desde la IP de datacenter de GitHub Actions
(`error_subida` en el historial), así que el workflow guarda el video como
artefacto `video-fallido` y lo sube Romo desde su navegador. (2) El horario
programado de Actions (15:30 y 23:30 UTC) **nunca se ha disparado solo**
(verificado el 2026-11-21: el workflow está activo y el cron es correcto, pero
en el historial del repo solo existen corridas manuales). Por eso las rutinas
de Romo también **disparan la generación** desde la sesión de GitHub de David,
abierta en el perfil «TikTok» (`pc7057f97d86f`) del navegador, donde además
vive la sesión de @firstpaycheckmath.

## Ciclo completo (en orden)

0. **Disparar la generación (si falta).** Leer `historial.json` del repo
   `daviddnk13/tiktok-auto`. Si ya existe una entrada de la franja actual
   (commit del bot o entrada nueva en las últimas ~2 h), el disparo ya ocurrió
   (quizá GitHub despertó solo): saltar al paso 1. Si no: en el perfil
   «TikTok» del navegador, abrir Actions → «Auto First Paycheck Math» →
   **Run workflow** → confirmar. Después esperar a que aterrice la corrida:
   releer `historial.json` cada ~5 min hasta que aparezca la entrada nueva
   (máximo ~50 min). Si la sesión de GitHub está caída, NO pedir credenciales:
   reportar a David en el chat principal y terminar.
1. **Detectar el video a subir.** Hay trabajo si existe alguna entrada del
   historial con `estado: "error_subida"` cuyo tema siga `pendiente` en la
   `cola` de `estrategia.json`. Se procesa **la más antigua** (orden de la
   cola), una sola por ciclo. Si no hay ninguna, terminar en silencio.
2. **Bajar el video.** En el perfil «TikTok»: Actions → la corrida que produjo
   esa entrada (emparejar corridas y entradas por orden temporal) → descargar
   su artefacto `video-fallido` → descomprimir → `final_video.mp4`. Verificar
   con ffprobe: 1080×1920 y duración 55–95 s.
3. **Caption.** Reconstruir: la descripción guardada en el campo `error` de la
   entrada (viene truncada al final) se completa con el `cta` del tema en
   estrategia; se añade la línea de cifras clave del `visual` del tema
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
   a ahora + 20 min** (el selector de Studio muestra hora local GMT-4: 15:30
   UTC = 11:30, 23:30 UTC = 19:30). Si la programación no está disponible,
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
- Una sola subida por ciclo, siempre la más antigua pendiente.
- El video 1 (Roth IRA, publicado a mano el 2026-11-21) y el tema 1 de la cola
  (`en_produccion`) son el mismo: no volver a subirlo.
- Las publicaciones programadas NO se pueden editar en Studio: para cambiar la hora hay que eliminar la publicación y volver a subirla.
- Si el hueco (15:30 o 23:30 UTC) ya lo ocupa otra publicación programada, usar el siguiente hueco libre; nunca dos videos en el mismo minuto.
- Si el horario de Actions despierta algún día, el paso 0 lo detecta (la
  entrada ya existe) y no se duplica ninguna generación.
- Las cookies y los secrets no intervienen en esta rutina: las sesiones del
  navegador son la única llave. Si una sesión muere, David vuelve a iniciar
  sesión en el perfil «TikTok» y la rutina sigue.
