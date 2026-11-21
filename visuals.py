# -*- coding: utf-8 -*-
"""
Visuales generados para First Paycheck Math (TikTok).

TikTok penaliza como "no original" el formato de video de stock + texto,
asi que TODOS los visuales de este canal se generan por codigo para cada
tema: graficos de crecimiento, tablas tipo hoja de calculo y barras
comparativas animadas, sobre fondo carbon oscuro con acento verde lima
(#66FF99), la identidad del canal.

Uso desde main.py:
    import visuals
    visuals.render_visual(spec, duracion_seg, "fondo.mp4", workdir)
    visuals.resumen_datos(spec)   # cifras clave para el prompt del guion

El spec viene de estrategia.json (clave "visual" de cada tema) y puede ser:
  - {"tipo": "growth_curve", "mensual": 100, "tasa_anual": 0.08,
     "anios": 40, "edad_inicio": 25, "titulo_visual": ..., "subtitulo": ...}
  - {"tipo": "budget_table", "columnas": [...], "filas":
     [{"celdas": [...], "tipo": "normal|total|resta"}, ...], ...}
  - {"tipo": "comparison_bars", "barras": [...]}  o con calculo en codigo:
     {"tipo": "comparison_bars", "calculo": {"tipo": "deuda", ...}}
     {"tipo": "comparison_bars", "calculo": {"tipo": "match401k", ...}}
     {"tipo": "comparison_bars", "calculo": {"tipo": "interes", ...}}
"""
import os
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

W, H = 1080, 1920
FPS_FRAMES = 10  # frames unicos por segundo; main.py convierte a 30 fps

BG = "#0D100E"
PANEL = "#151A16"
LIME = "#66FF99"
LIME_DIM = "#3E9C63"
WHITE = "#F2F5F2"
GRAY = "#9AA5A0"
GRAY_DIM = "#5C665F"
RED = "#FF7A7A"
BLUEGRAY = "#8FA8BF"


def fmt_dinero(v):
    return f"${v:,.0f}"


def fmt_valor(v, formato):
    if formato == "$":
        return fmt_dinero(v)
    if formato == "%":
        return f"{v:,.0f}%"
    return f"{v:,.0f}"


# ---------------------------------------------------------------------------
# Calculos financieros (las cifras del video salen de aqui, nunca del modelo)
# ---------------------------------------------------------------------------

def serie_crecimiento(mensual, tasa_anual, anios):
    """Devuelve (meses, contribuciones, valores) mes a mes."""
    r = tasa_anual / 12.0
    n = int(anios * 12)
    meses = np.arange(n + 1)
    contrib = mensual * meses.astype(float)
    if r > 0:
        valores = mensual * (((1 + r) ** meses - 1) / r)
        valores[0] = 0.0
    else:
        valores = contrib.copy()
    return meses, contrib, valores


def fv_mensual(mensual, tasa_anual, anios):
    return float(serie_crecimiento(mensual, tasa_anual, anios)[2][-1])


def payoff_deuda(balance, apr, pago_fijo):
    """Simula pagar una tarjeta de dos formas y devuelve las cifras reales.
    Pago minimo tipico: interes del mes + 1% del balance, con piso de $25."""
    def simula(modo):
        bal, total_int, meses = float(balance), 0.0, 0
        while bal > 0.005 and meses < 1200:
            interes = bal * apr / 12.0
            if modo == "minimo":
                pago = max(interes + bal * 0.01, 25.0)
            else:
                pago = float(pago_fijo)
            pago = min(pago, bal + interes)
            total_int += interes
            bal = bal + interes - pago
            meses += 1
        return meses, total_int

    m_min, i_min = simula("minimo")
    m_fix, i_fix = simula("fijo")
    return {
        "minimo": {"meses": m_min, "interes": i_min, "total": balance + i_min},
        "fijo": {"meses": m_fix, "interes": i_fix, "total": balance + i_fix},
    }


