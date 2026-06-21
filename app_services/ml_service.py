from __future__ import annotations

from typing import Any

from app.api_utils import none_if_blank
from ml.model_bundle import list_model_bundles
from ml.model_inference import list_local_models, predict_with_local_models
from ml.similar_records import find_similar_records
from ml.training_tasks import list_task_payloads, tasks_for_phase


def list_ml_tasks(phase: str = "") -> list[dict[str, Any]]:
    return list_task_payloads(none_if_blank(phase))


def list_ml_models(phase: str = "") -> list[dict[str, Any]]:
    return list_local_models(phase=none_if_blank(phase))


def list_ml_bundles() -> list[dict[str, Any]]:
    return list_model_bundles()


def find_similar(payload: dict[str, Any], *, phase: str = "postfit", limit: int = 5, include_rejected: bool = False):
    return find_similar_records(payload, phase=phase, limit=limit, include_rejected=include_rejected)


def ml_phase_response(payload: dict[str, Any], phase: str) -> dict[str, Any]:
    tasks = tasks_for_phase(phase)
    return {
        "ok": True,
        "phase": phase,
        "tasks": list_task_payloads(phase),
        "similar": find_similar_records(payload, phase=phase, limit=5),
        "models": predict_with_local_models(payload, phase=phase, tasks=tasks),
    }


def ml_prefit_response(payload: dict[str, Any]) -> dict[str, Any]:
    return ml_phase_response(payload, "prefit")


def ml_postfit_response(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("result"):
        raise ValueError("Post-fit ML payload must include a fitting result.")
    return ml_phase_response(payload, "postfit")


def ml_recommend_response(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("result"):
        raise ValueError("ML recommendation payload must include a fitting result.")
    return predict_with_local_models(payload)

