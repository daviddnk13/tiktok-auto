# -*- coding: utf-8 -*-
"""
First Paycheck Math — pipeline automatico de TikTok.

Hermano de los pipelines de YouTube (sharpcents-auto): misma arquitectura
probada (guion con IA y fallbacks Gemini -> NVIDIA NIM, voz Kokoro con
respaldo edge-tts, tiempos por palabra con faster-whisper, subtitulos
ASS, avisos por Telegram, historial/estrategia versionados), adaptada a
TikTok:

  - Videos explicativos de 65-90 s (guiones de ~190-210 palabras).
  - Visuales GENERADOS por codigo (visuals.py): TikTok penaliza el
    stock + texto como "no original", asi que nada de Pexels aqui.
  - La subida la hace upload_tiktok.py (tiktok-uploader, cookies de
    sesion) si config.json -> subida.activada es true.
  - Cumplimiento financiero dentro del prompt: solo explicar como
    funcionan las cosas; nada de consejo personalizado ni tickers.

Flujo de una corrida (1 video):
  estrategia.json -> siguiente tema "pendiente" -> guion IA -> TTS por
  escenas -> subtitulos -> visual animado -> ffmpeg -> subida ->
  historial.json + estrategia.json actualizados (el workflow los
  commitea) -> aviso por Telegram.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

import edge_tts

import visuals

BASE = os.path.dirname(os.path.abspath(__file__))
WORKDIR = os.environ.get("TT_WORKDIR", os.path.join(BASE, "work"))

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
NVIDIA_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()


def cargar_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


cfg = cargar_json(os.path.join(BASE, "config.json"), {})

# Modelos de IA: se leen de config.json (clave "modelos") para poder
# actualizarlos sin tocar el codigo; si faltan, se usan estos por defecto.
_MODELOS_CFG = cfg.get("modelos") or {}
GEMINI_MODELS = _MODELOS_CFG.get("gemini") or ["gemini-3.5-flash-lite"]
NIM_MODELS = _MODELOS_CFG.get("nvidia_nim") or ["nvidia/nemotron-3.5-lightning-30b-a3b", "nvidia/nemotron-3-ultra-550b-a55b"]


def _tg_alert(texto):
    tok = os.environ.get("TG_BOT_TOKEN", "").strip()
    cid = os.environ.get("TG_CHAT_ID", "").strip()
    if tok and cid:
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                data=json.dumps({"chat_id": cid, "text": texto}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10).read()
        except Exception:
            pass


def parse_json_text(raw):
    m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw)
    if not m:
        raise ValueError("No JSON in response")
    return json.loads(m.group(0))


def call_ai(prompt_text):
    for model_name in GEMINI_MODELS:
        payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
        for intento in range(2):
            try:
                req = urllib.request.Request(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_KEY}",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=60) as r:
                    resp_json = json.loads(r.read().decode())
                parts = resp_json["candidates"][0]["content"]["parts"]
                raw = "\n".join(p.get("text", "") for p in parts if "text" in p)
                return parse_json_text(raw)
            except urllib.error.HTTPError as he:
                try:
                    detalle = he.read().decode("utf-8", "ignore")[:200]
                except Exception:
                    detalle = ""
                print(f"Gemini {model_name} HTTP {he.code}, try {intento+1}: {detalle}")
                if he.code == 429:
                    time.sleep(8)
                else:
                    break
            except Exception as ex:
                print("Gemini retry:", ex)
                time.sleep(2)

    if NVIDIA_KEY:
        for nim_model in NIM_MODELS:
            try:
                nim_payload = {
                    "model": nim_model,
                    "messages": [{"role": "user", "content": prompt_text}],
                    "temperature": 0.7,
                    "max_tokens": 2500
                }
                req = urllib.request.Request(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    data=json.dumps(nim_payload).encode(),
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {NVIDIA_KEY}"},
                )
                with urllib.request.urlopen(req, timeout=90) as r:
                    rj = json.loads(r.read().decode())
                _msg = rj["choices"][0]["message"]
                raw = _msg.get("content") or _msg.get("reasoning_content") or ""
                if not raw.strip():
                    raise ValueError("respuesta vacia del modelo NIM")
                print("Used NVIDIA NIM fallback:", nim_model)
                return parse_json_text(raw)
            except Exception as ne:
                print(f"NVIDIA NIM {nim_model} failed:", ne)

    raise RuntimeError("Both Gemini and NVIDIA NIM failed")


# ---------------------------------------------------------------------------
# Guion (con el cumplimiento financiero dentro del prompt)
# ---------------------------------------------------------------------------

def generar_guion(tarea):
    spec = tarea.get("visual", {})
    resumen = visuals.resumen_datos(spec)
    vcfg = cfg.get("video", {})
    wmin, wmax = (vcfg.get("palabras_objetivo") or [190, 210])
    prompt = f"""You are the scriptwriter for "First Paycheck Math", a TikTok channel that explains personal finance in plain American English to young US workers with their first salary.
