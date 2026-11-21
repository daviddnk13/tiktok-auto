# -*- coding: utf-8 -*-
"""
Analitica de SOLO LECTURA para First Paycheck Math (TikTok-Api).

Rellena el campo `metricas_48h` de historial.json con el snapshot de
metricas (vistas, likes, comentarios, compartidos) de cada video ya
publicado, igual que el `views_48h` de los canales de YouTube:

  - Una entrada del historial es candidata cuando su estado es
    "publicado", aun no tiene `metricas_48h` y han pasado >= 48 h desde
    que el video salio (su `programado_para` si el post quedo programado
    con la programacion nativa; si no, su `fecha` de subida).
  - Los videos propios se traen con TikTok-Api (davidteather/TikTok-Api,
    MIT) usando las cookies de la sesion (el mismo cookies.txt Netscape
    de la subida; se parsea a dict y se pasa a create_sessions).
  - Emparejado historial <-> video de TikTok, en este orden:
      1. Por descripcion: el caption guardado empieza por el gancho, y
         la descripcion del video en TikTok es ese mismo caption; si el
         inicio normalizado coincide, es el video.
      2. Por fecha: el video cuya createTime este mas cerca del instante
         de publicacion, dentro de una ventana de +-36 h.
    Cada video de TikTok se asigna como mucho a una entrada.

REGLA DE ORO: esto es best-effort y NUNCA puede romper la publicacion.
ejecutar() captura cualquier excepcion, la registra por stdout y
devuelve 0; main.py ademas lo llama envuelto en su propio try/except al
final de la corrida. Si TikTok bloquea la IP (pasa con IPs de
datacenter como las de GitHub Actions) o las cookies vencieron, la
corrida sigue como si nada y el snapshot se intentara en la siguiente.

Uso manual:
    python analitica.py [ruta_al_cookies.txt]
Sin argumento, las cookies se resuelven como en upload_tiktok.py
(TIKTOK_COOKIES / TIKTOK_COOKIES_FILE / config subida.cookies_archivo).
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
ESPERA_MINIMA = timedelta(hours=48)
TOLERANCIA_FECHA = timedelta(hours=36)


# ---------------------------------------------------------------------------
# Cookies (Netscape -> dict) y sesion de TikTok-Api
# ---------------------------------------------------------------------------

def parsear_cookies_netscape(ruta):
    """Parsea un cookies.txt en formato Netscape a {nombre: valor}.

    Solo se quedan las cookies de dominios de TikTok (el archivo puede
    traer cookies de www.tiktok.com y de .tiktok.com; si un nombre se
    repite, gana la del dominio mas especifico procesada despues... en la
    practica sessionid/msToken vienen una sola vez)."""
    cookies = {}
    with open(ruta, encoding="utf-8", errors="ignore") as f:
        for linea in f:
            linea = linea.rstrip("\n")
            if not linea or linea.startswith("#"):
                continue
            partes = linea.split("\t")
            if len(partes) < 7:
                continue
            dominio, nombre, valor = partes[0], partes[5], partes[6]
            if "tiktok" not in dominio:
                continue
            cookies[nombre] = valor
    return cookies


def _normalizar_video(d):
    """Convierte el dict crudo de un video de TikTok-Api a un dict
    plano: {id, descripcion, creado_en (datetime UTC), vistas, likes,
    comentarios, compartidos, hashtags}. None si no es usable."""
    if not isinstance(d, dict):
        return None
    stats = d.get("statsV2") or d.get("stats") or {}

    def _int(x):
        try:
            return int(x)
        except Exception:
            return 0

    creado = None
    try:
        creado = datetime.fromtimestamp(int(d.get("createTime")),
                                        tz=timezone.utc)
    except Exception:
        pass
    hashtags = []
    for te in d.get("textExtra") or []:
        nombre = (te or {}).get("hashtagName")
        if nombre and nombre not in hashtags:
            hashtags.append(nombre)
    for m in re.findall(r"#([A-Za-z0-9_]+)", d.get("desc") or ""):
        if m not in hashtags:
            hashtags.append(m)
    return {
        "id": str(d.get("id") or ""),
        "descripcion": d.get("desc") or "",
        "creado_en": creado,
        "vistas": _int(stats.get("playCount")),
        "likes": _int(stats.get("diggCount")),
        "comentarios": _int(stats.get("commentCount")),
        "compartidos": _int(stats.get("shareCount")),
        "hashtags": hashtags,
    }


async def _videos_propios_async(cookies, usuario, limite):
    from TikTokApi import TikTokApi
    try:
        import logging
        logging.getLogger("TikTokApi").setLevel(logging.WARNING)
    except Exception:
        pass
    videos = []
    async with TikTokApi() as api:
        kwargs = {
            "num_sessions": 1,
            "headless": True,
            "browser": "chromium",
            "sleep_after": 3,
            # TikTok-Api 7.x acepta una lista de dicts {nombre: valor},
            # uno por sesion; con eso la sesion queda iniciada como la
            # cuenta duena de las cookies.
            "cookies": [cookies],
        }
        if cookies.get("msToken"):
            kwargs["ms_tokens"] = [cookies["msToken"]]
        await api.create_sessions(**kwargs)
        user = api.user(username=usuario)
        async for v in user.videos(count=limite):
            nv = _normalizar_video(v.as_dict)
            if nv is not None:
                videos.append(nv)
    return videos


def obtener_videos_propios(cookies, usuario, limite=30):
    """Trae los videos propios con TikTok-Api (sincrono por fuera)."""
    return asyncio.run(_videos_propios_async(cookies, usuario, limite))


# ---------------------------------------------------------------------------
# Emparejado historial <-> videos y relleno de metricas_48h
# ---------------------------------------------------------------------------

def _parse_fecha(valor):
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _instante_publicacion(entrada):
    """Cuando salio el video de verdad: el slot programado si lo hay
    (la subida pudo ser horas antes), si no la fecha de la subida."""
    return _parse_fecha(entrada.get("programado_para")) or \
        _parse_fecha(entrada.get("fecha"))


def _es_candidata(entrada, ahora):
    if entrada.get("estado") != "publicado":
        return False
    if entrada.get("metricas_48h"):
        return False
    instante = _instante_publicacion(entrada)
    if instante is None:
        return False
    return ahora - instante >= ESPERA_MINIMA


def _norm_texto(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _emparejar(entrada, pool):
    """Busca en `pool` (videos normalizados) el que corresponde a la
    entrada del historial. Devuelve el video o None."""
    # 1) Por descripcion: el caption guardado empieza por el gancho y es
    #    (salvo recortes de TikTok) la descripcion del video.
    caption = entrada.get("caption") or ""
    primera_linea = next((ln for ln in caption.splitlines() if ln.strip()),
                         "")
    gancho = _norm_texto(primera_linea)
    if len(gancho) >= 12:
        for v in pool:
            desc = _norm_texto(v.get("descripcion"))
            if desc.startswith(gancho[:50]) or gancho.startswith(desc[:50]):
                return v
    # 2) Por proximidad de fecha dentro de la ventana de tolerancia.
    instante = _instante_publicacion(entrada)
    if instante is not None:
        mejor, mejor_delta = None, None
        for v in pool:
            creado = v.get("creado_en")
            if creado is None:
                continue
            delta = abs(creado - instante)
            if delta <= TOLERANCIA_FECHA and \
                    (mejor_delta is None or delta < mejor_delta):
                mejor, mejor_delta = v, delta
        return mejor
    return None


def actualizar_metricas(historial, videos, ahora=None):
    """Rellena metricas_48h en las entradas candidatas de `historial`
    (mutacion in situ) usando `videos` normalizados. Devuelve cuantas
    entradas se actualizaron. Funcion pura salvo la mutacion: es la que
    ejercitan las pruebas con un proveedor falso."""
    ahora = ahora or datetime.now(timezone.utc)
    candidatas = [e for e in historial if _es_candidata(e, ahora)]
    candidatas.sort(key=lambda e: _instante_publicacion(e)
                    or datetime.max.replace(tzinfo=timezone.utc))
    pool = list(videos)
    n = 0
    for entrada in candidatas:
        v = _emparejar(entrada, pool)
        if v is None:
            print(f"Analitica: sin emparejar '{entrada.get('tema')}' "
                  "(aun no aparece en la cuenta o fuera de ventana)")
            continue
        pool.remove(v)
        entrada["metricas_48h"] = {
            "vistas": v["vistas"],
            "likes": v["likes"],
            "comentarios": v["comentarios"],
            "compartidos": v["compartidos"],
            "capturado_en": ahora.isoformat(),
        }
        n += 1
        print(f"Analitica: metricas_48h de '{entrada.get('tema')}': "
              f"{v['vistas']} vistas, {v['likes']} likes, "
              f"{v['comentarios']} comentarios, "
              f"{v['compartidos']} compartidos")
    return n


# ---------------------------------------------------------------------------
# Orquestacion (best-effort total: nunca lanza)
# ---------------------------------------------------------------------------

def _cargar_config():
    try:
        with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ejecutar(cfg=None, ruta_cookies=None, ruta_historial=None,
             proveedor=None, ahora=None, limite=30):
    """Punto de entrada reutilizable (lo llama main.py al final de la
    corrida y el CLI). Devuelve el numero de entradas actualizadas.

    `proveedor` permite inyectar una fuente de videos alternativa con la
    firma proveedor(cookies_dict, usuario, limite) -> [videos
    normalizados]; las pruebas lo usan con un mock de TikTok-Api.

    NUNCA lanza: cualquier fallo se registra y se devuelve 0."""
    ahora = ahora or datetime.now(timezone.utc)
    cfg = cfg if cfg is not None else _cargar_config()
    ruta_historial = ruta_historial or os.path.join(BASE, "historial.json")
    ruta_temp = None
    try:
        try:
            with open(ruta_historial, encoding="utf-8") as f:
                historial = json.load(f)
        except Exception:
            historial = []
        if not any(_es_candidata(e, ahora) for e in historial):
            print("Analitica: ninguna entrada cumple las 48 h todavia")
            return 0

        if ruta_cookies:
            ruta, es_temporal = ruta_cookies, False
        else:
            import upload_tiktok
            ruta, es_temporal = upload_tiktok._resolver_cookies(cfg)
            if es_temporal:
                ruta_temp = ruta
        cookies = parsear_cookies_netscape(ruta)
        if proveedor is None and not (cookies.get("sessionid")
                                      or cookies.get("msToken")):
            print("Analitica: las cookies no traen sessionid ni msToken; "
                  "se omite el snapshot de esta corrida")
            return 0

        usuario = str(cfg.get("usuario", "@firstpaycheckmath"))
        usuario = usuario.lstrip("@")
        if proveedor is not None:
            videos = proveedor(cookies, usuario, limite)
        else:
            videos = obtener_videos_propios(cookies, usuario, limite)
        if not videos:
            print("Analitica: TikTok-Api no devolvio videos propios")
            return 0

        n = actualizar_metricas(historial, videos, ahora)
        if n:
            with open(ruta_historial, "w", encoding="utf-8") as f:
                f.write(json.dumps(historial, indent=2,
                                   ensure_ascii=False))
        return n
    except Exception as e:
        print(f"Analitica: fallo sin consecuencias (best-effort): {e}")
        return 0
    finally:
        if ruta_temp:
            try:
                os.remove(ruta_temp)
            except Exception:
                pass


if __name__ == "__main__":
    ruta_arg = sys.argv[1] if len(sys.argv) > 1 else None
    n = ejecutar(ruta_cookies=ruta_arg)
    print(f"Analitica: {n} entrada(s) del historial actualizadas")
