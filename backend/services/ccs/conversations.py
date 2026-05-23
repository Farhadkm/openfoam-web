"""In-memory conversation metadata and message history for CCS.

Persistence is process-local only (lost on restart). MongoDB can replace this
module later without changing the public REST paths on CCS.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

PageContext = Literal["run", "job"]
MessageRole = Literal["user", "assistant", "system"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StoredMessage:
    role: MessageRole
    content: str
    created_at: str


@dataclass
class ConversationRecord:
    id: str
    title: str
    page_context: PageContext
    created_at: str
    updated_at: str
    messages: list[StoredMessage] = field(default_factory=list)


class ConversationStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._by_id: dict[str, ConversationRecord] = {}

    async def create(self, *, title: str = "", page_context: PageContext = "run") -> ConversationRecord:
        now = _utc_now()
        rec = ConversationRecord(
            id=str(uuid.uuid4()),
            title=title.strip(),
            page_context=page_context,
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            self._by_id[rec.id] = rec
        return rec

    async def list_all(self) -> list[ConversationRecord]:
        async with self._lock:
            items = list(self._by_id.values())
        items.sort(key=lambda r: r.updated_at, reverse=True)
        return items

    async def get(self, conversation_id: str) -> ConversationRecord | None:
        async with self._lock:
            return self._by_id.get(conversation_id)

    async def delete(self, conversation_id: str) -> bool:
        async with self._lock:
            return self._by_id.pop(conversation_id, None) is not None

    async def append_message(
        self,
        conversation_id: str,
        *,
        role: MessageRole,
        content: str,
    ) -> bool:
        async with self._lock:
            rec = self._by_id.get(conversation_id)
            if rec is None:
                return False
            rec.messages.append(
                StoredMessage(role=role, content=content, created_at=_utc_now())
            )
            rec.updated_at = _utc_now()
            return True


conversation_store = ConversationStore()
