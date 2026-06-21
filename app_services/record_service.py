from __future__ import annotations

from pathlib import Path
from typing import Any

from app.api_utils import save_record
from ml.package_export import build_offline_data_package
from ml.record_features import export_records_dataset, list_record_summaries
from ml.recommender import recommend_from_records


def save_training_record(payload: dict[str, Any]) -> Path:
    if not payload.get("result"):
        raise ValueError("Record payload must include a fitting result.")
    return save_record(payload)


def list_training_records() -> list[dict[str, Any]]:
    return list_record_summaries()


def export_training_records_dataset() -> tuple[Path, int]:
    return export_records_dataset()


def export_training_records_package(*, include_rejected: bool, app_version: str):
    return build_offline_data_package(include_rejected=include_rejected, app_version=app_version)


def recommend_from_training_records(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("result"):
        raise ValueError("Recommendation payload must include a fitting result.")
    return recommend_from_records(payload)

