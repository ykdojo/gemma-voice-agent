"""Client for the self-hosted speech GPU service (Whisper ears, Kokoro mouth).

Enabled by setting SPEECH_SERVICE_URL; when unset, the app keeps its hosted
backends (Gemini transcription, Cloud TTS). The service is private, so calls
carry an identity token: fetched from the metadata server on Cloud Run, or via
the gcloud CLI when running locally as a user.
"""
import os
import subprocess
import time

import requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token

BASE = os.environ.get("SPEECH_SERVICE_URL", "").rstrip("/")
# The speech service scales to zero; while an instance boots, Cloud Run answers
# 429 (no capacity). Retry through a cold start instead of failing the turn.
RETRY_DELAYS = (5, 10, 20, 40, 60)


def enabled() -> bool:
    return bool(BASE)


def _post_with_retry(url: str, **kwargs) -> requests.Response:
    last_error = None
    for delay in RETRY_DELAYS + (None,):
        try:
            resp = requests.post(
                url, headers={"Authorization": f"Bearer {_token()}"}, **kwargs
            )
            if resp.status_code not in (429, 500, 503):
                resp.raise_for_status()
                return resp
            last_error = requests.HTTPError(f"{resp.status_code} from {url}", response=resp)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
        if delay is None:
            break
        time.sleep(delay)
    raise last_error


def _token() -> str:
    try:
        return id_token.fetch_id_token(Request(), BASE)
    except Exception:  # noqa: BLE001 - local dev: user creds can't mint ID tokens
        return subprocess.check_output(
            "gcloud auth print-identity-token -q", shell=True
        ).decode().strip()


def transcribe(audio: bytes, mime: str = "audio/webm") -> str:
    resp = _post_with_retry(
        f"{BASE}/v1/audio/transcriptions",
        files={"file": ("audio", audio, mime)},
        timeout=120,
    )
    return (resp.json().get("text") or "").strip()


def synthesize(text: str) -> bytes:
    resp = _post_with_retry(
        f"{BASE}/v1/audio/speech",
        json={"input": text},
        timeout=120,
    )
    return resp.content
