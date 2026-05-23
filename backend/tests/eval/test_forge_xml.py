"""Fast unit tests for forge_xml parser (no Vertex)."""

from __future__ import annotations

from tests.eval.forge_xml import (
    parse_assistant_xml,
    update_inputs_merged,
    viewer_actions,
)


def test_update_inputs_single_brace() -> None:
    raw = 'Updated. <UpdateInputs>{"velocity": "5"}</UpdateInputs>'
    parsed = parse_assistant_xml(raw)
    assert update_inputs_merged(parsed) == {"velocity": "5"}


def test_update_inputs_double_brace() -> None:
    raw = '<UpdateInputs>{{"velocity": "5"}}</UpdateInputs>'
    parsed = parse_assistant_xml(raw)
    assert update_inputs_merged(parsed) == {"velocity": "5"}


def test_viewer_cmd_double_brace() -> None:
    raw = '<ViewerCmd>{{"action": "play"}}</ViewerCmd>'
    parsed = parse_assistant_xml(raw)
    assert viewer_actions(parsed) == ["play"]
