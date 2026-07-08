"""HTTP server: serves the chat frontend and one /chat endpoint (text or audio in, text + audio out)."""
import base64
import os
import re
import traceback
from concurrent.futures import ThreadPoolExecutor

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
        session_id = "default"
        if request.content_type and request.content_type.startswith("multipart/form-data"):
            f = request.files.get("audio")
            if f:
                audio = f.read()
                audio_mime = f.mimetype or audio_mime
            text = request.form.get("text") or None
            session_id = request.form.get("session_id") or session_id
        else:
            body = request.get_json(silent=True) or {}
            text = body.get("text")
            session_id = body.get("session_id") or session_id

        transcription = None
        if audio:
            # The agent hears the audio natively; transcription runs in parallel, for display only
            with ThreadPoolExecutor(max_workers=2) as pool:
                t_future = pool.submit(model.transcribe, audio, audio_mime)
                a_future = pool.submit(
                    model.reply, text=text, audio=audio, audio_mime=audio_mime, session_id=session_id
                )
                answer = a_future.result()
                try:
                    transcription = t_future.result()
                except Exception:  # noqa: BLE001 - display-only, never fail the answer
                    traceback.print_exc()
        else:
            answer = model.reply(text=text, session_id=session_id)

        # Speech is fetched separately via /speak so the text lands as soon as it is ready
        return jsonify({
            "text": answer,
            "transcription": transcription,
            "speech_available": os.environ.get("DISABLE_TTS") != "1",
        })
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.post("/speak")
def speak():
    try:
        text = (request.get_json(silent=True) or {}).get("text", "")
        if not text:
            return jsonify({"error": "no text"}), 400
        spoken = re.sub(r"[*#_`]+", "", text)  # markdown reads terribly aloud
        voice_b64 = base64.b64encode(tts.synthesize(spoken)).decode()
        return jsonify({"audio_wav_base64": voice_b64})
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
