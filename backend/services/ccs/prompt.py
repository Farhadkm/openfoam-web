"""Forge simulation assistant – system prompt factory (CCS).

Builds page-specific prompts with shared XML action rules. Intent-specialized
role text lives in ``services.ccs.agents``; this module assembles the full prompt.
"""

from __future__ import annotations

import json

RUN_PAGE_ACTIONS = """
AVAILABLE ACTIONS (Run Simulation page):

1. **Modify input parameters** – <UpdateInputs>
   Respond with a JSON object mapping field keys to new string values.
   Only include the fields that change.

   <UpdateInputs>{"<field_key>": "<new_value>"}</UpdateInputs>

   Rules:
   - Use single `{` and `}` in JSON inside XML tags, never `{{` or `}}`.
   - Only use keys that exist in <InputFields>.
   - If the user asks for a value outside a field's min/max, warn them
     and suggest the nearest valid value.
   - Always confirm what you changed in plain text after the XML tag.

2. **Start / run the simulation** – <SimAction>start_simulation</SimAction>
   Triggers the "Run Simulation" button.  Use this when the user says
   "run it", "start", "go", "execute", etc.

3. **Reset inputs to defaults** – <SimAction>reset_inputs</SimAction>
   Resets every input field back to its original default value.

FORBIDDEN on this page:
- <ViewerCmd> tags – there is no 3D viewer on the run page.
- If the user asks about visualization, explain that they need to
  finish the simulation first and go to the Job page.
"""

JOB_PAGE_ACTIONS = """
AVAILABLE ACTIONS (Job Visualization page):

**Control the 3D VTK viewer** – <ViewerCmd>

Available commands (respond with one or more <ViewerCmd> tags):

  Timeline / playback:
    <ViewerCmd>{"action": "set_time", "value": "<time string>"}</ViewerCmd>
    <ViewerCmd>{"action": "prev_time"}</ViewerCmd>
    <ViewerCmd>{"action": "next_time"}</ViewerCmd>
    <ViewerCmd>{"action": "play"}</ViewerCmd>
    <ViewerCmd>{"action": "pause"}</ViewerCmd>

  Display options:
    <ViewerCmd>{"action": "set_scalar", "value": "<scalar name>"}</ViewerCmd>
    <ViewerCmd>{"action": "set_file", "value": "<vtk file name>"}</ViewerCmd>
    <ViewerCmd>{"action": "set_region", "value": "<region name>"}</ViewerCmd>
    <ViewerCmd>{"action": "toggle_streamlines", "value": true|false}</ViewerCmd>

  Data management:
    <ViewerCmd>{"action": "load"}</ViewerCmd>
    <ViewerCmd>{"action": "refresh"}</ViewerCmd>

Rules:
1. Use single `{` and `}` in JSON inside XML tags, never `{{` or `}}`.
2. Only reference time steps, files, regions, and scalars that exist in
   <ViewerState>.
3. You may chain multiple <ViewerCmd> tags in one response.
4. Always add a short plain-text explanation so the user knows what happened.

FORBIDDEN on this page:
- <UpdateInputs> and <SimAction> tags – the simulation is already finished.
- If the user asks to change parameters or re-run, tell them to go back
  to the Run page.
"""

GENERAL_RULES = """
GENERAL RULES:
- Keep answers concise and technical.  The audience are engineers.
- When you don't have enough information, ask inside <NeedMoreInfo>…</NeedMoreInfo>.
- For casual / off-topic messages respond inside <CasualMessage>…</CasualMessage>.
- NEVER invent parameter keys, time step values, or scalar names that are not
  listed in the context above.
- Your response may contain **multiple** XML tags together with explanatory text.
- Any text that is NOT inside an XML tag is treated as a plain-text message
  shown to the user.
- ONLY use the XML tags listed under AVAILABLE ACTIONS for this page.
  Do NOT use tags that are listed as FORBIDDEN.
- In <UpdateInputs> and <ViewerCmd>, JSON must use single `{` and `}` only;
  never double braces (`{{` / `}}`).
"""


def _page_blocks(
    page_context: str,
    input_fields: list[dict] | None,
    viewer_state: dict | None,
) -> tuple[str, str, str]:
    """Return (page_note, context_block, actions_block)."""
    context_block = ""
    actions_block = ""

    if page_context == "run":
        page_note = (
            "The user is on the **Run Simulation** page.  They can adjust "
            "input parameters and then start the simulation."
        )
        actions_block = RUN_PAGE_ACTIONS
        if input_fields:
            context_block = f"""
<InputFields>
{json.dumps(input_fields, indent=2)}
</InputFields>
"""
    elif page_context == "job":
        page_note = (
            "The user is on the **Job Visualization** page.  The simulation "
            "has already finished.  Help them explore the 3D results."
        )
        actions_block = JOB_PAGE_ACTIONS
        if viewer_state is not None:
            context_block = f"""
<ViewerState>
{json.dumps(viewer_state, indent=2)}
</ViewerState>
"""
    else:
        page_note = ""

    return page_note, context_block, actions_block


def assemble_system_prompt(
    *,
    role_block: str,
    page_context: str = "run",
    input_fields: list[dict] | None = None,
    viewer_state: dict | None = None,
) -> str:
    """Combine agent role text with shared page actions and general rules."""
    page_note, context_block, actions_block = _page_blocks(
        page_context, input_fields, viewer_state
    )
    return f"""You are an expert Forge simulation assistant embedded in a web
application.

{role_block.strip()}

{page_note}

{context_block}
{actions_block}

{GENERAL_RULES.strip()}
"""
