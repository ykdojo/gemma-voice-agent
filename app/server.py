"""HTTP server: serves the chat frontend and one /chat endpoint (text or audio in, text + audio out)."""
import base64
import os
import re
import traceback

from flask import Flask, jsonify, request, send_from_directory

import model
import tts

app = Flask(__name__, static_folder="static")


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.post("/chat")
def chat():
    try:
        text = None
        audio = None
        audio_mime = "audio/webm"
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            f = request.files.get("audio")
            if f:
                audio = f.read()
                audio_mime = f.mimetype or audio_mime
            text = request.form.get("text") or None
        else:
            text = (request.get_json(silent=True) or {}).get("text")

        answer = model.reply(text=text, audio=audio, audio_mime=audio_mime)

        voice_b64 = None
        if os.environ.get("DISABLE_TTS") != "1":
            try:
                spoken = re.sub(r"[*#_`]+", "", answer)  # markdown reads terribly aloud
                voice_b64 = base64.b64encode(tts.synthesize(spoken)).decode()
            except Exception:  # noqa: BLE001 - voice is best-effort; text is the contract
                traceback.print_exc()

        return jsonify({"text": answer, "audio_wav_base64": voice_b64})
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
