"""
Forge chatbot evaluation (ICS classify + CCS Gemini agents).

Cases load from tests/eval/cases/*.json at collection time.

Environment (set by scripts/run-chatbot-eval.sh or manually):
  FORGE_EVAL_CASES   Comma-separated suite filenames or paths (default: full.json)
  FORGE_EVAL_CASE_ID Run a single case by id (optional)
  FORGE_EVAL_JUDGE   Set to 1 for DeepEval GEval judge tests
  FORGE_EVAL_THRESHOLD  GEval threshold (default 0.7)

Run from repo root:
  ./scripts/run-chatbot-eval.sh structural
  ./scripts/run-chatbot-eval.sh structural smoke.json
  ./scripts/run-chatbot-eval.sh structural full.json --case run-param-01
  ./scripts/run-chatbot-eval.sh list smoke.json
  ./scripts/run-chatbot-eval.sh deepeval
"""

from __future__ import annotations

import os

import pytest
from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from tests.eval.chatbot_cases import ChatbotCase
from tests.eval.conftest import deepeval_judge_enabled, vertex_configured
from tests.eval.fixtures import resolve_fields, resolve_viewer
from tests.eval.harness import run_chat_turn
from tests.eval.load_cases import CaseLoadError, get_eval_cases
from tests.eval.structural import StructuralAssertionError, apply_structural_expectations


def _case_id(case: ChatbotCase) -> str:
    return str(case["id"])


def _run_context(case: ChatbotCase) -> tuple[str, list[dict] | None, dict | None]:
    page = case["page_context"]
    fields = resolve_fields(case.get("fields_profile"))
    viewer = resolve_viewer(case.get("viewer_profile"))
    return page, fields, viewer


def _deepeval_cases(cases: list[ChatbotCase]) -> list[ChatbotCase]:
    return [c for c in cases if c.get("geval_criteria") or c.get("expected_output")]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "case" not in metafunc.fixturenames:
        return
    try:
        cases = get_eval_cases()
    except CaseLoadError as exc:
        pytest.fail(str(exc), pytrace=False)
    if metafunc.definition.name == "test_chatbot_deepeval_quality":
        cases = _deepeval_cases(cases)
    metafunc.parametrize("case", cases, ids=_case_id)


@pytest.mark.slow
@pytest.mark.structural
async def test_chatbot_structural(case: ChatbotCase, require_vertex: None) -> None:
    """Live Gemini + ICS; assert intents and XML tags match expectations."""
    page, fields, viewer = _run_context(case)
    result = await run_chat_turn(
        user_message=case["user_message"],
        page_context=page,
        input_fields=fields,
        viewer_state=viewer,
        classify=not case.get("skip_classify", False),
    )
    expect = case.get("expect") or {}
    try:
        apply_structural_expectations(result, expect)
    except StructuralAssertionError as exc:
        pytest.fail(
            f"{case['id']}: {exc}\n--- reply ---\n{result.reply[:2000]}",
            pytrace=False,
        )


@pytest.mark.slow
@pytest.mark.deepeval
async def test_chatbot_deepeval_quality(case: ChatbotCase, require_vertex: None) -> None:
    """LLM-as-judge on assistant replies (costs API calls)."""
    if not deepeval_judge_enabled():
        pytest.skip("Set FORGE_EVAL_JUDGE=1 to run DeepEval GEval judge tests.")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY required for DeepEval GEval judge.")

    page, fields, viewer = _run_context(case)
    result = await run_chat_turn(
        user_message=case["user_message"],
        page_context=page,
        input_fields=fields,
        viewer_state=viewer,
    )

    criteria = case.get("geval_criteria") or (
        "Determine whether the assistant response correctly follows Forge XML rules "
        "and satisfies the expected behavior."
    )
    expected = case.get("expected_output") or ""

    metric = GEval(
        name="ForgeChatbot",
        criteria=criteria,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=float(os.getenv("FORGE_EVAL_THRESHOLD", "0.7")),
    )

    test_case = LLMTestCase(
        input=case["user_message"],
        actual_output=result.reply,
        expected_output=expected,
        context=[
            f"page_context={page}",
            f"primary_intent={result.primary_intent}",
            f"resolved_intent={result.resolved_intent}",
        ],
    )
    assert_test(test_case, [metric])


@pytest.mark.slow
@pytest.mark.structural
async def test_vertex_credentials_present() -> None:
    if not vertex_configured():
        pytest.fail("Vertex credentials not configured for eval runs.")