def calcular_barras(spec):
    """Normaliza un spec de comparison_bars a una lista de barras:
    {etiqueta, valor, formato, color, detalle}. Los calculos (deuda,
    match 401k, interes) se hacen aqui, en codigo, con cifras reales."""
    calc = spec.get("calculo") or {}
    tipo = calc.get("tipo")
    if tipo == "deuda":
        r = payoff_deuda(calc["balance"], calc["apr"], calc["pago_fijo"])
        return [
            {"etiqueta": "Paying only the minimum",
             "valor": r["minimo"]["interes"], "formato": "$", "color": RED,
             "detalle": f"in interest · {r['minimo']['meses']} months of payments"},
            {"etiqueta": f"Paying ${calc['pago_fijo']:,.0f} a month",
             "valor": r["fijo"]["interes"], "formato": "$", "color": LIME,
             "detalle": f"in interest · done in {r['fijo']['meses']} months"},
        ]
    if tipo == "match401k":
        mensual = calc["salario"] * calc["pct"] / 12.0
        sin = fv_mensual(mensual, calc["retorno"], calc["anios"])
        con = fv_mensual(mensual * 2, calc["retorno"], calc["anios"])
        return [
            {"etiqueta": "Your 5% alone, no match",
             "valor": sin, "formato": "$", "color": BLUEGRAY,
             "detalle": f"after {calc['anios']} years"},
            {"etiqueta": "Your 5% + employer match",
             "valor": con, "formato": "$", "color": LIME,
             "detalle": f"after {calc['anios']} years — the match doubled it"},
        ]
    if tipo == "interes":
        out = []
        for i, t in enumerate(calc["tasas"]):
            ganado = calc["principal"] * ((1 + t["tasa"] / 12.0) ** (12 * calc["anios"]) - 1)
            out.append({"etiqueta": t["etiqueta"], "valor": float(ganado),
                        "formato": "$",
                        "color": LIME if i == len(calc["tasas"]) - 1 else BLUEGRAY,
                        "detalle": f"earned in {calc['anios']} year(s)"})
        return out
    barras = []
    for b in spec.get("barras", []):
        barras.append({
            "etiqueta": b["etiqueta"],
            "valor": float(b["valor"]),
            "formato": b.get("formato", "$"),
            "color": b.get("color", LIME),
            "detalle": b.get("detalle", ""),
        })
    return barras


def resumen_datos(spec):
    """Cifras clave del visual, en texto, para que el prompt del guion use
    EXACTAMENTE estos numeros (la regla de oro: el video entrega lo que
    promete, con las cifras calculadas en codigo)."""
    tipo = spec.get("tipo")
    if tipo == "growth_curve":
        meses, contrib, valores = serie_crecimiento(
            spec["mensual"], spec["tasa_anual"], spec["anios"])
        fv = float(valores[-1])
        total_in = float(contrib[-1])
        return (f"Growth chart: ${spec['mensual']:,.0f}/month for {spec['anios']} years "
                f"at {spec['tasa_anual']*100:.0f}% average return. Total put in: "
                f"${total_in:,.0f}. Final value: ${fv:,.0f}. Growth part: "
                f"${fv-total_in:,.0f}.")
    if tipo == "budget_table":
        filas = "; ".join(" | ".join(f["celdas"]) for f in spec.get("filas", []))
        return f"Table ({spec.get('titulo_visual','')}): {filas}"
    if tipo == "comparison_bars":
        partes = []
        for b in calcular_barras(spec):
            partes.append(f"{b['etiqueta']}: {fmt_valor(b['valor'], b['formato'])}"
                          + (f" ({b['detalle']})" if b.get("detalle") else ""))
        return "Comparison: " + "; ".join(partes) + "."
    return ""


# ---------------------------------------------------------------------------
# Dibujo
# ---------------------------------------------------------------------------

