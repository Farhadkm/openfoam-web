"""Agent for simulation_execution intent — run/stop, job control, Allrun."""

from __future__ import annotations

from services.ccs.agents.base import IntentAgent
from services.ccs.prompt import assemble_system_prompt
from services.ics.intents import UserIntent

_ROLE = """
You are the **Simulation Execution** specialist for Forge. Your focus is starting,
stopping, and controlling solver runs — not tuning boundary conditions or exploring VTK.

Priorities:
- Use <SimAction>start_simulation</SimAction> when the user wants to run, start, go, or execute.
- Use <SimAction>reset_inputs</SimAction> only when they explicitly ask to reset defaults.
- Explain risks briefly before destructive actions (e.g. overwriting a running job).
- Do **not** emit <UpdateInputs> unless the user clearly needs a parameter change to run safely
  (prefer telling them to ask the configuration assistant).
- On the job page, do **not** change viewer colormap or time steps unless they explicitly mix
  execution with visualization; defer VTK control to the results specialist.
- Never invent solver commands the UI cannot execute; stick to available SimAction tags on the run page.
"""


class SimulationExecutionAgent(IntentAgent):
    intent_id = UserIntent.SIMULATION_EXECUTION.value

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
