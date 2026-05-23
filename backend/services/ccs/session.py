"""Gemini chat session for the Chat Conversation Service (CCS)."""

from __future__ import annotations

import asyncio

from vertexai.preview.generative_models import GenerativeModel

from services.ccs.agents.registry import create_system_prompt
from shared.vertex import MODEL_NAME, ensure_vertex


class ChatSession:
    """One Gemini chat per (WebSocket connection × ICS intent)."""

    def __init__(
        self,
        *,
        intent: str,
        page_context: str = "run",
        input_fields: list[dict] | None = None,
        viewer_state: dict | None = None,
    ):
        self.intent = intent
        ensure_vertex()
        self.model = GenerativeModel(MODEL_NAME)
        system_prompt = create_system_prompt(
            intent=intent,
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