def _base_fig(spec):
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    titulo = spec.get("titulo_visual", "")
    y = 0.952
    for linea in textwrap.wrap(titulo, 24)[:2]:
        fig.text(0.5, y, linea, ha="center", va="center", color=WHITE,
                 fontsize=41, fontweight="bold")
        y -= 0.034
    sub = spec.get("subtitulo", "")
    if sub:
        for linea in textwrap.wrap(sub, 42)[:2]:
            fig.text(0.5, y - 0.004, linea, ha="center", va="center",
                     color=GRAY, fontsize=23)
            y -= 0.026
    # El @ del canal va abajo del todo, en la franja libre bajo la zona
    # de subtitulos (que ocupan desde ~440 px del borde inferior).
    fig.text(0.5, 0.022, "@firstpaycheckmath", ha="center", va="center",
             color=GRAY_DIM, fontsize=20)
    return fig


def _draw_growth(fig, spec, p):
    ax = fig.add_axes([0.115, 0.30, 0.80, 0.47])
    ax.set_facecolor(BG)
    meses, contrib, valores = serie_crecimiento(
        spec["mensual"], spec["tasa_anual"], spec["anios"])
    edad0 = spec.get("edad_inicio")
    x = (edad0 + meses / 12.0) if edad0 else (meses / 12.0)
    k = max(2, int(round(p * len(meses))))
    ax.fill_between(x[:k], 0, contrib[:k], color=GRAY_DIM, alpha=0.85,
                    label="You put in")
    ax.fill_between(x[:k], contrib[:k], valores[:k], color=LIME, alpha=0.85,
                    label="Growth")
    ax.plot(x[:k], valores[:k], color=LIME, lw=3.5)
    ax.set_xlim(float(x[0]), float(x[-1]))
    ax.set_ylim(0, float(valores[-1]) * 1.12)
    ax.grid(axis="y", color="white", alpha=0.10)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRAY_DIM)
    ax.tick_params(colors=GRAY, labelsize=19)
    ax.set_xlabel("Age" if edad0 else "Years", color=GRAY, fontsize=21)
    ax.yaxis.set_major_formatter(lambda v, _pos: f"${v/1000:,.0f}k")
    ax.legend(loc="upper left", frameon=False, fontsize=20,
              labelcolor=WHITE)
    actual = float(valores[k - 1])
    puesto = float(contrib[k - 1])
    ax.text(0.97, 0.60, fmt_dinero(actual), transform=ax.transAxes,
            ha="right", va="center", color=LIME, fontsize=47,
            fontweight="bold")
    ax.text(0.97, 0.485, f"from {fmt_dinero(puesto)} you put in",
            transform=ax.transAxes, ha="right", va="center",
            color=WHITE, fontsize=23)
    if p > 0.965:
        ax.text(0.5, 0.16,
                f"Growth did {fmt_dinero(actual - puesto)} of the work",
                transform=ax.transAxes, ha="center", va="center",
                color=LIME, fontsize=26, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.55", fc=PANEL, ec=LIME, lw=1.5))


def _draw_table(fig, spec, p):
    ax = fig.add_axes([0.045, 0.27, 0.91, 0.55])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    columnas = spec.get("columnas", [])
    filas = spec.get("filas", [])
    ncols = len(columnas) if columnas else (len(filas[0]["celdas"]) if filas else 2)
    if ncols <= 2:
        bordes = [0.0, 0.66, 1.0]
    else:
        bordes = [0.0, 0.50, 0.75, 1.0]
    total_filas = len(filas) + (1 if columnas else 0)
    rh = 1.0 / max(total_filas, 1)
    ytop = 1.0
    if columnas:
        ax.add_patch(Rectangle((0, ytop - rh), 1, rh, fc=PANEL, ec="none"))
        for j, col in enumerate(columnas):
            x0, x1 = bordes[j], bordes[j + 1]
            ha = "left" if j == 0 else ("right" if j == ncols - 1 else "center")
            xt = x0 + 0.02 if ha == "left" else (x1 - 0.02 if ha == "right"
                                                 else (x0 + x1) / 2)
            ax.text(xt, ytop - rh / 2, col, ha=ha, va="center", color=LIME,
                    fontsize=24, fontweight="bold")
        ytop -= rh
    for i, fila in enumerate(filas):
        tipo = fila.get("tipo", "normal")
        inicio = 0.06 + 0.86 * (i / max(len(filas), 1))
        alpha = min(1.0, max(0.0, (p - inicio) / 0.07))
        if alpha <= 0:
            ytop -= rh
            continue
        if tipo == "total":
            ax.add_patch(Rectangle((0, ytop - rh), 1, rh, fc=LIME,
                                   ec="none", alpha=alpha))
            color_txt, color_val = "#0D100E", "#0D100E"
        else:
            fc = "#141815" if i % 2 == 0 else "#10130F"
            ax.add_patch(Rectangle((0, ytop - rh), 1, rh, fc=fc,
                                   ec="none", alpha=alpha))
            color_txt = WHITE
            color_val = RED if tipo == "resta" else LIME
        for j, celda in enumerate(fila["celdas"]):
            x0, x1 = bordes[j], bordes[j + 1]
            ha = "left" if j == 0 else ("right" if j == ncols - 1 else "center")
            xt = x0 + 0.02 if ha == "left" else (x1 - 0.02 if ha == "right"
                                                 else (x0 + x1) / 2)
            es_valor = j == ncols - 1
            texto = celda
            # Las etiquetas largas de la primera columna se parten en dos
            # lineas para que nunca invadan la columna siguiente.
            if j == 0 and len(celda) > (30 if ncols >= 3 else 44):
                texto = "\n".join(textwrap.wrap(
                    celda, 28 if ncols >= 3 else 42)[:2])
            ax.text(xt, ytop - rh / 2, texto, ha=ha, va="center",
                    color=color_val if es_valor else color_txt,
                    fontsize=26 if not es_valor else 28,
                    fontweight="bold" if (es_valor or tipo == "total") else "normal",
                    alpha=alpha)
        ytop -= rh


def _draw_bars(fig, spec, p):
    ax = fig.add_axes([0.06, 0.28, 0.88, 0.52])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    barras = calcular_barras(spec)
    if not barras:
        return
    vmax = max(b["valor"] for b in barras) or 1.0
    slot = 1.0 / len(barras)
    for i, b in enumerate(barras):
        ytop = 1.0 - i * slot
        inicio = 0.05 + i * 0.13
        g = min(1.0, max(0.0, (p - inicio) / 0.5))
        g = 1 - (1 - g) ** 3
        valor_mostrado = b["valor"] * g
        ax.text(0.0, ytop - slot * 0.10, b["etiqueta"], ha="left", va="center",
                color=WHITE, fontsize=26, fontweight="bold")
        ybar = ytop - slot * 0.52
        hbar = slot * 0.30
        ax.add_patch(Rectangle((0, ybar), 1.0, hbar, fc=PANEL, ec="none"))
        ax.add_patch(Rectangle((0, ybar), max(0.004, (b["valor"] / vmax) * g),
                               hbar, fc=b["color"], ec="none"))
        ax.text(0.0, ybar - slot * 0.17, fmt_valor(valor_mostrado, b["formato"]),
                ha="left", va="center", color=b["color"], fontsize=37,
                fontweight="bold")
        if b.get("detalle") and g > 0.85:
            ax.text(0.44, ybar - slot * 0.17, b["detalle"], ha="left",
                    va="center", color=GRAY, fontsize=21)


_DIBUJOS = {
    "growth_curve": _draw_growth,
    "budget_table": _draw_table,
    "comparison_bars": _draw_bars,
}


def render_visual(spec, duracion, out_mp4, workdir):
    """Renderiza el visual animado completo (mp4 mudo, FPS_FRAMES fps) que
    dura exactamente `duracion` segundos y lo deja en out_mp4."""
    import subprocess
    tipo = spec.get("tipo")
    if tipo not in _DIBUJOS:
        raise ValueError(f"Tipo de visual no soportado: {tipo}")
    frames_dir = os.path.join(workdir, f"frames_{tipo}")
    os.makedirs(frames_dir, exist_ok=True)
    n = max(2, int(round(duracion * FPS_FRAMES)))
    fig = _base_fig(spec)
    for i in range(n):
        p = i / (n - 1) if n > 1 else 1.0
        # Redibujar solo la zona del grafico: quitar los axes anteriores
        for ax in list(fig.axes):
            ax.remove()
        _DIBUJOS[tipo](fig, spec, p)
        fig.savefig(os.path.join(frames_dir, f"f_{i:04d}.png"),
                    facecolor=BG)
    plt.close(fig)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-framerate", str(FPS_FRAMES),
        "-i", os.path.join(frames_dir, "f_%04d.png"),
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-r", str(FPS_FRAMES), out_mp4,
    ], check=True)
    return out_mp4


