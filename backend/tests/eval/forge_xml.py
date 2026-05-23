"""Parse Forge assistant XML (mirrors frontend/lib/aiChat.ts)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

TagName = Literal[
    "UpdateInputs",
    "ViewerCmd",
    "SimAction",
    "NeedMoreInfo",
    "CasualMessage",
]

VALID_SIM_ACTIONS = frozenset({"start_simulation", "reset_inputs"})

TAG_RE = re.compile(
    r"<(UpdateInputs|ViewerCmd|SimAction|NeedMoreInfo|CasualMessage)>([\s\S]*?)</\1>"
)


@dataclass
class ParsedTag:
    tag: TagName
    data: dict[str, Any] | None = None
    action: str | None = None
    text: str | None = None


@dataclass
class ParsedAssistantMessage:
    tags: list[ParsedTag] = field(default_factory=list)
    plain_text: str = ""


def normalize_json_tag_inner(inner: str) -> str:
    """Collapse doubled braces when the model echoes format-escaped examples."""
    return inner.replace("{{", "{").replace("}}", "}")


def parse_assistant_xml(raw: str) -> ParsedAssistantMessage:
    tags: list[ParsedTag] = []
    plain = raw

    for m in TAG_RE.finditer(raw):
        tag_name = m.group(1)
        inner = m.group(2).strip()
        plain = plain.replace(m.group(0), "")

        if tag_name == "UpdateInputs":
            try:
                data = json.loads(normalize_json_tag_inner(inner))
                if isinstance(data, dict):
                    tags.append(ParsedTag(tag="UpdateInputs", data=data))
            except json.JSONDecodeError:
                pass
        elif tag_name == "ViewerCmd":
            try:
                data = json.loads(normalize_json_tag_inner(inner))
                if isinstance(data, dict):
                    tags.append(ParsedTag(tag="ViewerCmd", data=data))
            except json.JSONDecodeError:
                pass
        elif tag_name == "SimAction":
            if inner in VALID_SIM_ACTIONS:
                tags.append(ParsedTag(tag="SimAction", action=inner))
        elif tag_name == "NeedMoreInfo":
            tags.append(ParsedTag(tag="NeedMoreInfo", text=inner))
        elif tag_name == "CasualMessage":
            tags.append(ParsedTag(tag="CasualMessage", text=inner))

    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
    return ParsedAssistantMessage(tags=tags, plain_text=plain)


def tag_names(parsed: ParsedAssistantMessage) -> list[TagName]:
    return [t.tag for t in parsed.tags]


def update_inputs_merged(parsed: ParsedAssistantMessage) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in parsed.tags:
        if t.tag == "UpdateInputs" and t.data:
            for k, v in t.data.items():
                out[str(k)] = str(v)
    return out


def viewer_actions(parsed: ParsedAssistantMessage) -> list[str]:
    actions: list[str] = []
    for t in parsed.tags:
        if t.tag == "ViewerCmd" and t.data:
            act = t.data.get("action")
            if act is not None:
                actions.append(str(act))
    return actions


def sim_actions(parsed: ParsedAssistantMessage) -> list[str]:
    return [t.action for t in parsed.tags if t.tag == "SimAction" and t.action]
