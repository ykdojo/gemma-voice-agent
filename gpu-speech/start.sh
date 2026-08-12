#!/usr/bin/env bash
# One GPU box: Whisper (ears) + Gemma 4 31B (brain) as two vLLM processes on
# side ports, Kokoro (mouth) inside the front app, which owns the exposed port.
set -e

# Ears: small, baked into the image, loads in seconds.
vllm serve "${WHISPER_MODEL:-openai/whisper-large-v3-turbo}" \
  --port 8001 --host 127.0.0.1 \
  --gpu-memory-utilization "${WHISPER_GPU_MEM_UTIL:-0.12}" \
  &

# Brain: weights streamed from the public GCS bucket at startup (~30GB fp8,
# a few minutes). Flags mirror the validated codelab deployment.
if [[ -n "${BRAIN_MODEL_LOCATION:-}" ]]; then
  vllm serve "${BRAIN_MODEL_LOCATION}" \
    --served-model-name "${BRAIN_MODEL_NAME:-google/gemma-4-31B-it}" \
    --port 8002 --host 127.0.0.1 \
    --enable-chunked-prefill --enable-prefix-caching \
    --generation-config auto \
    --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4 \
    --dtype bfloat16 --quantization fp8 --kv-cache-dtype fp8 \
    --max-num-seqs "${BRAIN_MAX_NUM_SEQS:-8}" \
    --max-model-len "${BRAIN_MAX_MODEL_LEN:-16384}" \
    --gpu-memory-utilization "${BRAIN_GPU_MEM_UTIL:-0.60}" \
    --load-format runai_streamer \
    &
fi

# Cloud Run's startup probe waits on /healthz, which requires every enabled
# process to be ready.
exec uvicorn server:app --host 0.0.0.0 --port "${PORT:-8080}"
