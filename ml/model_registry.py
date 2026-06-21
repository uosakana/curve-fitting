from __future__ import annotations

import json
import pickle
import re
from pathlib import Path
from typing import Any

from ml.training_tasks import TASK_DEFS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_DIR = ROOT / "app_data" / "models"
MODEL_NAME_RE = re.compile(r"^(?P<task>[a-z_]+)_random_forest_(?P<timestamp>\d{8}_\d{6})\.pkl$")


def _metrics_summary(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        metrics = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {
        "accuracy": metrics.get("accuracy"),
        "balanced_accuracy": metrics.get("balanced_accuracy"),
        "train_count": metrics.get("train_count"),
        "eval_count": metrics.get("eval_count"),
        "class_counts": metrics.get("class_counts"),
        "model_type": metrics.get("model_type"),
    }


def model_info(path: Path) -> dict[str, Any] | None:
    match = MODEL_NAME_RE.match(path.name)
    if not match:
        return None
    task = match.group("task")
    task_def = TASK_DEFS.get(task)
    if task_def is None:
        return None
    metrics = path.with_name(f"{path.stem}_metrics.json")
    return {
        "task": task,
        "phase": task_def.phase,
        "target": task_def.target,
        "description": task_def.description,
        "path": str(path),
        "metrics_path": str(metrics) if metrics.exists() else None,
        "metrics": _metrics_summary(metrics),
        "timestamp": match.group("timestamp"),
        "modified_at": path.stat().st_mtime,
    }


def list_local_models(
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    *,
    phase: str | None = None,
    task: str | None = None,
) -> list[dict[str, Any]]:
    directory = Path(model_dir)
    if not directory.exists():
        return []
    phase_filter = phase.strip().lower() if phase else None
    task_filter = task.strip().lower() if task else None
    models = []
    for path in directory.glob("*_random_forest_*.pkl"):
        info = model_info(path)
        if info is None:
            continue
        if phase_filter and info["phase"] != phase_filter:
            continue
        if task_filter and info["task"] != task_filter:
            continue
        models.append(info)
    return sorted(models, key=lambda item: (item["task"], item["timestamp"]), reverse=True)


def latest_models_by_task(
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    *,
    phase: str | None = None,
    tasks: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    task_filter = {task.strip().lower() for task in tasks} if tasks is not None else None
    latest: dict[str, dict[str, Any]] = {}
    for info in list_local_models(model_dir, phase=phase):
        task = info["task"]
        if task_filter is not None and task not in task_filter:
            continue
        current = latest.get(task)
        if current is None or info["timestamp"] > current["timestamp"]:
            latest[task] = info
    return latest


def load_model_artifact(path: str | Path) -> dict[str, Any]:
    with Path(path).open("rb") as handle:
        artifact = pickle.load(handle)
    if not isinstance(artifact, dict) or "pipeline" not in artifact:
        raise ValueError(f"Model artifact is not valid: {path}")
    return artifact
