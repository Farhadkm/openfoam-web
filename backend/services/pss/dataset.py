"""Build training matrices from simulation mass-run results CSV."""

from __future__ import annotations

import csv
import io
from typing import Any

import httpx
import pandas as pd

COMPLETED_STATUS = "completed"
MIN_TRAIN_ROWS = 5


def _norm_label(s: str) -> str:
    return " ".join(str(s).strip().split()).casefold()


def _label_to_field_key(input_fields: list[dict[str, Any]]) -> dict[str, str]:
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


def _result_target_columns(result_fields: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return (csv_header_label, result_field_key) for each target."""
    cols: list[tuple[str, str]] = []
    for field in result_fields:
        key = str(field.get("key") or "").strip()
        label = str(field.get("label") or key).strip() or key
        if key:
            cols.append((label, key))
    return cols


def _feature_columns(input_fields: list[dict[str, Any]]) -> list[str]:
    return [str(f.get("label") or f.get("key") or "").strip() for f in input_fields if f.get("key")]


async def fetch_results_csv(
    client: httpx.AsyncClient,
    simulation_base: str,
    mass_run_id: str,
) -> str:
    url = f"{simulation_base.rstrip('/')}/api/mass-runs/{mass_run_id}/results.csv"
    r = await client.get(url, timeout=120.0)
    r.raise_for_status()
    return r.text


def _parse_csv_rows(
    csv_text: str,
    *,
    feature_labels: list[str],
    target_labels: list[str],
) -> pd.DataFrame:
    """Parse mass-run results CSV; keep completed rows with numeric targets."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for row in reader:
        status = str(row.get("status") or "").strip()
        rc = str(row.get("returncode") or "").strip()
        if status != COMPLETED_STATUS or rc not in ("0", "0.0"):
            continue
        record: dict[str, Any] = {}
        ok = True
        for lab in feature_labels:
            val = row.get(lab, "")
            try:
                record[lab] = float(str(val).strip()) if str(val).strip() != "" else float("nan")
            except ValueError:
                record[lab] = float("nan")
        for lab in target_labels:
            val = row.get(lab, "")
            try:
                record[f"__target__{lab}"] = (
                    float(str(val).strip()) if str(val).strip() != "" else float("nan")
                )
            except ValueError:
                record[f"__target__{lab}"] = float("nan")
            if pd.isna(record[f"__target__{lab}"]):
                ok = False
        for lab in feature_labels:
            if pd.isna(record.get(lab)):
                ok = False
        if ok:
            rows.append(record)

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


async def load_dataset_from_mass_runs(
    client: httpx.AsyncClient,
    simulation_base: str,
    mass_run_ids: list[str],
    *,
    input_fields: list[dict[str, Any]],
    result_fields: list[dict[str, Any]],
) -> pd.DataFrame:
    feature_labels = _feature_columns(input_fields)
    targets = _result_target_columns(result_fields)
    target_labels = [t[0] for t in targets]

    frames: list[pd.DataFrame] = []
    for mid in mass_run_ids:
        csv_text = await fetch_results_csv(client, simulation_base, mid)
        df = _parse_csv_rows(
            csv_text,
            feature_labels=feature_labels,
            target_labels=target_labels,
        )
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def split_features_targets(
    df: pd.DataFrame,
    *,
    feature_labels: list[str],
    result_fields: list[dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    targets = _result_target_columns(result_fields)
    target_labels = [t[0] for t in targets]
    target_keys = [t[1] for t in targets]
    if df.empty:
        return pd.DataFrame(), pd.DataFrame(), target_keys

    x = df[feature_labels].copy()
    y_cols = [f"__target__{lab}" for lab in target_labels]
    y = df[y_cols].copy()
    y.columns = target_keys
    return x, y, target_keys


def overrides_to_feature_row(
    overrides: dict[str, str],
    *,
    input_fields: list[dict[str, Any]],
    feature_labels: list[str],
) -> dict[str, float]:
    label_map = _label_to_field_key(input_fields)
    by_label: dict[str, float] = {}
    for key, raw in overrides.items():
        fk = label_map.get(_norm_label(key)) or key
        for field in input_fields:
            if str(field.get("key") or "") == fk:
                lab = str(field.get("label") or fk).strip()
                try:
                    by_label[lab] = float(str(raw).strip())
                except ValueError as exc:
                    raise ValueError(f"Non-numeric value for {lab!r}") from exc
    row: dict[str, float] = {}
    for lab in feature_labels:
        if lab not in by_label:
            raise ValueError(f"Missing input for feature {lab!r}")
        row[lab] = by_label[lab]
    return row
