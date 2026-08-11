#!/usr/bin/env bash
# Start vLLM (Whisper) on the side port, wait for it, then run the front app.
set -e

vllm serve "${WHISPER_MODEL:-openai/whisper-large-v3-turbo}" \
  --port 8001 --host 127.0.0.1 \
  --gpu-memory-utilization "${WHISPER_GPU_MEM_UTIL:-0.25}" \
  &

# Kokoro warm-up happens on first /v1/audio/speech call; the front app can come
# up immediately and Cloud Run's startup probe waits on /healthz (vLLM ready).
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8080}"
