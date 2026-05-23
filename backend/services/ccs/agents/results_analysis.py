"""Agent for results_analysis intent — VTK viewer, timesteps, field interpretation."""

from __future__ import annotations

from services.ccs.agents.base import IntentAgent
from services.ccs.prompt import assemble_system_prompt
from services.ics.intents import UserIntent

_ROLE = """
You are the **Results Analysis** specialist for Forge. Your focus is finished CFD output:
VTK visualization, time steps, scalars, regions, streamlines, and interpreting fields.

Priorities:
- On the job page, use <ViewerCmd> with values that exist in <ViewerState> only.
- Chain multiple <ViewerCmd> tags when needed; always add a short plain-text explanation.
- Help users understand physical meaning of fields (pressure, velocity, etc.) from context.
- Do **not** use <SimAction> or start solvers unless the user explicitly asks to re-run.
- On the run page, explain they must finish the simulation and open the Job page to visualize;
  do not emit <ViewerCmd> there.
- Do **not** change input parameters with <UpdateInputs> unless they explicitly want to re-configure
  before a new run (suggest the configuration specialist instead).
"""


class ResultsAnalysisAgent(IntentAgent):
    intent_id = UserIntent.RESULTS_ANALYSIS.value

    @classmethod
    def build_system_prompt(
        cls,
        *,
        page_context: str,
        input_fields: list[dict] | None = None,
        viewer_state: dict | None = None,
    ) -> str:
        return assemble_system_prompt(
            role_block=_ROLE,
            page_context=page_context,
            input_fields=input_fields,
            viewer_state=viewer_state,
        )
