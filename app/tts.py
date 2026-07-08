"""Voice out: text in, WAV bytes out. Two switchable backends:

- cloudtts (current): Google Cloud Text-to-Speech. Interim while this service is CPU-only,
  because synthesis returns in a second or two. Hosted, so not part of the private design.
- kokoro: Kokoro 82M, open weights, self-hosted. The mouth in the fully-private design;
  returns with the GPU era. Its dependencies are NOT in the image right now: to enable, add
  kokoro and soundfile to requirements.txt, apt-get espeak-ng in the Dockerfile, and set
  TTS_BACKEND=kokoro.

Select with TTS_BACKEND=kokoro|cloudtts.
"""
import io
import os
import wave

import numpy as np

BACKEND = os.environ.get("TTS_BACKEND", "cloudtts")
SAMPLE_RATE = 24000

_kokoro = None
_cloud_client = None


def _kokoro_synthesize(text: str) -> bytes:
    global _kokoro
    if _kokoro is None:
        from kokoro import KPipeline

        _kokoro = KPipeline(lang_code="a")  # American English
    voice = os.environ.get("KOKORO_VOICE", "af_heart")
    chunks = []
    for _, _, audio in _kokoro(text, voice=voice):
        chunks.append(audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio))
    samples = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def _cloudtts_synthesize(text: str) -> bytes:
    global _cloud_client
    from google.cloud import texttospeech

    if _cloud_client is None:
        _cloud_client = texttospeech.TextToSpeechClient()
    voice_name = os.environ.get("CLOUDTTS_VOICE", "en-US-Chirp3-HD-Aoede")
    response = _cloud_client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            language_code="-".join(voice_name.split("-")[:2]), name=voice_name
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=SAMPLE_RATE,
        ),
    )
    return response.audio_content  # LINEAR16 comes back as a WAV container


def synthesize(text: str) -> bytes:
    """Render text to a mono 24kHz 16-bit WAV using the configured backend."""
    if BACKEND == "cloudtts":
        return _cloudtts_synthesize(text)
    return _kokoro_synthesize(text)
