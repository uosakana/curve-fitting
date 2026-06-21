from __future__ import annotations

from pathlib import Path
from typing import Any

from ml.model_registry import DEFAULT_MODEL_DIR, latest_models_by_task, list_local_models, load_model_artifact
from ml.record_features import flatten_record


def _record_for_inference(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": "current",
        "saved_at": None,
        "data_selection": payload.get("data_selection") or {},
        "sample_context": payload.get("sample_context") or {},
        "analysis_settings": payload.get("analysis_settings") or {},
        "manual_parameters": payload.get("manual_parameters") or {},
        "labels": payload.get("labels") or {},
        "result": payload.get("result") or payload,
    }


def _predict_one(row: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    import pandas as pd

    artifact = load_model_artifact(info["path"])
    features = list(artifact.get("numeric_features") or []) + list(artifact.get("categorical_features") or [])
    frame = pd.DataFrame([{feature: row.get(feature) for feature in features}], columns=features)
    pipeline = artifact["pipeline"]
    prediction = pipeline.predict(frame)[0]
    probabilities = {}
    top_probability = None
    if hasattr(pipeline, "predict_proba"):
        proba = pipeline.predict_proba(frame)[0]
        classes = getattr(pipeline, "classes_", None)
        if classes is None and hasattr(pipeline, "named_steps"):
            model = pipeline.named_steps.get("model")
            classes = getattr(model, "classes_", [])
        classes = [str(item) for item in classes]
        probabilities = {label: float(value) for label, value in zip(classes, proba)}
        if probabilities:
            top_probability = max(probabilities.values())
    return {
        "task": artifact.get("task") or info["task"],
        "prediction": str(prediction),
        "probability": top_probability,
        "probabilities": probabilities,
        "model_path": info["path"],
        "metrics_path": info.get("metrics_path"),
        "features_used": features,
    }


def predict_with_local_models(
    payload: dict[str, Any],
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    *,
    tasks: list[str] | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    latest = latest_models_by_task(model_dir, phase=phase, tasks=tasks)
    if not latest:
        return {
            "ok": True,
            "status": "no_models",
            "message": "No matching local ML model artifacts were found in app_data/models.",
            "models": [],
            "predictions": {},
        }

    row = flatten_record(_record_for_inference(payload))
    predictions: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for task, info in sorted(latest.items()):
        try:
            predictions[task] = _predict_one(row, info)
        except Exception as exc:
            errors[task] = str(exc)

    status = "ready" if predictions else "error"
    if predictions and errors:
        status = "partial"
    return {
        "ok": True,
        "status": status,
        "message": f"Loaded {len(predictions)} local ML model(s).",
        "phase": phase,
        "models": list(latest.values()),
        "predictions": predictions,
        "errors": errors,
    }
