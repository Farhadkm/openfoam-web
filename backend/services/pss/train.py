"""XGBoost training and regression metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor

from services.pss.dataset import MIN_TRAIN_ROWS, split_features_targets


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | None]:
    if len(y_true) == 0:
        return {"rmse": None, "mae": None, "r2": None}
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    try:
        r2 = float(r2_score(y_true, y_pred))
    except ValueError:
        r2 = None
    return {"rmse": rmse, "mae": mae, "r2": r2}


def _aggregate_metric(per_target: dict[str, dict[str, float | None]], key: str) -> float | None:
    vals = [m[key] for m in per_target.values() if m.get(key) is not None]
    if not vals:
        return None
    return float(np.mean(vals))


def train_xgboost(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    *,
    feature_labels: list[str],
    result_fields: list[dict[str, Any]],
    artifact_dir: Path,
) -> tuple[dict[str, Any], Path]:
    x_train, y_train, target_keys = split_features_targets(
        train_df, feature_labels=feature_labels, result_fields=result_fields
    )
    x_test, y_test, _ = split_features_targets(
        test_df, feature_labels=feature_labels, result_fields=result_fields
    )

    if len(x_train) < MIN_TRAIN_ROWS:
        raise ValueError(
            f"Need at least {MIN_TRAIN_ROWS} completed training rows, got {len(x_train)}",
        )

    artifact_dir.mkdir(parents=True, exist_ok=True)
    models: dict[str, XGBRegressor] = {}
    per_target: dict[str, dict[str, float | None]] = {}

    for tkey in target_keys:
        reg = XGBRegressor(
            n_estimators=80,
            max_depth=6,
            learning_rate=0.1,
            objective="reg:squarederror",
            n_jobs=1,
        )
        reg.fit(x_train.values, y_train[tkey].values)
        models[tkey] = reg
        joblib.dump(reg, artifact_dir / f"{tkey.replace('/', '_')}.joblib")

        if len(x_test) > 0:
            pred = reg.predict(x_test.values)
            per_target[tkey] = _metrics(y_test[tkey].values, pred)
        else:
            per_target[tkey] = {"rmse": None, "mae": None, "r2": None}

    metrics = {
        "per_target": per_target,
        "aggregate": {
            "rmse": _aggregate_metric(per_target, "rmse"),
            "mae": _aggregate_metric(per_target, "mae"),
            "r2": _aggregate_metric(per_target, "r2"),
        },
        "note": "Per-target RMSE/MAE/R² on held-out test rows; aggregate is unweighted mean across targets.",
    }

    meta = {
        "technique": "xgboost",
        "feature_columns": feature_labels,
        "target_keys": target_keys,
        "models": list(models.keys()),
    }
    (artifact_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return metrics, artifact_dir
