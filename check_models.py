import os, json, sys, urllib.request

# Chequeo semanal de modelos de IA: avisa por Telegram si algun modelo
# de la lista en config.json dejo de responder (fue la causa de los
# fallos del 2026-11-20). Solo usa la libreria estandar.

cfg = json.load(open("config.json", encoding="utf-8"))
modelos = cfg.get("modelos", {})
gemini_models = modelos.get("gemini", [])
nim_models = modelos.get("nvidia_nim", [])

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
NVIDIA_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()

muertos = []

for m in gemini_models:
    try:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_KEY}",
            data=json.dumps({"contents": [{"parts": [{"text": "Responde solo: OK"}]}]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print("OK Gemini:", m)
    except Exception as e:
        print("MUERTO Gemini:", m, "->", e)
        muertos.append(f"Gemini {m}")

for m in nim_models:
    try:
        req = urllib.request.Request(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            data=json.dumps({"model": m, "messages": [{"role": "user", "content": "Responde solo: OK"}], "max_tokens": 8}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {NVIDIA_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=45) as r:
            r.read()
        print("OK NIM:", m)
    except Exception as e:
        print("MUERTO NIM:", m, "->", e)
        muertos.append(f"NIM {m}")

if muertos:
    canal = cfg.get("canal", "Canal")
    msg = f"\u26a0\ufe0f {canal}: modelos de IA sin respuesta:\n" + "\n".join("- " + x for x in muertos) + "\nRevisa la lista 'modelos' en config.json antes de la proxima publicacion."
    tok = os.environ.get("TG_BOT_TOKEN", "").strip()
    cid = os.environ.get("TG_CHAT_ID", "").strip()
    if tok and cid:
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                data=json.dumps({"chat_id": cid, "text": msg}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10).read()
            print("Alerta Telegram enviada")
        except Exception as te:
            print("Telegram skip:", te)
    sys.exit(1)

print("Todos los modelos responden.")
