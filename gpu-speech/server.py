"""Speech GPU service: ears and mouth on one GPU, no LLM.

- POST /v1/audio/transcriptions: audio file in (webm/ogg/wav/anything ffmpeg
  reads; transcoded to 16k mono wav), transcription JSON out. Proxied to a
  local vLLM serving Whisper.
- POST /v1/audio/speech: {"input": text} in, WAV bytes out. Kokoro on CUDA in
  this process.
- GET /healthz: 200 when both halves are ready.

vLLM runs as a second process on this same GPU (started by start.sh); this app
owns the exposed port. The layout is deliberately the same one the full
self-hosted box will use, with the LLM added as a third consumer later.
"""
import io
import os
import subprocess
import tempfile
import wave

import httpx
import numpy as np
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import JSONResponse, Response

VLLM_URL = os.environ.get("VLLM_URL", "http://127.0.0.1:8001")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "openai/whisper-large-v3-turbo")
SAMPLE_RATE = 24000

app = FastAPI()
_kokoro = None


def _to_wav16k(data: bytes) -> bytes:
    """Transcode arbitrary browser audio (webm/opus, ogg, m4a, wav) to 16k mono WAV."""
    with tempfile.NamedTemporaryFile(suffix=".bin") as src:
        src.write(data)
        src.flush()
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src.name,
             "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
            capture_output=True, check=True,
        )
        return out.stdout


@app.post("/v1/audio/transcriptions")
async def transcribe(file: UploadFile):
    raw = await file.read()
    try:
        wav = _to_wav16k(raw)
    except subprocess.CalledProcessError as e:
        return JSONResponse({"error": "transcode failed", "detail": e.stderr.decode()[-500:]}, status_code=400)
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{VLLM_URL}/v1/audio/transcriptions",
            files={"file": ("audio.wav", wav, "audio/wav")},
            data={"model": WHISPER_MODEL},
        )
    return JSONResponse(resp.json(), status_code=resp.status_code)


def _kokoro_pipeline():
    global _kokoro
    if _kokoro is None:
        from kokoro import KPipeline

        _kokoro = KPipeline(lang_code="a")  # American English
    return _kokoro


@app.post("/v1/audio/speech")
async def speak(request: Request):
    body = await request.json()
    text = (body.get("input") or "").strip()
    if not text:
        return JSONResponse({"error": "no input"}, status_code=400)
    voice = body.get("voice") or os.environ.get("KOKORO_VOICE", "af_heart")
    pipeline = _kokoro_pipeline()
    chunks = []
    for _, _, audio in pipeline(text, voice=voice):
        chunks.append(audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio))
    samples = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return Response(buf.getvalue(), media_type="audio/wav")


@app.get("/healthz")
async def healthz():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            v = await client.get(f"{VLLM_URL}/health")
        vllm_ok = v.status_code == 200
    except Exception:  # noqa: BLE001
        vllm_ok = False
    return JSONResponse({"vllm": vllm_ok}, status_code=200 if vllm_ok else 503)
