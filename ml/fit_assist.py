from __future__ import annotations

from typing import Any

import numpy as np

from ml.model_inference import predict_with_local_models
from ml.similar_records import find_similar_records
from ml.training_tasks import list_task_payloads, tasks_for_phase


POLICY_VERSION = 1
ML_ASSIST_MODES = ("advisory", "auto_fit_mode", "efficiency", "quality")
PRODUCT_FIT_MODES = ("fast_fit", "diagnostic_fit")


def normalize_ml_assist_mode(value: str | None) -> str:
    normalized = str(value or "advisory").strip().lower().replace("-", "_")
    aliases = {
        "auto": "auto_fit_mode",
        "auto_mode": "auto_fit_mode",
        "fit_mode": "auto_fit_mode",
        "fast": "efficiency",
        "accurate": "quality",
        "diagnostic": "quality",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in ML_ASSIST_MODES:
        raise ValueError(f"ml_assist_mode must be one of: {', '.join(ML_ASSIST_MODES)}.")
    return normalized


def prefit_payload(voltage: Any, current: Any, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "analysis_settings": settings,
        "series": {
            "voltage": np.asarray(voltage, dtype=float).reshape(-1).tolist(),
            "measured": np.asarray(current, dtype=float).reshape(-1).tolist(),
        },
    }


def _prediction_confidence(prediction: dict[str, Any] | None) -> float | None:
    if not prediction:
        return None
    value = prediction.get("probability")
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    return confidence if np.isfinite(confidence) else None


def _model_product_mode(models: dict[str, Any], *, min_confidence: float) -> tuple[str | None, float | None]:
    prediction = (models.get("predictions") or {}).get("strategy")
    mode = prediction.get("prediction") if isinstance(prediction, dict) else None
    confidence = _prediction_confidence(prediction)
    if mode not in PRODUCT_FIT_MODES:
        return None, confidence
    if confidence is not None and confidence < min_confidence:
        return None, confidence
    return str(mode), confidence


def _similar_product_mode(similar: dict[str, Any]) -> str | None:
    mode = ((similar.get("summary") or {}).get("recommended_product_fit_mode"))
    return str(mode) if mode in PRODUCT_FIT_MODES else None


def _suggest_product_fit_mode(mode: str, models: dict[str, Any], similar: dict[str, Any]) -> tuple[str | None, str]:
    if mode == "advisory":
        prediction, _confidence = _model_product_mode(models, min_confidence=0.0)
        return prediction or _similar_product_mode(similar), "advisory_only"
    if mode == "auto_fit_mode":
        prediction, _confidence = _model_product_mode(models, min_confidence=0.65)
        return prediction or _similar_product_mode(similar), "auto_fit_mode"
    if mode == "efficiency":
        prediction, _confidence = _model_product_mode(models, min_confidence=0.70)
        return ("fast_fit" if prediction == "fast_fit" else None), "efficiency_fast_only"
    if mode == "quality":
        prediction, _confidence = _model_product_mode(models, min_confidence=0.60)
        if prediction == "diagnostic_fit":
            return "diagnostic_fit", "quality_diagnostic_model"
        similar_mode = _similar_product_mode(similar)
        return ("diagnostic_fit" if similar_mode == "diagnostic_fit" else None), "quality_diagnostic_similar"
    return None, "unknown"


def build_prefit_ml_assist(
    voltage: Any,
    current: Any,
    settings: dict[str, Any],
    *,
    enabled: bool,
    mode: str = "advisory",
) -> dict[str, Any]:
    normalized_mode = normalize_ml_assist_mode(mode)
    audit: dict[str, Any] = {
        "enabled": bool(enabled),
        "mode": normalized_mode,
        "policy_version": POLICY_VERSION,
        "phase": "prefit",
        "requested_settings": dict(settings),
        "tasks": list_task_payloads("prefit"),
        "suggested_overrides": {},
        "applied_overrides": {},
        "messages": [],
    }
    if not enabled:
        audit["status"] = "disabled"
        return audit

    payload = prefit_payload(voltage, current, settings)
    similar = find_similar_records(payload, phase="prefit", limit=5)
    models = predict_with_local_models(payload, phase="prefit", tasks=tasks_for_phase("prefit"))
    suggested_mode, reason = _suggest_product_fit_mode(normalized_mode, models, similar)

    audit.update(
        {
            "status": "ready",
            "similar": similar,
            "models": models,
            "suggestion_reason": reason,
        }
    )
    if suggested_mode:
        audit["suggested_overrides"]["product_fit_mode"] = suggested_mode
        audit["messages"].append(f"ML assist suggests {suggested_mode}.")

    if normalized_mode != "advisory" and suggested_mode:
        audit["applied_overrides"]["product_fit_mode"] = suggested_mode
        audit["messages"].append(f"ML assist applied product_fit_mode={suggested_mode}.")
    elif normalized_mode == "advisory":
        audit["messages"].append("ML assist is advisory-only; no fit settings were changed.")
    else:
        audit["messages"].append("ML assist did not find a confident override.")

    return audit
