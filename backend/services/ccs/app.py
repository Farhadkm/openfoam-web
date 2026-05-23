"""Chat Conversation Service (CCS) – conversations REST, WebSocket chat, thumbnails."""

from __future__ import annotations

from shared.request_logging import install_request_logging
from shared.telemetry import configure_telemetry, instrument_fastapi

configure_telemetry()

import asyncio
import logging
import json
import os
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from services.ccs.agents import AGENTS_BY_INTENT, intent_label, resolve_intent
from services.ccs.conversations import PageContext, conversation_store
from services.ccs.openapi import install_openapi
from services.ccs.session import ChatSession
from services.ccs.troubleshoot import (
    TroubleshootRequest,
    TroubleshootResponse,
    run_troubleshoot,
)
from services.ccs.ws_logging import log_ws_inbound, log_ws_outbound
from shared.payload_preview import preview_max_chars
from shared.conversation_tracing import (
    attach_conversation_baggage,
    conversation_session_span,
    conversation_turn,
    detach_context,
)
from shared.vertex import (
    IMAGE_MODEL,
    MODEL_NAME,
    PROJECT_ID,
    credentials_health,
    ensure_vertex,
)

load_dotenv()

ICS_URL = os.getenv("ICS_URL", "http://ics:8082").rstrip("/")

app = FastAPI(
    title="Chat Conversation Service",
    version="1.0.0",
    description=(
        "Owns AI chat conversations (REST + WebSocket), thumbnail generation, and "
        "Gemini sessions. Message history is stored in-memory only (see README)."
    ),
    openapi_tags=[
        {"name": "health", "description": "Service health and Vertex credentials"},
        {"name": "conversations", "description": "Conversation CRUD and message history"},
        {"name": "ai", "description": "Thumbnail generation and WebSocket streaming chat"},
    ],
)

install_request_logging(app)
instrument_fastapi(app)
install_openapi(app)

_logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health():
    cred = credentials_health()
    return {
        "service": "ccs",
        "status": "ok" if cred["ok"] else "degraded",
        "model": MODEL_NAME,
        "image_model": IMAGE_MODEL,
        "vertex_credentials": cred,
        "ics_url": ICS_URL,
        "storage": "in-memory (conversations lost on restart)",
    }


# ── Conversations REST ──────────────────────────────────────────────────────


class ConversationCreate(BaseModel):
    title: str = Field(default="", max_length=500)
    page_context: PageContext = "run"


class ConversationSummary(BaseModel):
    id: str
    title: str
    page_context: PageContext
    created_at: str
    updated_at: str
    message_count: int


class ConversationDetail(ConversationSummary):
    messages: list[dict]


def _to_summary(rec) -> ConversationSummary:
    return ConversationSummary(
        id=rec.id,
        title=rec.title,
        page_context=rec.page_context,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        message_count=len(rec.messages),
    )


@app.post("/api/conversations", response_model=ConversationSummary, tags=["conversations"])
async def create_conversation(body: ConversationCreate):
    rec = await conversation_store.create(title=body.title, page_context=body.page_context)
    _logger.info("conversation created id=%s page_context=%s", rec.id, body.page_context)
    return _to_summary(rec)


@app.get("/api/conversations", tags=["conversations"])
async def list_conversations():
    items = await conversation_store.list_all()
    return {"conversations": [_to_summary(r) for r in items]}


@app.get(
    "/api/conversations/{conversation_id}",
    response_model=ConversationDetail,
    tags=["conversations"],
)
async def get_conversation(conversation_id: str):
    rec = await conversation_store.get(conversation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    summary = _to_summary(rec)
    return ConversationDetail(
        **summary.model_dump(),
        messages=[
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in rec.messages
        ],
    )


@app.delete("/api/conversations/{conversation_id}", tags=["conversations"])
async def delete_conversation(conversation_id: str):
    if not await conversation_store.delete(conversation_id):
        raise HTTPException(status_code=404, detail="conversation not found")
    _logger.info("conversation deleted id=%s", conversation_id)
    return {"ok": True, "id": conversation_id}


@app.get("/api/conversations/{conversation_id}/messages", tags=["conversations"])
async def list_conversation_messages(conversation_id: str):
    rec = await conversation_store.get(conversation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "conversation_id": conversation_id,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in rec.messages
        ],
    }


# ── Thumbnails ──────────────────────────────────────────────────────────────


class ThumbnailRequest(BaseModel):
    title: str = ""
    description: str = ""
    prompt: str = ""