Topic: {tarea.get('titulo')}
MANDATORY opening line (scene 1 must be exactly this hook, word for word): {tarea.get('gancho')}
The on-screen graphic shows these EXACT figures, computed in code (use them verbatim in meaning; never invent different numbers): {resumen}
Closing call to action to weave naturally into the last scene: {tarea.get('cta')}

FINANCE COMPLIANCE (non-negotiable):
- Explainers only: explain how things work. NEVER give personalized advice ("you should buy", "open this exact account"), never recommend a specific stock, fund ticker, bank or product. Generic concepts are fine ("a broad market index fund", "a high-yield savings account").
- No guaranteed returns: growth numbers are math examples with an assumed average return; phrase them as examples ("if it averaged 8% a year...").
- GOLDEN RULE: never tease a number, tool or resource in the hook that the video does not fully deliver and explain.

FORMAT:
- 6 to 8 scenes, {wmin}-{wmax} words in TOTAL (a 65-90 second video at speaking pace). Scene 1 = the hook, verbatim. Last scene = the call to action + a follow invitation + a one-line tease of the next video.
- Spoken, punchy American English, short sentences. Write money and percents in WORDS in the scene text ("one hundred dollars", "eight percent") so the voice reads them naturally; the on-screen graphic carries the digits.
Reply ONLY with valid JSON:
{{
  "caption": "First line = the hook. Then 2 short value lines, the question for comments, and 5-7 hashtags (#personalfinance #moneytok #firstpaycheck ...)",
  "pregunta": "One short question to invite comments",
  "hook_banner": "MAX 4 WORDS IN ALL CAPS",
  "escenas": [
    {{"texto": "Spoken line of scene 1 (the hook, verbatim)"}},
    {{"texto": "Spoken line"}}
  ]
}}"""
    data = call_ai(prompt)
    escenas = data.get("escenas") or []
    if len(escenas) < 4:
        raise RuntimeError(f"Guion invalido: solo {len(escenas)} escenas")
    palabras = sum(len(e.get("texto", "").split()) for e in escenas)
    print(f"Guion: {len(escenas)} escenas, {palabras} palabras")
    if not (wmin - 30 <= palabras <= wmax + 30):
        print(f"AVISO: el guion tiene {palabras} palabras (objetivo "
              f"{wmin}-{wmax}); la duracion puede salir del rango 65-90 s")
    return data


# ---------------------------------------------------------------------------
# TTS: Kokoro (principal) + edge-tts (respaldo por escena) + faster-whisper
# Bloque portado de sharpcents-auto, donde lleva en produccion desde el
# 2026-11-21: whisper SOLO aporta tiempos; el texto mostrado es el guion.
# ---------------------------------------------------------------------------

def fmt_ass_time(sec):
    h = int(sec // 3600)
    mn = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = min(99, int(round((sec - int(sec)) * 100)))
    return f"{h}:{mn:02d}:{s:02d}.{cs:02d}"


def esc_drawtext(t):
    return re.sub(r"[^A-Za-z0-9 ?!.,/-]", "", t).replace(":", "").strip()[:36]


async def gen_scene_tts(texto, out_mp3, voz, rate):
    comm = edge_tts.Communicate(texto.strip(), voz, rate=rate)
    words = []
    with open(out_mp3, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                st = chunk["offset"] / 10_000_000
                dw = chunk["duration"] / 10_000_000
                words.append((chunk["text"], st, st + dw))
    return words


_KOKORO = {"obj": None, "falla": False}
# En GitHub Actions los modelos se descargan a /tmp en cada corrida (como
# en los repos de YouTube). En local se puede apuntar TT_KOKORO_DIR a la
# carpeta donde ya estan descargados para no bajarlos otra vez.
_KOKORO_DIR = os.environ.get("TT_KOKORO_DIR", "/tmp")
_KOKORO_FILES = {
    os.path.join(_KOKORO_DIR, "kokoro-v1.0.onnx"): "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx",
    os.path.join(_KOKORO_DIR, "voices-v1.0.bin"): "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin",
}


def _kokoro_cargar():
    if _KOKORO["obj"] is not None:
        return _KOKORO["obj"]
    if _KOKORO["falla"]:
        return None
    try:
        for ruta, url in _KOKORO_FILES.items():
            if not os.path.exists(ruta) or os.path.getsize(ruta) < 1000000:
                print("Kokoro: descargando", url.rsplit("/", 1)[-1])
                urllib.request.urlretrieve(url, ruta)
        from kokoro_onnx import Kokoro
        rutas = list(_KOKORO_FILES.keys())
        _KOKORO["obj"] = Kokoro(rutas[0], rutas[1])
        print("Kokoro: modelo listo")
    except Exception as e:
        print("Kokoro no disponible, se usa edge-tts:", e)
        _KOKORO["falla"] = True
        return None
    return _KOKORO["obj"]


_WHISPER = {"obj": None, "falla": False, "modelo": "small"}


def _whisper_cargar():
    if _WHISPER["obj"] is not None:
        return _WHISPER["obj"]
    if _WHISPER["falla"]:
        return None
    try:
        from faster_whisper import WhisperModel
        _WHISPER["obj"] = WhisperModel(_WHISPER["modelo"], device="cpu", compute_type="int8")
        print("faster-whisper: modelo listo")
    except Exception as e:
        print("faster-whisper no disponible, subtitulos aproximados:", e)
        _WHISPER["falla"] = True
        return None
    return _WHISPER["obj"]


def _whisper_transcribir(samples24k, lang):
    """Transcribe el audio de la escena con faster-whisper (audio en memoria
    remuestreado a 16 kHz, sin depender de PyAV) y devuelve las palabras con
    tiempos reales [(palabra, inicio, fin), ...]; None si algo falla."""
    m = _whisper_cargar()
    if m is None:
        return None
    try:
        import numpy as np
        n16 = int(len(samples24k) * 16000 / 24000)
        if n16 < 1600:
            return None
        x = np.linspace(0, len(samples24k) - 1, n16)
        audio16 = np.interp(x, np.arange(len(samples24k)), samples24k).astype(np.float32)
        segs, _info = m.transcribe(audio16, language=str(lang).split("-")[0],
                                   word_timestamps=True, beam_size=2)
        out = []
        for s in segs:
            for w in (s.words or []):
                t = (w.word or "").strip()
                if t:
                    out.append((t, float(w.start), float(w.end)))
        return out or None
    except Exception as e:
        print("faster-whisper fallo en una escena:", e)
        return None


def _norm_palabra(w):
    import unicodedata
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return "".join(c for c in w if c.isalnum())


def _alinear_palabras(toks, escuchadas):
    """Alinea las palabras del guion con las escuchadas por whisper (DP) y
    devuelve [(palabra_del_guion, inicio, fin), ...] con tiempos reales: el
    texto mostrado es siempre el del guion, nunca el oido por whisper.
    None si la cobertura es mala y conviene el reparto proporcional."""
    import difflib
    a = [_norm_palabra(t) for t in toks]
    b = [_norm_palabra(w[0]) for w in escuchadas]
    n, m = len(a), len(b)
    if not n or not m:
        return None
    INF = float("inf")
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    bk = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == INF:
                continue
            if i < n and j < m:
                c = 1.0 - difflib.SequenceMatcher(None, a[i], b[j]).ratio()
                if dp[i][j] + c < dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = dp[i][j] + c
                    bk[i + 1][j + 1] = ("par", i, j)
            if i < n and dp[i][j] + 0.9 < dp[i + 1][j]:
                dp[i + 1][j] = dp[i][j] + 0.9
                bk[i + 1][j] = ("sin", i, j)
            if j < m and dp[i][j] + 0.9 < dp[i][j + 1]:
                dp[i][j + 1] = dp[i][j] + 0.9
                bk[i][j + 1] = ("extra", i, j)
    pares = {}
    i, j = n, m
    while (i, j) != (0, 0):
        paso = bk[i][j]
        if paso is None:
            return None
        tipo, pi, pj = paso
        if tipo == "par":
            pares[pi] = (escuchadas[pj][1], escuchadas[pj][2])
        i, j = pi, pj
    if len(pares) < 0.6 * n:
        return None
    total_fin = escuchadas[-1][2]
    res = []
    for idx, t in enumerate(toks):
        if idx in pares:
            st, en = pares[idx]
        else:
            prev_en = res[-1][2] if res else 0.0
            nxt = next((pares[k][0] for k in sorted(pares) if k > idx), total_fin)
            st, en = prev_en, max(prev_en + 0.05, nxt)
        res.append((t, float(st), float(max(en, st + 0.05))))
    return res


def gen_scene_tts_kokoro(texto, out_mp3, voz_k, lang, speed):
    """Genera el audio de una escena con Kokoro y devuelve los tiempos por
    palabra (alineados con whisper si se puede; si no, reparto
    proporcional al largo de cada palabra), en el mismo formato que
    gen_scene_tts: [(palabra, inicio, fin), ...]."""
    import soundfile as sf
    k = _kokoro_cargar()
    if k is None:
        raise RuntimeError("kokoro no cargado")
    samples, sr = k.create(texto.strip(), voice=voz_k, speed=speed, lang=lang)
    if samples is None or len(samples) == 0:
        raise RuntimeError("kokoro devolvio audio vacio")
    wav_path = out_mp3 + ".wav"
    sf.write(wav_path, samples, sr)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav_path,
                    "-codec:a", "libmp3lame", "-q:a", "3", out_mp3], check=True)
    os.remove(wav_path)
    dur = len(samples) / float(sr)
    toks = texto.strip().split()
    tot = max(1, sum(len(t) for t in toks))
    words, acc = [], 0.0
    for t in toks:
        d = dur * (len(t) / tot)
        words.append((t, acc, acc + d))
        acc += d
    escuchadas = _whisper_transcribir(samples, lang)
    if escuchadas:
        alineadas = _alinear_palabras(toks, escuchadas)
        if alineadas:
            return alineadas
    return words


# ---------------------------------------------------------------------------
# Sintesis de todas las escenas + subtitulos ASS
# ---------------------------------------------------------------------------

def sintetizar_y_subtitular(data):
    """Genera el audio de cada escena, concatena la voz y escribe el ASS.
    Devuelve (duracion_total, ruta_voz_mp3, ruta_ass)."""
    os.makedirs(WORKDIR, exist_ok=True)
    voz = cfg.get("voz", "en-US-AndrewNeural")
    rate = cfg.get("velocidad", "+8%")
    tts_cfg = cfg.get("tts", {})
    usa_kokoro = tts_cfg.get("proveedor", "kokoro") == "kokoro"
    try:
        kokoro_speed = 1.0 + float(str(rate).replace("%", "")) / 100.0
    except Exception:
        kokoro_speed = 1.08
    kokoro_voz = tts_cfg.get("kokoro_voz", "am_michael")
    kokoro_lang = tts_cfg.get("kokoro_lang", "en-us")
    _WHISPER["modelo"] = tts_cfg.get("whisper_modelo", "small")

    scene_audios, all_ass_events, cursor = [], [], 0.0
    for i, esc in enumerate(data["escenas"]):
        mp3_path = os.path.join(WORKDIR, f"aud_{i}.mp3")
        words = None
        if usa_kokoro:
            try:
                words = gen_scene_tts_kokoro(esc["texto"], mp3_path,
                                             kokoro_voz, kokoro_lang,
                                             kokoro_speed)
            except Exception as e:
                print("Kokoro failed on scene", i,
                      "- falling back to edge-tts:", e)
                words = None
        if words is None:
            words = asyncio.run(gen_scene_tts(esc["texto"], mp3_path, voz, rate))
        dur_s = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", mp3_path
        ]).decode().strip())
        scene_audios.append((mp3_path, dur_s))
        if words:
            for j in range(0, len(words), 3):
                grp = words[j:j + 3]
                txt = " ".join(w[0] for w in grp).upper().replace("{", "").replace("}", "")
                st = cursor + grp[0][1]
                en = cursor + grp[-1][2]
                all_ass_events.append((st, max(en, st + 0.25), txt))
        else:
            toks_fb = esc["texto"].strip().upper().split()
            if toks_fb:
                tot_fb = max(1, sum(len(t) for t in toks_fb))
                acc_fb = 0.0
                for j in range(0, len(toks_fb), 3):
                    grp = toks_fb[j:j + 3]
                    d_fb = dur_s * (sum(len(t) for t in grp) / tot_fb)
                    all_ass_events.append((cursor + acc_fb,
                                           cursor + acc_fb + max(d_fb, 0.25),
                                           " ".join(grp)))
                    acc_fb += d_fb
            else:
                all_ass_events.append((cursor, cursor + dur_s,
                                       esc["texto"].strip().upper()))
        cursor += dur_s

    list_path = os.path.join(WORKDIR, "aud_list.txt")
    with open(list_path, "w") as af:
        for mp3_path, _ in scene_audios:
            af.write(f"file '{mp3_path}'\n")
    voice_mp3 = os.path.join(WORKDIR, "voice.mp3")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat",
                    "-safe", "0", "-i", list_path, "-c", "copy",
                    voice_mp3], check=True)

    vcfg = cfg.get("video", {})
    W = vcfg.get("ancho", 1080)
    H = vcfg.get("alto", 1920)
    # WrapStyle 0 = el texto se parte en 2-3 lineas dentro de los margenes
    # (con WrapStyle 2 los subtitulos se salian del cuadro: bug ya
    # corregido en los canales de YouTube el 2026-11-21).
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Viral,DejaVu Sans,70,&H0066FF99,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,440,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_path = os.path.join(WORKDIR, "subs.ass")
    with open(ass_path, "w", encoding="utf-8") as sf:
        sf.write(ass_header)
        for st, en, txt in all_ass_events:
            sf.write(f"Dialogue: 0,{fmt_ass_time(st)},{fmt_ass_time(en)},Viral,,0,0,0,,{txt}\n")
    return cursor, voice_mp3, ass_path


# ---------------------------------------------------------------------------
# Composicion final
# ---------------------------------------------------------------------------

def componer_video(bg_mp4, voice_mp3, ass_path, banner, duracion):
    out = os.path.join(WORKDIR, "final_video.mp4")
    hook_txt = esc_drawtext(banner or "FIRST PAYCHECK MATH")
    # Sin marca de agua aqui: el @usuario ya va integrado abajo en el
    # propio visual (visuals._base_fig), lejos de los subtitulos ASS.
    vf_chain = (
        f"fps=30,ass={ass_path},"
        f"drawtext=text='{hook_txt}':fontcolor=black:fontsize=50:box=1:boxcolor=0x66FF99@0.95:boxborderw=22:x=(w-text_w)/2:y=250:enable='between(t,0,2.8)'"
    )
    subprocess.run([
        "ffmpeg", "-y",
        "-i", bg_mp4,
        "-i", voice_mp3,
        "-filter_complex",
        f"[0:v]{vf_chain}[v];[1:a]acompressor=threshold=-18dB:ratio=3:attack=5:release=50[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-shortest", out
    ], check=True)
    return out


# ---------------------------------------------------------------------------
# Corrida principal
# ---------------------------------------------------------------------------

def guardar_estado(est, hist):
    with open(os.path.join(BASE, "estrategia.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(est, indent=2, ensure_ascii=False))
    with open(os.path.join(BASE, "historial.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(hist, indent=2, ensure_ascii=False))


def main():
    os.chdir(BASE)
    os.makedirs(WORKDIR, exist_ok=True)
    if not GEMINI_KEY and not NVIDIA_KEY:
        _tg_alert("🚨 First Paycheck Math: faltan las claves de IA "
                  "(GEMINI_API_KEY / NVIDIA_API_KEY) en los secrets del repo.")
        sys.exit(1)

    hist = cargar_json(os.path.join(BASE, "historial.json"), [])
    est = cargar_json(os.path.join(BASE, "estrategia.json"), {"cola": []})
    pendientes = [x for x in est.get("cola", []) if x.get("estado") == "pendiente"]
    if not pendientes:
        _tg_alert("⚠️ First Paycheck Math: la cola de temas esta vacia. "
                  "Agrega temas nuevos a estrategia.json.")
        print("Sin temas pendientes; nada que publicar.")
        return

    tarea = pendientes[0]
    print("Running -> TIKTOK 9:16 |", tarea.get("titulo"))
    data = generar_guion(tarea)
    duracion, voice_mp3, ass_path = sintetizar_y_subtitular(data)
    print(f"Duracion total: {duracion:.1f}s")
    rango = (cfg.get("video", {}).get("duracion_objetivo_seg") or [65, 90])
    if not (rango[0] - 5 <= duracion <= rango[1] + 5):
        print(f"AVISO: duracion {duracion:.1f}s fuera del objetivo "
              f"{rango[0]}-{rango[1]}s")

    bg_mp4 = os.path.join(WORKDIR, "bg.mp4")
    visuals.render_visual(tarea["visual"], duracion, bg_mp4, WORKDIR)
    banner = data.get("hook_banner") or " ".join(
        str(tarea.get("gancho", "FIRST PAYCHECK MATH")).split()[:4])
    final = componer_video(bg_mp4, voice_mp3, ass_path, banner, duracion)

    caption = (data.get("caption") or tarea.get("titulo", "")).strip()
    pregunta = (data.get("pregunta") or "").strip()
    if pregunta and pregunta not in caption:
        caption = caption + "\n\n" + pregunta
    caption += ("\n\nEducational content only — not financial advice. "
                "Examples use an assumed average return; markets vary.")

    subida_cfg = cfg.get("subida", {})
    if subida_cfg.get("activada"):
        import upload_tiktok
        portada_path = None
        if subida_cfg.get("portada", True):
            candidata = os.path.join(WORKDIR, f"cover-{tarea.get('id')}.jpg")
            try:
                visuals.render_cover(tarea.get("visual", {}),
                                     tarea.get("gancho", ""),
                                     candidata,
                                     cfg.get("usuario", "@firstpaycheckmath"))
                portada_path = candidata
                print("Portada generada:", candidata)
            except Exception as e:
                print("Portada no generada (se sube sin ella):", e)
        try:
            resultado = upload_tiktok.subir(final, caption, cfg,
                                            portada=portada_path)
        except upload_tiktok.CookiesError as e:
            _tg_alert("🚨 First Paycheck Math: la sesion de TikTok no "
                      f"funciona.\n{e}")
            hist.append({
                "fecha": datetime.now(timezone.utc).isoformat(),
                "tema": tarea.get("titulo"),
                "estado": "error_subida_cookies",
                "error": str(e)[:300],
                "metricas_48h": None,
            })
            guardar_estado(est, hist)
            raise
        except upload_tiktok.TikTokUploadError as e:
            _tg_alert(f"🚨 First Paycheck Math: fallo la subida a TikTok.\n{e}")
            hist.append({
                "fecha": datetime.now(timezone.utc).isoformat(),
                "tema": tarea.get("titulo"),
                "estado": "error_subida",
                "error": str(e)[:300],
                "metricas_48h": None,
            })
            guardar_estado(est, hist)
            raise
        tarea["estado"] = "publicado"
        tarea["fecha"] = datetime.now(timezone.utc).isoformat()
        hist.append({
            "fecha": datetime.now(timezone.utc).isoformat(),
            "tema": tarea.get("titulo"),
            "titulo": tarea.get("titulo"),
            "caption": caption,
            "duracion_seg": round(duracion, 1),
            "plataforma": "tiktok",
            "estado": "publicado",
            "portada": bool(portada_path),
            # Si la subida dejo el post programado (programacion nativa
            # de TikTok), aqui va el ISO del slot; None = salio al momento.
            "programado_para": resultado.get("programado_para"),
            # Snapshot de metricas a las 48 h (vistas/likes/comentarios/
            # compartidos), igual que el views_48h de los canales de
            # YouTube: lo rellena analitica.py (TikTok-Api, solo lectura)
            # al final de una corrida posterior, si config trae
            # "analitica": true. Hasta entonces queda en None.
            "metricas_48h": None,
        })
        guardar_estado(est, hist)
        prog = resultado.get("programado_para")
        if prog:
            _tg_alert(f"🎵 First Paycheck Math: video subido y programado "
                      f"en TikTok para {prog} (UTC):\n"
                      f"{tarea.get('titulo')}\n({duracion:.0f}s) "
                      f"https://www.tiktok.com/{cfg.get('usuario', '')}")
        else:
            _tg_alert(f"🎵 First Paycheck Math publico en TikTok:\n"
                      f"{tarea.get('titulo')}\n({duracion:.0f}s) "
                      f"https://www.tiktok.com/{cfg.get('usuario', '')}")
        print("Publicado en TikTok:", tarea.get("titulo"))
    else:
        tarea["estado"] = "renderizado"
        tarea["fecha"] = datetime.now(timezone.utc).isoformat()
        hist.append({
            "fecha": datetime.now(timezone.utc).isoformat(),
            "tema": tarea.get("titulo"),
            "titulo": tarea.get("titulo"),
            "caption": caption,
            "duracion_seg": round(duracion, 1),
            "plataforma": "tiktok",
            "estado": "renderizado_sin_subir",
            "metricas_48h": None,
        })
        guardar_estado(est, hist)
        _tg_alert(f"🎵 First Paycheck Math: video renderizado (subida "
                  f"desactivada en config.json): {tarea.get('titulo')}")
        print("Renderizado sin subir (subida desactivada):", final)


def _analitica_best_effort():
    """Snapshot de metricas a las 48 h con analitica.py (TikTok-Api,
    solo lectura). Se ejecuta al final de TODA corrida (finally): si
    config.json trae "analitica": true, intenta rellenar metricas_48h
    en historial.json y el paso de commit del workflow lo recoge.
    Best-effort absoluto: cualquier fallo se registra y se sigue; nunca
    cambia el resultado de la corrida ni bloquea el aviso de Telegram
    de la publicacion (que ya se envio dentro de main())."""
    try:
        if not cfg.get("analitica"):
            return
        import analitica
        n = analitica.ejecutar(cfg)
        if n:
            print(f"Analitica: metricas_48h rellenadas en {n} "
                  "entrada(s) del historial")
    except Exception as e:
        print("Analitica best-effort: fallo sin afectar a la corrida:", e)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _tg_alert(f"🚨 First Paycheck Math: la corrida fallo: {e}")
        raise
    finally:
        _analitica_best_effort()
