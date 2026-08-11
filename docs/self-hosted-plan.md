# Self-hosted plan: one GPU box for brain, ears, and mouth

GPU quota is no longer a blocker (verified 2026-08-11: RTX 6000 Pro, 96GB,
deploys fine on Cloud Run under the current billing account). This is the plan
to replace the interim Gemini + Cloud TTS setup with the fully self-hosted
design, everything in one Cloud Run GPU service.

## Target stack

| Role | Component | Serving | Memory |
|---|---|---|---|
| Brain | Gemma 4 31B it (fp8) | vLLM, localhost port | ~30GB + KV |
| Ears | Whisper large-v3-turbo | vLLM, localhost port | ~2GB |
| Mouth | Kokoro 82M | in-process (CUDA) | <1GB |
| Front door | Flask + ADK Agent/Runner | exposed port | CPU |

Weights: 31B from Google's public GCS bucket (proven, no token), Whisper and
Kokoro ungated on Hugging Face. Nothing gated, no HF license flow.

## Decisions already made

- Transcription-first: audio goes to Whisper, the transcript feeds both the UI
  bubble and the agent turn as text. The 31B has no audio encoder, and this
  kills the unverified audio-over-LiteLLM path entirely.
- One transcription per turn: /chat transcribes once and emits the transcript
  as an early NDJSON event; the separate /transcribe request (which duplicated
  the work) goes away.
- /chat keeps taking text or voice, as today: text goes straight to the agent
  (no transcript event), audio goes through Whisper first.
- No ADK graph for the interactive path: ADK 2 graphs don't support live
  streaming, and the streamed deltas are the UX. Agent + Runner + SSE stays.
- Keep TTS behind /speak, after the text: audio output is slower than text,
  so text renders first, exactly as today.
- ADK stays; the model swap is LiteLlm(base_url=localhost vLLM), the pattern
  validated end to end in the cloud-run-adk-bq-mcp codelab.

## Order of work

1. **Cleanup first** (this branch, no behavior change):
   - Collapse reply() into reply_stream() (duplicated turn logic).
   - Replace the per-request asyncio.run() session bridge with one owned event
     loop (or move the server to async); today's code spins up an event loop
     per request inside threaded gunicorn.
   - Fix the stale transcribe() docstring (claims the transcript enters the
     history; the raw audio does).
2. **Mouth on GPU**: enable the Kokoro backend (deps + espeak-ng + TTS_BACKEND)
   and verify it on a GPU service on its own. Already a separate module, so it
   is the lowest-risk GPU step.
3. **Brain + ears together**: one container running both vLLM processes plus
   the app; startup script, memory split, transcript-in-stream refactor,
   /transcribe removal. Local-ish test via the existing Cloud Run project.
4. **Deploy + swap**: point the service at the one-box image, retire the
   Gemini and Cloud TTS code paths, update README (the "temporarily Gemini"
   note finally dies).

## Open questions to settle during 3

- webm/opus from the browser: does vLLM's Whisper endpoint decode it, or do we
  transcode to wav in Flask first (ffmpeg in the image either way)?
- gpu-memory-utilization split between the two vLLM processes.
- Cold start budget: 31B load is ~2-3 min; decide idle vs min-instances later.
