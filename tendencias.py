# -*- coding: utf-8 -*-
"""
Tendencias de TikTok adyacentes a finanzas (SOLO LECTURA, TikTok-Api).

Trae los videos en tendencia, se queda con los adyacentes al nicho del
canal (finanzas personales, presupuesto, nomina, trabajo en EE. UU.) y
escribe `tendencias.json`:

    {
      "generado_en": "<ISO UTC>",
      "videos": [{"descripcion": ..., "vistas": ..., "likes": ...,
                  "hashtags": [...]}],
      "hashtags_top": [{"hashtag": ..., "menciones": ...}, ...]
    }

Es un INSUMO para elegir los proximos temas de estrategia.json a mano;
no modifica estrategia.json ni toca la publicacion en absoluto.

Uso:
    python tendencias.py

AVISO (tambien en el README): TikTok suele bloquear estas lecturas
desde IPs de datacenter — los runners de GitHub Actions lo son —, asi
que el sitio recomendado para correrlo es el servidor de David. En
Actions puede fallar; como es un CLI independiente que main.py no
invoca, ese fallo no afecta a la publicacion. Primero se intenta sin
cuenta; si TikTok exige sesion, se reintenta con las mismas cookies de
la subida (resolucion identica a upload_tiktok.py).
"""
import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))

# Subcadenas (en minusculas) que marcan un video como adyacente al
# nicho: finanzas personales, presupuesto, nomina y trabajo en EE. UU.
PALABRAS_CLAVE = [
    "money", "budget", "paycheck", "salary", "finance", "financial",
    "saving", "savings", "ira", "401k", "credit", "debt", "rent",
    "bill", "tax", "invest", "bank", "cash", "wealth", "side hustle",
    "hustle", "job", "career", "income", "frugal", "retire", "stock",
    "emergency fund", "minimum wage", "overtime", "wage", "employer",
    "first job", "direct deposit", "checking account", "savings account",
]


def es_adyacente_finanzas(video):
    texto = (video.get("descripcion") or "").lower()
    texto += " " + " ".join("#" + h.lower()
                            for h in video.get("hashtags") or [])
    return any(k in texto for k in PALABRAS_CLAVE)


async def _trending_async(limite, cookies=None):
    from TikTokApi import TikTokApi
    try:
        import logging
        logging.getLogger("TikTokApi").setLevel(logging.WARNING)
    except Exception:
        pass
    from analitica import _normalizar_video
    videos = []
    async with TikTokApi() as api:
        kwargs = {"num_sessions": 1, "headless": True,
                  "browser": "chromium", "sleep_after": 3}
        if cookies:
            kwargs["cookies"] = [cookies]
            if cookies.get("msToken"):
                kwargs["ms_tokens"] = [cookies["msToken"]]
        await api.create_sessions(**kwargs)
        async for v in api.trending.videos(count=limite):
            nv = _normalizar_video(v.as_dict)
            if nv is not None:
                videos.append(nv)
    return videos


def obtener_trending(limite=50, cookies=None):
    return asyncio.run(_trending_async(limite, cookies))


def construir_salida(videos, ahora=None):
    """Filtra los videos adyacentes a finanzas y arma el dict de
    tendencias.json. Funcion pura: la ejercitan las pruebas con mock."""
    ahora = ahora or datetime.now(timezone.utc)
    elegidos = [v for v in videos if es_adyacente_finanzas(v)]
    contador = Counter()
    for v in elegidos:
        for h in v.get("hashtags") or []:
            contador[h] += 1
    return {
        "generado_en": ahora.isoformat(),
        "videos": [
            {
                "descripcion": v.get("descripcion") or "",
                "vistas": v.get("vistas", 0),
                "likes": v.get("likes", 0),
                "hashtags": v.get("hashtags") or [],
            }
            for v in elegidos
        ],
        "hashtags_top": [
            {"hashtag": h, "menciones": n}
            for h, n in contador.most_common(15)
        ],
    }


def ejecutar(ruta_salida=None, proveedor=None, limite=50, ahora=None):
    """Trae tendencias y escribe el JSON. Devuelve el dict escrito, o
    None si no se pudo (el fallo se registra; nunca toca la
    publicacion porque main.py no llama a este modulo).

    `proveedor` inyectable para pruebas: proveedor(cookies_o_None,
    limite) -> [videos normalizados]."""
    ruta_salida = ruta_salida or os.path.join(BASE, "tendencias.json")
    videos = None
    if proveedor is not None:
        try:
            videos = proveedor(None, limite)
        except Exception as e:
            print(f"Tendencias: el proveedor fallo: {e}")
            return None
    else:
        try:
            videos = obtener_trending(limite, cookies=None)
        except Exception as e:
            print(f"Tendencias: sin cuenta fallo ({e}); "
                  "reintentando con las cookies de la sesion...")
        if not videos:
            try:
                import upload_tiktok
                from analitica import _cargar_config, \
                    parsear_cookies_netscape
                cfg = _cargar_config()
                ruta, es_temporal = upload_tiktok._resolver_cookies(cfg)
                try:
                    cookies = parsear_cookies_netscape(ruta)
                finally:
                    if es_temporal:
                        try:
                            os.remove(ruta)
                        except Exception:
                            pass
                videos = obtener_trending(limite, cookies=cookies)
            except Exception as e:
                print(f"Tendencias: tambien fallo con cookies: {e}")
                return None
    if not videos:
        print("Tendencias: TikTok-Api no devolvio videos en tendencia")
        return None
    salida = construir_salida(videos, ahora)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(json.dumps(salida, indent=2, ensure_ascii=False))
    print(f"Tendencias: {len(salida['videos'])} videos adyacentes a "
          f"finanzas de {len(videos)} en tendencia -> {ruta_salida}")
    return salida


if __name__ == "__main__":
    if ejecutar() is None:
        sys.exit(1)
