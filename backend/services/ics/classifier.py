"""Classify user messages into one or more simulation-related intents."""

from __future__ import annotations

import asyncio
import json
import re

from vertexai.preview.generative_models import GenerativeModel

from services.ics.intents import INTENT_DEFINITIONS, VALID_INTENT_IDS, UserIntent
from shared.vertex import MODEL_NAME, ensure_vertex


def _traces_on() -> bool:
    try:
        from shared.conversation_tracing import traces_enabled

        return traces_enabled()
    except ImportError:
        return False


def _conversation_tracer():
    from opentelemetry import trace

    return trace.get_tracer("forge.conversation", "1.0.0")

_KEYWORD_HINTS: dict[str, tuple[str, ...]] = {
    UserIntent.SIMULATION_EXECUTION.value: (
        "run",
        "start",
        "execute",
        "allrun",
        "blockmesh",
        "simplefoam",
        "solver",
        "simulate",
        "launch",
    ),
    UserIntent.PARAMETER_CONFIGURATION.value: (
        "parameter",
        "input",
        "boundary",
        "velocity",
        "pressure",
        "viscosity",
        "controlDict",
        "set",
        "change",
        "increase",
        "decrease",
        "adjust",
        "configure",
    ),
    UserIntent.RESULTS_ANALYSIS.value: (
        "result",
        "vtk",
        "visual",
        "viewer",
        "scalar",
        "time step",
        "timestep",
        "streamline",
        "plot",
        "field",
        "analyze",
        "analysis",
        "show me",
        "display",
    ),
}


def _normalize_scores(raw: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in raw:
        intent_id = str(item.get("intent", "")).strip()
        if intent_id not in VALID_INTENT_IDS:
            continue
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        definition = next(d for d in INTENT_DEFINITIONS if d["intent"] == intent_id)
        out.append(
            {
                "intent": intent_id,
                "label": definition["label"],
                "confidence": confidence,
                "rationale": str(item.get("rationale", "")).strip(),
            }
        )
    out.sort(key=lambda x: x["confidence"], reverse=True)
    return out


def _keyword_classify(message: str, page_context: str) -> list[dict]:
    text = message.lower()
    scores: dict[str, float] = {d["intent"]: 0.05 for d in INTENT_DEFINITIONS}

    for intent_id, keywords in _KEYWORD_HINTS.items():
        for kw in keywords:
            if kw in text:
                scores[intent_id] = min(1.0, scores[intent_id] + 0.35)

    if page_context == "run":
        scores[UserIntent.SIMULATION_EXECUTION.value] += 0.1
        scores[UserIntent.PARAMETER_CONFIGURATION.value] += 0.1
    elif page_context == "job":
        scores[UserIntent.RESULTS_ANALYSIS.value] += 0.2

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = ranked[0][1]
    if top < 0.2:
        ranked = [
            (UserIntent.PARAMETER_CONFIGURATION.value, 0.34),
            (UserIntent.SIMULATION_EXECUTION.value, 0.33),
            (UserIntent.RESULTS_ANALYSIS.value, 0.33),
        ]

    return _normalize_scores(
        [
            {
                "intent": intent_id,
                "confidence": score,
                "rationale": "Keyword and page-context heuristic.",
            }
            for intent_id, score in ranked
        ]
    )


def _build_classifier_prompt(message: str, page_context: str) -> str:
    catalog = json.dumps(INTENT_DEFINITIONS, indent=2)
    return f"""You are the Intent Classification Service for an Forge web app.

Classify the user message into these intents (use exact intent ids):
{catalog}

Page context: {page_context!r} ("run" = setup/run page, "job" = results viewer page).

User message:
{message}

Respond with ONLY a JSON array (no markdown). Each element:
{{"intent": "<id>", "confidence": <0-1>, "rationale": "<short reason>"}}

Include all three intents with confidence scores that sum to roughly 1.
Order from highest to lowest confidence.
"""


def _llm_classify_sync(message: str, page_context: str) -> list[dict]:
    ensure_vertex()
    model = GenerativeModel(MODEL_NAME)
    resp = model.generate_content(_build_classifier_prompt(message, page_context))
    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty classification.")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Expected JSON array from classifier.")
    return _normalize_scores(data)


async def classify_message(message: str, page_context: str = "run") -> dict:
    message = (message or "").strip()
    if not message:
        return {
            "message": "",
            "page_context": page_context,
            "intents": [],
            "primary_intent": None,
        }

    try:
        from opentelemetry import context

        otel_ctx = context.get_current()

        def _classify_in_context() -> list[dict]:
            token = context.attach(otel_ctx)
            try:
                if _traces_on():
                    from opentelemetry.trace import SpanKind

                    tracer = _conversation_tracer()
                    with tracer.start_as_current_span(
                        "conversation.classify.model",
                        kind=SpanKind.INTERNAL,
                    ):
                        return _llm_classify_sync(message, page_context)
                return _llm_classify_sync(message, page_context)
            finally:
                context.detach(token)

        intents = await asyncio.get_event_loop().run_in_executor(
            None, _classify_in_context
        )
    except Exception:
        intents = _keyword_classify(message, page_context)

    primary = intents[0]["intent"] if intents else None
    return {
        "message": message,
        "page_context": page_context,
        "intents": intents,
        "primary_intent": primary,
    }
