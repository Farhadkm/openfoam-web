"""Types for Forge chatbot eval cases. Data lives in tests/eval/cases/*.json — use load_cases()."""

from __future__ import annotations

from typing import TypedDict


class ExpectBlock(TypedDict, total=False):
    primary_intent: str
    resolved_intent: str
    required_tags: list[str]
    forbidden_tags: list[str]
    min_tag_count: int
    update_inputs_contains: dict[str, str]
    update_inputs_keys_any: list[str]
    viewer_actions_contains: list[str]
    sim_actions_contains: list[str]
    plain_text_non_empty: bool
    plain_text_contains: str
    reply_contains: str


class ChatbotCase(TypedDict, total=False):
    id: str
    description: str
    page_context: str
    user_message: str
    fields_profile: str
    viewer_profile: str
    expect: ExpectBlock
    expected_output: str
    geval_criteria: str
    skip_classify: bool
