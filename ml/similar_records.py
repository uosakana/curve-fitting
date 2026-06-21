from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from ml.record_features import DEFAULT_RECORD_DIR, flatten_record, load_records
from ml.training_tasks import CURVE_FEATURES


POSTFIT_DISTANCE_FEATURES = CURVE_FEATURES + (
    "mean_error",
    "max_error",
    "median_error",
    "negative_mean_error",
    "positive_mean_error",
    "reverse_mean_error",
    "near_zero_mean_error",
    "forward_mean_error",
    "high_forward_mean_error",
    "boundary_hit_count",
    "warning_count",
)


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _record_for_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if result is None:
        if isinstance(payload.get("series"), dict):
            result = {"series": payload["series"], "fit": {"series": payload["series"]}}
        else:
            result = payload
    return {
        "record_id": "current",
        "saved_at": None,
        "data_selection": payload.get("data_selection") or {},
        "sample_context": payload.get("sample_context") or {},
        "analysis_settings": payload.get("analysis_settings") or {},
        "labels": payload.get("labels") or {},
        "result": result,
    }


def _candidate_rows(record_dir: str | Path, include_rejected: bool) -> list[dict[str, Any]]:
    rows = [flatten_record(record) for record in load_records(record_dir)]
    if include_rejected:
        return rows
    return [
        row
        for row in rows
        if row.get("accepted") or row.get("quality") in {"good", "acceptable", "poor"}
    ]


def _distance_features(phase: str) -> tuple[str, ...]:
    return POSTFIT_DISTANCE_FEATURES if phase == "postfit" else CURVE_FEATURES


def _feature_scales(rows: list[dict[str, Any]], features: tuple[str, ...]) -> dict[str, float]:
    scales: dict[str, float] = {}
    for key in features:
        numeric = np.array(
            [value for value in (_as_float(row.get(key)) for row in rows) if value is not None],
            dtype=float,
        )
        if numeric.size < 2:
            scales[key] = 1.0
            continue
        spread = float(np.nanpercentile(numeric, 75) - np.nanpercentile(numeric, 25))
        scales[key] = spread if spread > 0.0 else float(np.nanstd(numeric) or 1.0)
    return scales


def _distance(current: dict[str, Any], candidate: dict[str, Any], features: tuple[str, ...], scales: dict[str, float]) -> float:
    total = 0.0
    count = 0
    for key in features:
        a = _as_float(current.get(key))
        b = _as_float(candidate.get(key))
        if a is None or b is None:
            continue
        scale = max(scales.get(key, 1.0), 1e-12)
        total += ((a - b) / scale) ** 2
        count += 1
    if count == 0:
        return float("inf")
    return float(np.sqrt(total / count))


def _mode(values: list[Any]) -> Any:
    clean = [value for value in values if value not in {None, ""}]
    if not clean:
        return None
    return Counter(clean).most_common(1)[0][0]


def _median(values: list[Any]) -> float | None:
    clean = [value for value in (_as_float(value) for value in values) if value is not None]
    if not clean:
        return None
    return float(np.median(clean))


def _counts(values: list[Any]) -> dict[str, int]:
    return {
        str(key): int(count)
        for key, count in Counter(value for value in values if value not in {None, ""}).items()
    }


def _neighbor_payload(row: dict[str, Any], distance: float) -> dict[str, Any]:
    return {
        "distance": distance,
        "record_id": row.get("record_id"),
        "saved_at": row.get("saved_at"),
        "sample_id": row.get("sample_id"),
        "sample_role": row.get("sample_role"),
        "comparison_group": row.get("comparison_group"),
        "quality": row.get("quality"),
        "confidence": row.get("confidence"),
        "hypothesis": row.get("hypothesis"),
        "product_fit_mode": row.get("product_fit_mode"),
        "fit_strategy": row.get("fit_strategy"),
        "selected_result_source": row.get("selected_result_source"),
        "scan_m": row.get("scan_m"),
        "scan_n": row.get("scan_n"),
        "m": row.get("m"),
        "n": row.get("n"),
        "mean_error": row.get("mean_error"),
        "max_error": row.get("max_error"),
        "worst_region": row.get("worst_region"),
        "record_path": row.get("record_path"),
    }


def _risk_notes(current: dict[str, Any], neighbors: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    current_worst = current.get("worst_region")
    if current_worst:
        notes.append(f"Current worst-error region is {current_worst}.")
    region_counts = Counter(row.get("worst_region") for row in neighbors if row.get("worst_region"))
    if region_counts:
        likely_region, count = region_counts.most_common(1)[0]
        notes.append(f"Similar records most often struggled in {likely_region} ({count}/{len(neighbors)}).")
    current_mean = _as_float(current.get("mean_error"))
    neighbor_mean = _median([row.get("mean_error") for row in neighbors])
    if current_mean is not None and neighbor_mean is not None and current_mean > neighbor_mean * 1.5:
        notes.append("Current mean error is higher than similar records; inspect weighting, candidates, or manual adjustment.")
    return notes


def summarize_neighbors(current: dict[str, Any], neighbors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "quality_counts": _counts([row.get("quality") for row in neighbors]),
        "hypothesis_counts": _counts([row.get("hypothesis") for row in neighbors]),
        "product_fit_mode_counts": _counts([row.get("product_fit_mode") for row in neighbors]),
        "fit_strategy_counts": _counts([row.get("fit_strategy") for row in neighbors]),
        "worst_region_counts": _counts([row.get("worst_region") for row in neighbors]),
        "recommended_product_fit_mode": _mode([row.get("product_fit_mode") for row in neighbors]),
        "recommended_fit_strategy": _mode([row.get("fit_strategy") for row in neighbors]),
        "recommended_hypothesis": _mode([row.get("hypothesis") for row in neighbors]),
        "median_m": _median([row.get("m") for row in neighbors]),
        "median_mean_error": _median([row.get("mean_error") for row in neighbors]),
        "risk_notes": _risk_notes(current, neighbors),
    }


def find_similar_records(
    payload: dict[str, Any],
    record_dir: str | Path = DEFAULT_RECORD_DIR,
    *,
    phase: str = "postfit",
    limit: int = 5,
    include_rejected: bool = False,
) -> dict[str, Any]:
    normalized_phase = phase.strip().lower()
    if normalized_phase not in {"prefit", "postfit"}:
        raise ValueError("phase must be prefit or postfit.")

    current = flatten_record(_record_for_payload(payload))
    rows = _candidate_rows(record_dir, include_rejected)
    if not rows:
        return {
            "ok": True,
            "status": "insufficient_records",
            "phase": normalized_phase,
            "message": "No labeled records are available yet. Save records first.",
            "neighbors": [],
            "summary": {},
            "record_count": 0,
        }

    features = _distance_features(normalized_phase)
    scales = _feature_scales(rows + [current], features)
    ranked = sorted(
        (_neighbor_payload(row, _distance(current, row, features, scales)) for row in rows),
        key=lambda row: row["distance"],
    )
    neighbors = ranked[: max(1, int(limit))]
    return {
        "ok": True,
        "status": "ready",
        "phase": normalized_phase,
        "message": f"Found {len(neighbors)} similar record(s) from {len(rows)} labeled record(s).",
        "features_used": list(features),
        "current": {
            "curve_points": current.get("curve_points"),
            "quality": current.get("quality"),
            "product_fit_mode": current.get("product_fit_mode"),
            "mean_error": current.get("mean_error"),
            "worst_region": current.get("worst_region"),
        },
        "neighbors": neighbors,
        "summary": summarize_neighbors(current, neighbors),
        "record_count": len(rows),
    }
