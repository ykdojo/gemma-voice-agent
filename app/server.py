"""HTTP server: chat frontend + two endpoints.

- POST /chat: text or audio in; streams the answer as NDJSON events. Audio is
  transcribed (Whisper on the speech GPU service) exactly once: the transcript
  is emitted as an early `transcript` event for the UI bubble, and the same
  text (never the raw audio) is what the agent receives.
  Event order: meta, [transcript], [status...], delta..., done.
- POST /speak: text in, WAV audio out (Kokoro on the speech GPU service)
"""
import base64
import json
import os
import re
import traceback

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

import model
import speech_client

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


@app.get("/status")
def status():
    """Are the scale-to-zero GPU boxes awake? Probing a cold one also starts it,
    so the frontend polling this at page load doubles as the wake-up trigger."""
    model_base = os.environ.get("MODEL_API_BASE", "").rstrip("/")
    model_ok = speech_client.awake(model_base, "/health") if model_base else True
    speech_ok = speech_client.awake(speech_client.BASE) if speech_client.enabled() else True
    return jsonify({"model": model_ok, "speech": speech_ok, "ready": model_ok and speech_ok})


@app.post("/chat")
def chat():
    text, audio, audio_mime, session_id = _parse_request()

    def generate():
        yield json.dumps({"type": "meta", "speech_available": os.environ.get("DISABLE_TTS") != "1"}) + "\n"
        try:
            # The GPU services scale to zero; probe the ones this turn needs and be
            # honest about the wait. The probes also kick their startups off early.
            model_base = os.environ.get("MODEL_API_BASE", "").rstrip("/")
            cold = (model_base and not speech_client.awake(model_base, "/health")) or (
                audio and speech_client.enabled() and not speech_client.awake(speech_client.BASE)
            )
            if cold:
                yield json.dumps({
                    "type": "status",
                    "status": "Waking up the GPU (it sleeps when idle) - the first reply can take a few minutes",
                }) + "\n"
            message = text
            if audio:
                transcript = speech_client.transcribe(audio, audio_mime)
                yield json.dumps({"type": "transcript", "text": transcript}) + "\n"
                message = f"{text}\n{transcript}" if text else transcript
            if not message or not message.strip():
                yield json.dumps({"type": "error", "error": "I couldn't hear that - please try again."}) + "\n"
                return
            for event in model.reply_stream(text=message, session_id=session_id):
                yield json.dumps(event) + "\n"
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            yield json.dumps({"type": "error", "error": str(e)}) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/speak")
def speak():
    try:
        text = (request.get_json(silent=True) or {}).get("text", "")
        if not text:
            return jsonify({"error": "no text"}), 400
        spoken = re.sub(r"[*#_`]+", "", text)  # markdown reads terribly aloud
        voice_b64 = base64.b64encode(speech_client.synthesize(spoken)).decode()
        return jsonify({"audio_wav_base64": voice_b64})
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
