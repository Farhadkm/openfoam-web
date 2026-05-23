"""Shared agent interface for intent-specialized CCS prompts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

class IntentAgent(ABC):
    """Builds a Gemini system prompt specialized for one ICS intent."""

    intent_id: ClassVar[str]

    @classmethod
    @abstractmethod
    def build_system_prompt(
        cls,
        *,
        page_context: str,
        input_fields: list[dict] | None = None,
        viewer_state: dict | None = None,
    ) -> str:
        """Return the full system prompt for this agent."""
