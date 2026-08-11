# app

The voice-agent front: chat UI, the ADK agent, and thin clients for the
self-hosted speech service. Voice in and voice out are **only** served by the
GPU speech service ([`../gpu-speech/`](../gpu-speech/)); the brain is Gemini
via your Cloud account for now, swapping to self-hosted Gemma 4 next (see
[docs/self-hosted-plan.md](../docs/self-hosted-plan.md)).

- `server.py` - Flask app: serves the chat page, `POST /chat` (text or audio
  in, NDJSON event stream out), `POST /transcribe` (display transcription),
  `POST /speak` (text in, WAV out)
- `model.py` - the ADK agent (Gemini for now, behind one narrow interface)
- `speech_client.py` - authenticated client for the speech GPU service
  (Whisper ears, Kokoro mouth)
- `tools.py` - paper search/lookup via the OpenAlex API (stand-in for your
  in-infra data source)
- `static/index.html` - mobile chat UI: text field plus a mic button

Required env: `SPEECH_SERVICE_URL` (the deployed gpu-speech service; the app
authenticates to it with its identity token), `GOOGLE_CLOUD_PROJECT`, and
`GOOGLE_GENAI_USE_ENTERPRISE=TRUE` for the interim Gemini brain.

Deploy:

```sh
gcloud run deploy paper-voice-agent \
  --source . \
  --region us-central1 \
  --cpu 2 --memory 2Gi \
  --max-instances 1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=<project id>,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_ENTERPRISE=TRUE,SPEECH_SERVICE_URL=<gpu-speech url>
```

The service account running this app needs `roles/run.invoker` on the
gpu-speech service.
