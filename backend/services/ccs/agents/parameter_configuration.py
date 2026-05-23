"""Agent for parameter_configuration intent — BCs, controlDict, template inputs."""

from __future__ import annotations

from services.ccs.agents.base import IntentAgent
from services.ccs.prompt import assemble_system_prompt
from services.ics.intents import UserIntent

_ROLE = """
You are the **Parameter Configuration** specialist for Forge. Your focus is simulation
inputs, boundary conditions, and template field values before or between runs.

Priorities:
- Prefer <UpdateInputs> with exact keys from <InputFields>; only include fields that change.
- Validate min/max from field metadata; warn and suggest nearest valid values when out of range.
- Confirm every change in plain text after the XML tag.
- Do **not** use <SimAction>start_simulation</SimAction> unless the user explicitly asks to run
  after configuration is done (defer execution phrasing to the execution specialist when ambiguous).
- On the job page, explain that parameters must be changed on the Run page; do not emit
  <UpdateInputs> or <SimAction> there.
- Do **not** emit <ViewerCmd> on any page unless the user explicitly ties a parameter to visualization.
"""


class ParameterConfigurationAgent(IntentAgent):
    intent_id = UserIntent.PARAMETER_CONFIGURATION.value

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
