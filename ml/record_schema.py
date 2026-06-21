from __future__ import annotations

import copy
import math
from datetime import datetime
from typing import Any


SCHEMA_VERSION = 4
RECORD_TYPE = "fit_label"
COMPONENT_SERIES_KEYS = (
    "voltage",
    "measured",
    "fitted",
    "diode",
    "recombination",
    "diffusion",
    "ohmic",
    "nonohmic",
    "extra_current",
    "extended_nonohmic_total",
    "relative_error",
)
REQUIRED_COMPONENT_SERIES_KEYS = ("voltage", "measured", "fitted", "diode", "ohmic", "nonohmic")
COMPONENT_SERIES_COLUMNS = (
    {"key": "voltage", "label": "Voltage(V)"},
    {"key": "measured", "label": "Measured_Current(A)"},
    {"key": "fitted", "label": "Fitted_Current(A)"},
    {"key": "diode", "label": "Diode_Current(A)"},
    {"key": "recombination", "label": "Recombination_Current(A)"},
    {"key": "diffusion", "label": "Diffusion_Current(A)"},
    {"key": "ohmic", "label": "Ohmic_Current(A)"},
    {"key": "nonohmic", "label": "Nonohmic_Current(A)"},
    {"key": "extra_current", "label": "Extended_Branch_Current(A)"},
    {"key": "extended_nonohmic_total", "label": "Nonohmic_Plus_Extended_Current(A)"},
    {"key": "relative_error", "label": "Relative_Error(%)"},
)

QUALITY_VALUES = ("good", "acceptable", "poor", "reject")
CONFIDENCE_VALUES = ("high", "medium", "low")
HYPOTHESIS_VALUES = (
    "none",
    "leakage_reduced",
    "leakage_increased",
    "recombination_changed",
    "series_resistance_changed",
    "interface_passivation",
    "other",
)
EVIDENCE_VALUES = (
    "crack",
    "pinhole",
    "morphology",
    "interlayer",
    "reference_comparison",
    "device_structure",
)
ACCEPT_REASON_VALUES = (
    "global_error_ok",
    "reverse_region_ok",
    "forward_region_ok",
    "high_forward_region_ok",
    "visual_fit_ok",
    "parameter_plausible",
)
MAIN_ISSUE_VALUES = (
    "none",
    "reverse_mismatch",
    "forward_mismatch",
    "high_forward_mismatch",
    "boundary_hit",
    "parameter_coupling",
    "wrong_model",
    "other",
)
NEXT_ACTION_VALUES = (
    "review_nonohmic_exponent",
    "retry_weighted",
    "manual_refit_needed",
    "collect_more_evidence",
    "reject_for_training",
)
SAMPLE_ROLE_VALUES = ("unknown", "reference", "control", "treatment", "target")
FIT_STRATEGY_VALUES = ("auto", "quick_global", "robust_global", "weighted_regions", "staged_physical", "continuation_fit")
PRODUCT_FIT_MODE_VALUES = ("legacy", "fast_fit", "diagnostic_fit")
TRAINING_FAILURE_TAG_VALUES = ("shunt", "contact", "noise", "hysteresis", "outlier", "unstable")
MODEL_FEEDBACK_VALUES = ("uncertain", "model_correct", "model_wrong", "diagnostic_useful", "manual_override")


def _clean_text(value: Any, *, max_len: int = 500) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


def _choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    text = _clean_text(value, max_len=80).lower()
    return text if text in allowed else default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number


def _finite_number(value: Any, default: float | None = None) -> float | None:
    number = _number(value, default)
    return number if number is not None and math.isfinite(number) else default


def _int_number(value: Any, default: int = 0) -> int:
    number = _finite_number(value)
    return int(number) if number is not None else default


