"""Eval shim: exposes the app's Agent as root_agent, per ADK eval convention.

The eval framework builds its own in-process Runner around this agent, so the
model substrate follows the same env vars as the app (MODEL_API_BASE set =
self-hosted Gemma; unset = hosted Gemini).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))

from model import _agent as root_agent  # noqa: E402,F401
