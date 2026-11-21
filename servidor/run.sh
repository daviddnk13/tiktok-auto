#!/usr/bin/env bash
# =====================================================================
#  First Paycheck Math — envoltorio de cada corrida en el servidor
# =====================================================================
#  Lo ejecuta tiktok-auto.service (systemd, Type=oneshot). Espeja el
#  paso "Generate and Upload Video" y el paso "Save plan and history"
#  de .github/workflows/publish.yml:
#    - Entorno: GEMINI_API_KEY, NVIDIA_API_KEY, TG_BOT_TOKEN,
#      TG_CHAT_ID y las cookies de TikTok, leidos de .env.
#    - TIKTOK_COOKIES llega como CONTENIDO en .env; aqui se
#      materializa en un archivo temporal (mktemp, 0600) que se pasa
#      al codigo como TIKTOK_COOKIES_FILE y se borra al salir (trap),
#      igual que el codigo en Actions escribe el secret a un temporal
#      y lo elimina al terminar.
#    - Commit del bot SIEMPRE (haya ido bien o mal la subida), con el
#      mismo usuario, mensaje y pasos que el workflow:
#      git add historial.json estrategia.json ->
#      commit "chore: update plan and history" -> pull --rebase -> push
#    - El script termina con el codigo de salida de main.py.
# =====================================================================

BASE=/opt/tiktok-auto
cd "$BASE" || { echo "run.sh: no existe $BASE" >&2; exit 1; }

# --- 1. Cargar .env (exporta todas las variables) ---------------------
if [ ! -f "$BASE/.env" ]; then
    echo "run.sh: falta $BASE/.env — crealo desde servidor/env.ejemplo y rellenalo." >&2
    exit 1
fi
set -a
# shellcheck disable=SC1091
. "$BASE/.env"
set +a

# --- 2. Materializar las cookies en un temporal -----------------------
TMP_COOKIES=""
cleanup() {
    if [ -n "$TMP_COOKIES" ]; then
        rm -f "$TMP_COOKIES"
    fi
}
trap cleanup EXIT

if [ -n "${TIKTOK_COOKIES:-}" ]; then
    TMP_COOKIES=$(mktemp /tmp/tiktok-cookies.XXXXXX.txt)
    chmod 600 "$TMP_COOKIES"
    printf '%s' "$TIKTOK_COOKIES" > "$TMP_COOKIES"
    export TIKTOK_COOKIES_FILE="$TMP_COOKIES"
    unset TIKTOK_COOKIES
    echo "run.sh: cookies materializadas en temporal (TIKTOK_COOKIES_FILE)."
else
    echo "run.sh: TIKTOK_COOKIES vacio en .env; el codigo usara cookies.txt junto al repo si existe."
fi

# --- 3. Traer lo ultimo del repo (equivale al checkout de Actions) ----
git pull --rebase || echo "run.sh: AVISO — git pull --rebase fallo; sigo con la copia local." >&2

# --- 4. La corrida -----------------------------------------------------
"$BASE/venv/bin/python" main.py
RC=$?
echo "run.sh: main.py termino con codigo $RC."

# --- 5. Commit del bot, SIEMPRE (espejo del paso del workflow) --------
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add historial.json estrategia.json
if git commit -m "chore: update plan and history"; then
    git pull --rebase
    git push
else
    echo "run.sh: sin cambios en historial/estrategia; nada que commitear."
fi

exit $RC
