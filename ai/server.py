"""OpenFOAM AI assistant – FastAPI + Vertex AI Gemini chat service.

WebSocket /ws  – stateful chat (init → ready; user_message → assistant_message)
POST     /generate-thumbnail – generate a thumbnail image from a text prompt
GET      /health
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    default_creds = "/app/credentials/key.json"
    if os.path.exists(default_creds):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = default_creds

import vertexai
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from vertexai.preview.generative_models import GenerativeModel

from prompt import create_system_prompt

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Image-capable Gemini on Vertex (see model versions doc); override via GEMINI_IMAGE_MODEL if needed.
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

_vertex_initialized = False

# google-auth Application Default Credentials JSON "type" values (see google.auth._default).
_GOOGLE_ADC_TYPES = frozenset(
    {
        "authorized_user",
        "service_account",
        "external_account",
        "external_account_authorized_user",
        "impersonated_service_account",
        "gdch_service_account",
    }
)


def _credential_file_path() -> str | None:
    """Path to the JSON file used for Vertex / genai, if it exists."""
    p = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if p and os.path.isfile(p):
        return p
    default = "/app/credentials/key.json"
    if os.path.isfile(default):
        return default
    return None


def _validate_google_credential_json(path: str) -> None:
    """Ensure the file is real ADC JSON (not an empty object from AWS bootstrap)."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read Google credentials JSON at {path}: {exc}") from exc
    cred_type = data.get("type")
    if cred_type not in _GOOGLE_ADC_TYPES:
        raise RuntimeError(
            f"Google credentials at {path} are invalid (type is {cred_type!r}; expected one of "
            f"{sorted(_GOOGLE_ADC_TYPES)}). "
            "Use a GCP service account JSON with Vertex AI / Gemini access. "
            "On AWS dev, set Terraform variable gemini_secret_arn to a Secrets Manager secret "
            "containing that JSON, or replace the host file ai/credentials/key.json — "
            "the placeholder empty object from bootstrap is not valid."
        )


def _credentials_health() -> dict:
    path = _credential_file_path()
    if not path:
        return {"ok": False, "path": None, "detail": "No credentials file found."}
    try:
        _validate_google_credential_json(path)
    except RuntimeError as exc:
        return {"ok": False, "path": path, "detail": str(exc)}
    return {"ok": True, "path": path, "detail": None}


def _ensure_vertex():
    global _vertex_initialized
    if _vertex_initialized:
        return
    if not PROJECT_ID:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID is not set")
    path = _credential_file_path()
    if not path:
        raise RuntimeError(
            "No Google credentials file. Set GOOGLE_APPLICATION_CREDENTIALS or mount "
            "/app/credentials/key.json with a valid service account JSON."
        )
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
    _validate_google_credential_json(path)
    vertexai.init(project=PROJECT_ID, location="us-central1")
    _vertex_initialized = True


class ChatSession:
    """One per WebSocket connection."""

    def __init__(
        self,
        *,
        page_context: str = "run",
        input_fields: list[dict] | None = None,
        viewer_state: dict | None = None,
    ):
        _ensure_vertex()
        self.model = GenerativeModel(MODEL_NAME)
        system_prompt = create_system_prompt(
            input_fields=input_fields,
            viewer_state=viewer_state,
            page_context=page_context,
        )
        self.chat = self.model.start_chat()
        self.chat.send_message(system_prompt)

    def _send_sync(self, message: str) -> str:
        resp = self.chat.send_message(
            f"The user message is: <UserMessage>{message}</UserMessage>"
        )
        text = getattr(resp, "text", None)
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text.strip()

    async def send(self, message: str) -> str:
        return await asyncio.get_event_loop().run_in_executor(
            None, self._send_sync, message
        )


app = FastAPI(title="OpenFOAM AI Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    cred = _credentials_health()
    return {
        "status": "ok" if cred["ok"] else "degraded",
        "model": MODEL_NAME,
        "image_model": IMAGE_MODEL,
        "vertex_credentials": cred,
    }


class ThumbnailRequest(BaseModel):
    """Body uses title + description to build the image brief (prompt is optional legacy)."""

    title: str = ""
    description: str = ""
    prompt: str = ""


def _generate_image_sync(prompt: str) -> bytes:
    """Call Gemini with image output modality and return PNG bytes."""
    from google import genai
    from google.genai.types import GenerateContentConfig, Modality

    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location="us-central1",
    )
    full_prompt = (
        f"Generate a clean, professional thumbnail image for a simulation. "
        f"The image should be visually appealing and suitable as a card thumbnail (landscape, ~16:9 ratio). "
        f"Style: technical illustration, modern, dark theme friendly. "
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


@app.post("/generate-thumbnail")
async def generate_thumbnail(req: ThumbnailRequest):
    _ensure_vertex()
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


@app.websocket("/ws")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    session: Optional[ChatSession] = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON."})
                continue

            msg_type = payload.get("type")

            if msg_type == "init":
                page_context = payload.get("pageContext", "run")
                input_fields = payload.get("inputFields")
                viewer_state = payload.get("viewerState")
                try:
                    session = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: ChatSession(
                            page_context=page_context,
                            input_fields=input_fields,
                            viewer_state=viewer_state,
                        ),
                    )
                    await websocket.send_json({"type": "ready"})
                except Exception as exc:
                    await websocket.send_json(
                        {"type": "error", "message": str(exc)}
                    )
                    session = None

            elif msg_type == "user_message":
                if not session:
                    await websocket.send_json(
                        {"type": "error", "message": "Session not initialised. Send init first."}
                    )
                    continue

                text = (payload.get("message") or "").strip()
                if not text:
                    await websocket.send_json(
                        {"type": "error", "message": "Empty message."}
                    )
                    continue

                try:
                    reply = await session.send(text)
                    await websocket.send_json(
                        {"type": "assistant_message", "message": reply}
                    )
                except Exception as exc:
                    await websocket.send_json(
                        {"type": "error", "message": str(exc)}
                    )

            elif msg_type == "update_context":
                if session:
                    new_viewer = payload.get("viewerState")
                    new_fields = payload.get("inputFields")
                    if new_viewer is not None or new_fields is not None:
                        try:
                            session = await asyncio.get_event_loop().run_in_executor(
                                None,
                                lambda: ChatSession(
                                    page_context=payload.get("pageContext", "run"),
                                    input_fields=new_fields,
                                    viewer_state=new_viewer,
                                ),
                            )
                            await websocket.send_json({"type": "context_updated"})
                        except Exception as exc:
                            await websocket.send_json(
                                {"type": "error", "message": str(exc)}
                            )
                else:
                    await websocket.send_json(
                        {"type": "error", "message": "No session to update."}
                    )
            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown type: {msg_type}"}
                )

    except WebSocketDisconnect:
        pass
    finally:
        session = None
