"""Deterministic checks on ICS intent + assistant XML (no LLM judge)."""

from __future__ import annotations

from typing import Any

from tests.eval.forge_xml import (
    ParsedAssistantMessage,
    sim_actions,
    tag_names,
    update_inputs_merged,
    viewer_actions,
)
from tests.eval.harness import ChatTurnResult


class StructuralAssertionError(AssertionError):
    pass


def _fail(msg: str) -> None:
    raise StructuralAssertionError(msg)


def apply_structural_expectations(
    result: ChatTurnResult,
    expect: dict[str, Any],
) -> None:
    """Validate a turn against the ``expect`` block from a case definition."""
    if "primary_intent" in expect:
        if result.primary_intent != expect["primary_intent"]:
            _fail(
                f"intent: expected primary={expect['primary_intent']!r}, "
                f"got {result.primary_intent!r}"
            )

    if "resolved_intent" in expect:
        if result.resolved_intent != expect["resolved_intent"]:
            _fail(
                f"resolved agent: expected {expect['resolved_intent']!r}, "
                f"got {result.resolved_intent!r}"
            )

    names = tag_names(result.parsed)

    for tag in expect.get("required_tags", []):
        if tag not in names:
            _fail(f"missing required tag <{tag}>; got tags={names}")

    for tag in expect.get("forbidden_tags", []):
        if tag in names:
            _fail(f"forbidden tag <{tag}> present in response")

    if "min_tag_count" in expect:
        if len(result.parsed.tags) < int(expect["min_tag_count"]):
            _fail(f"expected at least {expect['min_tag_count']} XML tags")

    updates = update_inputs_merged(result.parsed)
    for key, value in (expect.get("update_inputs_contains") or {}).items():
        if updates.get(key) != str(value):
            _fail(
                f"UpdateInputs: expected {key}={value!r}, "
                f"got updates={updates!r}"
            )

    for key in expect.get("update_inputs_keys_any", []):
        if key not in updates:
            _fail(f"UpdateInputs: expected key {key!r} in {list(updates)}")

    for action in expect.get("viewer_actions_contains", []):
        if action not in viewer_actions(result.parsed):
            _fail(
                f"ViewerCmd: expected action {action!r}, "
                f"got {viewer_actions(result.parsed)}"
            )

    for action in expect.get("sim_actions_contains", []):
        if action not in sim_actions(result.parsed):
            _fail(
                f"SimAction: expected {action!r}, got {sim_actions(result.parsed)}"
            )

    if expect.get("plain_text_non_empty"):
        if not result.parsed.plain_text.strip():
            _fail("expected non-empty plain text outside XML tags")

    if "plain_text_contains" in expect:
        needle = expect["plain_text_contains"].lower()
        if needle not in result.parsed.plain_text.lower():
            _fail(f"plain text should mention {needle!r}")

    if expect.get("reply_contains"):
        if expect["reply_contains"].lower() not in result.reply.lower():
            _fail(f"raw reply should contain {expect['reply_contains']!r}")
