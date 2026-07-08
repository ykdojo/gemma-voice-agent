"""The agent brain, behind one narrow interface so the model is swappable.

Current implementation: an ADK agent running Gemini via Vertex AI (interim, hosted; no GPU
quota needed). Target: the same ADK agent pointed at Gemma 4 self-hosted on this Cloud Run
service with an L4 GPU.

ADK sessions carry the conversation history: each browser session maps to an ADK session, the
Runner assembles prior turns (including past tool calls and results) into context, and new
events are appended automatically. Long-term memory is deliberately not used.
"""
import asyncio
import os
import time

from google import genai
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import tools

MODEL_ID = os.environ.get("MODEL_ID", "gemini-3-flash-preview")
# Transcription is a narrow ASR task: a cheaper model on a separate quota pool, so the
# display-only transcription call never competes with the agent call for rate limit.
TRANSCRIBE_MODEL = os.environ.get("TRANSCRIBE_MODEL", "gemini-2.5-flash")
APP_NAME = "paper-voice-agent"

SYSTEM_PROMPT = (
    "You are a friendly customer-service agent for a scientific-paper knowledge base. "
    "Users ask questions by voice or text. Use the search_papers and get_paper tools to ground "
    "your answers in actual papers, and cite them as (Author, Year). Match the level of detail "
    "to the question. If the user's audio is unclear, ask them to repeat."
)

_agent = Agent(
    name="paper_agent",
    model=MODEL_ID,
    instruction=SYSTEM_PROMPT,
    tools=[tools.search_papers, tools.get_paper],
)
_sessions = InMemorySessionService()
_runner = Runner(agent=_agent, app_name=APP_NAME, session_service=_sessions)
_genai_client = None


def transcribe(audio: bytes, audio_mime: str = "audio/webm") -> str:
    """Speech to text with the same model's native audio input. Shown in the UI, and the
    transcription (not the raw audio) is what enters the conversation history."""
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        )
    last_error = None
    for attempt in range(2):
        try:
            response = _genai_client.models.generate_content(
                model=TRANSCRIBE_MODEL,
                contents=[
                    types.Part.from_bytes(data=audio, mime_type=audio_mime),
                    types.Part.from_text(
                        text="Transcribe this audio verbatim. Reply with only the transcription, no quotes."
                    ),
                ],
                config=types.GenerateContentConfig(temperature=0),
            )
            return (response.text or "").strip()
        except Exception as e:  # noqa: BLE001 - retry once (e.g. transient 429), then give up
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    raise last_error


def _ensure_session(user_id: str, session_id: str) -> None:
    async def go():
        existing = await _sessions.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
        if existing is None:
            await _sessions.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )

    asyncio.run(go())


def reply_stream(
    text: str | None = None,
    audio: bytes | None = None,
    audio_mime: str = "audio/webm",
    session_id: str = "default",
):
    """Streaming turn: yields dicts. type=status (tool running), delta (text chunk),
    done (authoritative full text). Falls back to one done event if streaming is unavailable."""
    parts = []
    if audio:
        parts.append(types.Part.from_bytes(data=audio, mime_type=audio_mime))
    if text:
        parts.append(types.Part.from_text(text=text))
    if not parts:
        raise ValueError("need text or audio")

    user_id = session_id
    _ensure_session(user_id, session_id)

    try:
        from google.adk.agents.run_config import RunConfig, StreamingMode

        run_config = RunConfig(streaming_mode=StreamingMode.SSE)
    except Exception:  # noqa: BLE001
        run_config = None

    final = None
    events = _runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=parts),
        **({"run_config": run_config} if run_config else {}),
    )
    for event in events:
        try:
            if event.get_function_calls():
                yield {"type": "status", "status": "Searching papers"}
        except Exception:  # noqa: BLE001
            pass
        if event.content and event.content.parts:
            chunk = "".join(p.text or "" for p in event.content.parts if p.text)
            if not chunk:
                continue
            if getattr(event, "partial", False):
                yield {"type": "delta", "text": chunk}
            elif event.is_final_response():
                final = chunk
    yield {"type": "done", "text": final or "Sorry, I could not come up with an answer."}


def reply(
    text: str | None = None,
    audio: bytes | None = None,
    audio_mime: str = "audio/webm",
    session_id: str = "default",
) -> str:
    """One turn: text or audio in, assistant text out. Tool calls run automatically, and the
    session's earlier turns are included as context."""
    parts = []
    if audio:
        parts.append(types.Part.from_bytes(data=audio, mime_type=audio_mime))
    if text:
        parts.append(types.Part.from_text(text=text))
    if not parts:
        raise ValueError("need text or audio")

    user_id = session_id  # one user per browser session; no cross-session identity yet
    _ensure_session(user_id, session_id)

    final = None
    for event in _runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=parts),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final = "".join(p.text or "" for p in event.content.parts if p.text)
    return final or "Sorry, I could not come up with an answer."
