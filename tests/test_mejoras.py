# -*- coding: utf-8 -*-
"""
Pruebas locales de analitica.py y tendencias.py con un proveedor falso
de TikTok-Api (sin cookies reales y sin llamar a TikTok).

    python tests/test_mejoras.py

Cubre:
  - Una entrada del historial de hace 49 h se empareja con el video del
    mock (por inicio de descripcion = gancho) y recibe metricas_48h.
  - Una entrada de hace 10 h queda intacta (aun no cumple las 48 h).
  - Una entrada vieja que ya tiene metricas_48h no se toca, y una con
    estado de error tampoco.
  - El emparejado por proximidad de fecha funciona cuando la
    descripcion no coincide.
  - tendencias.py escribe tendencias.json solo con los videos
    adyacentes a finanzas y con hashtags_top coherentes.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analitica
import tendencias

AHORA = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def _video(desc, creado, vistas, likes, comentarios, compartidos,
           hashtags=None):
    return {
        "id": f"v-{vistas}",
        "descripcion": desc,
        "creado_en": creado,
        "vistas": vistas,
        "likes": likes,
        "comentarios": comentarios,
        "compartidos": compartidos,
        "hashtags": hashtags or [],
    }


def prueba_analitica():
    hace_49h = AHORA - timedelta(hours=49)
    hace_10h = AHORA - timedelta(hours=10)
    hace_72h = AHORA - timedelta(hours=72)
    historial = [
        {
            "fecha": hace_49h.isoformat(),
            "tema": "Tema viejo emparejable por descripcion",
            "caption": "Your first paycheck is lying to you\n"
                       "segunda linea #moneytok",
            "estado": "publicado",
            "programado_para": None,
            "metricas_48h": None,
        },
        {
            "fecha": hace_10h.isoformat(),
            "tema": "Tema reciente, aun no toca",
            "caption": "Hook reciente que no debe tocarse",
            "estado": "publicado",
            "programado_para": None,
            "metricas_48h": None,
        },
        {
            "fecha": hace_72h.isoformat(),
            "tema": "Tema ya medido",
            "caption": "Hook ya medido",
            "estado": "publicado",
            "programado_para": None,
            "metricas_48h": {"vistas": 1, "likes": 1, "comentarios": 0,
                             "compartidos": 0, "capturado_en": "antes"},
        },
        {
            "fecha": hace_72h.isoformat(),
            "tema": "Tema con error de subida",
            "caption": "Hook con error",
            "estado": "error_subida",
            "programado_para": None,
            "metricas_48h": None,
        },
        {
            # Programado: la fecha de subida es hace 60 h pero el slot
            # (cuando salio de verdad) es hace 49 h; se empareja por
            # fecha porque la descripcion no coincide con el caption.
            "fecha": (AHORA - timedelta(hours=60)).isoformat(),
            "tema": "Tema programado emparejable por fecha",
            "caption": "Un caption que TikTok mostro distinto",
            "estado": "publicado",
            "programado_para": hace_49h.isoformat(),
            "metricas_48h": None,
        },
    ]
    videos_mock = [
        _video("Your first paycheck is lying to you\nsegunda linea "
               "#moneytok", hace_49h + timedelta(minutes=3),
               12345, 678, 90, 12, ["moneytok"]),
        _video("Descripcion recortada por TikTok sin relacion",
               hace_49h + timedelta(minutes=20), 999, 88, 7, 3),
        _video("Video reciente de la cuenta", hace_10h, 50, 5, 1, 0),
    ]

    def proveedor_falso(cookies, usuario, limite):
        assert usuario == "firstpaycheckmath"
        assert cookies.get("sessionid") == "falso"
        return list(videos_mock)

    with tempfile.TemporaryDirectory() as tmp:
        ruta_hist = os.path.join(tmp, "historial.json")
        with open(ruta_hist, "w", encoding="utf-8") as f:
            json.dump(historial, f)
        ruta_cookies = os.path.join(tmp, "cookies.txt")
        with open(ruta_cookies, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write(".tiktok.com\tTRUE\t/\tTRUE\t1893456000\t"
                    "sessionid\tfalso\n")
            f.write(".tiktok.com\tTRUE\t/\tTRUE\t1893456000\t"
                    "msToken\ttoken-falso\n")
            f.write(".example.com\tTRUE\t/\tTRUE\t1893456000\t"
                    "otra\tno-debe-pasar\n")

        n = analitica.ejecutar({"usuario": "@firstpaycheckmath"},
                               ruta_cookies=ruta_cookies,
                               ruta_historial=ruta_hist,
                               proveedor=proveedor_falso, ahora=AHORA)
        assert n == 2, f"se esperaban 2 actualizaciones, hubo {n}"
        with open(ruta_hist, encoding="utf-8") as f:
            resultado = json.load(f)

    por_tema = {e["tema"]: e for e in resultado}
    m = por_tema["Tema viejo emparejable por descripcion"]["metricas_48h"]
    assert m["vistas"] == 12345 and m["likes"] == 678
    assert m["comentarios"] == 90 and m["compartidos"] == 12
    assert m["capturado_en"] == AHORA.isoformat()
    assert por_tema["Tema reciente, aun no toca"]["metricas_48h"] is None
    assert por_tema["Tema ya medido"]["metricas_48h"]["vistas"] == 1
    assert por_tema["Tema con error de subida"]["metricas_48h"] is None
    m2 = por_tema["Tema programado emparejable por fecha"]["metricas_48h"]
    assert m2["vistas"] == 999, f"emparejado por fecha mal: {m2}"
    print("OK analitica: 49 h rellena, 10 h intacta, fecha y descripcion")


def prueba_tendencias():
    videos_mock = [
        _video("How to budget your first paycheck #moneytok #budget",
               AHORA, 500000, 40000, 0, 0, ["moneytok", "budget"]),
        _video("Dance challenge del momento #fyp #dance",
               AHORA, 9000000, 800000, 0, 0, ["fyp", "dance"]),
        _video("My salary breakdown as a nurse #salary #nurse",
               AHORA, 250000, 20000, 0, 0, ["salary", "nurse"]),
        _video("Receta de pasta en 10 minutos #food",
               AHORA, 100000, 9000, 0, 0, ["food"]),
    ]

    def proveedor_falso(cookies, limite):
        assert cookies is None  # primer intento: sin cuenta
        return list(videos_mock)

    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "tendencias.json")
        salida = tendencias.ejecutar(ruta_salida=ruta,
                                     proveedor=proveedor_falso,
                                     ahora=AHORA)
        assert salida is not None
        with open(ruta, encoding="utf-8") as f:
            en_disco = json.load(f)
    assert en_disco == salida
    assert salida["generado_en"] == AHORA.isoformat()
    assert len(salida["videos"]) == 2, salida["videos"]
    descripciones = [v["descripcion"] for v in salida["videos"]]
    assert any("budget your first paycheck" in d for d in descripciones)
    assert any("salary breakdown" in d for d in descripciones)
    assert salida["videos"][0]["vistas"] == 500000
    assert salida["videos"][0]["hashtags"] == ["moneytok", "budget"]
    top = {h["hashtag"]: h["menciones"] for h in salida["hashtags_top"]}
    assert top.get("moneytok") == 1 and top.get("salary") == 1
    assert "dance" not in top and "food" not in top
    print("OK tendencias: filtro de finanzas y tendencias.json correctos")


if __name__ == "__main__":
    prueba_analitica()
    prueba_tendencias()
    print("TODAS LAS PRUEBAS PASAN")
