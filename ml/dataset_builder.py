from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ml.record_features import DEFAULT_DATASET_DIR, DEFAULT_RECORD_DIR, flatten_record, load_records


FEATURE_COLUMNS = (
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
    "mean_error",
    "max_error",
    "median_error",
    "negative_mean_error",
    "positive_mean_error",
    "reverse_mean_error",
    "near_zero_mean_error",
    "forward_mean_error",
    "high_forward_mean_error",
    "diode_component_pct",
    "ohmic_component_pct",
    "nonohmic_component_pct",
    "negative_nonohmic_to_ohmic",
    "boundary_hit_count",
    "warning_count",
    "advice_count",
    "selected_series_point_count",
    "candidate_count",
    "candidate_renderable_count",
    "candidate_diagnostic_only_count",
    "candidate_promotable_count",
    "primary_candidate_rank",
    "top_candidate_rank",
    "top_candidate_mean_error",
    "top_candidate_max_error",
    "run_points",
    "run_voltage_min",
    "run_voltage_max",
    "run_voltage_span",
    "run_ranked_candidate_count",
    "run_strategy_candidate_count",
    "run_nm_profile_candidate_count",
    "run_m_model_candidate_count",
    "run_post_fit_candidate_count",
)

LABEL_COLUMNS = (
    "accepted",
    "quality",
    "confidence",
    "hypothesis",
    "product_fit_mode",
    "fit_strategy",
    "selected_display_mode",
    "selected_result_source",
    "selected_result_label",
    "selected_candidate_rank",
    "ml_assist_enabled",
    "ml_assist_mode",
    "ml_assist_status",
    "ml_assist_suggested_product_fit_mode",
    "ml_assist_applied_product_fit_mode",
    "run_snapshot_id",
    "run_product_fit_mode",
    "run_current_model_source",
    "run_current_model_label",
    "sweep_strategies",
    "scan_m",
    "scan_n",
    "compare_models",
    "post_fit_models",
    "m",
    "best_scan_m",
    "worst_region",
    "top_advice_level",
    "top_advice_title",
)

CONTEXT_COLUMNS = (
    "sample_id",
    "sample_batch",
    "sample_role",
    "sample_structure",
    "sample_process",
    "expected_outcome",
    "comparison_group",
    "external_evidence",
)


def _split_bucket(group_key: str, train_ratio: float, val_ratio: float) -> str:
    digest = hashlib.sha256(group_key.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) / 0xFFFFFFFF
    if value < train_ratio:
        return "train"
    if value < train_ratio + val_ratio:
        return "val"
    return "test"


def _group_key(row: dict[str, Any]) -> str:
    for key in ("comparison_group", "sample_batch", "sample_id", "record_id"):
        value = row.get(key)
        if value not in {None, ""}:
            return f"{key}:{value}"
    return "unknown"


def _is_candidate(row: dict[str, Any], include_rejected: bool) -> bool:
    if include_rejected:
        return True
    if row.get("accepted"):
        return True
    return row.get("quality") in {"good", "acceptable"}


def _fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "dataset_split",
        "record_id",
        "saved_at",
        *CONTEXT_COLUMNS,
        *LABEL_COLUMNS,
        *FEATURE_COLUMNS,
        "source_path",
        "current_range",
        "cell_range",
        "voltage_start",
        "voltage_end",
        "voltage_step",
        "record_path",
    ]
    names = [name for name in preferred if any(name in row for row in rows)]
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    return names or ["record_id"]


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_training_dataset(
    record_dir: str | Path = DEFAULT_RECORD_DIR,
    output_dir: str | Path = DEFAULT_DATASET_DIR,
    *,
    include_rejected: bool = False,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
) -> tuple[Path, Path, dict[str, Any]]:
    if train_ratio <= 0.0 or val_ratio < 0.0 or train_ratio + val_ratio >= 1.0:
        raise ValueError("Expected 0 < train_ratio and train_ratio + val_ratio < 1.")

    raw_records = load_records(record_dir)
    rows = [flatten_record(record) for record in raw_records]
    candidates = [row for row in rows if _is_candidate(row, include_rejected)]

    for row in candidates:
        row["dataset_split"] = _split_bucket(_group_key(row), train_ratio, val_ratio)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_id = f"fit_dataset_{timestamp}"
    csv_path = output / f"{dataset_id}.csv"
    manifest_path = output / f"{dataset_id}_manifest.json"

    fieldnames = _fieldnames(candidates)
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in candidates:
            writer.writerow(row)

    manifest = {
        "dataset_id": dataset_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "record_dir": str(Path(record_dir)),
        "output_csv": str(csv_path),
        "schema": {
            "feature_columns": list(FEATURE_COLUMNS),
            "label_columns": list(LABEL_COLUMNS),
            "context_columns": list(CONTEXT_COLUMNS),
        },
        "filters": {
            "include_rejected": bool(include_rejected),
            "default_candidate_rule": "accepted=true OR quality in {good, acceptable}",
        },
        "split": {
            "method": "deterministic_group_hash",
            "group_priority": ["comparison_group", "sample_batch", "sample_id", "record_id"],
            "train_ratio": float(train_ratio),
            "val_ratio": float(val_ratio),
            "test_ratio": float(1.0 - train_ratio - val_ratio),
            "counts": _count_by(candidates, "dataset_split"),
        },
        "counts": {
            "raw_records": len(raw_records),
            "candidate_records": len(candidates),
            "quality": _count_by(candidates, "quality"),
            "hypothesis": _count_by(candidates, "hypothesis"),
            "fit_strategy": _count_by(candidates, "fit_strategy"),
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, manifest_path, manifest
