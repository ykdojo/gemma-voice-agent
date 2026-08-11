"""Client for the self-hosted speech GPU service (Whisper ears, Kokoro mouth).

Enabled by setting SPEECH_SERVICE_URL; when unset, the app keeps its hosted
backends (Gemini transcription, Cloud TTS). The service is private, so calls
carry an identity token: fetched from the metadata server on Cloud Run, or via
the gcloud CLI when running locally as a user.
"""
import os
import subprocess

import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

BASE = os.environ.get("SPEECH_SERVICE_URL", "").rstrip("/")


def enabled() -> bool:
    return bool(BASE)


def _token() -> str:
    try:
        return id_token.fetch_id_token(Request(), BASE)
    except Exception:  # noqa: BLE001 - local dev: user creds can't mint ID tokens
        return subprocess.check_output(
            "gcloud auth print-identity-token -q", shell=True
        ).decode().strip()


def transcribe(audio: bytes, mime: str = "audio/webm") -> str:
    resp = requests.post(
        f"{BASE}/v1/audio/transcriptions",
        files={"file": ("audio", audio, mime)},
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=120,
    )
    resp.raise_for_status()
    return (resp.json().get("text") or "").strip()


def synthesize(text: str) -> bytes:
    resp = requests.post(
        f"{BASE}/v1/audio/speech",
        json={"input": text},
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.content
