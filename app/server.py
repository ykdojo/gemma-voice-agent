"""HTTP server: chat frontend + three endpoints.

- POST /chat: text or audio in; streams the answer as NDJSON events (meta, status, delta, done)
- POST /transcribe: audio in, transcription out (display-only; independent of /chat)
- POST /speak: text in, WAV audio out
"""
import base64
import json
import os
import re
import traceback

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

import model
import tts

app = Flask(__name__, static_folder="static")


def _parse_request():
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
    return text, audio, audio_mime, session_id


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.post("/chat")
def chat():
    text, audio, audio_mime, session_id = _parse_request()

    def generate():
        yield json.dumps({"type": "meta", "speech_available": os.environ.get("DISABLE_TTS") != "1"}) + "\n"
        try:
            for event in model.reply_stream(
                text=text, audio=audio, audio_mime=audio_mime, session_id=session_id
            ):
                yield json.dumps(event) + "\n"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/transcribe")
def transcribe():
    try:
        _, audio, audio_mime, _ = _parse_request()
        if not audio:
            return jsonify({"error": "no audio"}), 400
        return jsonify({"transcription": model.transcribe(audio, audio_mime)})
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
