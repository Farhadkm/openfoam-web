"""Run one chat turn through ICS + CCS (same path as production WebSocket handler)."""

from __future__ import annotations

from dataclasses import dataclass

from services.ccs.agents.registry import resolve_intent
from services.ccs.session import ChatSession
from services.ics.classifier import classify_message
from tests.eval.forge_xml import ParsedAssistantMessage, parse_assistant_xml


@dataclass
class ChatTurnResult:
    user_message: str
    page_context: str
    primary_intent: str | None
    resolved_intent: str
    reply: str
    parsed: ParsedAssistantMessage
    classification: dict | None


async def run_chat_turn(
    *,
    user_message: str,
    page_context: str,
    input_fields: list[dict] | None = None,
    viewer_state: dict | None = None,
    classify: bool = True,
) -> ChatTurnResult:
    """Classify (optional) then route to the specialist Gemini session."""
    classification: dict | None = None
    primary: str | None = None

    if classify:
        classification = await classify_message(user_message, page_context)
        primary = classification.get("primary_intent")

    resolved = resolve_intent(primary, page_context=page_context)
    session = ChatSession(
        intent=resolved,
        page_context=page_context,
        input_fields=input_fields,
        viewer_state=viewer_state,
    )
    reply = await session.send(user_message)
    parsed = parse_assistant_xml(reply)

    return ChatTurnResult(
        user_message=user_message,
        page_context=page_context,
        primary_intent=primary,
        resolved_intent=resolved,
        reply=reply,
        parsed=parsed,
        classification=classification,
    )
