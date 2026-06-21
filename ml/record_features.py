from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ml.record_schema import summarize_candidate_context, summarize_selected_result


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORD_DIR = ROOT / "app_data" / "records"
DEFAULT_DATASET_DIR = ROOT / "app_data" / "datasets"


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def _as_array(values: Any) -> np.ndarray:
    if values is None:
        return np.array([], dtype=float)
    return np.asarray(values, dtype=float).reshape(-1)


def _get(mapping: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = mapping
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _log_slope(voltage: np.ndarray, current: np.ndarray, mask: np.ndarray) -> float | None:
    selected = mask & np.isfinite(voltage) & np.isfinite(current) & (np.abs(current) > 0.0)
    if int(np.sum(selected)) < 3:
        return None
    x = voltage[selected]
    y = np.log10(np.abs(current[selected]))
    try:
        slope, _ = np.polyfit(x, y, 1)
    except Exception:
        return None
    return float(slope)


def curve_features(series: dict[str, Any]) -> dict[str, Any]:
    voltage = _as_array(series.get("voltage"))
    measured = _as_array(series.get("measured"))
    if voltage.size == 0 or measured.size == 0 or voltage.size != measured.size:
        return {
            "curve_points": 0,
            "voltage_min": None,
            "voltage_max": None,
            "voltage_span": None,
            "current_abs_min": None,
            "current_abs_max": None,
            "current_abs_log_span": None,
            "reverse_points": 0,
            "forward_points": 0,
            "current_sign_changes": 0,
            "reverse_log_slope": None,
            "forward_log_slope": None,
        }

    finite = np.isfinite(voltage) & np.isfinite(measured)
    abs_current = np.abs(measured[finite])
    positive_abs = abs_current[abs_current > 0.0]
    signs = np.sign(measured[finite])
    nonzero_signs = signs[signs != 0.0]
    sign_changes = int(np.sum(nonzero_signs[1:] != nonzero_signs[:-1])) if nonzero_signs.size > 1 else 0

    if positive_abs.size:
        current_min = float(np.min(positive_abs))
        current_max = float(np.max(positive_abs))
        log_span = float(np.log10(current_max) - np.log10(current_min)) if current_min > 0.0 else None
    else:
        current_min = None
        current_max = None
        log_span = None

    return {
        "curve_points": int(voltage.size),
        "voltage_min": float(np.min(voltage[finite])) if np.any(finite) else None,
        "voltage_max": float(np.max(voltage[finite])) if np.any(finite) else None,
        "voltage_span": float(np.max(voltage[finite]) - np.min(voltage[finite])) if np.any(finite) else None,
        "current_abs_min": current_min,
        "current_abs_max": current_max,
        "current_abs_log_span": log_span,
        "reverse_points": int(np.sum((voltage < 0.0) & finite)),
        "forward_points": int(np.sum((voltage > 0.0) & finite)),
        "current_sign_changes": sign_changes,
        "reverse_log_slope": _log_slope(voltage, measured, voltage < -0.05),
        "forward_log_slope": _log_slope(voltage, measured, voltage > 0.05),
    }


def load_records(record_dir: str | Path = DEFAULT_RECORD_DIR) -> list[dict[str, Any]]:
    directory = Path(record_dir)
    if not directory.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("fit_record_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        data["_record_path"] = str(path)
        records.append(data)
    return records


def flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    result = record.get("result") or {}
    fit = _get(record, "result.fit", {}) or {}
    stats = fit.get("stats", {}) or {}
    diagnostics = fit.get("diagnostics", {}) or {}
    params = list(fit.get("params") or [])
    labels = record.get("labels", {}) or {}
    context = record.get("sample_context", {}) or {}
    training_context = context.get("training_context", {}) if isinstance(context.get("training_context"), dict) else {}
    training_summary = record.get("training_summary", {}) or {}
    fit_delta = record.get("fit_delta", {}) or {}
    settings = record.get("analysis_settings", {}) or {}
    weights = settings.get("region_weights", {}) or {}
    selected = record.get("selected_result") or summarize_selected_result(result)
    candidate_context = record.get("candidate_context") or summarize_candidate_context(result)
    top_candidate = candidate_context.get("top_candidate", {}) or {}
    run_snapshot = record.get("run_snapshot") or result.get("run_snapshot") or {}
    snapshot_data = run_snapshot.get("data", {}) if isinstance(run_snapshot.get("data"), dict) else {}
    snapshot_voltage = snapshot_data.get("voltage", {}) if isinstance(snapshot_data.get("voltage"), dict) else {}
    snapshot_analysis = run_snapshot.get("analysis", {}) if isinstance(run_snapshot.get("analysis"), dict) else {}
    snapshot_settings = snapshot_analysis.get("settings", {}) if isinstance(snapshot_analysis.get("settings"), dict) else {}
    snapshot_counts = snapshot_analysis.get("candidate_counts", {}) if isinstance(snapshot_analysis.get("candidate_counts"), dict) else {}
    snapshot_model = snapshot_analysis.get("current_model", {}) if isinstance(snapshot_analysis.get("current_model"), dict) else {}
    snapshot_engine = run_snapshot.get("engine", {}) if isinstance(run_snapshot.get("engine"), dict) else {}
    ml_assist = record.get("ml_assist", {}) or {}
    region = diagnostics.get("region_stats", {}) or {}
    component = diagnostics.get("component_percent", {}) or {}
    m_scan = _get(record, "result.m_scan", []) or []
    models = _get(record, "result.model_comparison", []) or []
    post_models = _get(record, "result.post_fit_models", []) or []
    advice = _get(record, "result.advice", []) or []
    best_scan = m_scan[0] if m_scan else {}
    best_model = models[0] if models else {}
    post_candidates = [
        item
        for item in post_models
        if item.get("name") not in {"base_reference", "core_window_base"} and item.get("status") == "ok"
    ]
    selected_post = next(
        (item for item in post_candidates if _get(item, "diagnostics.selected_for_replacement")),
        {},
    )
    best_post_bic = min(
        post_candidates,
        key=lambda item: _as_float(item.get("bic"), float("inf")) or float("inf"),
        default={},
    )
    best_post_mean = max(
        post_candidates,
        key=lambda item: _as_float(_get(item, "diagnostics.mean_improvement"), -float("inf")) or -float("inf"),
        default={},
    )
    core_window = next((item for item in post_models if item.get("name") == "core_window_base"), {})
    top_advice = advice[0] if advice else {}

    row: dict[str, Any] = {
        "record_id": record.get("record_id"),
        "saved_at": record.get("saved_at"),
        "record_path": record.get("_record_path"),
        "schema_version": record.get("schema_version"),
        "record_type": record.get("record_type"),
        "sample_id": context.get("sample_id"),
        "sample_batch": context.get("batch"),
        "sample_role": context.get("role"),
        "sample_structure": context.get("structure"),
        "sample_process": context.get("process"),
        "device_stack": json.dumps(context.get("device_stack") or [], ensure_ascii=False),
        "aging_days": _as_float(context.get("aging_days")),
        "expected_outcome": context.get("expected_outcome"),
        "comparison_group": context.get("comparison_group"),
        "device_area_mm2": _as_float(training_context.get("device_area_mm2")),
        "training_batch_tag": training_context.get("batch_tag"),
        "training_failure_tags": "|".join(training_context.get("failure_tags") or []),
        "training_model_feedback": training_context.get("model_feedback"),
        "training_process_note": training_context.get("process_note"),
        "manual_checkpoint_count": _as_float(training_summary.get("manual_checkpoint_count")),
        "recommended_training_use": training_summary.get("recommended_training_use"),
        "dominant_parameter_changes": json.dumps(training_summary.get("dominant_parameter_changes") or [], ensure_ascii=False),
        "fit_mean_delta": _as_float(_get(fit_delta, "stats_delta.mean")),
        "fit_max_delta": _as_float(_get(fit_delta, "stats_delta.max")),
        "accepted": bool(labels.get("accepted", False)),
        "manual_adjusted": bool(labels.get("manual_adjusted", False)),
        "quality": labels.get("quality"),
        "confidence": labels.get("confidence"),
        "hypothesis": labels.get("hypothesis"),
        "external_evidence": "|".join(labels.get("external_evidence") or []),
        "accept_reasons": "|".join(labels.get("accept_reasons") or []),
        "main_issue": labels.get("main_issue"),
        "next_actions": "|".join(labels.get("next_actions") or []),
        "label_notes": labels.get("notes"),
        "product_fit_mode": settings.get("product_fit_mode") or result.get("product_fit_mode") or "legacy",
        "fit_strategy": settings.get("fit_strategy") or diagnostics.get("strategy"),
        "sweep_strategies": bool(settings.get("sweep_strategies", False)),
        "scan_m": bool(settings.get("scan_m", False)),
        "scan_n": bool(settings.get("scan_n", False)),
        "compare_models": bool(settings.get("compare_models", False)),
        "post_fit_models": bool(settings.get("post_fit_models", False)),
        "ml_assist_enabled": bool(settings.get("ml_assist_enabled", False) or ml_assist.get("enabled", False)),
        "ml_assist_mode": settings.get("ml_assist_mode") or ml_assist.get("mode"),
        "ml_assist_status": ml_assist.get("status"),
        "ml_assist_suggested_product_fit_mode": ml_assist.get("suggested_product_fit_mode"),
        "ml_assist_applied_product_fit_mode": ml_assist.get("applied_product_fit_mode"),
        "ml_assist_model_status": ml_assist.get("model_status"),
        "ml_assist_model_prediction_count": _as_float(ml_assist.get("model_prediction_count"), 0.0),
        "ml_assist_similar_record_count": _as_float(ml_assist.get("similar_record_count"), 0.0),
        "run_snapshot_id": run_snapshot.get("snapshot_id"),
        "run_file_name": snapshot_data.get("file_name"),
        "run_source_mode": snapshot_data.get("source_mode"),
        "run_points": _as_float(snapshot_data.get("points")),
        "run_voltage_min": _as_float(snapshot_voltage.get("min")),
        "run_voltage_max": _as_float(snapshot_voltage.get("max")),
        "run_voltage_span": _as_float(snapshot_voltage.get("span")),
        "run_product_fit_mode": snapshot_settings.get("product_fit_mode"),
        "run_ranked_candidate_count": _as_float(snapshot_counts.get("ranked"), 0.0),
        "run_strategy_candidate_count": _as_float(snapshot_counts.get("strategy"), 0.0),
        "run_nm_profile_candidate_count": _as_float(snapshot_counts.get("nm_profile"), 0.0),
        "run_m_model_candidate_count": _as_float(snapshot_counts.get("m_models"), 0.0),
        "run_post_fit_candidate_count": _as_float(snapshot_counts.get("post_fit"), 0.0),
        "run_current_model_source": snapshot_model.get("source"),
        "run_current_model_label": snapshot_model.get("label"),
        "run_random_seed": _as_float(snapshot_engine.get("random_seed")),
        "m_values": settings.get("m_values"),
        "n_values": settings.get("n_values"),
        "reverse_weight": _as_float(weights.get("reverse")),
        "near_zero_weight": _as_float(weights.get("near_zero")),
        "forward_weight": _as_float(weights.get("forward")),
        "high_forward_weight": _as_float(weights.get("high_forward")),
        "selected_display_mode": selected.get("display_mode") or result.get("display_mode") or "fit",
        "selected_result_source": selected.get("source")
        or _get(record, "result.candidate_selection.source")
        or _get(record, "result.model_context.display_fit_source")
        or diagnostics.get("display_fit_source"),
        "selected_result_label": selected.get("label") or _get(record, "result.candidate_selection.label"),
        "selected_candidate_index": _as_float(selected.get("candidate_index")),
        "selected_candidate_rank": _as_float(selected.get("candidate_rank")),
        "selected_series_point_count": _as_float(selected.get("series_point_count")),
        "candidate_count": _as_float(candidate_context.get("candidate_count"), 0.0),
        "candidate_renderable_count": _as_float(candidate_context.get("renderable_count"), 0.0),
        "candidate_diagnostic_only_count": _as_float(candidate_context.get("diagnostic_only_count"), 0.0),
        "candidate_promotable_count": _as_float(candidate_context.get("promotable_count"), 0.0),
        "primary_candidate_rank": _as_float(candidate_context.get("primary_rank")),
        "top_candidate_source": top_candidate.get("source"),
        "top_candidate_label": top_candidate.get("label"),
        "top_candidate_rank": _as_float(top_candidate.get("rank")),
        "top_candidate_mean_error": _as_float(top_candidate.get("mean")),
        "top_candidate_max_error": _as_float(top_candidate.get("max")),
        "m": _as_float(fit.get("m")),
        "n": _as_float(fit.get("n")),
        "evaluator_kind": _get(record, "result.evaluator_kind"),
        "display_fit_source": _get(record, "result.model_context.display_fit_source") or diagnostics.get("display_fit_source"),
        "J0": _as_float(params[0] if len(params) > 0 else None),
        "Rs": _as_float(params[1] if len(params) > 1 else None),
        "Rsh": _as_float(params[2] if len(params) > 2 else None),
        "k": _as_float(params[3] if len(params) > 3 else None),
        "mean_error": _as_float(stats.get("mean")),
        "max_error": _as_float(stats.get("max")),
        "median_error": _as_float(stats.get("median")),
        "included_points": _as_float(stats.get("included_points")),
        "negative_mean_error": _as_float(stats.get("negative_mean")),
        "positive_mean_error": _as_float(stats.get("positive_mean")),
        "reverse_mean_error": _as_float(_get(region, "reverse.mean")),
        "near_zero_mean_error": _as_float(_get(region, "near_zero.mean")),
        "forward_mean_error": _as_float(_get(region, "forward.mean")),
        "high_forward_mean_error": _as_float(_get(region, "high_forward.mean")),
        "worst_region": region.get("worst_region"),
        "diode_component_pct": _as_float(component.get("diode")),
        "ohmic_component_pct": _as_float(component.get("ohmic")),
        "nonohmic_component_pct": _as_float(component.get("nonohmic")),
        "negative_nonohmic_to_ohmic": _as_float(diagnostics.get("negative_leakage_nonohmic_to_ohmic")),
        "boundary_hit_count": len(diagnostics.get("boundary_hits") or []),
        "warning_count": len(diagnostics.get("warnings") or []),
        "advice_count": len(advice),
        "top_advice_level": top_advice.get("level"),
        "top_advice_title": top_advice.get("title"),
        "best_scan_m": _as_float(best_scan.get("m")),
        "best_scan_mean_error": _as_float(_get(best_scan, "stats.mean")),
        "best_model_name": best_model.get("name"),
        "best_model_bic": _as_float(best_model.get("bic")),
        "selected_post_model_name": selected_post.get("name"),
        "selected_post_model_confidence": _get(selected_post, "diagnostics.physical_confidence"),
        "best_post_bic_model": best_post_bic.get("name"),
        "best_post_bic_delta": _as_float(_get(best_post_bic, "diagnostics.bic_improvement")),
        "best_post_mean_model": best_post_mean.get("name"),
        "best_post_mean_delta": _as_float(_get(best_post_mean, "diagnostics.mean_improvement")),
        "core_window_model_limited": bool(_get(core_window, "diagnostics.model_limited", False)),
        "core_window_failure_regions": "|".join(_get(core_window, "diagnostics.failure_regions", []) or []),
        "source_path": _get(record, "result.dataset.path") or _get(record, "data_selection.path"),
        "current_range": _get(record, "data_selection.current_range") or _get(record, "result.dataset.current_range"),
        "cell_range": _get(record, "data_selection.cell_range") or _get(record, "result.dataset.cell_range"),
        "voltage_start": _as_float(_get(record, "data_selection.voltage_start")),
        "voltage_end": _as_float(_get(record, "data_selection.voltage_end")),
        "voltage_step": _as_float(_get(record, "data_selection.voltage_step")),
    }
    row.update(curve_features(fit.get("series", {}) or result.get("series", {}) or _get(record, "component_series.data", {}) or {}))
    return row


def list_record_summaries(record_dir: str | Path = DEFAULT_RECORD_DIR) -> list[dict[str, Any]]:
    summaries = []
    for record in load_records(record_dir):
        row = flatten_record(record)
        summaries.append(
            {
                "record_id": row.get("record_id"),
                "saved_at": row.get("saved_at"),
                "accepted": row.get("accepted"),
                "quality": row.get("quality"),
                "confidence": row.get("confidence"),
                "hypothesis": row.get("hypothesis"),
                "sample_id": row.get("sample_id"),
                "sample_role": row.get("sample_role"),
                "comparison_group": row.get("comparison_group"),
                "product_fit_mode": row.get("product_fit_mode"),
                "fit_strategy": row.get("fit_strategy"),
                "selected_result_source": row.get("selected_result_source"),
                "m": row.get("m"),
                "mean_error": row.get("mean_error"),
                "max_error": row.get("max_error"),
                "worst_region": row.get("worst_region"),
                "record_path": row.get("record_path"),
            }
        )
    return sorted(summaries, key=lambda item: item.get("saved_at") or "", reverse=True)


def export_records_dataset(
    record_dir: str | Path = DEFAULT_RECORD_DIR,
    output_dir: str | Path = DEFAULT_DATASET_DIR,
) -> tuple[Path, int]:
    rows = [flatten_record(record) for record in load_records(record_dir)]
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output / f"fit_records_dataset_{timestamp}.csv"

    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    if not fieldnames:
        fieldnames = ["record_id"]

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path, len(rows)
