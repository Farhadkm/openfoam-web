"""Parse mass-run CSV rows (label/value pairs) and map to simulation input field keys."""

from __future__ import annotations

import csv
import io
from typing import Any


def _norm_label(s: str) -> str:
    return " ".join(str(s).strip().split()).casefold()


def _label_to_field_key(input_fields: list[dict[str, Any]]) -> dict[str, str]:
    """Map normalized label (and key) -> field.key."""
    out: dict[str, str] = {}
    for field in input_fields:
        key = str(field.get("key") or "").strip()
        if not key:
            continue
        label = str(field.get("label") or "").strip()
        if label:
            out[_norm_label(label)] = key
        out[_norm_label(key)] = key
    return out


def parse_mass_run_csv(
    raw: bytes,
    input_fields: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Each CSV row is one simulation run.
    Columns alternate label, value, label, value, …

    Returns (runs, errors). Each run:
      {"index": int, "inputs": [{"label": str, "value": str}], "overrides": {field_key: value}}
    """
    errors: list[str] = []
    label_map = _label_to_field_key(input_fields)

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["CSV must be UTF-8 encoded"]

    reader = csv.reader(io.StringIO(text))
    runs: list[dict[str, Any]] = []
    for row_num, row in enumerate(reader, start=1):
        cells = [c.strip() for c in row]
        if not cells or all(not c for c in cells):
            continue
        if len(cells) % 2 != 0:
            errors.append(f"Row {row_num}: expected label/value pairs (even column count), got {len(cells)} columns")
            continue

        pairs: list[dict[str, str]] = []
        overrides: dict[str, str] = {}
        row_errors: list[str] = []

        for i in range(0, len(cells), 2):
            label = cells[i]
            value = cells[i + 1]
            if not label:
                row_errors.append(f"Row {row_num}: empty label in column {i + 1}")
                continue
            pairs.append({"label": label, "value": value})
            fk = label_map.get(_norm_label(label))
            if not fk:
                row_errors.append(f"Row {row_num}: unknown input label {label!r}")
            else:
                overrides[fk] = value

        if row_errors:
            errors.extend(row_errors)
            continue

        runs.append(
            {
                "index": len(runs),
                "inputs": pairs,
                "overrides": overrides,
            }
        )

    if not runs and not errors:
        errors.append("CSV contains no data rows")
    return runs, errors


def inputs_to_overrides(
    inputs: list[dict[str, str]],
    input_fields: list[dict[str, Any]],
) -> tuple[dict[str, str], list[str]]:
    """Map preview/start payload inputs (label/value) to field.key overrides."""
    label_map = _label_to_field_key(input_fields)
    overrides: dict[str, str] = {}
    errors: list[str] = []
    for inp in inputs:
        label = str(inp.get("label") or "").strip()
        value = str(inp.get("value") if inp.get("value") is not None else "")
        if not label:
            continue
        fk = label_map.get(_norm_label(label))
        if not fk:
            errors.append(f"Unknown input label {label!r}")
        else:
            overrides[fk] = value
    return overrides, errors
