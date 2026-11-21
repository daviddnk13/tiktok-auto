#!/usr/bin/env bash
# =====================================================================
#  First Paycheck Math — instalacion en el servidor (modo servidor)
# =====================================================================
#  Deja el pipeline corriendo en ESTE servidor con systemd, sin
#  GitHub Actions. Idempotente: se puede repetir sin romper nada.
#
#  Uso (como root, p. ej. desde el clon del repo):
#      sudo bash servidor/instalar.sh [URL_DEL_REPO]
#
#  Si /opt/tiktok-auto no existe, lo clona de URL_DEL_REPO (por
#  defecto la URL SSH normal de GitHub; pasa la tuya con tu alias SSH
#  habitual si la necesitas, igual que con cuba-bots). Si ya existe,
#  hace git pull.
#
#  Lo que hace:
#    1. Clona o actualiza el repo en /opt/tiktok-auto (como ubuntu).
#    2. Instala paquetes del sistema: git, python3 + venv, ffmpeg y
#       fonts-dejavu (los mismos que instala el workflow de Actions).
#    3. Crea el venv en /opt/tiktok-auto/venv e instala
#       requirements.txt.
#    4. Instala el Chromium de Playwright (navegador en la cache de
#       ubuntu, que es quien correra el servicio; dependencias del
#       sistema como root).
#    5. Crea /opt/tiktok-auto/.env desde servidor/env.ejemplo si no
#       existe (permisos 600) y avisa de que hay que rellenarlo.
#    6. Instala las unidades systemd y activa el timer
#       (15:30 y 23:30 UTC, 2 corridas/dia).
# =====================================================================
set -e

BASE=/opt/tiktok-auto
REPO_URL="${1:-git@github.com:daviddnk13/tiktok-auto.git}"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: ejecuta este script con sudo:  sudo bash servidor/instalar.sh" >&2
    exit 1
fi

# Ejecuta un comando como el usuario ubuntu (dueno del servicio).
como_ubuntu() {
    sudo -H -u ubuntu "$@"
}

echo "==> 1/6 Repo en $BASE"
if [ -d "$BASE/.git" ]; then
    echo "    Ya existe: actualizo con git pull..."
    como_ubuntu git -C "$BASE" pull --rebase
else
    echo "    Clono $REPO_URL ..."
    como_ubuntu git clone "$REPO_URL" "$BASE"
fi

echo "==> 2/6 Paquetes del sistema (git, python3, venv, ffmpeg, fuentes)"
apt-get update
apt-get install -y git python3 python3-venv ffmpeg fonts-dejavu

echo "==> 3/6 Entorno virtual e dependencias de Python"
if [ ! -x "$BASE/venv/bin/python" ]; then
    como_ubuntu python3 -m venv "$BASE/venv"
fi
como_ubuntu "$BASE/venv/bin/pip" install --upgrade pip
como_ubuntu "$BASE/venv/bin/pip" install -r "$BASE/requirements.txt"

echo "==> 4/6 Chromium de Playwright"
como_ubuntu "$BASE/venv/bin/python" -m playwright install chromium
"$BASE/venv/bin/python" -m playwright install-deps chromium

echo "==> 5/6 Archivo .env"
if [ -f "$BASE/.env" ]; then
    echo "    .env ya existe: lo dejo tal cual."
else
    cp "$BASE/servidor/env.ejemplo" "$BASE/.env"
    echo "    .env creado desde servidor/env.ejemplo."
fi
chmod 600 "$BASE/.env"
chmod +x "$BASE/servidor/run.sh"

echo "==> 6/6 Unidades systemd"
cp "$BASE/servidor/tiktok-auto.service" /etc/systemd/system/tiktok-auto.service
cp "$BASE/servidor/tiktok-auto.timer" /etc/systemd/system/tiktok-auto.timer
systemctl daemon-reload
systemctl enable tiktok-auto.timer

# Todo el arbol queda del usuario que corre el servicio.
chown -R ubuntu:ubuntu "$BASE"

echo ""
echo "=================================================================="
echo " Instalacion terminada. FALTA UN PASO MANUAL:"
echo ""
echo "   1. Rellena las 5 variables en el .env:"
echo "          nano $BASE/.env"
echo "      (instalar.sh lo dejo con marcadores; sin valores reales"
echo "       la corrida fallara con avisos claros.)"
echo ""
echo "   2. Primera corrida de prueba, a mano:"
echo "          sudo systemctl start tiktok-auto.service"
echo "          journalctl -u tiktok-auto -f"
echo ""
echo "   El timer ya quedo activado (enable) para las 15:30 y las"
echo "   23:30 UTC; para verlo:  systemctl list-timers tiktok-auto.timer"
echo "   Y recuerda DESACTIVAR el workflow de GitHub Actions en la web"
echo "   (ver README, «Modo servidor») para no publicar duplicado."
echo "=================================================================="
