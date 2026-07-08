# app (gemini branch)

The full voice-agent structure, with **Gemini via Vertex AI** standing in as the brain/ears while
Cloud Run GPU quota is pending (see [docs/gpu-quota-blocker.md](../docs/gpu-quota-blocker.md)).
The model sits behind one interface ([`model.py`](model.py)), so swapping in self-hosted
Gemma 4 E4B on an L4 GPU later is a module change, not a rewrite.

- `server.py` - Flask app: serves the chat page and a single `POST /chat` (text or audio in,
  text + WAV audio out)
- `model.py` - the swappable brain: Gemini with native audio input and automatic tool calling
- `tools.py` - paper search/lookup via the OpenAlex API (stand-in for your in-infra data source)
- `tts.py` - Kokoro (82M, open weights) voice synthesis on CPU
- `static/index.html` - mobile chat UI: text field plus a mic button on the right

Deploy (CPU only, no GPU quota needed):

```sh
gcloud services enable aiplatform.googleapis.com
gcloud run deploy paper-voice-agent \
  --source . \
  --region us-central1 \
  --cpu 2 --memory 2Gi \
  --max-instances 1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project id>,GOOGLE_CLOUD_LOCATION=us-central1
```
