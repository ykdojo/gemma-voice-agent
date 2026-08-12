"""The agent brain, behind one narrow interface so the model is swappable.

The same ADK agent runs either brain: self-hosted Gemma 4 on our Cloud Run GPU
(MODEL_API_BASE set, via LiteLlm against vLLM's OpenAI-compatible API) or hosted
Gemini through the Cloud account (MODEL_API_BASE unset). Input is always text;
voice notes are transcribed by the speech service before they get here.

ADK sessions carry the conversation history: each browser session maps to an ADK session, the
Runner assembles prior turns (including past tool calls and results) into context, and new
events are appended automatically. Long-term memory is deliberately not used.
"""
import asyncio
import os
import subprocess
import threading

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import tools

MODEL_ID = os.environ.get("MODEL_ID", "gemini-3-flash-preview")
# When set, the brain is a self-hosted OpenAI-compatible endpoint (vLLM serving
# Gemma on our Cloud Run GPU) reached through ADK's LiteLlm wrapper. Unset =
# hosted Gemini via the Cloud account (interim).
MODEL_API_BASE = os.environ.get("MODEL_API_BASE", "").rstrip("/")
APP_NAME = "paper-voice-agent"


def _self_hosted_model():
    from google.adk.models.lite_llm import LiteLlm
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    api_base = MODEL_API_BASE if MODEL_API_BASE.endswith("/v1") else MODEL_API_BASE + "/v1"
    # The model service is private; authenticate with an identity token. Fetched once
    # per process: instances recycle well within the token's 1h lifetime at this
    # app's scale-to-zero usage pattern.
    try:
        token = id_token.fetch_id_token(Request(), MODEL_API_BASE)
    except Exception:  # noqa: BLE001 - local dev: user creds can't mint ID tokens
        token = subprocess.check_output(
            "gcloud auth print-identity-token -q", shell=True
        ).decode().strip()
    return LiteLlm(
        model=f"openai/{MODEL_ID}",
        base_url=api_base,
        api_key=token,
        # Gemma 4 on vLLM wants these for thinking + clean output.
        extra_body={
            "chat_template_kwargs": {"enable_thinking": True},
            "skip_special_tokens": False,
        },
    )

SYSTEM_PROMPT = (
    "You are a friendly customer-service agent for a scientific-paper knowledge base. "
    "Users ask questions by voice or text. Use the search_papers and get_paper tools to ground "
    "your answers in actual papers, and cite them as (Author, Year). Keep your replies concise. "
    "If the user's audio is unclear, ask them to repeat."
)

_agent = Agent(
    name="paper_agent",
    model=_self_hosted_model() if MODEL_API_BASE else MODEL_ID,
    instruction=SYSTEM_PROMPT,
    tools=[tools.search_papers, tools.get_paper],
)
_sessions = InMemorySessionService()
_runner = Runner(agent=_agent, app_name=APP_NAME, session_service=_sessions)


# One long-lived event loop on a daemon thread for the session-service coroutines,
# instead of building and tearing down a fresh loop on every request.
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


def _ensure_session(user_id: str, session_id: str) -> None:
    async def go():
        existing = await _sessions.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing is None:
            await _sessions.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )

    asyncio.run_coroutine_threadsafe(go(), _loop).result()


def reply_stream(text: str, session_id: str = "default"):
    """Streaming turn: text in (voice notes arrive here already transcribed), yields dicts.
    type=status (tool running), delta (text chunk), done (authoritative full text).
    Falls back to one done event if streaming is unavailable."""
    if not text or not text.strip():
        raise ValueError("need text")
    parts = [types.Part.from_text(text=text)]

    user_id = session_id
    _ensure_session(user_id, session_id)

    try:
        from google.adk.agents.run_config import RunConfig, StreamingMode

        run_config = RunConfig(streaming_mode=StreamingMode.SSE)
    except Exception:  # noqa: BLE001
        run_config = None

    final = None
    streamed = ""  # deltas since the last tool call; fallback if no flagged final event arrives
    events = _runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=parts),
        **({"run_config": run_config} if run_config else {}),
    )
    for event in events:
        try:
            if event.get_function_calls():
                streamed = ""
                yield {"type": "status", "status": "Searching papers"}
        except Exception:  # noqa: BLE001
            pass
        if event.content and event.content.parts:
            chunk = "".join(p.text or "" for p in event.content.parts if p.text)
            if not chunk:
                continue
            if getattr(event, "partial", False):
                streamed += chunk
                yield {"type": "delta", "text": chunk}
            elif event.is_final_response():
                final = chunk
    yield {"type": "done", "text": final or streamed or "Sorry, I could not come up with an answer."}