def _generate_image_sync(prompt: str) -> bytes:
    from google import genai
    from google.genai.types import GenerateContentConfig, Modality

    from shared.vertex import VERTEX_LOCATION

    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=VERTEX_LOCATION,
    )
    full_prompt = (
        "Generate a clean, professional thumbnail image for a simulation. "
        "The image should be visually appealing and suitable as a card thumbnail "
        "(landscape, ~16:9 ratio). "
        "Style: technical illustration, modern, dark theme friendly. "
        f"Details: {prompt}"
    )
    resp = client.models.generate_content(
        model=IMAGE_MODEL,
        contents=full_prompt,
        config=GenerateContentConfig(
            response_modalities=[Modality.IMAGE, Modality.TEXT],
        ),
    )
    for part in resp.candidates[0].content.parts:
        if hasattr(part, "inline_data") and part.inline_data:
            return part.inline_data.data
    raise RuntimeError("Gemini did not return an image.")


def _thumbnail_topic_from_request(req: ThumbnailRequest) -> str:
    explicit = (req.prompt or "").strip()
    if explicit:
        return explicit
    title = (req.title or "").strip()
    desc = (req.description or "").strip()
    if title and desc:
        return f"{title}. {desc}"
    if title:
        return title
    if desc:
        return desc
    return ""


@app.post("/api/ai/troubleshoot", response_model=TroubleshootResponse, tags=["ai"])
async def troubleshoot_job(body: TroubleshootRequest):
    """One-shot log analysis; not routed through ICS."""
    ensure_vertex()
    try:
        result = await run_troubleshoot(body)
        _logger.info("troubleshoot job_id=%s guide_len=%d", body.job_id, len(result.guide))
        return result
    except Exception as exc:
        _logger.exception("troubleshoot failed job_id=%s", body.job_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/generate-thumbnail", tags=["ai"])
async def generate_thumbnail(req: ThumbnailRequest):
    ensure_vertex()
    prompt = _thumbnail_topic_from_request(req)
    if not prompt:
        return Response(
            status_code=400,
            content=json.dumps({"error": "Provide a title or description for the thumbnail."}),
            media_type="application/json",
        )
    try:
        img_bytes = await asyncio.get_event_loop().run_in_executor(
            None, _generate_image_sync, prompt
        )
        return Response(content=img_bytes, media_type="image/png")
    except Exception as exc:
        return Response(
            status_code=500,
            content=json.dumps({"error": str(exc)}),
            media_type="application/json",
        )


async def _classify_intents(
    message: str,
    page_context: str,
    *,
    conversation_id: str | None = None,
) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{ICS_URL}/classify",
                json={"message": message, "page_context": page_context},
            )
            if r.status_code == 200:
                result = r.json()
                _logger.info(
                    "classify conversation_id=%s page_context=%s primary=%s",
                    conversation_id or "unassigned",
                    page_context,
                    result.get("primary_intent"),
                )
                return result
    except Exception:
        pass
    return None


async def _send_ws_json(
    websocket: WebSocket,
    payload: dict,
    *,
    conversation_id: str | None,
) -> None:
    log_ws_outbound(conversation_id, payload)
    await websocket.send_json(payload)


async def _process_user_message(
    websocket: WebSocket,
    *,
    payload: dict,
    conversation_id: str,
    page_context: PageContext,
    sessions_by_intent: dict[str, ChatSession],
) -> None:
    text = (payload.get("message") or "").strip()
    if not text:
        err = {"type": "error", "message": "Empty message."}
        await _send_ws_json(websocket, err, conversation_id=conversation_id)
        return

    with conversation_turn(
        conversation_id=conversation_id,
        page_context=page_context,
        user_message=text,
    ) as turn:
        turn.record_inbound(payload)
        await conversation_store.append_message(
            conversation_id, role="user", content=text
        )

        with turn.child("conversation.classify"):
            classification = await _classify_intents(
                text, page_context, conversation_id=conversation_id
            )
        turn.record_classification(classification)

        if classification:
            intent_payload = {"type": "intent_classification", **classification}
            await _send_ws_json(
                websocket, intent_payload, conversation_id=conversation_id
            )
            turn.record_outbound(intent_payload)

        primary = classification.get("primary_intent") if classification else None
        intent_used = resolve_intent(primary, page_context=page_context)
        session = sessions_by_intent[intent_used]
        turn.record_agent(intent_used)
        _logger.info(
            "routing message conversation_id=%s agent=%s primary=%s page=%s",
            conversation_id,
            intent_used,
            primary,
            page_context,
        )

        try:
            with turn.child("conversation.agent", **{"forge.agent.id": intent_used}):
                reply = await session.send(text)
            turn.record_agent_reply(reply)
            await conversation_store.append_message(
                conversation_id, role="assistant", content=reply
            )
            assistant_payload = {
                "type": "assistant_message",
                "message": reply,
                "agent": intent_used,
                "agent_label": intent_label(intent_used),
            }
            await _send_ws_json(
                websocket, assistant_payload, conversation_id=conversation_id
            )
            turn.record_outbound(assistant_payload)
        except Exception as exc:
            err = {"type": "error", "message": str(exc)}
            await _send_ws_json(websocket, err, conversation_id=conversation_id)
            turn.record_outbound(err)
            raise


