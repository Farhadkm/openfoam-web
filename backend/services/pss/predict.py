"""Load trained artifacts and predict result field values."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from services.pss.dataset import overrides_to_feature_row


def load_artifact_meta(artifact_dir: Path) -> dict[str, Any]:
    meta_path = artifact_dir / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError("Model metadata not found")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def predict(
    artifact_dir: Path,
    *,
    input_fields: list[dict[str, Any]],
    overrides: dict[str, str],
) -> dict[str, str]:
    meta = load_artifact_meta(artifact_dir)
    feature_labels: list[str] = list(meta.get("feature_columns") or [])
    target_keys: list[str] = list(meta.get("target_keys") or [])

    row = overrides_to_feature_row(
        overrides,
        input_fields=input_fields,
        feature_labels=feature_labels,
    )
    x = pd.DataFrame([row])[feature_labels].values

    predictions: dict[str, str] = {}
    for tkey in target_keys:
        safe = tkey.replace("/", "_")
        model_path = artifact_dir / f"{safe}.joblib"
        if not model_path.is_file():
            raise FileNotFoundError(f"Missing model artifact for {tkey}")
        reg = joblib.load(model_path)
        val = float(reg.predict(x)[0])
        predictions[tkey] = str(val) if val == int(val) else f"{val:g}"

    return predictions
