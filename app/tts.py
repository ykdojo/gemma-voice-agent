"""Voice out: Kokoro (82M, open weights) on CPU. Text in, WAV bytes out."""
import io
import os
import wave

import numpy as np

_pipeline = None
VOICE = os.environ.get("KOKORO_VOICE", "af_heart")
SAMPLE_RATE = 24000


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from kokoro import KPipeline

        _pipeline = KPipeline(lang_code="a")  # American English
    return _pipeline


def synthesize(text: str) -> bytes:
    """Render text to a mono 24kHz 16-bit WAV."""
    chunks = []
    for _, _, audio in _get_pipeline()(text, voice=VOICE):
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
