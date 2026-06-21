from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ml.dataset_builder import FEATURE_COLUMNS


CURVE_FEATURES = (
    "curve_points",
    "voltage_min",
    "voltage_max",
    "voltage_span",
    "current_abs_min",
    "current_abs_max",
    "current_abs_log_span",
    "reverse_points",
    "forward_points",
    "current_sign_changes",
    "reverse_log_slope",
    "forward_log_slope",
)

POST_FIT_FEATURES = tuple(name for name in FEATURE_COLUMNS if name not in CURVE_FEATURES)

CONTEXT_FEATURES = (
    "sample_role",
    "external_evidence",
)

POST_FIT_CATEGORICAL = (
    "product_fit_mode",
    "fit_strategy",
    "scan_m",
    "scan_n",
    "compare_models",
    "post_fit_models",
    "selected_display_mode",
    "selected_result_source",
    "top_candidate_source",
    "worst_region",
    "best_model_name",
    "top_advice_level",
    "top_advice_title",
)


@dataclass(frozen=True)
class TaskDefinition:
    name: str
    target: str
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...]
    phase: str
    description: str

    @property
    def feature_columns(self) -> tuple[str, ...]:
        return self.numeric_features + self.categorical_features


TASK_DEFS: dict[str, TaskDefinition] = {
    "strategy": TaskDefinition(
        name="strategy",
        target="product_fit_mode",
        numeric_features=CURVE_FEATURES,
        categorical_features=CONTEXT_FEATURES,
        phase="prefit",
        description="Predict whether Fast Fit or Diagnostic Fit is likely to be useful from curve shape and sample context.",
    ),
    "scan_m": TaskDefinition(
        name="scan_m",
        target="scan_m",
        numeric_features=CURVE_FEATURES,
        categorical_features=CONTEXT_FEATURES,
        phase="prefit",
        description="Predict whether exponent scanning is likely to be useful from curve shape and sample context.",
    ),
    "quality": TaskDefinition(
        name="quality",
        target="quality",
        numeric_features=CURVE_FEATURES + POST_FIT_FEATURES,
        categorical_features=CONTEXT_FEATURES + POST_FIT_CATEGORICAL,
        phase="postfit",
        description="Predict fit quality/risk after a fit has been evaluated.",
    ),
    "hypothesis": TaskDefinition(
        name="hypothesis",
        target="hypothesis",
        numeric_features=CURVE_FEATURES + POST_FIT_FEATURES,
        categorical_features=CONTEXT_FEATURES + POST_FIT_CATEGORICAL,
        phase="postfit",
        description="Assist hypothesis selection from curve diagnostics and sample context.",
    ),
}


def tasks_for_phase(phase: str | None = None) -> list[str]:
    if phase is None:
        return list(TASK_DEFS)
    normalized = phase.strip().lower()
    return [name for name, task in TASK_DEFS.items() if task.phase == normalized]


def task_payload(task: TaskDefinition) -> dict[str, Any]:
    return {
        "name": task.name,
        "target": task.target,
        "phase": task.phase,
        "description": task.description,
        "numeric_features": list(task.numeric_features),
        "categorical_features": list(task.categorical_features),
    }


def list_task_payloads(phase: str | None = None) -> list[dict[str, Any]]:
    names = tasks_for_phase(phase)
    return [task_payload(TASK_DEFS[name]) for name in names]
