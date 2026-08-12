# gpu-speech: the GPU box

One Cloud Run GPU service (RTX 6000 Pro) running all three open-weights models:

- **Whisper large-v3-turbo** (vLLM, localhost:8001) - ears; weights baked into
  the image (~1.6GB)
- **Gemma 4 31B it, fp8** (vLLM, localhost:8002) - brain; weights streamed at
  startup from Google's public GCS bucket via the Run:ai streamer
- **Kokoro 82M** - mouth; runs on CUDA inside the front process, weights baked

The front process (FastAPI, exposed port) routes:

- `POST /v1/audio/transcriptions` - audio in (ffmpeg-transcoded to 16k wav),
  transcription out
- `POST /v1/chat/completions` - OpenAI-style chat, streaming-safe proxy to the
  brain
- `POST /v1/audio/speech` - text in, WAV out
- `GET /healthz` (also `/health`) - 200 only when every enabled model is ready

Deploy (the service is private, callers need `roles/run.invoker`):

```sh
gcloud beta run deploy speech-gpu --source . \
  --region us-central1 \
  --cpu 20 --memory 80Gi \
  --gpu 1 --gpu-type nvidia-rtx-pro-6000 --no-gpu-zonal-redundancy \
  --no-allow-unauthenticated --max-instances 1 \
  --network <vpc> --subnet <subnet> --vpc-egress all-traffic \
  --startup-probe httpGet.path=/healthz,initialDelaySeconds=60,failureThreshold=60,periodSeconds=10,timeoutSeconds=5 \
  --set-env-vars BRAIN_MODEL_LOCATION=gs://vertex-model-garden-public-us/gemma4/gemma-4-31B-it,BRAIN_MODEL_NAME=google/gemma-4-31B-it
```

Omit `BRAIN_MODEL_LOCATION` to run it as an ears-and-mouth-only box.
