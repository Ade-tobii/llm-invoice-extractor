"""The LLM layer, kept behind a one-method interface.

The graph only knows about `Extractor.extract(text, feedback)`. Swapping
Gemini for another provider, or for a scripted fake in tests, touches nothing else.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from invoice_extractor.models import Invoice

SYSTEM_PROMPT = """You extract data from supplier invoices.
Copy every number exactly as printed. Do not calculate, correct or round anything:
a separate program checks the arithmetic. Dates must be ISO 8601 (YYYY-MM-DD).
Use the ISO 4217 currency code."""

RETRY_PROMPT = """Your previous extraction failed these automated checks:
{errors}

Re-read the invoice and fix any value you misread. If the invoice itself
really prints these numbers, keep them as printed. Never change a number
just to make the totals balance."""


class Extractor(Protocol):
    def extract(self, text: str, feedback: Sequence[str] = ()) -> Invoice:
        """Return a structured invoice. `feedback` lists errors from the previous attempt."""
        ...


def build_messages(text: str, feedback: Sequence[str] = ()) -> list[tuple[str, str]]:
    messages = [("system", SYSTEM_PROMPT), ("human", f"Invoice text:\n\n{text}")]
    if feedback:
        errors = "\n".join(f"- {line}" for line in feedback)
        messages.append(("human", RETRY_PROMPT.format(errors=errors)))
    return messages


class GeminiExtractor:
    """Gemini via langchain-google-genai, using native structured output."""

    def __init__(self, model: str | None = None, temperature: float = 0.0):
        if not os.environ.get("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY is not set. Use --demo to run without a key.")
        from langchain_google_genai import ChatGoogleGenerativeAI  # imported lazily

        llm = ChatGoogleGenerativeAI(
            model=model or os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash",
            temperature=temperature,
        )
        self._llm = llm.with_structured_output(Invoice)

    def extract(self, text: str, feedback: Sequence[str] = ()) -> Invoice:
        return self._llm.invoke(build_messages(text, feedback))


class FakeExtractor:
    """Replays scripted responses, one per attempt. No network, fully deterministic.

    Used by the tests and by `--demo`. Each response is what a model *could* have
    returned, including realistic mistakes, so the retry path can be exercised.
    """

    def __init__(self, responses: Sequence[dict | Invoice]):
        if not responses:
            raise ValueError("FakeExtractor needs at least one response")
        self._responses = list(responses)
        self.calls: list[list[str]] = []  # feedback received on each call

    @classmethod
    def from_file(cls, path: str | Path) -> FakeExtractor:
        return cls(json.loads(Path(path).read_text(encoding="utf-8"))["attempts"])

    def extract(self, text: str, feedback: Sequence[str] = ()) -> Invoice:
        index = min(len(self.calls), len(self._responses) - 1)
        self.calls.append(list(feedback))
        return Invoice.model_validate(self._responses[index])
