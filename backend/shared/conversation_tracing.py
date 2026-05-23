"""OpenTelemetry spans for AI conversation turns (CCS ↔ ICS ↔ agents)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from shared.telemetry import _sdk_disabled, _traces_exporter_enabled


def traces_enabled() -> bool:
    return not _sdk_disabled() and _traces_exporter_enabled()


def _tracer():
    from opentelemetry import trace

    return trace.get_tracer("forge.conversation", "1.0.0")


def _truncate(text: str, max_chars: int = 512) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"... [{len(text)} chars]"


def _preview_payload(payload: dict[str, Any]) -> str:
    from shared.payload_preview import preview_ws_payload

    return preview_ws_payload(payload)


def attach_conversation_baggage(conversation_id: str):
    """Attach ``conversation.id`` to context for downstream HTTP (ICS) spans."""
    if not traces_enabled():
        from opentelemetry import context

        return context.attach(context.Context())

    from opentelemetry import context
    from opentelemetry.baggage import set_baggage

    return context.attach(set_baggage("conversation.id", conversation_id))


def detach_context(token) -> None:
    from opentelemetry import context

    context.detach(token)


def enrich_current_span_from_baggage() -> None:
    """Copy baggage ``conversation.id`` onto the active span (e.g. ICS /classify)."""
    if not traces_enabled():
        return
    from opentelemetry import baggage, trace

    span = trace.get_current_span()
    if not span.is_recording():
        return
    conv_id = baggage.get_baggage("conversation.id")
    if conv_id:
        span.set_attribute("conversation.id", str(conv_id))


def record_ws_event(direction: str, payload: dict[str, Any]) -> None:
    """Add a span event for WS traffic when a conversation span is active."""
    if not traces_enabled():
        return
    from opentelemetry import trace

    span = trace.get_current_span()
    if not span.is_recording():
        return
    span.add_event(
        f"conversation.ws.{direction}",
        attributes={
            "forge.message.type": str(payload.get("type", "")),
            "forge.payload.preview": _preview_payload(payload),
        },
    )


@contextmanager
def conversation_session_span(
    *,
    conversation_id: str,
    page_context: str,
) -> Iterator[None]:
    """Span for WebSocket session after ``init`` (baggage + session metadata)."""
    if not traces_enabled():
        yield
        return

    from opentelemetry import trace
    from opentelemetry.trace import SpanKind

    with _tracer().start_as_current_span(
        "conversation.session",
        kind=SpanKind.INTERNAL,
        attributes={
            "conversation.id": conversation_id,
            "forge.page.context": page_context,
        },
    ):
        yield


@contextmanager
def conversation_turn(
    *,
    conversation_id: str,
    page_context: str,
    user_message: str,
) -> Iterator[ConversationTurn]:
    """Root span for one ``user_message`` through classify, agent, and replies."""
    if not traces_enabled():
        yield ConversationTurn(None)
        return

    from opentelemetry import trace
    from opentelemetry.trace import SpanKind, Status, StatusCode

    tracer = _tracer()
    with tracer.start_as_current_span(
        "conversation.turn",
        kind=SpanKind.INTERNAL,
        attributes={
            "conversation.id": conversation_id,
            "forge.page.context": page_context,
            "forge.user.message.preview": _truncate(user_message),
            "forge.message.type": "user_message",
        },
    ) as span:
        turn = ConversationTurn(span)
        try:
            yield turn
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        else:
            if span.is_recording():
                span.set_status(Status(StatusCode.OK))


class ConversationTurn:
    """Helpers to record classify, agent, and outbound WS steps on a turn span."""

    def __init__(self, span: Any) -> None:
        self._span = span

    @property
    def active(self) -> bool:
        return self._span is not None and self._span.is_recording()

    @contextmanager
    def child(self, name: str, **attributes: str) -> Iterator[Any]:
        if not self.active:
            yield None
            return

        from opentelemetry.trace import SpanKind

        with _tracer().start_as_current_span(
            name,
            kind=SpanKind.INTERNAL,
            attributes=attributes,
        ) as child:
            yield child

    def record_inbound(self, payload: dict[str, Any]) -> None:
        record_ws_event("inbound", payload)
        if self.active:
            self._span.set_attribute(
                "forge.payload.preview.inbound",
                _preview_payload(payload),
            )

    def record_classification(self, result: dict[str, Any] | None) -> None:
        if not self.active or not result:
            return
        primary = result.get("primary_intent")
        if primary:
            self._span.set_attribute("forge.intent.primary", str(primary))
        intents = result.get("intents")
        if isinstance(intents, list):
            self._span.set_attribute("forge.intent.count", len(intents))
        self._span.add_event(
            "conversation.classify.result",
            attributes={
                "forge.intent.primary": str(primary or ""),
                "forge.payload.preview": _truncate(json.dumps(result, default=str)),
            },
        )

    def record_agent(self, agent_id: str) -> None:
        if self.active:
            self._span.set_attribute("forge.agent.id", agent_id)

    def record_agent_reply(self, reply: str) -> None:
        if not self.active:
            return
        self._span.set_attribute(
            "forge.agent.reply.preview",
            _truncate(reply, 1024),
        )
        self._span.add_event(
            "conversation.agent.reply",
            attributes={"forge.agent.reply.preview": _truncate(reply, 512)},
        )

    def record_outbound(self, payload: dict[str, Any]) -> None:
        record_ws_event("outbound", payload)
        if self.active:
            msg_type = str(payload.get("type", ""))
            self._span.set_attribute("forge.message.type.last_outbound", msg_type)
