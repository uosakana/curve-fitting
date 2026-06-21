from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from ml.model_registry import DEFAULT_MODEL_DIR, latest_models_by_task
from ml.record_schema import SCHEMA_VERSION


DEFAULT_BUNDLE_DIR = DEFAULT_MODEL_DIR / "bundles"


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value.strip())
    return cleaned.strip("_") or "fit_assist"


def build_model_bundle(
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    output_dir: str | Path = DEFAULT_BUNDLE_DIR,
    *,
    tasks: list[str] | None = None,
    bundle_name: str = "fit_assist",
    app_version: str = "0.1.0",
    dataset_id: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    selected = latest_models_by_task(model_dir, tasks=tasks)
    if not selected:
        raise ValueError("No local model artifacts are available to bundle.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bundle_id = f"{_safe_name(bundle_name)}_{timestamp}"
    bundle_path = Path(output_dir) / bundle_id
    bundle_path.mkdir(parents=True, exist_ok=False)

    bundled_models: list[dict[str, Any]] = []
    for task, info in sorted(selected.items()):
        model_path = Path(info["path"])
        copied_model = bundle_path / model_path.name
        shutil.copy2(model_path, copied_model)
        copied_metrics = None
        if info.get("metrics_path"):
            metrics_path = Path(info["metrics_path"])
            if metrics_path.exists():
                copied_metrics = bundle_path / metrics_path.name
                shutil.copy2(metrics_path, copied_metrics)
        bundled_models.append(
            {
                "task": task,
                "phase": info.get("phase"),
                "target": info.get("target"),
                "model_file": copied_model.name,
                "metrics_file": copied_metrics.name if copied_metrics is not None else None,
                "metrics": info.get("metrics"),
                "timestamp": info.get("timestamp"),
            }
        )

    manifest = {
        "bundle_id": bundle_id,
        "bundle_type": "fit_assist_models",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "app_version_min": app_version,
        "record_schema_version": SCHEMA_VERSION,
        "training_dataset_id": dataset_id,
        "safe_modes": ["advisory", "auto_fit_mode", "efficiency", "quality"],
        "models": bundled_models,
    }
    (bundle_path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle_path, manifest


def list_model_bundles(output_dir: str | Path = DEFAULT_BUNDLE_DIR) -> list[dict[str, Any]]:
    directory = Path(output_dir)
    if not directory.exists():
        return []
    bundles: list[dict[str, Any]] = []
    for manifest_path in directory.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        manifest["path"] = str(manifest_path.parent)
        bundles.append(manifest)
    return sorted(bundles, key=lambda item: item.get("created_at") or "", reverse=True)