# ---------------------------------------------------------------------------
# Portada (cover) del video
# ---------------------------------------------------------------------------

def cifra_clave(spec):
    """La cifra protagonista del tema, calculada en codigo como todo lo
    demas: devuelve (valor_grande, etiqueta) o (None, None) si el visual
    no tiene una cifra clara que poner en la portada."""
    tipo = spec.get("tipo")
    if tipo == "growth_curve":
        fv = fv_mensual(spec["mensual"], spec["tasa_anual"], spec["anios"])
        return (fmt_dinero(fv),
                f"from {fmt_dinero(spec['mensual'])}/month in {spec['anios']} years")
    if tipo == "budget_table":
        for fila in spec.get("filas", []):
            if fila.get("tipo") == "total" and fila.get("celdas"):
                return fila["celdas"][-1], fila["celdas"][0]
        return None, None
    if tipo == "comparison_bars":
        barras = calcular_barras(spec)
        if not barras:
            return None, None
        b = next((x for x in barras if x["color"] == LIME),
                 max(barras, key=lambda x: x["valor"]))
        return fmt_valor(b["valor"], b["formato"]), b["etiqueta"]
    return None, None


def render_cover(spec, gancho, out_jpg, usuario="@firstpaycheckmath"):
    """Genera la portada del video: JPG 1080x1920 con la misma identidad
    (carbon + verde lima), el gancho en grande y la cifra clave del tema.

    La rejilla de perfil de TikTok recorta la portada a ~3:4 centrado, asi
    que todo el texto vive en la banda central segura (del 12,5% al 87,5%
    de la altura): gancho centrado en esa banda, cifra debajo y el
    @usuario al final de la banda, nunca en los bordes que se cortan."""
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    fig.patch.set_facecolor(BG)
    titulo = (spec.get("titulo_visual") or "").upper()
    if titulo:
        fig.text(0.5, 0.845, titulo, ha="center", va="center", color=LIME,
                 fontsize=30, fontweight="bold")
    # Gancho: se busca el mayor tamano con el que cabe en <= 4 lineas.
    lineas, fs = None, 48
    for fs_try, ancho in ((74, 13), (66, 15), (58, 17), (50, 20), (44, 23)):
        cand = textwrap.wrap(gancho or "", ancho) or [""]
        if len(cand) <= 4:
            lineas, fs = cand, fs_try
            break
    if lineas is None:
        lineas = textwrap.wrap(gancho or "", 23)[:4]
        fs = 44
    dy = fs * 1.5 / 1382.4  # alto de linea en fraccion de la figura
    y = 0.665 + (len(lineas) - 1) * dy / 2
    for linea in lineas:
        fig.text(0.5, y, linea, ha="center", va="center", color=WHITE,
                 fontsize=fs, fontweight="bold")
        y -= dy
    valor, etiqueta = cifra_clave(spec)
    if valor:
        fig.add_artist(Rectangle((0.44, 0.368), 0.12, 0.006,
                                 transform=fig.transFigure, fc=LIME,
                                 ec="none"))
        fig.text(0.5, 0.295, valor, ha="center", va="center", color=LIME,
                 fontsize=86, fontweight="bold")
        if etiqueta:
            fig.text(0.5, 0.238, etiqueta, ha="center", va="center",
                     color=GRAY, fontsize=25)
    fig.text(0.5, 0.155, usuario, ha="center", va="center",
             color=GRAY_DIM, fontsize=24)
    fig.savefig(out_jpg, facecolor=BG)
    plt.close(fig)
    return out_jpg
