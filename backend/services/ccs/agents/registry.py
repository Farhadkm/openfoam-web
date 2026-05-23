"""Intent → agent registry and system-prompt factory (no prompt.py import cycle)."""

from __future__ import annotations

from services.ccs.agents.parameter_configuration import ParameterConfigurationAgent
from services.ccs.agents.results_analysis import ResultsAnalysisAgent
from services.ccs.agents.simulation_execution import SimulationExecutionAgent
from services.ics.intents import INTENT_DEFINITIONS, VALID_INTENT_IDS

AGENTS_BY_INTENT = {
    SimulationExecutionAgent.intent_id: SimulationExecutionAgent,
    ParameterConfigurationAgent.intent_id: ParameterConfigurationAgent,
    ResultsAnalysisAgent.intent_id: ResultsAnalysisAgent,
}

INTENT_AGENT_IDS = frozenset(VALID_INTENT_IDS)

_INTENT_LABELS = {d["intent"]: d["label"] for d in INTENT_DEFINITIONS}

DEFAULT_INTENT_BY_PAGE: dict[str, str] = {
    "run": ParameterConfigurationAgent.intent_id,
    "job": ResultsAnalysisAgent.intent_id,
}


def intent_label(intent_id: str) -> str:
    return _INTENT_LABELS.get(intent_id, intent_id.replace("_", " ").title())


def resolve_intent(primary_intent: str | None, *, page_context: str) -> str:
    if primary_intent and primary_intent in AGENTS_BY_INTENT:
        return primary_intent
    return DEFAULT_INTENT_BY_PAGE.get(page_context, ParameterConfigurationAgent.intent_id)


def create_system_prompt(
    *,
    input_fields: list[dict] | None = None,
    viewer_state: dict | None = None,
    page_context: str = "run",
    intent: str | None = None,
) -> str:
    intent_id = resolve_intent(intent, page_context=page_context)
    agent_cls = AGENTS_BY_INTENT[intent_id]
    return agent_cls.build_system_prompt(
        page_context=page_context,
        input_fields=input_fields,
        viewer_state=viewer_state,
    )
