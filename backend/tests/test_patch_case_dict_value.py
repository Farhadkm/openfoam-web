"""Unit tests for OpenFOAM case dictionary patching."""

from __future__ import annotations

from services.simulation.app import _patch_case_dict_value


def test_patch_value_uniform_vector_stays_unquoted() -> None:
    text = "        value           uniform (1 0 0);\n"
    for new_value in ("uniform (1 0 0)", "uniform (2 0 0)"):
        patched, changed = _patch_case_dict_value(text, "value", new_value, "text")
        assert changed
        assert f"value           {new_value};" in patched
        assert f'"{new_value}"' not in patched


def test_patch_value_nonuniform_stays_unquoted() -> None:
    text = "        value           nonuniform List<vector> 2((1 0 0) (0 1 0));\n"
    new_value = "nonuniform List<vector> 2((2 0 0) (0 2 0))"
    patched, changed = _patch_case_dict_value(text, "value", new_value, "text")
    assert changed
    assert new_value in patched
    assert f'"{new_value}"' not in patched


def test_patch_simple_token_stays_unquoted() -> None:
    text = "        type            fixedValue;\n"
    patched, changed = _patch_case_dict_value(text, "type", "zeroGradient", "text")
    assert changed
    assert "type            zeroGradient;" in patched


def test_patch_text_with_spaces_gets_quoted() -> None:
    text = '        name            "inlet";\n'
    patched, changed = _patch_case_dict_value(text, "name", "my inlet", "text")
    assert changed
    assert 'name            "my inlet";' in patched
