"""Thin wrapper around the Anthropic SDK.

Two call shapes only:
  - extract(): structured output parsed into a Pydantic model (scope analysis,
    hours estimate, past-proposal extraction, draft sections)
  - draft_stream(): long-form prose, streamed, with server-side refusal
    fallbacks enabled

Model defaults to Claude Opus 5; override with FEEPROP_MODEL.
"""

from __future__ import annotations

import os
from typing import Type, TypeVar

import anthropic
from pydantic import BaseModel

DEFAULT_MODEL = "claude-opus-5"

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None


def model_id() -> str:
    return os.environ.get("FEEPROP_MODEL", DEFAULT_MODEL)


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def extract(system: str, prompt: str, output: Type[T], max_tokens: int = 16000) -> T:
    """One-shot structured extraction, validated against `output`."""
    response = client().messages.parse(
        model=model_id(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_format=output,
    )
    return response.parsed_output


def draft_stream(system: str, prompt: str, max_tokens: int = 32000) -> str:
    """Long-form drafting. Streams (long outputs) and enables server-side
    refusal fallbacks so a safety decline reroutes instead of failing."""
    with client().beta.messages.stream(
        model=model_id(),
        max_tokens=max_tokens,
        system=system,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        detail = ""
        if message.stop_details:
            detail = f" ({message.stop_details.explanation})"
        raise RuntimeError(f"Model declined to draft this content{detail}.")
    return "".join(b.text for b in message.content if b.type == "text")
