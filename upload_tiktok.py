# -*- coding: utf-8 -*-
"""
Subida automatica a TikTok para First Paycheck Math.

Usa el paquete `tiktok-uploader` (wkaisertexas/tiktok-uploader), que
automatiza la web de TikTok con Playwright usando las cookies de la
sesion iniciada (archivo cookies.txt en formato Netscape, el que exporta
la extension "Get cookies.txt LOCALLY"). Es una ruta NO oficial: la API
oficial de TikTok mantiene privados los videos de cuentas sin auditar.

Contrato con main.py:
    from upload_tiktok import subir, TikTokUploadError, CookiesError
    subir("video.mp4", "caption con #hashtags", cfg, portada="cover-2.jpg")

- Exito: devuelve {"ok": True, "video": ..., "programado_para": ...}
  ("programado_para" es el ISO del slot si el post quedo programado con
  la programacion nativa de TikTok, o None si se publico de inmediato).
- Portada: si se pasa `portada` (JPG) y existe, va como cover= de
  tiktok-uploader 1.2.0 (verificado contra el README de PyPI de la 1.2.0
  y el fuente de upload.py: upload_video(..., cover=str, schedule=datetime)).
- Programacion: si config subida.programar es true, decidir_programacion()
  deja el post programado para el slot de hoy (subida.hora_slot_utc,
  por defecto 23.5 = 23:30 UTC) cuando aun falta mas de media hora;
  si no, publica de inmediato.
- Cookies ausentes/vencidas o sesion rechazada: lanza CookiesError con
  las instrucciones para exportar cookies frescas (main.py lo convierte
  en alerta de Telegram).
- Cualquier otro fallo (CAPTCHA, rechazo, red): TikTokUploadError.

De donde salen las cookies (en este orden):
  1. Variable de entorno TIKTOK_COOKIES con el CONTENIDO del cookies.txt
     (asi se guarda como secret de GitHub; se escribe a un archivo
     temporal con permisos 0600 y se borra al terminar).
  2. Variable de entorno TIKTOK_COOKIES_FILE con la ruta a un cookies.txt.
  3. El archivo indicado en config.json -> subida.cookies_archivo
     (por defecto "cookies.txt" junto al repo; esta en .gitignore).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

INSTRUCCIONES_COOKIES = (
    "Exporta cookies frescas: abre TikTok en el navegador con la sesion "
    "de @firstpaycheckmath, usa la extension 'Get cookies.txt LOCALLY' "
    "sobre tiktok.com y actualiza el secret TIKTOK_COOKIES del repo "
    "(o el archivo cookies.txt si corres en el servidor)."
)


class TikTokUploadError(Exception):
    """Fallo generico de subida (CAPTCHA, rechazo de TikTok, red...)."""


class CookiesError(TikTokUploadError):
    """Cookies ausentes, vencidas o sesion rechazada por TikTok."""


def _escribir_cookies_temporal(contenido, workdir):
    ruta = os.path.join(workdir, ".cookies_tiktok.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)
    try:
        os.chmod(ruta, 0o600)
    except Exception:
        pass
    return ruta


def _resolver_cookies(cfg):
    """Devuelve (ruta_cookies, es_temporal)."""
    contenido = os.environ.get("TIKTOK_COOKIES", "").strip()
    if contenido:
        workdir = os.environ.get("TT_WORKDIR", "work")
        os.makedirs(workdir, exist_ok=True)
        return _escribir_cookies_temporal(contenido, workdir), True
    ruta_env = os.environ.get("TIKTOK_COOKIES_FILE", "").strip()
    if ruta_env:
        return ruta_env, False
    ruta_cfg = (cfg or {}).get("subida", {}).get("cookies_archivo", "cookies.txt")
    return ruta_cfg, False


def _comprobar_cookies(ruta):
    if not ruta or not os.path.exists(ruta):
        raise CookiesError(
            f"No se encontro el archivo de cookies ({ruta}). "
            + INSTRUCCIONES_COOKIES)
    try:
        with open(ruta, encoding="utf-8", errors="ignore") as f:
            contenido = f.read()
    except Exception as e:
        raise CookiesError(f"No se pudo leer el archivo de cookies: {e}")
    if "sessionid" not in contenido:
        raise CookiesError(
            "El archivo de cookies no contiene 'sessionid': no es una "
            "sesion valida de TikTok o ya vencio. " + INSTRUCCIONES_COOKIES)


def decidir_programacion(ahora_utc=None, hora_slot_utc=23.5,
                         anticipacion_min=30):
    """Decide si el post se programa para el slot de hoy o sale ya.

    Devuelve un datetime aware en UTC con la hora del slot de hoy si
    ahora es anterior al slot menos `anticipacion_min` minutos; en
    cualquier otro caso devuelve None (publicar de inmediato).

    Supuesto de zona horaria (verificado en tiktok-uploader 1.2.0): el
    `schedule` se interpreta en UTC — un datetime naive lo convierte
    desde la zona local del proceso y uno aware con offset 0 lo toma
    tal cual como UTC; por eso aqui se devuelve siempre aware en UTC,
    que es correcto en cualquier maquina (los runners de GitHub Actions
    trabajan en UTC). La libreria exige >= 20 min de antelacion y <= 10
    dias, y redondea a multiplos de 5 min: con la anticipacion de 30 min
    el hueco hasta el slot siempre es > 30 min, dentro de lo valido."""
    ahora = ahora_utc or datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    ahora = ahora.astimezone(timezone.utc)
    horas = int(hora_slot_utc)
    minutos = int(round((hora_slot_utc - horas) * 60))
    slot = ahora.replace(hour=horas, minute=minutos, second=0, microsecond=0)
    if ahora < slot - timedelta(minutes=anticipacion_min):
        return slot
    return None


def subir(video_path, caption, cfg=None, portada=None):
    """Sube el video a TikTok. Con config subida.programar en true, si
    aun falta mas de media hora para el slot (subida.hora_slot_utc), el
    post queda programado con la programacion nativa de TikTok para ese
    slot; si no, se publica de inmediato. Si se pasa `portada` (ruta a
    un JPG) y existe, se sube como portada personalizada (cover=).
    Devuelve {"ok": True, "video": video_path, "programado_para": iso|None}
    o lanza TikTokUploadError / CookiesError con un mensaje accionable."""
    if not os.path.exists(video_path):
        raise TikTokUploadError(f"El video a subir no existe: {video_path}")
    ruta_cookies, es_temporal = _resolver_cookies(cfg)
    try:
        _comprobar_cookies(ruta_cookies)
        try:
            from tiktok_uploader.upload import upload_video
        except ImportError as e:
            raise TikTokUploadError(
                f"tiktok-uploader no esta instalado ({e}). Revisa "
                "requirements.txt y que el workflow instale Playwright "
                "(python -m playwright install --with-deps chromium).")
        sub_cfg = (cfg or {}).get("subida", {})
        kwargs = {}
        if portada and os.path.exists(portada):
            kwargs["cover"] = os.path.abspath(portada)
        programado_para = None
        if sub_cfg.get("programar", True):
            try:
                hora_slot = float(sub_cfg.get("hora_slot_utc", 23.5))
            except Exception:
                hora_slot = 23.5
            sched = decidir_programacion(hora_slot_utc=hora_slot)
            if sched is not None:
                kwargs["schedule"] = sched
                programado_para = sched.isoformat()
        try:
            fallidos = upload_video(
                filename=os.path.abspath(video_path),
                description=caption,
                cookies=ruta_cookies,
                browser="chromium",
                headless=True,
                **kwargs,
            )
        except Exception as e:
            msg = str(e).lower()
            if any(k in msg for k in ("sessionid", "auth", "login",
                                      "redirected", "cookies")):
                raise CookiesError(
                    "TikTok rechazo la sesion (cookies vencidas o sesion "
                    f"cerrada): {e}. " + INSTRUCCIONES_COOKIES)
            if "captcha" in msg or "verify" in msg:
                raise TikTokUploadError(
                    f"TikTok pidio una verificacion (CAPTCHA) durante la "
                    f"subida: {e}. Suele pasar con IPs de datacenter; "
                    "valora correr la subida desde el servidor de David.")
            raise TikTokUploadError(f"Fallo la subida a TikTok: {e}")
        # La libreria devuelve la lista de videos que NO se subieron:
        # lista vacia = exito.
        if fallidos:
            raise TikTokUploadError(
                f"tiktok-uploader reporto el video como no subido: "
                f"{fallidos}. Si la sesion sigue abierta, suele ser un "
                "CAPTCHA o un rechazo puntual; si persiste, "
                + INSTRUCCIONES_COOKIES)
        return {"ok": True, "video": video_path,
                "programado_para": programado_para}
    finally:
        if es_temporal:
            try:
                os.remove(ruta_cookies)
            except Exception:
                pass


if __name__ == "__main__":
    # Uso manual (p. ej. en el servidor de David):
    #   python upload_tiktok.py video.mp4 "Caption con #hashtags"
    if len(sys.argv) < 3:
        print("Uso: python upload_tiktok.py <video.mp4> \"<caption>\"")
        sys.exit(2)
    try:
        subir(sys.argv[1], sys.argv[2])
        print("Subida OK")
    except TikTokUploadError as e:
        print("ERROR:", e)
        sys.exit(1)
