from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.api_utils import (
    analysis_payload,
    fit_payload,
    none_if_blank,
    optional_float,
    params_meta_from_values,
    parse_m_values,
    parse_n_values,
    parse_params,
    run_snapshot_payload,
)
from app_services.product_modes import apply_product_fit_mode, normalize_product_fit_mode
from data_io import DataSelection, load_dataset
from data_io.data_source import DEFAULT_VOLTAGE_END, DEFAULT_VOLTAGE_START, DEFAULT_VOLTAGE_STEP
from fit.core import clone_config, evaluate_params
from fit.workflow import AnalysisOptions, run_analysis
from ml.fit_assist import build_prefit_ml_assist


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _float_value(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    return float(value)


def _bool_value(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_selected_dataset(file_path: str | Path, request: Mapping[str, Any]):
    return load_dataset(
        DataSelection(
            path=file_path,
            sheet_name=none_if_blank(_text(request.get("sheet_name"))),
            cell_range=none_if_blank(_text(request.get("cell_range"))),
            voltage_range=none_if_blank(_text(request.get("voltage_range"))),
            current_range=none_if_blank(_text(request.get("current_range"))),
            voltage_start=_float_value(request.get("voltage_start"), DEFAULT_VOLTAGE_START),
            voltage_end=_float_value(request.get("voltage_end"), DEFAULT_VOLTAGE_END),
            voltage_step=_float_value(request.get("voltage_step"), DEFAULT_VOLTAGE_STEP),
        )
    )


def _analysis_settings(request: Mapping[str, Any]) -> dict[str, Any]:
    settings = {
        "mode": _text(request.get("mode"), "fit"),
        "fit_strategy": _text(request.get("fit_strategy"), "quick_global"),
        "sweep_strategies": _bool_value(request.get("sweep_strategies"), False),
        "reverse_weight": _float_value(request.get("reverse_weight"), 1.5),
        "near_zero_weight": _float_value(request.get("near_zero_weight"), 0.5),
        "forward_weight": _float_value(request.get("forward_weight"), 1.0),
        "high_forward_weight": _float_value(request.get("high_forward_weight"), 1.5),
        "scan_m": _bool_value(request.get("scan_m"), False),
        "scan_n": _bool_value(request.get("scan_n"), False),
        "use_best_m_after_scan": _bool_value(request.get("use_best_m_after_scan"), True),
        "compare_models": _bool_value(request.get("compare_models"), False),
        "post_fit_models": _bool_value(request.get("post_fit_models"), False),
    }
    product_mode = normalize_product_fit_mode(_text(request.get("product_fit_mode")))
    return apply_product_fit_mode(settings, product_mode)


def analyze_file(file_path: str | Path, request: Mapping[str, Any]) -> dict[str, Any]:
    product_mode = normalize_product_fit_mode(_text(request.get("product_fit_mode")))
    settings = apply_product_fit_mode(_analysis_settings(request), product_mode)
    dataset = load_selected_dataset(file_path, request)

    ml_assist_enabled = _bool_value(request.get("ml_assist_enabled"), False)
    ml_assist_payload = build_prefit_ml_assist(
        dataset.data_v,
        dataset.data_jd,
        {
            "product_fit_mode": product_mode or "legacy",
            "fit_strategy": settings["fit_strategy"],
            "sweep_strategies": settings["sweep_strategies"],
            "scan_m": settings["scan_m"],
            "scan_n": settings["scan_n"],
            "compare_models": settings["compare_models"],
            "post_fit_models": settings["post_fit_models"],
        },
        enabled=ml_assist_enabled,
        mode=_text(request.get("ml_assist_mode"), "advisory"),
    )
    applied_product_mode = (ml_assist_payload.get("applied_overrides") or {}).get("product_fit_mode")
    if applied_product_mode:
        product_mode = normalize_product_fit_mode(applied_product_mode)
        settings = apply_product_fit_mode(settings, product_mode)

    run_scan = settings["mode"] in {"scan", "analyze"} or settings["scan_m"]
    run_compare = settings["mode"] in {"compare", "analyze"} or settings["compare_models"]
    m_value = optional_float(request.get("param_m"))
    config = clone_config(m=m_value) if m_value is not None else None
    params_meta = None
    if _bool_value(request.get("use_initial_params"), False):
        params_meta = params_meta_from_values(
            parse_params(
                _text(request.get("param_j0")),
                _text(request.get("param_rs")),
                _text(request.get("param_rsh")),
                _text(request.get("param_k")),
            )
        )

    options = AnalysisOptions(
        run_fit=True,
        fit_strategy=settings["fit_strategy"],
        sweep_strategies=settings["sweep_strategies"],
        reverse_weight=settings["reverse_weight"],
        near_zero_weight=settings["near_zero_weight"],
        forward_weight=settings["forward_weight"],
        high_forward_weight=settings["high_forward_weight"],
        scan_m=run_scan,
        scan_n=settings["scan_n"],
        use_best_m_after_scan=settings["use_best_m_after_scan"],
        compare_models=run_compare,
        post_fit_models=settings["post_fit_models"],
        m_values=parse_m_values(_text(request.get("m_values"))),
        n_values=parse_n_values(_text(request.get("n_values"))),
        fit_verbose=False,
        analysis_verbose=False,
    )
    analysis = run_analysis(dataset.data_v, dataset.data_jd, options, config=config, params_meta=params_meta)
    payload = analysis_payload(dataset, analysis)
    if product_mode:
        payload["product_fit_mode"] = product_mode
    payload["run_snapshot"] = run_snapshot_payload(
        dataset,
        analysis,
        product_fit_mode=product_mode,
        analysis_settings=settings,
        ranked_candidates=payload.get("candidates") or [],
    )
    if ml_assist_enabled:
        payload["ml_assist"] = ml_assist_payload
    return payload


def evaluate_file(file_path: str | Path, request: Mapping[str, Any]) -> dict[str, Any]:
    dataset = load_selected_dataset(file_path, request)
    params = parse_params(
        _text(request.get("param_j0")),
        _text(request.get("param_rs")),
        _text(request.get("param_rsh")),
        _text(request.get("param_k")),
    )
    n_value = optional_float(request.get("param_n"))
    m_value = optional_float(request.get("param_m"))
    config = clone_config(n=n_value, m=m_value) if n_value is not None or m_value is not None else None
    fit = evaluate_params(
        dataset.data_v,
        dataset.data_jd,
        params,
        config=config,
        params_meta=params_meta_from_values(params),
    )
    return fit_payload(dataset, fit, notes=["Manual parameter evaluation only; no optimization was run."])
