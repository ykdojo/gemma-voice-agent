# Gemma Voice Agent

A voice customer-service agent that is **fully self-hosted and fully yours**: ask a question by
voice, the agent searches a knowledge base, and answers back in voice — with **no external AI
APIs**. Audio, queries, and documents stay in your own infrastructure, and because every model is
open-weights, you can fine-tune any part of it for your domain.

The knowledge base in this demo is scientific papers, standing in for whatever *your* private data
source is — an internal database, docs, or search engine.

## Architecture

Everything runs in **one Google Cloud Run GPU service** (NVIDIA L4, scale-to-zero):

| Stage | Component |
|---|---|
| Voice in + understanding | **Gemma 4 E4B** — native audio input: transcription + intent in one call |
| Agent loop / tool use | Same Gemma instance, orchestrated with **ADK** |
| Knowledge lookup | OpenAlex paper search (stand-in for your in-infra data source) |
| Voice out | **Kokoro** (82M, CPU) |
| Frontend | Minimal mobile web page — press-and-hold to talk |

## Status

Early days — building in the open, step by step:

- [x] Step 1: verify a GPU container runs on Cloud Run — see [`hello-gpu/`](hello-gpu/)
- [ ] Gemma 4 E4B text-only Q&A endpoint
- [ ] Native audio input (voice note → answer)
- [ ] Paper-lookup tool wired in via ADK
- [ ] Kokoro voice out
- [ ] Web frontend

## Why self-host?

Frontier hosted models are more capable in general — but a customer-service bot doesn't need a
frontier model. It needs to understand speech (a largely-solved task where open models are
competitive), follow instructions over your data, and keep that data private. Self-hosting gives
you total control: no data leaves your infra, no per-token vendor bill, and a model you can
fine-tune.
