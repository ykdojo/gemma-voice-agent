FROM vllm/vllm-openai:latest

RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir fastapi uvicorn httpx kokoro soundfile librosa

WORKDIR /app
COPY server.py start.sh ./
RUN chmod +x start.sh

# Bake the (small, ungated) model weights into the image so cold starts skip
# the Hugging Face download: Whisper turbo ~1.6GB, Kokoro ~330MB.
ENV HF_HOME=/models
RUN python -c "from huggingface_hub import snapshot_download; \
    snapshot_download('openai/whisper-large-v3-turbo'); \
    snapshot_download('hexgrad/Kokoro-82M')"

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/app/start.sh"]