def _get_nested(mapping: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _get_any(mapping: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _get_nested(mapping, path)
        if value not in {None, ""}:
            return value
    return None


def _numeric_list(values: Any) -> list[float | None]:
    if values is None:
        return []
    try:
        raw_values = list(values)
    except TypeError:
        raw_values = [values]

    numbers: list[float | None] = []
    for value in raw_values:
        number = _number(value)
        numbers.append(number if number is not None and math.isfinite(number) else None)
    return numbers


def normalize_component_series(raw: dict[str, Any] | None) -> dict[str, Any]:
    source: Any = raw or {}
    if isinstance(source, dict) and isinstance(source.get("data"), dict):
        source = source["data"]
    if not isinstance(source, dict):
        source = {}

    data = {key: _numeric_list(source.get(key)) for key in COMPONENT_SERIES_KEYS}
    required_lengths = [len(data[key]) for key in REQUIRED_COMPONENT_SERIES_KEYS if data[key]]
    point_count = min(required_lengths) if len(required_lengths) == len(REQUIRED_COMPONENT_SERIES_KEYS) else 0
    if point_count:
        data = {key: values[:point_count] for key, values in data.items()}

    return {
        "point_count": point_count,
        "columns": list(COMPONENT_SERIES_COLUMNS),
        "data": data,
    }


def component_series_is_complete(component_series: dict[str, Any] | None) -> bool:
    if not isinstance(component_series, dict):
        return False
    data = component_series.get("data")
    if not isinstance(data, dict):
        return False
    point_count = int(component_series.get("point_count") or 0)
    if point_count <= 0:
        return False
    return all(len(data.get(key) or []) == point_count for key in REQUIRED_COMPONENT_SERIES_KEYS)


def _raw_result_series(raw_result: dict[str, Any]) -> Any:
    fit_series = _get_nested(raw_result, ("fit", "series"))
    if fit_series:
        return fit_series
    if isinstance(raw_result, dict):
        return raw_result.get("series")
    return None


def _fill_series_from_component_data(series: dict[str, Any], data: dict[str, Any]) -> None:
    for key in COMPONENT_SERIES_KEYS:
        if data.get(key) and not series.get(key):
            series[key] = data[key]


def _result_with_component_series(raw_result: dict[str, Any], component_series: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(raw_result or {})
    fit = result.get("fit")
    data = component_series.get("data") if isinstance(component_series, dict) else None
    if isinstance(data, dict):
        series = result.get("series")
        if not isinstance(series, dict):
            series = {}
            result["series"] = series
        _fill_series_from_component_data(series, data)
    if isinstance(fit, dict) and isinstance(data, dict):
        series = fit.get("series")
        if not isinstance(series, dict):
            series = {}
            fit["series"] = series
        _fill_series_from_component_data(series, data)
    return result


def _text_list(values: Any, allowed: tuple[str, ...] | None = None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        raw_values = [values]
    else:
        try:
            raw_values = list(values)
        except TypeError:
            raw_values = [values]

    cleaned: list[str] = []
    for value in raw_values:
        text = _clean_text(value, max_len=80).lower()
        if not text:
            continue
        if allowed is not None and text not in allowed:
            continue
        if text not in cleaned:
            cleaned.append(text)
    return cleaned


def normalize_labels(raw: dict[str, Any] | None) -> dict[str, Any]:
    labels = raw or {}
    return {
        "accepted": _bool(labels.get("accepted")),
        "manual_adjusted": _bool(labels.get("manual_adjusted")),
        "quality": _choice(labels.get("quality"), QUALITY_VALUES, "acceptable"),
        "confidence": _choice(labels.get("confidence"), CONFIDENCE_VALUES, "medium"),
        "hypothesis": _choice(labels.get("hypothesis"), HYPOTHESIS_VALUES, "none"),
        "external_evidence": _text_list(labels.get("external_evidence"), EVIDENCE_VALUES),
        "accept_reasons": _text_list(labels.get("accept_reasons"), ACCEPT_REASON_VALUES),
        "main_issue": _choice(labels.get("main_issue"), MAIN_ISSUE_VALUES, "none"),
        "next_actions": _text_list(labels.get("next_actions"), NEXT_ACTION_VALUES),
        "notes": _clean_text(labels.get("notes"), max_len=3000),
    }


def normalize_training_context(raw: dict[str, Any] | None) -> dict[str, Any]:
    context = raw if isinstance(raw, dict) else {}
    device_area = _finite_number(context.get("device_area_mm2"))
    if device_area is not None and device_area <= 0:
        device_area = None
    return {
        "device_area_mm2": device_area,
        "batch_tag": _clean_text(context.get("batch_tag"), max_len=120),
        "failure_tags": _text_list(context.get("failure_tags"), TRAINING_FAILURE_TAG_VALUES),
        "model_feedback": _choice(context.get("model_feedback"), MODEL_FEEDBACK_VALUES, "uncertain"),
        "process_note": _clean_text(context.get("process_note"), max_len=500),
    }


def normalize_sample_context(raw: dict[str, Any] | None) -> dict[str, Any]:
    context = raw or {}
    device_stack = context.get("device_stack") or []
    if not isinstance(device_stack, list):
        device_stack = []
    return {
        "sample_id": _clean_text(context.get("sample_id"), max_len=120),
        "batch": _clean_text(context.get("batch"), max_len=120),
        "role": _choice(context.get("role"), SAMPLE_ROLE_VALUES, "unknown"),
        "structure": _clean_text(context.get("structure"), max_len=500),
        "process": _clean_text(context.get("process"), max_len=500),
        "expected_outcome": _clean_text(context.get("expected_outcome"), max_len=500),
        "comparison_group": _clean_text(context.get("comparison_group"), max_len=120),
        "aging_days": _number(context.get("aging_days"), 0.0),
        "training_context": normalize_training_context(context.get("training_context")),
        "device_stack": [
            {
                "index": int(_number(layer.get("index"), idx) or idx),
                "role": _clean_text(layer.get("role"), max_len=80),
                "name": _clean_text(layer.get("name"), max_len=120),
                "thickness_nm": _clean_text(layer.get("thickness_nm"), max_len=80),
                "absorption_peak_nm": _clean_text(layer.get("absorption_peak_nm"), max_len=80),
            }
            for idx, layer in enumerate(device_stack)
            if isinstance(layer, dict) and _clean_text(layer.get("name"), max_len=120)
        ],
    }


def normalize_analysis_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    settings = raw or {}
    weights = settings.get("region_weights") or {}
    return {
        "product_fit_mode": _choice(settings.get("product_fit_mode"), PRODUCT_FIT_MODE_VALUES, "legacy"),
        "fit_strategy": _choice(settings.get("fit_strategy"), FIT_STRATEGY_VALUES, "quick_global"),
        "sweep_strategies": _bool(settings.get("sweep_strategies")),
        "scan_m": _bool(settings.get("scan_m")),
        "scan_n": _bool(settings.get("scan_n")),
        "use_best_m_after_scan": _bool(settings.get("use_best_m_after_scan", True)),
        "compare_models": _bool(settings.get("compare_models")),
        "post_fit_models": _bool(settings.get("post_fit_models")),
        "ml_assist_enabled": _bool(settings.get("ml_assist_enabled")),
        "ml_assist_mode": _clean_text(settings.get("ml_assist_mode"), max_len=80) or "advisory",
        "m_values": _clean_text(settings.get("m_values"), max_len=200),
        "n_values": _clean_text(settings.get("n_values"), max_len=200),
        "region_weights": {
            "reverse": _number(weights.get("reverse")),
            "near_zero": _number(weights.get("near_zero")),
            "forward": _number(weights.get("forward")),
            "high_forward": _number(weights.get("high_forward")),
        },
    }


def normalize_ml_assist(raw: dict[str, Any] | None) -> dict[str, Any]:
    assist = raw or {}
    suggested = assist.get("suggested_overrides") if isinstance(assist.get("suggested_overrides"), dict) else {}
    applied = assist.get("applied_overrides") if isinstance(assist.get("applied_overrides"), dict) else {}
    models = assist.get("models") if isinstance(assist.get("models"), dict) else {}
    similar = assist.get("similar") if isinstance(assist.get("similar"), dict) else {}
    return {
        "enabled": _bool(assist.get("enabled")),
        "mode": _clean_text(assist.get("mode"), max_len=80) or "advisory",
        "status": _clean_text(assist.get("status"), max_len=80),
        "phase": _clean_text(assist.get("phase"), max_len=80),
        "policy_version": _int_number(assist.get("policy_version"), 0),
        "suggested_product_fit_mode": _clean_text(suggested.get("product_fit_mode"), max_len=80),
        "applied_product_fit_mode": _clean_text(applied.get("product_fit_mode"), max_len=80),
        "model_status": _clean_text(models.get("status"), max_len=80),
        "model_prediction_count": len(models.get("predictions") or {}) if isinstance(models.get("predictions"), dict) else 0,
        "similar_status": _clean_text(similar.get("status"), max_len=80),
        "similar_record_count": _int_number(similar.get("record_count"), 0),
        "messages": _text_list(assist.get("messages")),
        "raw": copy.deepcopy(assist),
    }


def _summary_stats(raw: dict[str, Any] | None) -> dict[str, float | None]:
    stats = raw or {}
    return {
        "mean": _finite_number(stats.get("mean")),
        "max": _finite_number(stats.get("max")),
        "median": _finite_number(stats.get("median")),
        "included_points": _finite_number(stats.get("included_points")),
    }


def _series_point_count(series: Any) -> int:
    if not isinstance(series, dict):
        return 0
    lengths = []
    for key in ("voltage", "measured", "fitted"):
        values = series.get(key)
        if not values:
            return 0
        try:
            lengths.append(len(values))
        except TypeError:
            return 0
    return min(lengths) if lengths else 0


def summarize_selected_result(result: dict[str, Any] | None) -> dict[str, Any]:
    source = result or {}
    fit = source.get("fit") if isinstance(source.get("fit"), dict) else {}
    diagnostics = fit.get("diagnostics") if isinstance(fit.get("diagnostics"), dict) else {}
    selection = source.get("candidate_selection") if isinstance(source.get("candidate_selection"), dict) else {}
    model_context = source.get("model_context") if isinstance(source.get("model_context"), dict) else {}
    return {
        "display_mode": _clean_text(source.get("display_mode"), max_len=80) or "fit",
        "source": _clean_text(
            selection.get("source")
            or model_context.get("display_fit_source")
            or diagnostics.get("display_fit_source")
            or "selected_fit",
            max_len=120,
        ),
        "label": _clean_text(selection.get("label"), max_len=200),
        "candidate_index": _int_number(selection.get("index"), -1),
        "candidate_rank": _int_number(selection.get("rank"), 0),
        "evaluator_kind": _clean_text(source.get("evaluator_kind"), max_len=120),
        "manual_adjusted": _bool(diagnostics.get("manual_adjusted")),
        "n": _finite_number(fit.get("n")),
        "m": _finite_number(fit.get("m")),
        "stats": _summary_stats(fit.get("stats") if isinstance(fit.get("stats"), dict) else {}),
        "series_point_count": _series_point_count(fit.get("series") or source.get("series")),
    }


def _candidate_series(candidate: dict[str, Any]) -> Any:
    fit = candidate.get("fit")
    if isinstance(fit, dict):
        series = fit.get("series")
        if series:
            return series
    return candidate.get("series")


def summarize_candidate(candidate: dict[str, Any], index: int) -> dict[str, Any]:
    fit = candidate.get("fit") if isinstance(candidate.get("fit"), dict) else {}
    manual_capability = candidate.get("manual_capability") if isinstance(candidate.get("manual_capability"), dict) else {}
    point_count = _series_point_count(_candidate_series(candidate))
    return {
        "index": index,
        "rank": _int_number(candidate.get("rank"), index + 1),
        "source": _clean_text(candidate.get("source"), max_len=120),
        "label": _clean_text(candidate.get("label"), max_len=200),
        "reason": _clean_text(candidate.get("reason"), max_len=500),
        "is_primary": _bool(candidate.get("is_primary")),
        "diagnostic_only": _bool(candidate.get("diagnostic_only")),
        "promotable": _bool(candidate.get("promotable")),
        "can_evaluate_manually": _bool(manual_capability.get("can_evaluate")),
        "evaluator_kind": _clean_text(candidate.get("evaluator_kind") or manual_capability.get("evaluator_kind"), max_len=120),
        "has_renderable_fit": bool(fit and point_count > 0),
        "series_point_count": point_count,
        "n": _finite_number(candidate.get("n") if candidate.get("n") is not None else fit.get("n")),
        "m": _finite_number(candidate.get("m") if candidate.get("m") is not None else fit.get("m")),
        "stats": _summary_stats(candidate.get("stats") if isinstance(candidate.get("stats"), dict) else fit.get("stats")),
    }


def summarize_candidate_context(result: dict[str, Any] | None) -> dict[str, Any]:
    source = result or {}
    raw_candidates = source.get("candidates") if isinstance(source.get("candidates"), list) else []
    candidates = [
        summarize_candidate(candidate, index)
        for index, candidate in enumerate(raw_candidates)
        if isinstance(candidate, dict)
    ]
    selected = summarize_selected_result(source)
    primary = next((item for item in candidates if item.get("is_primary")), {})
    top = candidates[0] if candidates else {}
    return {
        "selected": {
            "source": selected.get("source"),
            "label": selected.get("label"),
            "candidate_index": selected.get("candidate_index"),
            "candidate_rank": selected.get("candidate_rank"),
            "display_mode": selected.get("display_mode"),
        },
        "candidate_count": len(candidates),
        "renderable_count": sum(1 for item in candidates if item.get("has_renderable_fit")),
        "diagnostic_only_count": sum(1 for item in candidates if item.get("diagnostic_only")),
        "promotable_count": sum(1 for item in candidates if item.get("promotable")),
        "primary_rank": primary.get("rank"),
        "top_candidate": {
            "source": top.get("source"),
            "label": top.get("label"),
            "rank": top.get("rank"),
            "mean": _get_nested(top, ("stats", "mean")) if top else None,
            "max": _get_nested(top, ("stats", "max")) if top else None,
        },
        "candidates": candidates,
    }


def normalize_record_payload(
    payload: dict[str, Any],
    *,
    record_id: str,
    saved_at: str | None = None,
) -> dict[str, Any]:
    timestamp = saved_at or datetime.now().isoformat(timespec="seconds")
    raw_result = payload.get("result") or {}
    run_snapshot = copy.deepcopy(payload.get("run_snapshot") or raw_result.get("run_snapshot") or {})
    component_series = normalize_component_series(
        payload.get("component_series") or _raw_result_series(raw_result)
    )
    result = _result_with_component_series(raw_result, component_series)
    labels = normalize_labels(payload.get("labels"))
    selected_result = summarize_selected_result(result)
    candidate_context = summarize_candidate_context(result)
    ml_assist = normalize_ml_assist(payload.get("ml_assist") or result.get("ml_assist"))
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": RECORD_TYPE,
        "record_id": record_id,
        "created_at": _clean_text(payload.get("created_at"), max_len=80) or timestamp,
        "saved_at": timestamp,
        "source": "web_app",
        "data_selection": payload.get("data_selection") or {},
        "sample_context": normalize_sample_context(payload.get("sample_context")),
        "analysis_settings": normalize_analysis_settings(payload.get("analysis_settings")),
        "manual_parameters": payload.get("manual_parameters") or {},
        "manual_history": payload.get("manual_history") or [],
        "fit_delta": payload.get("fit_delta") or {},
        "training_summary": payload.get("training_summary") or {},
        "run_snapshot": run_snapshot,
        "component_series": component_series,
        "labels": labels,
        "human_labels": labels,
        "selected_result": selected_result,
        "candidate_context": candidate_context,
        "ml_assist": ml_assist,
        "result": result,
    }
