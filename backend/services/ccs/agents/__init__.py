"""Intent-specialized CCS agents (one system prompt per ICS intent)."""

from services.ccs.agents.registry import (
    AGENTS_BY_INTENT,
    DEFAULT_INTENT_BY_PAGE,
    INTENT_AGENT_IDS,
    create_system_prompt,
    intent_label,
    resolve_intent,
)

__all__ = [
    "AGENTS_BY_INTENT",
    "DEFAULT_INTENT_BY_PAGE",
    "INTENT_AGENT_IDS",
    "create_system_prompt",
    "intent_label",
    "resolve_intent",
]
