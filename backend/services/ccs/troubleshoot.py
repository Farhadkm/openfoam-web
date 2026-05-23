"""One-shot Gemini troubleshooting for job logs."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import BaseModel, Field
from vertexai.preview.generative_models import GenerativeModel

from services.ccs.agents.troubleshooting import TroubleshootingAgent
from shared.vertex import MODEL_NAME, ensure_vertex

_MAX_LOG_CHARS = 80_000


class TroubleshootJobMeta(BaseModel):
    status: str = ""
    returncode: int | None = None
    error_message: str | None = None
    commands: str = ""


class TroubleshootSimulation(BaseModel):
    title: str = ""
    commands: str = ""
    input_fields: list[dict[str, Any]] = Field(default_factory=list)
    result_fields: list[dict[str, Any]] = Field(default_factory=list)


class TroubleshootRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    log: str = ""
    job: TroubleshootJobMeta = Field(default_factory=TroubleshootJobMeta)
    simulation: TroubleshootSimulation | None = None
    inputs_applied: dict[str, str] | None = None
    fatal_hints: list[str] = Field(default_factory=list)


class TroubleshootResponse(BaseModel):
    guide: str
    job_id: str


def format_troubleshoot_user_message(req: TroubleshootRequest) -> str:
    log_text = req.log
    if len(log_text) > _MAX_LOG_CHARS:
        log_text = log_text[-_MAX_LOG_CHARS:]
        log_text = f"(truncated to last {_MAX_LOG_CHARS} characters)\n{log_text}"

    blocks: list[str] = [
        f"<JobId>{req.job_id}</JobId>",
        "<JobMetadata>",
        json.dumps(req.job.model_dump(), indent=2),
        "</JobMetadata>",
    ]
    if req.simulation is not None:
        blocks.extend(
            [
                "<SimulationTemplate>",
                json.dumps(req.simulation.model_dump(), indent=2),
                "</SimulationTemplate>",
            ]
        )
    if req.inputs_applied:
        blocks.extend(
            [
                "<InputsApplied>",
                json.dumps(req.inputs_applied, indent=2),
                "</InputsApplied>",
            ]
        )
    if req.fatal_hints:
        blocks.append("<FatalLogHints>")
        blocks.extend(req.fatal_hints)
        blocks.append("</FatalLogHints>")
    blocks.extend(
        [
            "<FullJobLog>",
            log_text or "(empty)",
            "</FullJobLog>",
            (
                "<UserRequest>Analyze this simulation run and provide troubleshooting "
                "guidance using the Cause / Fix steps / Prevention structure.</UserRequest>"
            ),
        ]
    )
    return "\n".join(blocks)


def _generate_sync(user_message: str) -> str:
    ensure_vertex()
    model = GenerativeModel(MODEL_NAME)
    system_prompt = TroubleshootingAgent.build_system_prompt()
    resp = model.generate_content([system_prompt, user_message])
    text = getattr(resp, "text", None)
    if not text:
        raise RuntimeError("Gemini returned an empty response.")
    return text.strip()


async def run_troubleshoot(req: TroubleshootRequest) -> TroubleshootResponse:
    user_message = format_troubleshoot_user_message(req)
    guide = await asyncio.get_event_loop().run_in_executor(
        None, _generate_sync, user_message
    )
    return TroubleshootResponse(guide=guide, job_id=req.job_id)
