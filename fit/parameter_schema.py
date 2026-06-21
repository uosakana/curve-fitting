from __future__ import annotations

from typing import Any

import numpy as np


BASE_EVALUATOR_KIND = "base_j0_rs_rsh_k"
POST_FIT_EVALUATOR_KIND = "post_fit_model"
CUSTOM_EVALUATOR_KIND = "custom_model"

PARAM_NAMES = ("J0", "Rs", "Rsh", "k")
PARAM_LB = np.array([1e-12, 1e1, 1e5, 1e-10], dtype=float)
PARAM_UB = np.array([1e-5, 1e4, 1e10, 1e-5], dtype=float)
PARAM_SCALE = np.array([1e-9, 1e3, 1e7, 1e-8], dtype=float)

DEFAULT_N = 1.4
DEFAULT_M = 2.4
DEFAULT_M_VALUES = (1.8, 2.0, 2.4, 2.8, 3.2)
DEFAULT_N_VALUES = (1.1, 1.3, 1.4, 1.7, 2.0)


def _as_vector(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def params_meta_from_values(values: Any) -> dict[str, Any]:
    params = _as_vector(values)
    if params.size != len(PARAM_NAMES):
        raise ValueError(f"Expected {len(PARAM_NAMES)} parameters: {', '.join(PARAM_NAMES)}.")
    return {
        "x0": np.clip(params, PARAM_LB, PARAM_UB),
        "lb": PARAM_LB.copy(),
        "ub": PARAM_UB.copy(),
        "scale_factors": PARAM_SCALE.copy(),
        "param_names": PARAM_NAMES,
    }


def default_params_meta() -> dict[str, Any]:
    return params_meta_from_values(PARAM_SCALE)


def standard_param_names(names: Any) -> bool:
    if not isinstance(names, (list, tuple)):
        return False
    normalized = tuple(str(name).strip().lower() for name in names[: len(PARAM_NAMES)])
    return normalized == tuple(name.lower() for name in PARAM_NAMES)


def _same_param_names(left: Any, right: Any) -> bool:
    if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
        return False
    if len(left) != len(right):
        return False
    return tuple(str(name).strip().lower() for name in left) == tuple(
        str(name).strip().lower() for name in right
    )


def fit_evaluator_kind(fit: Any) -> str:
    diagnostics = getattr(fit, "diagnostics", None) or {}
    if diagnostics.get("display_fit_source") == POST_FIT_EVALUATOR_KIND:
        return POST_FIT_EVALUATOR_KIND

    fit_results = getattr(fit, "fit_results", None) or {}
    if fit_results.get("recombination") is not None or fit_results.get("diffusion") is not None:
        return POST_FIT_EVALUATOR_KIND

    params = _as_vector(getattr(fit, "params", []))
    names = diagnostics.get("param_names")
    if params.size == len(PARAM_NAMES) and (names is None or standard_param_names(names)):
        return BASE_EVALUATOR_KIND
    return CUSTOM_EVALUATOR_KIND


def manual_capability_payload(fit: Any) -> dict[str, Any]:
    evaluator_kind = fit_evaluator_kind(fit)
    can_evaluate = evaluator_kind == BASE_EVALUATOR_KIND
    reason = None
    if not can_evaluate:
        reason = "Displayed fit is not reproducible by the base J0/Rs/Rsh/k evaluator."
    return {
        "can_evaluate": can_evaluate,
        "evaluator_kind": evaluator_kind,
        "reason": reason,
    }


def model_context_payload(fit: Any) -> dict[str, Any]:
    diagnostics = getattr(fit, "diagnostics", None) or {}
    display_source = diagnostics.get("display_fit_source") or "strategy_fit"
    return {
        "display_fit_source": display_source,
        "display_fit_switched": bool(diagnostics.get("display_fit_switched", False)),
        "strategy": diagnostics.get("strategy"),
        "strategy_preset": diagnostics.get("strategy_preset"),
        "model_stage": diagnostics.get("model_stage"),
        "model_category": diagnostics.get("model_category"),
        "model_name": diagnostics.get("model_name"),
        "recommended_baseline_stage": diagnostics.get("recommended_baseline_stage"),
        "promoted": display_source in {"m_model_recommended_baseline", POST_FIT_EVALUATOR_KIND},
    }


def parameter_schema_payload(fit: Any | None = None, params_meta: dict | None = None) -> dict[str, Any]:
    diagnostics = getattr(fit, "diagnostics", None) or {}
    names = diagnostics.get("param_names")
    if not isinstance(names, (list, tuple)) or not names:
        names = PARAM_NAMES

    kind = fit_evaluator_kind(fit) if fit is not None else BASE_EVALUATOR_KIND
    meta = params_meta or getattr(fit, "params_meta", None) or {}
    params = _as_vector(getattr(fit, "params", [])) if fit is not None else np.array([], dtype=float)
    meta_names = meta.get("param_names")
    meta_matches_names = all(
        key in meta and _as_vector(meta.get(key)).size >= len(names)
        for key in ("lb", "ub", "scale_factors")
    ) and _same_param_names(meta_names, names)
    expose_bounds = kind == BASE_EVALUATOR_KIND or meta_matches_names
    lb = _as_vector(meta.get("lb", PARAM_LB)) if expose_bounds else np.array([], dtype=float)
    ub = _as_vector(meta.get("ub", PARAM_UB)) if expose_bounds else np.array([], dtype=float)
    scale = _as_vector(meta.get("scale_factors", PARAM_SCALE)) if expose_bounds else np.array([], dtype=float)

    parameters: list[dict[str, Any]] = []
    for idx, name in enumerate(names):
        item: dict[str, Any] = {"name": str(name)}
        if idx < lb.size:
            item["lower"] = float(lb[idx])
        if idx < ub.size:
            item["upper"] = float(ub[idx])
        if idx < scale.size:
            item["scale"] = float(scale[idx])
        if idx < params.size:
            item["value"] = float(params[idx])
        parameters.append(item)

    n_value = getattr(getattr(fit, "config", None), "physics", None)
    n = getattr(n_value, "n", DEFAULT_N)
    m = getattr(n_value, "m", DEFAULT_M)
    return {
        "kind": kind,
        "parameters": parameters,
        "exponents": {"n": float(n), "m": float(m)},
        "optimizer_space": meta.get("space"),
    }


def fit_contract_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "evaluator_kind": BASE_EVALUATOR_KIND,
        "parameter_schema": parameter_schema_payload(),
        "manual_capability": {
            "can_evaluate": True,
            "evaluator_kind": BASE_EVALUATOR_KIND,
            "reason": None,
        },
        "defaults": {
            "n": DEFAULT_N,
            "m": DEFAULT_M,
            "n_values": list(DEFAULT_N_VALUES),
            "m_values": list(DEFAULT_M_VALUES),
        },
    }
