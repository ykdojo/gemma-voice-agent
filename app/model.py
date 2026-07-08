"""The agent brain, behind one narrow interface so the model is swappable.

Current implementation: Gemini via Vertex AI (interim, hosted; no GPU quota needed).
Target implementation: Gemma 4 E4B self-hosted on this same Cloud Run service with an L4 GPU.
Both take text or raw audio in and return the assistant's text reply after tool use.
"""
import os

from google import genai
from google.genai import types

import tools

MODEL_ID = os.environ.get("MODEL_ID", "gemini-3-flash-preview")

SYSTEM_PROMPT = (
    "You are a friendly customer-service agent for a scientific-paper knowledge base. "
    "Users ask questions by voice or text. Use the search_papers and get_paper tools to ground "
    "your answers in actual papers, and cite them as (Author, Year). Match the level of detail "
    "to the question. If the user's audio is unclear, ask them to repeat."
)

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        )
    return _client


def reply(text: str | None = None, audio: bytes | None = None, audio_mime: str = "audio/webm") -> str:
    """One turn: text or audio in, assistant text out. Tool calls run automatically."""
    parts = []
    if audio:
        parts.append(types.Part.from_bytes(data=audio, mime_type=audio_mime))
    if text:
        parts.append(types.Part.from_text(text=text))
    if not parts:
        raise ValueError("need text or audio")

    response = _get_client().models.generate_content(
        model=MODEL_ID,
        contents=parts,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[tools.search_papers, tools.get_paper],  # automatic function calling
            temperature=0.7,
        ),
    )
    return response.text or "Sorry, I could not come up with an answer."