def _create_sessions_by_intent(
    *,
    page_context: str,
    input_fields: list[dict] | None,
    viewer_state: dict | None,
) -> dict[str, ChatSession]:
    return {
        intent_id: ChatSession(
            intent=intent_id,
            page_context=page_context,
            input_fields=input_fields,
            viewer_state=viewer_state,
        )
        for intent_id in AGENTS_BY_INTENT
    }


@app.websocket("/ws")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    _logger.info("ws connected conversation_id=unassigned")
    sessions_by_intent: dict[str, ChatSession] | None = None
    page_context: PageContext = "run"
    conversation_id: str | None = None
    baggage_token = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                _logger.info(
                    "ws inbound conversation_id=%s type=invalid_json raw=%s",
                    conversation_id or "unassigned",
                    raw[: preview_max_chars()]
                    if len(raw) > preview_max_chars()
                    else raw,
                )
                err = {"type": "error", "message": "Invalid JSON."}
                await _send_ws_json(websocket, err, conversation_id=conversation_id)
                continue

            if isinstance(payload, dict):
                log_ws_inbound(conversation_id, payload)
            msg_type = payload.get("type") if isinstance(payload, dict) else None

            if msg_type == "init":
                page_context = payload.get("pageContext", "run")
                if page_context not in ("run", "job"):
                    page_context = "run"
                input_fields = payload.get("inputFields")
                viewer_state = payload.get("viewerState")
                raw_conv_id = payload.get("conversationId")
                if raw_conv_id:
                    rec = await conversation_store.get(str(raw_conv_id))
                    if rec is None:
                        rec = await conversation_store.create(page_context=page_context)
                        conversation_id = rec.id
                        _logger.info(
                            "conversation created (stale id=%s) new_id=%s page_context=%s",
                            raw_conv_id,
                            conversation_id,
                            page_context,
                        )
                    else:
                        conversation_id = rec.id
                        page_context = rec.page_context
                        _logger.info(
                            "conversation resumed id=%s page_context=%s",
                            conversation_id,
                            page_context,
                        )
                else:
                    rec = await conversation_store.create(page_context=page_context)
                    conversation_id = rec.id
                    _logger.info(
                        "conversation created id=%s page_context=%s",
                        conversation_id,
                        page_context,
                    )
                if baggage_token is not None:
                    detach_context(baggage_token)
                baggage_token = attach_conversation_baggage(conversation_id)
                try:
                    with conversation_session_span(
                        conversation_id=conversation_id,
                        page_context=page_context,
                    ):
                        sessions_by_intent = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda: _create_sessions_by_intent(
                                page_context=page_context,
                                input_fields=input_fields,
                                viewer_state=viewer_state,
                            ),
                        )
                    ready_payload = {
                        "type": "ready",
                        "conversationId": conversation_id,
                    }
                    await _send_ws_json(
                        websocket,
                        ready_payload,
                        conversation_id=conversation_id,
                    )
                except Exception as exc:
                    err = {"type": "error", "message": str(exc)}
                    await _send_ws_json(websocket, err, conversation_id=conversation_id)
                    sessions_by_intent = None

            elif msg_type == "user_message":
                if not sessions_by_intent or not conversation_id:
                    err = {
                        "type": "error",
                        "message": "Session not initialised. Send init first.",
                    }
                    await _send_ws_json(websocket, err, conversation_id=conversation_id)
                    continue

                try:
                    await _process_user_message(
                        websocket,
                        payload=payload,
                        conversation_id=conversation_id,
                        page_context=page_context,
                        sessions_by_intent=sessions_by_intent,
                    )
                except Exception:
                    _logger.exception(
                        "user_message failed conversation_id=%s",
                        conversation_id,
                    )

            elif msg_type == "update_context":
                if sessions_by_intent:
                    new_viewer = payload.get("viewerState")
                    new_fields = payload.get("inputFields")
                    page_context = payload.get("pageContext", page_context)
                    if page_context not in ("run", "job"):
                        page_context = "run"
                    if new_viewer is not None or new_fields is not None:
                        try:
                            sessions_by_intent = await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: _create_sessions_by_intent(
                                    page_context=page_context,
                                    input_fields=new_fields,
                                    viewer_state=new_viewer,
                                ),
                            )
                            await _send_ws_json(
                                websocket,
                                {"type": "context_updated"},
                                conversation_id=conversation_id,
                            )
                        except Exception as exc:
                            err = {"type": "error", "message": str(exc)}
                            await _send_ws_json(
                                websocket, err, conversation_id=conversation_id
                            )
                else:
                    err = {"type": "error", "message": "No session to update."}
                    await _send_ws_json(websocket, err, conversation_id=conversation_id)
            else:
                err = {"type": "error", "message": f"Unknown type: {msg_type}"}
                await _send_ws_json(websocket, err, conversation_id=conversation_id)

    except WebSocketDisconnect:
        _logger.info("ws disconnected conversation_id=%s", conversation_id or "unassigned")
    finally:
        if baggage_token is not None:
            detach_context(baggage_token)
        sessions_by_intent = None
