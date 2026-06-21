from __future__ import annotations

import copy
from typing import Any

import numpy as np
from scipy.optimize import brentq

from config import Config
from fit.cqd_heterointerface import CQDHeterointerfaceConstants, cqd_heterointerface_model, derived_values
from fit.core import FitResult, clone_config, evaluate_params
from fit.model import error_function, error_statistics, relative_errors, valid_error_mask
from fit.optimization import _params_to_optimizer, run_with_multistart
from fit.strategy import FitStrategyOptions, run_fit_strategy


DD_PARAM_NAMES = ("J01", "J02", "Rs", "Rsh", "k")
DD_LB = np.array([1e-14, 1e-14, 1e1, 1e5, 1e-10], dtype=float)
DD_UB = np.array([1e-5, 1e-5, 1e4, 1e10, 1e-5], dtype=float)

DRD_PARAM_NAMES = ("Jr", "Jd", "Rs", "Rsh")
DRD_LB = np.array([1e-14, 1e-14, 1e1, 1e5], dtype=float)
DRD_UB = np.array([1e-4, 1e-4, 1e4, 1e11], dtype=float)
DRD_RECOMBINATION_N_VALUES = (1.8, 2.0, 2.2)
DRD_DIFFUSION_N_VALUES = (0.9, 1.0, 1.1)

CQD_HETERO_PARAM_NAMES = ("phi", "Vbi", "tau", "n0", "Rs_area")
CQD_HETERO_LB = np.array([0.05, 0.35, 1e-9, 1e12, 1e-4], dtype=float)
CQD_HETERO_UB = np.array([0.35, 1.8, 1e-3, 1e18, 1e6], dtype=float)
CQD_HETERO_TRANSFORMS = ("linear", "linear", "log", "log", "log")

EXTENDED_PARAM_NAMES = {
    "reverse_field_assisted": ("J0", "Rs", "Rsh", "k", "A_pf", "B_pf"),
    "reverse_trap_saturation": ("J0", "Rs", "Rsh", "k", "A_trap", "C_trap"),
    "high_forward_power": ("J0", "Rs", "Rsh", "k", "A_hf", "Vt_hf"),
}

EXTENDED_BOUNDS = {
    "reverse_field_assisted": (
        np.array([1e-12, 1e1, 1e5, 1e-10, 1e-14, 1e-4], dtype=float),
        np.array([1e-5, 1e4, 1e10, 1e-5, 1e-2, 15.0], dtype=float),
        ("log", "log", "log", "log", "log", "linear"),
    ),
    "reverse_trap_saturation": (
        np.array([1e-12, 1e1, 1e5, 1e-10, 1e-14, 1e-3], dtype=float),
        np.array([1e-5, 1e4, 1e10, 1e-5, 1e-2, 30.0], dtype=float),
        ("log", "log", "log", "log", "log", "linear"),
    ),
    "high_forward_power": (
        np.array([1e-12, 1e1, 1e5, 1e-10, 1e-14, 0.02], dtype=float),
        np.array([1e-5, 1e4, 1e10, 1e-5, 1e-2, 0.9], dtype=float),
        ("log", "log", "log", "log", "log", "linear"),
    ),
}


def _as_vector(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def _safe_exp(values: np.ndarray | float) -> np.ndarray | float:
    return np.exp(np.clip(values, -700.0, 700.0))


def _information_criteria(residuals: np.ndarray, parameter_count: int) -> tuple[float, float]:
    residuals = _as_vector(residuals)
    n = max(1, residuals.size)
    rss = max(float(np.sum(residuals**2)), np.finfo(float).tiny)
    return float(n * np.log(rss / n) + 2.0 * parameter_count), float(
        n * np.log(rss / n) + parameter_count * np.log(n)
    )


def _stats(voltage: np.ndarray, current: np.ndarray, predicted: np.ndarray, config: Config) -> dict[str, float]:
    return error_statistics(
        voltage,
        current,
        predicted,
        voltage_zero_atol=config.fitting.voltage_zero_atol,
        current_noise_floor=config.fitting.current_noise_floor,
    )


def _safe_float(value: Any, default: float = np.inf) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def _masked_stats(
    voltage: np.ndarray,
    current: np.ndarray,
    predicted: np.ndarray,
    mask: np.ndarray,
    config: Config,
) -> dict[str, float | None]:
    rel = relative_errors(predicted, current)
    valid = valid_error_mask(
        voltage,
        current,
        voltage_zero_atol=config.fitting.voltage_zero_atol,
        current_noise_floor=config.fitting.current_noise_floor,
    )
    selected = np.asarray(mask, dtype=bool) & valid & np.isfinite(rel)
    if not np.any(selected):
        return {"mean": None, "max": None, "median": None, "count": 0.0}
    return {
        "mean": float(np.mean(rel[selected])),
        "max": float(np.max(rel[selected])),
        "median": float(np.median(rel[selected])),
        "count": float(np.sum(selected)),
    }


def _region_breakdown(
    voltage: np.ndarray,
    current: np.ndarray,
    predicted: np.ndarray,
    config: Config,
) -> dict[str, Any]:
    low = float(config.fitting.core_window_low)
    high = float(config.fitting.core_window_high)
    masks = {
        "reverse_outside": voltage < low,
        "core": (voltage >= low) & (voltage <= high),
        "forward_outside": voltage > high,
    }
    region = {name: _masked_stats(voltage, current, predicted, mask, config) for name, mask in masks.items()}
    worst_name = None
    worst_mean = -np.inf
    for name, stats in region.items():
        mean = stats.get("mean")
        if mean is not None and float(mean) > worst_mean:
            worst_mean = float(mean)
            worst_name = name
    region["worst_region"] = worst_name
    return region


def _region_mean(region: dict[str, Any] | None, name: str) -> float | None:
    if not isinstance(region, dict):
        return None
    stats = region.get(name)
    if not isinstance(stats, dict):
        return None
    value = stats.get("mean")
    if value is None:
        return None
    number = _safe_float(value, default=np.nan)
    return None if not np.isfinite(number) else number


def _parameter_boundary_hits(
    params: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    names: tuple[str, ...],
    config: Config,
) -> list[dict[str, str | float]]:
    values = _as_vector(params)
    lower = _as_vector(lb)
    upper = _as_vector(ub)
    tol = float(config.fitting.boundary_relative_tol)
    hits: list[dict[str, str | float]] = []
    for name, value, lo, hi in zip(names, values, lower, upper, strict=False):
        if value <= lo * (1.0 + tol):
            hits.append({"parameter": name, "side": "lower", "value": float(value), "bound": float(lo)})
        elif value >= hi / (1.0 + tol):
            hits.append({"parameter": name, "side": "upper", "value": float(value), "bound": float(hi)})
    return hits


def _boundary_warnings(boundary_hits: list[dict[str, str | float]]) -> list[str]:
    return [
        f"{hit['parameter']} is near its {hit['side']} bound."
        for hit in boundary_hits
    ]


def _forward_semilog_two_slope_evidence(
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
) -> dict[str, Any]:
    v = _as_vector(voltage)
    j = _as_vector(current)
    threshold = float(config.fitting.current_noise_floor)
    forward_min = max(0.05, float(config.fitting.pos_voltage_threshold))
    mask = (v > forward_min) & (np.abs(j) > threshold) & np.isfinite(v) & np.isfinite(j)
    x = v[mask]
    y = np.log10(np.abs(j[mask]))
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    min_segment_points = 4
    if x.size < min_segment_points * 2:
        return {
            "has_evidence": False,
            "reason": "not_enough_forward_semilog_points",
            "point_count": int(x.size),
        }

    one_coeff = np.polyfit(x, y, 1)
    one_fit = np.polyval(one_coeff, x)
    one_sse = float(np.sum((y - one_fit) ** 2))
    best: dict[str, Any] | None = None
    for split in range(min_segment_points, x.size - min_segment_points + 1):
        left_x, right_x = x[:split], x[split:]
        left_y, right_y = y[:split], y[split:]
        left_coeff = np.polyfit(left_x, left_y, 1)
        right_coeff = np.polyfit(right_x, right_y, 1)
        left_fit = np.polyval(left_coeff, left_x)
        right_fit = np.polyval(right_coeff, right_x)
        sse = float(np.sum((left_y - left_fit) ** 2) + np.sum((right_y - right_fit) ** 2))
        if best is None or sse < float(best["sse"]):
            best = {
                "sse": sse,
                "split_voltage": float(0.5 * (x[split - 1] + x[split])),
                "slope_low_forward": float(left_coeff[0]),
                "slope_high_forward": float(right_coeff[0]),
                "left_points": int(left_x.size),
                "right_points": int(right_x.size),
            }

    if best is None:
        return {"has_evidence": False, "reason": "split_search_failed", "point_count": int(x.size)}
    improvement = 0.0 if one_sse <= np.finfo(float).eps else (one_sse - float(best["sse"])) / one_sse
    slope_delta = abs(float(best["slope_high_forward"]) - float(best["slope_low_forward"]))
    slope_scale = max(abs(float(best["slope_low_forward"])), abs(float(best["slope_high_forward"])), 1e-12)
    slope_contrast = slope_delta / slope_scale
    has_evidence = bool(improvement >= 0.35 and slope_contrast >= 0.35 and slope_delta >= 0.25)
    best.update(
        {
            "has_evidence": has_evidence,
            "reason": "two_forward_semilog_slopes_detected" if has_evidence else "single_slope_or_weak_contrast",
            "point_count": int(x.size),
            "single_slope": float(one_coeff[0]),
            "single_sse": one_sse,
            "two_segment_sse": float(best["sse"]),
            "sse_improvement_fraction": float(improvement),
            "slope_contrast": float(slope_contrast),
            "slope_delta": float(slope_delta),
        }
    )
    return best


def _is_bad(stats: dict[str, Any], config: Config) -> bool:
    mean = _safe_float(stats.get("mean"), default=np.inf)
    max_error = _safe_float(stats.get("max"), default=np.inf)
    return (
        mean >= float(config.fitting.post_model_trigger_mean_error)
        or max_error >= float(config.fitting.post_model_trigger_max_error)
    )


def _is_good_core(stats: dict[str, Any], config: Config) -> bool:
    mean = _safe_float(stats.get("mean"), default=np.inf)
    max_error = _safe_float(stats.get("max"), default=np.inf)
    return (
        mean <= float(config.fitting.core_fit_good_mean_error)
        and max_error <= float(config.fitting.core_fit_good_max_error)
    )


def _failure_regions(region: dict[str, Any], config: Config) -> list[str]:
    failures: list[str] = []
    for name in ("reverse_outside", "forward_outside"):
        stats = region.get(name) or {}
        if _is_bad(stats, config):
            failures.append(name)
    return failures


def _display_series(
    voltage: np.ndarray,
    current: np.ndarray,
    fitted: np.ndarray,
    *,
    diode: np.ndarray | None = None,
    ohmic: np.ndarray | None = None,
    nonohmic: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    v = _as_vector(voltage)
    j = _as_vector(current)
    y = _as_vector(fitted)
    zeros = np.zeros_like(y)
    return {
        "voltage": v,
        "measured": j,
        "fitted": y,
        "diode": _as_vector(diode) if diode is not None else y,
        "ohmic": _as_vector(ohmic) if ohmic is not None else zeros,
        "nonohmic": _as_vector(nonohmic) if nonohmic is not None else zeros,
        "relative_error": relative_errors(y, j),
    }


def _base_reference_result(
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
) -> dict[str, Any]:
    aic, bic = _base_information_criteria(voltage, current, base_fit)
    info = base_fit.diagnostics.get("information_criteria") or {}
    baseline_stage = base_fit.diagnostics.get("recommended_baseline_stage") or base_fit.diagnostics.get("model_stage") or "baseline"
    baseline_selection = base_fit.diagnostics.get("baseline_selection") or {}
    free_count = int(info.get("free_parameter_count") or 4)
    return {
        "name": "base_reference",
        "description": f"selected M0-M3 baseline reference ({baseline_stage})",
        "status": "ok",
        "params": base_fit.params,
        "param_names": ["J0", "Rs", "Rsh", "k"],
        "stats": base_fit.stats,
        "aic": aic,
        "bic": bic,
        "free_parameter_count": free_count,
        "series": _display_series(
            voltage,
            current,
            base_fit.fit_results["JD"],
            diode=base_fit.currents.diode,
            ohmic=base_fit.currents.ohmic,
            nonohmic=base_fit.currents.nonohmic,
        ),
        "diagnostics": {
            "physical_confidence": "baseline",
            "publication_confidence": "standard_model",
            "selected_for_replacement": False,
            "selected_for_baseline": True,
            "recommended_baseline_stage": baseline_stage,
            "baseline_selection": baseline_selection,
            "region_stats": _region_breakdown(voltage, current, base_fit.fit_results["JD"], base_fit.config),
            "warnings": base_fit.diagnostics.get("warnings", []),
        },
    }


def _candidate_decision(
    *,
    name: str,
    stats: dict[str, Any],
    aic: float | None,
    bic: float | None,
    base_fit: FitResult,
    base_aic: float | None,
    base_bic: float | None,
    config: Config,
    publication_confidence: str,
    default_physical_confidence: str,
    warnings: list[str] | None = None,
    boundary_hits: list[dict[str, str | float]] | None = None,
    candidate_region_stats: dict[str, Any] | None = None,
    base_region_stats: dict[str, Any] | None = None,
    allow_auto_replacement: bool = True,
    auto_replacement_blockers: list[str] | None = None,
) -> dict[str, Any]:
    warnings = list(warnings or [])
    boundary_hits = list(boundary_hits or [])
    auto_replacement_blockers = list(auto_replacement_blockers or [])
    mean_improvement = float(base_fit.stats.get("mean", np.inf)) - float(stats.get("mean", np.inf))
    max_improvement = float(base_fit.stats.get("max", np.inf)) - float(stats.get("max", np.inf))
    aic_improvement = None if base_aic is None or aic is None else float(base_aic - aic)
    bic_improvement = None if base_bic is None or bic is None else float(base_bic - bic)
    bic_ok = (
        bic_improvement is not None
        and bic_improvement >= float(config.fitting.post_model_min_bic_improvement)
    )
    mean_ok = bool(mean_improvement > 1.0)
    max_ok = bool(max_improvement >= 0.0)
    boundary_ok = not boundary_hits
    base_core_mean = _region_mean(base_region_stats, "core")
    candidate_core_mean = _region_mean(candidate_region_stats, "core")
    if base_core_mean is None or candidate_core_mean is None:
        core_not_sacrificed = True
        core_mean_delta = None
    else:
        core_mean_delta = float(base_core_mean - candidate_core_mean)
        core_not_sacrificed = bool(core_mean_delta >= -1.0)
    selection_criteria = {
        "bic_improvement_at_least_6": bool(bic_ok),
        "mean_error_improved": mean_ok,
        "max_error_not_worse": max_ok,
        "parameters_not_at_bounds": boundary_ok,
        "core_region_not_sacrificed": core_not_sacrificed,
        "auto_replacement_allowed": bool(allow_auto_replacement),
    }
    selected = bool(
        mean_ok
        and max_ok
        and bic_ok
        and boundary_ok
        and core_not_sacrificed
        and allow_auto_replacement
    )
    if not selected:
        failed = [key for key, ok in selection_criteria.items() if not ok]
        failed.extend(auto_replacement_blockers)
        if failed:
            warnings.append(f"{name} remains diagnostic; failed promotion check(s): {', '.join(failed)}.")
        warnings.append(
            f"{name} did not clear the automatic replacement threshold; keep it as a diagnostic candidate."
        )
    return {
        "base_aic": base_aic,
        "base_bic": base_bic,
        "mean_improvement": float(mean_improvement),
        "max_improvement": float(max_improvement),
        "aic_improvement": aic_improvement,
        "bic_improvement": bic_improvement,
        "selected_for_replacement": selected,
        "physical_confidence": default_physical_confidence if selected else "exploratory",
        "publication_confidence": publication_confidence if selected else "diagnostic_only",
        "selection_criteria": selection_criteria,
        "core_mean_improvement": core_mean_delta,
        "boundary_hits": boundary_hits,
        "warnings": warnings,
    }


def _rank_candidate(item: dict[str, Any]) -> tuple[float, float, float]:
    if item.get("status") != "ok":
        return (3.0, np.inf, np.inf)
    diagnostics = item.get("diagnostics") or {}
    selected = bool(diagnostics.get("selected_for_replacement"))
    bic = item.get("bic")
    mean = (item.get("stats") or {}).get("mean")
    return (
        0.0 if selected else 1.0,
        float(bic) if bic is not None else np.inf,
        float(mean) if mean is not None else np.inf,
    )


def _meta_from_fit(fit: FitResult) -> dict[str, Any]:
    meta = {
        key: value.copy() if isinstance(value, np.ndarray) else copy.deepcopy(value)
        for key, value in fit.params_meta.items()
    }
    meta["x0"] = fit.params.copy()
    return meta


def _run_core_window_fit(
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
    config: Config,
    verbose: bool,
) -> dict[str, Any]:
    low = float(config.fitting.core_window_low)
    high = float(config.fitting.core_window_high)
    mask = (voltage >= low) & (voltage <= high)
    point_count = int(np.sum(mask))
    min_points = int(config.fitting.core_window_min_points)
    if point_count < min_points:
        return {
            "name": "core_window_base",
            "description": "base model fitted only on the trusted core voltage window",
            "status": "skipped",
            "params": [],
            "param_names": ["J0", "Rs", "Rsh", "k"],
            "stats": {},
            "aic": None,
            "bic": None,
            "free_parameter_count": 4,
            "diagnostics": {
                "reason": f"core window has {point_count} points; at least {min_points} are required",
                "window": {"low": low, "high": high, "points": point_count},
            },
        }

    core_config = clone_config(config)
    core_config.optimization.staged_fallback = False
    core_config.optimization.use_de_fallback = False
    core_config.optimization.max_attempts = 1
    core_config.optimization.max_retries = 0
    core_options = FitStrategyOptions(name="quick_global")
    core_fit = run_fit_strategy(
        voltage[mask],
        current[mask],
        core_config,
        _meta_from_fit(base_fit),
        core_options,
        verbose=verbose,
    )
    full_eval = evaluate_params(voltage, current, core_fit.params, core_fit.config, core_fit.params_meta)
    region = _region_breakdown(voltage, current, full_eval.fit_results["JD"], config)
    failures = _failure_regions(region, config)
    core_good = _is_good_core(core_fit.stats, config)
    full_bad = _is_bad(full_eval.stats, config)
    model_limited = bool(core_good and full_bad and failures)

    return {
        "name": "core_window_base",
        "description": "base model fitted on the core window, then extrapolated to the full selected voltage range",
        "status": "ok",
        "params": core_fit.params,
        "param_names": ["J0", "Rs", "Rsh", "k"],
        "stats": full_eval.stats,
        "aic": None,
        "bic": None,
        "free_parameter_count": 4,
        "diagnostics": {
            "window": {"low": low, "high": high, "points": point_count},
            "core_stats": core_fit.stats,
            "full_extrapolation_stats": full_eval.stats,
            "region_stats": region,
            "failure_regions": failures,
            "core_good": core_good,
            "full_bad": full_bad,
            "model_limited": model_limited,
            "physical_confidence": "local_high_global_limited" if model_limited else "diagnostic",
        },
    }


def _dd_branch_current(
    v_drop: np.ndarray,
    params: np.ndarray,
    config: Config,
    n1: float,
    n2: float,
) -> np.ndarray:
    j01, j02, _, rsh, k = params
    physics = config.physics
    diode_1 = j01 * (_safe_exp(physics.A * v_drop / n1) - 1.0)
    diode_2 = j02 * (_safe_exp(physics.A * v_drop / n2) - 1.0)
    ohmic = v_drop / rsh
    nonohmic = k * np.abs(v_drop) ** physics.m * np.sign(v_drop)
    return diode_1 + diode_2 + ohmic + nonohmic


def _dd_branch_derivative(
    v_drop: np.ndarray,
    params: np.ndarray,
    config: Config,
    n1: float,
    n2: float,
) -> np.ndarray:
    j01, j02, _, rsh, k = params
    physics = config.physics
    exp_1 = _safe_exp(physics.A * v_drop / n1)
    exp_2 = _safe_exp(physics.A * v_drop / n2)
    nonohmic_deriv = k * physics.m * np.abs(v_drop) ** (physics.m - 1.0)
    return j01 * (physics.A / n1) * exp_1 + j02 * (physics.A / n2) * exp_2 + 1.0 / rsh + nonohmic_deriv


def _dd_scalar_root(v: float, params: np.ndarray, config: Config, n1: float, n2: float) -> float:
    rs = params[2]

    def residual(u: float) -> float:
        return float(_dd_branch_current(np.array([u]), params, config, n1, n2)[0] - (v - u) / rs)

    width = max(1.0, abs(v))
    lo = -width
    hi = width
    f_lo = residual(lo)
    f_hi = residual(hi)
    for _ in range(80):
        if np.isfinite(f_lo) and np.isfinite(f_hi) and f_lo <= 0.0 <= f_hi:
            return brentq(residual, lo, hi, xtol=1e-13, rtol=1e-13, maxiter=100)
        width *= 2.0
        lo = -width
        hi = width
        f_lo = residual(lo)
        f_hi = residual(hi)
    raise RuntimeError(f"Could not bracket double-diode root at V={v:.6g}")


def solve_double_diode_v_drop(
    voltage: np.ndarray,
    params: np.ndarray,
    config: Config,
    n1: float = 1.0,
    n2: float = 2.0,
) -> np.ndarray:
    v = _as_vector(voltage)
    params = _as_vector(params)
    rs = params[2]
    if rs <= 0.0:
        raise ValueError(f"Physical parameter error: Rs must be positive, got {rs:.6e}")

    u = v.copy()
    converged = np.zeros_like(u, dtype=bool)
    for _ in range(60):
        f = _dd_branch_current(u, params, config, n1, n2) - (v - u) / rs
        df = _dd_branch_derivative(u, params, config, n1, n2) + 1.0 / rs
        step = np.clip(f / np.maximum(df, 1e-300), -1.0, 1.0)
        next_u = u - step
        good = np.isfinite(next_u) & (np.abs(step) <= 1e-12 * (1.0 + np.abs(next_u)))
        converged |= good
        u = np.where(np.isfinite(next_u), next_u, u)
        if bool(np.all(converged)):
            break

    residual = _dd_branch_current(u, params, config, n1, n2) - (v - u) / rs
    ok = np.isfinite(residual) & (np.abs(residual) <= 1e-10 * (1.0 + np.abs(v / rs)))
    if not bool(np.all(ok)):
        for idx in np.where(~ok)[0]:
            u[idx] = _dd_scalar_root(float(v[idx]), params, config, n1, n2)
    return u


def double_diode_model(
    voltage: np.ndarray,
    params: np.ndarray,
    config: Config,
    n1: float = 1.0,
    n2: float = 2.0,
) -> np.ndarray:
    v = _as_vector(voltage)
    params = _as_vector(params)
    v_drop = solve_double_diode_v_drop(v, params, config, n1, n2)
    return (v - v_drop) / params[2]


def double_diode_series(
    voltage: np.ndarray,
    current: np.ndarray,
    params: np.ndarray,
    config: Config,
    n1: float = 1.0,
    n2: float = 2.0,
) -> dict[str, np.ndarray]:
    v = _as_vector(voltage)
    values = _as_vector(params)
    v_drop = solve_double_diode_v_drop(v, values, config, n1, n2)
    physics = config.physics
    diode_1 = values[0] * (_safe_exp(physics.A * v_drop / n1) - 1.0)
    diode_2 = values[1] * (_safe_exp(physics.A * v_drop / n2) - 1.0)
    ohmic = v_drop / values[3]
    nonohmic = values[4] * np.abs(v_drop) ** physics.m * np.sign(v_drop)
    fitted = (v - v_drop) / values[2]
    series = _display_series(
        v,
        current,
        fitted,
        diode=diode_1 + diode_2,
        ohmic=ohmic,
        nonohmic=nonohmic,
    )
    series["diode_1"] = diode_1
    series["diode_2"] = diode_2
    series["v_drop"] = v_drop
    return series


def _dd_optimizer_to_params(x: np.ndarray) -> np.ndarray:
    return np.power(10.0, _as_vector(x))


def _dd_params_to_optimizer(params: np.ndarray) -> np.ndarray:
    return np.log10(np.clip(_as_vector(params), DD_LB, DD_UB))


def _drd_params_to_optimizer(params: np.ndarray) -> np.ndarray:
    return np.log10(np.clip(_as_vector(params), DRD_LB, DRD_UB))


def _drd_optimizer_to_params(x: np.ndarray) -> np.ndarray:
    return np.power(10.0, _as_vector(x))


def _params_to_mixed_optimizer(
    params: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    transforms: tuple[str, ...],
) -> np.ndarray:
    values = np.clip(_as_vector(params), _as_vector(lb), _as_vector(ub))
    out = values.copy()
    for idx, transform in enumerate(transforms):
        if transform == "log":
            out[idx] = np.log10(values[idx])
    return out


def _mixed_optimizer_to_params(
    x: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    transforms: tuple[str, ...],
) -> np.ndarray:
    values = _as_vector(x).copy()
    for idx, transform in enumerate(transforms):
        if transform == "log":
            values[idx] = np.power(10.0, values[idx])
    return np.clip(values, _as_vector(lb), _as_vector(ub))


def _mixed_bounds(
    lb: np.ndarray,
    ub: np.ndarray,
    transforms: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray]:
    lower = _as_vector(lb).copy()
    upper = _as_vector(ub).copy()
    for idx, transform in enumerate(transforms):
        if transform == "log":
            lower[idx] = np.log10(lower[idx])
            upper[idx] = np.log10(upper[idx])
    return lower, upper


def _log_residuals(
    predicted: np.ndarray,
    current: np.ndarray,
    voltage: np.ndarray,
    config: Config,
) -> np.ndarray:
    threshold = float(config.fitting.current_noise_floor)
    max_val = max(1e-12, float(np.max(np.abs(current))))
    actual_abs = np.abs(current)
    pred_abs = np.abs(predicted)
    err = np.zeros_like(current)

    mask_small = (actual_abs < threshold) | (pred_abs < threshold)
    err[mask_small] = (predicted[mask_small] - current[mask_small]) / max_val
    mask_log = ~mask_small
    err[mask_log] = np.log10(pred_abs[mask_log]) - np.log10(actual_abs[mask_log])

    sign_mismatch = (
        (np.sign(predicted) != np.sign(current))
        & (pred_abs > threshold)
        & (actual_abs > threshold)
    )
    err[sign_mismatch] *= 3.0
    idx = np.abs(voltage) > 0.05
    err[idx] *= 1.0 + np.abs(err[idx])
    return np.nan_to_num(err, nan=1e12, posinf=1e12, neginf=-1e12)


def _double_diode_error_from_params(
    params: np.ndarray,
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    n1: float,
    n2: float,
) -> np.ndarray:
    predicted = double_diode_model(voltage, _as_vector(params)[:5], config, n1, n2)
    return _log_residuals(predicted, current, voltage, config)


def _double_diode_error(
    x: np.ndarray,
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    n1: float,
    n2: float,
) -> np.ndarray:
    params = _dd_optimizer_to_params(x)
    return _double_diode_error_from_params(params, voltage, current, config, n1, n2)


def _dual_rd_branch_current(
    v_drop: np.ndarray,
    params: np.ndarray,
    config: Config,
    n_recombination: float,
    n_diffusion: float,
) -> np.ndarray:
    jr, jd, _, rsh = params
    vt = config.physics.v_th
    recombination = jr * (_safe_exp(v_drop / (n_recombination * vt)) - 1.0)
    diffusion = jd * (_safe_exp(v_drop / (n_diffusion * vt)) - 1.0)
    shunt = v_drop / rsh
    return recombination + diffusion + shunt


def _dual_rd_branch_derivative(
    v_drop: np.ndarray,
    params: np.ndarray,
    config: Config,
    n_recombination: float,
    n_diffusion: float,
) -> np.ndarray:
    jr, jd, _, rsh = params
    vt = config.physics.v_th
    recombination = jr * _safe_exp(v_drop / (n_recombination * vt)) / (n_recombination * vt)
    diffusion = jd * _safe_exp(v_drop / (n_diffusion * vt)) / (n_diffusion * vt)
    return recombination + diffusion + 1.0 / rsh


def _dual_rd_scalar_root(
    voltage: float,
    params: np.ndarray,
    config: Config,
    n_recombination: float,
    n_diffusion: float,
) -> float:
    rs = params[2]

    def residual(u: float) -> float:
        return float(
            _dual_rd_branch_current(np.array([u]), params, config, n_recombination, n_diffusion)[0]
            - (voltage - u) / rs
        )

    width = max(1.0, abs(voltage))
    lo = -width
    hi = width
    f_lo = residual(lo)
    f_hi = residual(hi)
    for _ in range(80):
        if np.isfinite(f_lo) and np.isfinite(f_hi) and f_lo <= 0.0 <= f_hi:
            return brentq(residual, lo, hi, xtol=1e-13, rtol=1e-13, maxiter=100)
        width *= 2.0
        lo = -width
        hi = width
        f_lo = residual(lo)
        f_hi = residual(hi)
    raise RuntimeError(f"Could not bracket dual recombination/diffusion root at V={voltage:.6g}")


def solve_dual_rd_v_drop(
    voltage: np.ndarray,
    params: np.ndarray,
    config: Config,
    n_recombination: float,
    n_diffusion: float,
) -> np.ndarray:
    v = _as_vector(voltage)
    params = _as_vector(params)
    rs = params[2]
    if rs <= 0.0:
        raise ValueError(f"Physical parameter error: Rs must be positive, got {rs:.6e}")

    u = v.copy()
    converged = np.zeros_like(u, dtype=bool)
    for _ in range(60):
        f = _dual_rd_branch_current(u, params, config, n_recombination, n_diffusion) - (v - u) / rs
        df = _dual_rd_branch_derivative(u, params, config, n_recombination, n_diffusion) + 1.0 / rs
        step = np.clip(f / np.maximum(df, 1e-300), -1.0, 1.0)
        next_u = u - step
        good = np.isfinite(next_u) & (np.abs(step) <= 1e-12 * (1.0 + np.abs(next_u)))
        converged |= good
        u = np.where(np.isfinite(next_u), next_u, u)
        if bool(np.all(converged)):
            break

    residual = _dual_rd_branch_current(u, params, config, n_recombination, n_diffusion) - (v - u) / rs
    ok = np.isfinite(residual) & (np.abs(residual) <= 1e-10 * (1.0 + np.abs(v / rs)))
    if not bool(np.all(ok)):
        for idx in np.where(~ok)[0]:
            u[idx] = _dual_rd_scalar_root(
                float(v[idx]),
                params,
                config,
                n_recombination,
                n_diffusion,
            )
    return u


def dual_recombination_diffusion_model(
    voltage: np.ndarray,
    params: np.ndarray,
    config: Config,
    n_recombination: float = 2.0,
    n_diffusion: float = 1.0,
) -> np.ndarray:
    v = _as_vector(voltage)
    params = _as_vector(params)
    v_drop = solve_dual_rd_v_drop(v, params, config, n_recombination, n_diffusion)
    return (v - v_drop) / params[2]


def dual_recombination_diffusion_series(
    voltage: np.ndarray,
    current: np.ndarray,
    params: np.ndarray,
    config: Config,
    n_recombination: float = 2.0,
    n_diffusion: float = 1.0,
) -> dict[str, np.ndarray]:
    v = _as_vector(voltage)
    j = _as_vector(current)
    values = _as_vector(params)
    v_drop = solve_dual_rd_v_drop(v, values, config, n_recombination, n_diffusion)
    recombination = values[0] * (_safe_exp(config.physics.A * v_drop / n_recombination) - 1.0)
    diffusion = values[1] * (_safe_exp(config.physics.A * v_drop / n_diffusion) - 1.0)
    ohmic = v_drop / values[3]
    fitted = (v - v_drop) / values[2]
    return {
        "voltage": v,
        "measured": j,
        "fitted": fitted,
        "diode": recombination + diffusion,
        "ohmic": ohmic,
        "nonohmic": np.zeros_like(fitted),
        "relative_error": relative_errors(fitted, j),
        "recombination": recombination,
        "diffusion": diffusion,
        "v_drop": v_drop,
    }


def _dual_rd_residuals_from_params(
    params: np.ndarray,
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    n_recombination: float,
    n_diffusion: float,
) -> np.ndarray:
    predicted = dual_recombination_diffusion_model(
        voltage,
        _as_vector(params)[:4],
        config,
        n_recombination,
        n_diffusion,
    )
    return _log_residuals(predicted, current, voltage, config)


def _run_dual_recombination_diffusion_fit(
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
    config: Config,
    *,
    variant: str = "standard",
    n_recombination_override: float | None = None,
    n_diffusion_override: float | None = None,
) -> dict[str, Any]:
    if variant == "perovskite_double_interface":
        n_recombination = 4.0
        n_diffusion = 2.0
        name = "perovskite_double_interface"
        description = (
            "source-backed double-heterojunction branch: shunt + recombination + diffusion "
            "with perovskite effective idealities"
        )
        publication_confidence = "medium_if_perovskite_or_double_interface_stack"
    elif variant == "clean_double_diode":
        n_recombination = 2.0
        n_diffusion = 1.0
        name = "clean_double_diode"
        description = (
            "clean double-diode branch: SRH-like recombination (n=2) + diffusion (n=1) "
            "with shared Rs/Rsh and no empirical non-ohmic k term"
        )
        publication_confidence = "first_stage_physical_candidate"
    elif variant == "cqd_srh_diffusion":
        n_recombination = 2.0
        n_diffusion = 1.0
        name = "cqd_srh_diffusion"
        description = (
            "source-backed compact branch: shunt + SRH-like recombination + diffusion "
            "without the empirical non-ohmic leakage term"
        )
        publication_confidence = "medium_literature_supported"
    else:
        raise ValueError(f"Unknown dual recombination/diffusion variant: {variant}")
    if n_recombination_override is not None:
        n_recombination = float(n_recombination_override)
    if n_diffusion_override is not None:
        n_diffusion = float(n_diffusion_override)

    base_params = _as_vector(base_fit.params)
    start = np.array(
        [
            np.clip(base_params[0] * 0.8, DRD_LB[0], DRD_UB[0]),
            np.clip(base_params[0] * 0.2, DRD_LB[1], DRD_UB[1]),
            np.clip(base_params[1], DRD_LB[2], DRD_UB[2]),
            np.clip(base_params[2], DRD_LB[3], DRD_UB[3]),
        ],
        dtype=float,
    )
    x0 = _drd_params_to_optimizer(start)
    lb = np.log10(DRD_LB)
    ub = np.log10(DRD_UB)
    optcfg = copy.deepcopy(config.optimization)
    optcfg.multistart_points = min(max(5, int(getattr(optcfg, "multistart_points", 5))), 10)
    rng = np.random.default_rng(optcfg.random_seed)

    def fun(x: np.ndarray) -> np.ndarray:
        params = _drd_optimizer_to_params(x)
        return _dual_rd_residuals_from_params(
            params,
            voltage,
            current,
            config,
            n_recombination,
            n_diffusion,
        )

    x_opt, _ = run_with_multistart(fun, x0, lb, ub, optcfg, max_nfev=7000, tol=1e-10, rng=rng)
    params = _drd_optimizer_to_params(x_opt)
    predicted = dual_recombination_diffusion_model(
        voltage,
        params,
        config,
        n_recombination,
        n_diffusion,
    )
    stats = _stats(voltage, current, predicted, config)
    residuals = fun(x_opt)
    aic, bic = _information_criteria(residuals, len(params))
    base_aic, base_bic = _base_information_criteria(voltage, current, base_fit)
    region_stats = _region_breakdown(voltage, current, predicted, config)
    base_region_stats = _region_breakdown(voltage, current, base_fit.fit_results["JD"], base_fit.config)
    boundary_hits = _parameter_boundary_hits(params, DRD_LB, DRD_UB, DRD_PARAM_NAMES, config)
    warnings: list[str] = _boundary_warnings(boundary_hits)
    semilog_evidence = _forward_semilog_two_slope_evidence(voltage, current, config)
    bic_improvement = None if base_bic is None else float(base_bic - bic)
    mean_improvement = float(base_fit.stats.get("mean", np.inf)) - float(stats.get("mean", np.inf))
    max_improvement = float(base_fit.stats.get("max", np.inf)) - float(stats.get("max", np.inf))
    overwhelming_fit_evidence = (
        variant == "clean_double_diode"
        and not boundary_hits
        and bic_improvement is not None
        and bic_improvement >= 50.0
        and mean_improvement >= 10.0
        and max_improvement >= 20.0
        and float(stats.get("mean", np.inf)) <= 10.0
        and float(stats.get("max", np.inf)) <= 40.0
    )
    auto_blockers: list[str] = []
    allow_auto_replacement = True
    if (
        variant == "clean_double_diode"
        and not semilog_evidence.get("has_evidence")
        and not overwhelming_fit_evidence
    ):
        allow_auto_replacement = False
        auto_blockers.append("missing_forward_semilog_two_slope_evidence")
    diagnostics = _candidate_decision(
        name=name,
        stats=stats,
        aic=aic,
        bic=bic,
        base_fit=base_fit,
        base_aic=base_aic,
        base_bic=base_bic,
        config=config,
        publication_confidence=publication_confidence,
        default_physical_confidence="medium",
        warnings=warnings,
        boundary_hits=boundary_hits,
        candidate_region_stats=region_stats,
        base_region_stats=base_region_stats,
        allow_auto_replacement=allow_auto_replacement,
        auto_replacement_blockers=auto_blockers,
    )
    diagnostics.update(
        {
            "model_stage": "M4" if variant == "clean_double_diode" else "diagnostic",
            "mechanism": "dual_recombination_diffusion",
            "source": [
                "https://doi.org/10.1007/s40820-017-0159-z",
                "https://doi.org/10.1021/acs.jpcc.4c04316",
                "https://doi.org/10.1038/ncomms7180",
            ],
            "fixed_ideality": {
                "recombination": n_recombination,
                "diffusion": n_diffusion,
            },
            "region_stats": region_stats,
            "base_region_stats": base_region_stats,
            "forward_semilog_two_slope_evidence": semilog_evidence,
            "required_metadata": ["device_stack", "active_material", "etl", "htl", "temperature_K"],
        }
    )
    if overwhelming_fit_evidence:
        diagnostics["selection_criteria"]["overwhelming_fit_evidence"] = True
        diagnostics["warnings"].append(
            "clean_double_diode passed by overwhelming fit evidence even though forward semilog two-slope evidence was weak."
        )
    if variant == "clean_double_diode" and not diagnostics.get("selected_for_replacement"):
        diagnostics["publication_confidence"] = "diagnostic_only"
    return {
        "name": name,
        "description": description,
        "status": "ok",
        "params": params,
        "param_names": list(DRD_PARAM_NAMES),
        "stats": stats,
        "aic": aic,
        "bic": bic,
        "free_parameter_count": len(params),
        "diagnostics": diagnostics,
        "series": dual_recombination_diffusion_series(
            voltage,
            current,
            params,
            config,
            n_recombination,
            n_diffusion,
        ),
    }


def run_clean_double_diode_rescue(
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
    config: Config,
    *,
    verbose: bool = False,
) -> dict[str, Any]:
    _ = verbose
    v = _as_vector(voltage)
    j = _as_vector(current)
    fixed = _run_dual_recombination_diffusion_fit(v, j, base_fit, config, variant="clean_double_diode")
    candidates: list[dict[str, Any]] = [fixed]
    for n_recombination in DRD_RECOMBINATION_N_VALUES:
        for n_diffusion in DRD_DIFFUSION_N_VALUES:
            if abs(n_recombination - 2.0) < 1e-12 and abs(n_diffusion - 1.0) < 1e-12:
                continue
            candidate = _run_dual_recombination_diffusion_fit(
                v,
                j,
                base_fit,
                config,
                variant="clean_double_diode",
                n_recombination_override=n_recombination,
                n_diffusion_override=n_diffusion,
            )
            candidate["diagnostics"]["bounded_ideality_profile"] = True
            candidates.append(candidate)

    ordered = sorted(candidates, key=lambda item: (float((item.get("stats") or {}).get("mean", np.inf)), float((item.get("stats") or {}).get("max", np.inf))))
    best = ordered[0]
    fixed_stats = fixed.get("stats") or {}
    best_stats = best.get("stats") or {}
    best_diag = best.get("diagnostics") or {}
    fixed_diag = fixed.get("diagnostics") or {}
    mean_gain_vs_fixed = float(fixed_stats.get("mean", np.inf)) - float(best_stats.get("mean", np.inf))
    max_delta_vs_fixed = float(best_stats.get("max", np.inf)) - float(fixed_stats.get("max", np.inf))
    profile_summary = [
        {
            "n_recombination": float((item.get("diagnostics") or {}).get("fixed_ideality", {}).get("recombination", 2.0)),
            "n_diffusion": float((item.get("diagnostics") or {}).get("fixed_ideality", {}).get("diffusion", 1.0)),
            "mean": float((item.get("stats") or {}).get("mean", np.inf)),
            "max": float((item.get("stats") or {}).get("max", np.inf)),
            "selected_for_replacement": bool((item.get("diagnostics") or {}).get("selected_for_replacement")),
        }
        for item in ordered[:8]
    ]
    profile = {
        "status": "used_for_candidate" if best is not fixed else "fixed_ideality_kept",
        "fixed_n_recombination": 2.0,
        "fixed_n_diffusion": 1.0,
        "n_recombination_values": list(DRD_RECOMBINATION_N_VALUES),
        "n_diffusion_values": list(DRD_DIFFUSION_N_VALUES),
        "mean_gain_vs_fixed": mean_gain_vs_fixed,
        "max_delta_vs_fixed": max_delta_vs_fixed,
        "top_candidates": profile_summary,
    }
    best_diag["bounded_ideality_profile"] = profile
    if best is not fixed:
        best_diag["warnings"].append(
            "clean_double_diode used bounded ideality profiling; treat fitted n values as diagnostic unless supported by independent slope evidence."
        )
        if mean_gain_vs_fixed < 0.5 or max_delta_vs_fixed > 1.0:
            fixed_diag["bounded_ideality_profile"] = {**profile, "status": "diagnostic_only_fixed_ideality_kept"}
            fixed_diag["warnings"].append(
                "Bounded M4 ideality profiling did not improve the fixed n=2/n=1 candidate enough to replace it."
            )
            return fixed
    return best


def _cqd_heterointerface_residuals_from_params(
    params: np.ndarray,
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    *,
    simplified: bool = False,
) -> np.ndarray:
    constants = CQDHeterointerfaceConstants(temperature_k=float(config.physics.T))
    predicted = cqd_heterointerface_model(voltage, params, constants, simplified=simplified)
    return _log_residuals(predicted, current, voltage, config)


def _run_cqd_heterointerface_fit(
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
    config: Config,
    *,
    simplified: bool = False,
) -> dict[str, Any]:
    name = "cqd_heterointerface_s25" if simplified else "cqd_heterointerface_s20"
    description = (
        "Arya SI Eq. S25 Shockley-like CQD heterointerface dark-current approximation"
        if simplified
        else "Arya SI Eq. S20 CQD heterointerface dark-current expression with area-normalized series resistance"
    )
    constants = CQDHeterointerfaceConstants(temperature_k=float(config.physics.T))
    start = np.array([0.1258, 1.0, 5e-6, 1e15, 100.0], dtype=float)
    base_params = _as_vector(base_fit.params)
    if base_params.size >= 2 and np.isfinite(base_params[1]):
        start[4] = float(np.clip(base_params[1], CQD_HETERO_LB[4], CQD_HETERO_UB[4]))
    start = np.clip(start, CQD_HETERO_LB, CQD_HETERO_UB)
    x0 = _params_to_mixed_optimizer(start, CQD_HETERO_LB, CQD_HETERO_UB, CQD_HETERO_TRANSFORMS)
    lb, ub = _mixed_bounds(CQD_HETERO_LB, CQD_HETERO_UB, CQD_HETERO_TRANSFORMS)
    optcfg = copy.deepcopy(config.optimization)
    optcfg.multistart_points = min(max(4, int(getattr(optcfg, "multistart_points", 4))), 8)
    optcfg.staged_fallback = False
    rng = np.random.default_rng(optcfg.random_seed)

    def fun(x: np.ndarray) -> np.ndarray:
        params = _mixed_optimizer_to_params(x, CQD_HETERO_LB, CQD_HETERO_UB, CQD_HETERO_TRANSFORMS)
        return _cqd_heterointerface_residuals_from_params(
            params,
            voltage,
            current,
            config,
            simplified=simplified,
        )

    x_opt, _ = run_with_multistart(fun, x0, lb, ub, optcfg, max_nfev=4000, tol=1e-9, rng=rng)
    params = _mixed_optimizer_to_params(x_opt, CQD_HETERO_LB, CQD_HETERO_UB, CQD_HETERO_TRANSFORMS)
    predicted = cqd_heterointerface_model(voltage, params, constants, simplified=simplified)
    stats = _stats(voltage, current, predicted, config)
    residuals = fun(x_opt)
    aic, bic = _information_criteria(residuals, len(params))
    base_aic, base_bic = _base_information_criteria(voltage, current, base_fit)
    derived = derived_values(float(params[0]), float(params[1]), constants)
    region_stats = _region_breakdown(voltage, current, predicted, config)
    base_region_stats = _region_breakdown(voltage, current, base_fit.fit_results["JD"], base_fit.config)
    boundary_hits = _parameter_boundary_hits(params, CQD_HETERO_LB, CQD_HETERO_UB, CQD_HETERO_PARAM_NAMES, config)
    warnings: list[str] = _boundary_warnings(boundary_hits)
    warnings.append("n0 and tau can be weakly identifiable from a single dark J-V curve; interpret their ratio first.")
    diagnostics = _candidate_decision(
        name=name,
        stats=stats,
        aic=aic,
        bic=bic,
        base_fit=base_fit,
        base_aic=base_aic,
        base_bic=base_bic,
        config=config,
        publication_confidence="medium_if_stack_matches_PbS_CQD_ZnO_and_current_density_units",
        default_physical_confidence="medium",
        warnings=warnings,
        boundary_hits=boundary_hits,
        candidate_region_stats=region_stats,
        base_region_stats=base_region_stats,
    )
    passed_replacement_threshold = bool(diagnostics.get("selected_for_replacement"))
    diagnostics["diagnostic_passed_replacement_threshold"] = passed_replacement_threshold
    diagnostics["selected_for_replacement"] = False
    diagnostics["physical_confidence"] = "metadata_required_diagnostic"
    diagnostics.setdefault("warnings", []).append(
        "CQD heterointerface parameters require matching stack/unit metadata; keep this as a diagnostic candidate."
    )
    diagnostics.update(
        {
            "model_stage": "M8",
            "mechanism": "cqd_heterointerface_dark_current",
            "component_series_kind": "total_only",
            "source": [
                "https://doi.org/10.1021/acs.nanolett.3c02899",
                "nl3c02899_si_001.pdf Eq. S20" if not simplified else "nl3c02899_si_001.pdf Eq. S25",
            ],
            "required_metadata": [
                "device_stack",
                "device_area_cm2",
                "active_material",
                "etl",
                "absorber_thickness_nm",
                "temperature_K",
            ],
            "unit_expectation": "J(A/cm^2)",
            "derived": {
                "Eeq_V_per_cm": derived.equilibrium_field_v_cm,
                "B_V_per_cm": derived.tunneling_b_v_cm,
                "vR_cm_per_s": derived.richardson_velocity_cm_s,
                "vd0_cm_per_s": derived.zero_bias_drift_velocity_cm_s,
                "D_cm2_per_s": derived.diffusion_cm2_s,
                "W_nm": derived.band_bending_width_nm,
                "beta_cm_inv": derived.beta_cm_inv,
            },
            "region_stats": region_stats,
            "base_region_stats": base_region_stats,
        }
    )
    return {
        "name": name,
        "description": description,
        "status": "ok",
        "params": params,
        "param_names": list(CQD_HETERO_PARAM_NAMES),
        "stats": stats,
        "aic": aic,
        "bic": bic,
        "free_parameter_count": len(params),
        "series": _display_series(voltage, current, predicted),
        "diagnostics": diagnostics,
    }


def _base_information_criteria(
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
) -> tuple[float | None, float | None]:
    info = base_fit.diagnostics.get("information_criteria") or {}
    if info.get("aic") is not None and info.get("bic") is not None:
        return float(info["aic"]), float(info["bic"])
    try:
        free_count = int(info.get("free_parameter_count") or 4)
        x_base = _params_to_optimizer(base_fit.params, base_fit.params_meta)
        residuals = error_function(
            x_base,
            voltage,
            current,
            base_fit.params_meta,
            base_fit.config,
            base_fit.config.regularization.prior,
        )
        return _information_criteria(residuals, free_count)
    except Exception:
        return None, None


def _run_double_diode_fit(
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
    config: Config,
    *,
    free_n2: bool = False,
) -> dict[str, Any]:
    n1 = 1.0
    n2 = 2.0
    base_params = _as_vector(base_fit.params)
    start = np.array(
        [
            np.clip(base_params[0] * 0.7, DD_LB[0], DD_UB[0]),
            np.clip(base_params[0] * 0.3, DD_LB[1], DD_UB[1]),
            np.clip(base_params[1], DD_LB[2], DD_UB[2]),
            np.clip(base_params[2], DD_LB[3], DD_UB[3]),
            np.clip(base_params[3], DD_LB[4], DD_UB[4]),
        ],
        dtype=float,
    )
    if free_n2:
        start = np.concatenate([start, np.array([2.0])])
        lb_params = np.concatenate([DD_LB, np.array([1.2])])
        ub_params = np.concatenate([DD_UB, np.array([4.0])])
        transforms = ("log", "log", "log", "log", "log", "linear")
        x0 = _params_to_mixed_optimizer(start, lb_params, ub_params, transforms)
        lb, ub = _mixed_bounds(lb_params, ub_params, transforms)
    else:
        x0 = _dd_params_to_optimizer(start)
        lb = np.log10(DD_LB)
        ub = np.log10(DD_UB)
    optcfg = copy.deepcopy(config.optimization)
    optcfg.multistart_points = min(max(4, int(getattr(optcfg, "multistart_points", 4))), 8)
    rng = np.random.default_rng(optcfg.random_seed)

    if free_n2:
        def fun(x: np.ndarray) -> np.ndarray:
            params = _mixed_optimizer_to_params(x, lb_params, ub_params, transforms)
            return _double_diode_error_from_params(params, voltage, current, config, n1, float(params[5]))
    else:
        fun = lambda x: _double_diode_error(x, voltage, current, config, n1, n2)

    x_opt, _ = run_with_multistart(fun, x0, lb, ub, optcfg, max_nfev=6000, tol=1e-10, rng=rng)
    if free_n2:
        params = _mixed_optimizer_to_params(x_opt, lb_params, ub_params, transforms)
        n2 = float(params[5])
        model_params = params[:5]
    else:
        params = _dd_optimizer_to_params(x_opt)
        model_params = params
    predicted = double_diode_model(voltage, model_params, config, n1, n2)
    stats = _stats(voltage, current, predicted, config)
    residuals = fun(x_opt)
    free_count = 6 if free_n2 else 5
    aic, bic = _information_criteria(residuals, free_count)
    base_aic, base_bic = _base_information_criteria(voltage, current, base_fit)
    dd_lb = np.concatenate([DD_LB, np.array([1.2])]) if free_n2 else DD_LB
    dd_ub = np.concatenate([DD_UB, np.array([4.0])]) if free_n2 else DD_UB
    dd_names = tuple(list(DD_PARAM_NAMES) + (["n2"] if free_n2 else []))
    boundary_hits = _parameter_boundary_hits(params, dd_lb, dd_ub, dd_names, config)
    region_stats = _region_breakdown(voltage, current, predicted, config)
    base_region_stats = _region_breakdown(voltage, current, base_fit.fit_results["JD"], base_fit.config)
    warnings: list[str] = _boundary_warnings(boundary_hits)
    warnings.append(
        "This legacy double-diode candidate still includes the empirical non-ohmic k term; "
        "use cqd_srh_diffusion for the clean recombination/diffusion branch."
    )
    diagnostics = _candidate_decision(
        name="free_n2_double_diode" if free_n2 else "constrained_double_diode",
        stats=stats,
        aic=aic,
        bic=bic,
        base_fit=base_fit,
        base_aic=base_aic,
        base_bic=base_bic,
        config=config,
        publication_confidence="medium_literature_supported",
        default_physical_confidence="medium",
        warnings=warnings,
        boundary_hits=boundary_hits,
        candidate_region_stats=region_stats,
        base_region_stats=base_region_stats,
    )
    diagnostics["selected_for_replacement"] = False
    diagnostics["physical_confidence"] = "exploratory"
    diagnostics["publication_confidence"] = "diagnostic_only_legacy_k_mixed"
    diagnostics["model_stage"] = "legacy_diagnostic"
    diagnostics["region_stats"] = region_stats
    diagnostics["base_region_stats"] = base_region_stats
    diagnostics["fixed_ideality"] = {"n1": n1, "n2": None if free_n2 else n2}
    if free_n2:
        diagnostics["fitted_ideality"] = {"n2": n2}

    return {
        "name": "free_n2_double_diode" if free_n2 else "constrained_double_diode",
        "description": (
            "two diode branches with n1 fixed at 1 and n2 fitted in a constrained physical range"
            if free_n2
            else "two fixed-ideality diode branches with shared Rs, Rsh, and non-ohmic leakage"
        ),
        "status": "ok",
        "params": params,
        "param_names": list(DD_PARAM_NAMES) + (["n2"] if free_n2 else []),
        "stats": stats,
        "aic": aic,
        "bic": bic,
        "free_parameter_count": free_count,
        "series": double_diode_series(voltage, current, model_params, config, n1, n2),
        "diagnostics": diagnostics,
    }


def _single_branch_current(v_drop: np.ndarray, params: np.ndarray, config: Config) -> np.ndarray:
    j0, _, rsh, k = _as_vector(params)[:4]
    physics = config.physics
    diode = j0 * (_safe_exp(physics.A * v_drop / physics.n) - 1.0)
    ohmic = v_drop / rsh
    nonohmic = k * np.abs(v_drop) ** physics.m * np.sign(v_drop)
    return diode + ohmic + nonohmic


def _single_branch_derivative(v_drop: np.ndarray, params: np.ndarray, config: Config) -> np.ndarray:
    j0, _, rsh, k = _as_vector(params)[:4]
    physics = config.physics
    exp_term = _safe_exp(physics.A * v_drop / physics.n)
    nonohmic_deriv = k * physics.m * np.abs(v_drop) ** (physics.m - 1.0)
    return j0 * (physics.A / physics.n) * exp_term + 1.0 / rsh + nonohmic_deriv


def _extended_extra_current(kind: str, v_drop: np.ndarray, params: np.ndarray) -> np.ndarray:
    values = _as_vector(params)
    u = _as_vector(v_drop)
    if kind == "reverse_field_assisted":
        amp, beta = values[4], values[5]
        x = np.maximum(-u, 0.0)
        return -amp * x * _safe_exp(beta * np.sqrt(x))
    if kind == "reverse_trap_saturation":
        amp, decay = values[4], values[5]
        x = np.maximum(-u, 0.0)
        return -amp * x * _safe_exp(-decay * x)
    if kind == "high_forward_power":
        amp, threshold = values[4], values[5]
        x = np.maximum(u - threshold, 0.0)
        return amp * x**2
    raise ValueError(f"Unknown extended model kind: {kind}")


def _extended_extra_derivative(kind: str, v_drop: np.ndarray, params: np.ndarray) -> np.ndarray:
    values = _as_vector(params)
    u = _as_vector(v_drop)
    deriv = np.zeros_like(u, dtype=float)
    if kind == "reverse_field_assisted":
        amp, beta = values[4], values[5]
        mask = u < 0.0
        x = np.maximum(-u[mask], 0.0)
        sqrt_x = np.sqrt(np.maximum(x, np.finfo(float).eps))
        deriv[mask] = amp * _safe_exp(beta * sqrt_x) * (1.0 + 0.5 * beta * sqrt_x)
        return deriv
    if kind == "reverse_trap_saturation":
        amp, decay = values[4], values[5]
        mask = u < 0.0
        x = np.maximum(-u[mask], 0.0)
        deriv[mask] = amp * _safe_exp(-decay * x) * (1.0 - decay * x)
        return deriv
    if kind == "high_forward_power":
        amp, threshold = values[4], values[5]
        mask = u > threshold
        deriv[mask] = 2.0 * amp * (u[mask] - threshold)
        return deriv
    raise ValueError(f"Unknown extended model kind: {kind}")


def _extended_branch_current(kind: str, v_drop: np.ndarray, params: np.ndarray, config: Config) -> np.ndarray:
    return _single_branch_current(v_drop, params, config) + _extended_extra_current(kind, v_drop, params)


def _extended_branch_derivative(kind: str, v_drop: np.ndarray, params: np.ndarray, config: Config) -> np.ndarray:
    return _single_branch_derivative(v_drop, params, config) + _extended_extra_derivative(kind, v_drop, params)


def _extended_scalar_root(kind: str, voltage: float, params: np.ndarray, config: Config) -> float:
    rs = float(params[1])

    def residual(u: float) -> float:
        return float(_extended_branch_current(kind, np.array([u]), params, config)[0] - (voltage - u) / rs)

    width = max(1.0, abs(voltage))
    lo = -width
    hi = width
    f_lo = residual(lo)
    f_hi = residual(hi)
    for _ in range(90):
        if np.isfinite(f_lo) and np.isfinite(f_hi) and f_lo <= 0.0 <= f_hi:
            return brentq(residual, lo, hi, xtol=1e-13, rtol=1e-13, maxiter=100)
        width *= 2.0
        lo = -width
        hi = width
        f_lo = residual(lo)
        f_hi = residual(hi)
    raise RuntimeError(f"Could not bracket {kind} root at V={voltage:.6g}")


def solve_extended_v_drop(kind: str, voltage: np.ndarray, params: np.ndarray, config: Config) -> np.ndarray:
    v = _as_vector(voltage)
    params = _as_vector(params)
    rs = params[1]
    if rs <= 0.0:
        raise ValueError(f"Physical parameter error: Rs must be positive, got {rs:.6e}")

    u = v.copy()
    converged = np.zeros_like(u, dtype=bool)
    for _ in range(60):
        f = _extended_branch_current(kind, u, params, config) - (v - u) / rs
        df = _extended_branch_derivative(kind, u, params, config) + 1.0 / rs
        step = np.clip(f / np.maximum(np.abs(df), 1e-300), -1.0, 1.0) * np.sign(df)
        next_u = u - step
        good = np.isfinite(next_u) & (np.abs(step) <= 1e-12 * (1.0 + np.abs(next_u)))
        converged |= good
        u = np.where(np.isfinite(next_u), next_u, u)
        if bool(np.all(converged)):
            break

    residual = _extended_branch_current(kind, u, params, config) - (v - u) / rs
    ok = np.isfinite(residual) & (np.abs(residual) <= 1e-10 * (1.0 + np.abs(v / rs)))
    if not bool(np.all(ok)):
        for idx in np.where(~ok)[0]:
            u[idx] = _extended_scalar_root(kind, float(v[idx]), params, config)
    return u


def extended_model(kind: str, voltage: np.ndarray, params: np.ndarray, config: Config) -> np.ndarray:
    v = _as_vector(voltage)
    params = _as_vector(params)
    v_drop = solve_extended_v_drop(kind, v, params, config)
    return (v - v_drop) / params[1]


def extended_series(
    kind: str,
    voltage: np.ndarray,
    current: np.ndarray,
    params: np.ndarray,
    config: Config,
) -> dict[str, np.ndarray]:
    v = _as_vector(voltage)
    values = _as_vector(params)
    v_drop = solve_extended_v_drop(kind, v, values, config)
    physics = config.physics
    diode = values[0] * (_safe_exp(physics.A * v_drop / physics.n) - 1.0)
    ohmic = v_drop / values[2]
    empirical_nonohmic = values[3] * np.abs(v_drop) ** physics.m * np.sign(v_drop)
    extra = _extended_extra_current(kind, v_drop, values)
    fitted = (v - v_drop) / values[1]
    series = _display_series(
        v,
        current,
        fitted,
        diode=diode,
        ohmic=ohmic,
        nonohmic=empirical_nonohmic,
    )
    series["empirical_nonohmic"] = empirical_nonohmic
    series["extra_current"] = extra
    series["extended_nonohmic_total"] = empirical_nonohmic + extra
    series["v_drop"] = v_drop
    return series


def _extended_residuals_from_params(
    kind: str,
    params: np.ndarray,
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
) -> np.ndarray:
    predicted = extended_model(kind, voltage, params, config)
    return _log_residuals(predicted, current, voltage, config)


def _estimate_extra_amplitude(
    kind: str,
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
    config: Config,
) -> float:
    base_predicted = base_fit.fit_results.get("JD")
    if base_predicted is None:
        return 1e-8
    residual = np.abs(_as_vector(current) - _as_vector(base_predicted))
    if kind.startswith("reverse"):
        mask = voltage < -0.05
        if not np.any(mask):
            return 1e-8
        x = np.maximum(-voltage[mask], 1e-6)
        shape = x
        if kind == "reverse_field_assisted":
            shape = x * np.exp(np.sqrt(x))
        if kind == "reverse_trap_saturation":
            shape = x * np.exp(-x)
        values = residual[mask] / np.maximum(shape, np.finfo(float).eps)
    else:
        mask = voltage > 0.2
        if not np.any(mask):
            return 1e-8
        x = np.maximum(voltage[mask] - 0.3, 1e-6) ** 2
        values = residual[mask] / np.maximum(x, np.finfo(float).eps)
    values = values[np.isfinite(values) & (values > 0.0)]
    if values.size == 0:
        return 1e-8
    return float(np.clip(np.median(values), 1e-14, 1e-2))


def _run_extended_candidate(
    kind: str,
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
    config: Config,
) -> dict[str, Any]:
    lb, ub, transforms = EXTENDED_BOUNDS[kind]
    base_params = np.clip(_as_vector(base_fit.params), lb[:4], ub[:4])
    amp = _estimate_extra_amplitude(kind, voltage, current, base_fit, config)
    if kind == "reverse_field_assisted":
        extra = np.array([amp, 1.0], dtype=float)
        description = "reverse-bias field-assisted leakage term added to the standard branch"
        publication_confidence = "medium_if_device_context_supports_field_leakage"
        default_confidence = "medium"
    elif kind == "reverse_trap_saturation":
        extra = np.array([amp, 1.0], dtype=float)
        description = "reverse-bias trap-saturation diagnostic term that can capture a peak or rollover"
        publication_confidence = "diagnostic_only"
        default_confidence = "exploratory"
    elif kind == "high_forward_power":
        extra = np.array([amp, 0.3], dtype=float)
        description = "high-forward transport power term activated above a fitted threshold"
        publication_confidence = "exploratory_transport_model"
        default_confidence = "exploratory"
    else:
        raise ValueError(f"Unknown extended candidate: {kind}")

    start = np.clip(np.concatenate([base_params, extra]), lb, ub)
    x0 = _params_to_mixed_optimizer(start, lb, ub, transforms)
    opt_lb, opt_ub = _mixed_bounds(lb, ub, transforms)
    optcfg = copy.deepcopy(config.optimization)
    optcfg.multistart_points = min(max(5, int(getattr(optcfg, "multistart_points", 5))), 10)
    optcfg.staged_fallback = False
    rng = np.random.default_rng(optcfg.random_seed)

    def fun(x: np.ndarray) -> np.ndarray:
        params = _mixed_optimizer_to_params(x, lb, ub, transforms)
        return _extended_residuals_from_params(kind, params, voltage, current, config)

    x_opt, _ = run_with_multistart(fun, x0, opt_lb, opt_ub, optcfg, max_nfev=7000, tol=1e-10, rng=rng)
    params = _mixed_optimizer_to_params(x_opt, lb, ub, transforms)
    predicted = extended_model(kind, voltage, params, config)
    stats = _stats(voltage, current, predicted, config)
    residuals = fun(x_opt)
    aic, bic = _information_criteria(residuals, len(params))
    base_aic, base_bic = _base_information_criteria(voltage, current, base_fit)
    boundary_hits = _parameter_boundary_hits(params, lb, ub, EXTENDED_PARAM_NAMES[kind], config)
    region_stats = _region_breakdown(voltage, current, predicted, config)
    base_region_stats = _region_breakdown(voltage, current, base_fit.fit_results["JD"], base_fit.config)
    warnings: list[str] = _boundary_warnings(boundary_hits)
    diagnostics = _candidate_decision(
        name=kind,
        stats=stats,
        aic=aic,
        bic=bic,
        base_fit=base_fit,
        base_aic=base_aic,
        base_bic=base_bic,
        config=config,
        publication_confidence=publication_confidence,
        default_physical_confidence=default_confidence,
        warnings=warnings,
        boundary_hits=boundary_hits,
        candidate_region_stats=region_stats,
        base_region_stats=base_region_stats,
    )
    diagnostics["region_stats"] = region_stats
    diagnostics["base_region_stats"] = base_region_stats
    diagnostics["mechanism"] = kind
    return {
        "name": kind,
        "description": description,
        "status": "ok",
        "params": params,
        "param_names": list(EXTENDED_PARAM_NAMES[kind]),
        "stats": stats,
        "aic": aic,
        "bic": bic,
        "free_parameter_count": len(params),
        "series": extended_series(kind, voltage, current, params, config),
        "diagnostics": diagnostics,
    }


def run_post_fit_models(
    voltage: np.ndarray,
    current: np.ndarray,
    base_fit: FitResult,
    config: Config,
    *,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    v = _as_vector(voltage)
    j = _as_vector(current)
    model_results: list[dict[str, Any]] = [_base_reference_result(v, j, base_fit)]

    bad_base = _is_bad(base_fit.stats, config)
    first_stage_specs = [
        ("clean_double_diode", lambda: run_clean_double_diode_rescue(v, j, base_fit, config, verbose=verbose)),
        ("cqd_heterointerface_s25", lambda: _run_cqd_heterointerface_fit(v, j, base_fit, config, simplified=True)),
    ]
    diagnostic_specs = [
        ("cqd_heterointerface_s20", lambda: _run_cqd_heterointerface_fit(v, j, base_fit, config, simplified=False)),
        ("perovskite_double_interface", lambda: _run_dual_recombination_diffusion_fit(v, j, base_fit, config, variant="perovskite_double_interface")),
        ("constrained_double_diode", lambda: _run_double_diode_fit(v, j, base_fit, config, free_n2=False)),
        ("free_n2_double_diode", lambda: _run_double_diode_fit(v, j, base_fit, config, free_n2=True)),
        ("reverse_field_assisted", lambda: _run_extended_candidate("reverse_field_assisted", v, j, base_fit, config)),
        ("reverse_trap_saturation", lambda: _run_extended_candidate("reverse_trap_saturation", v, j, base_fit, config)),
        ("high_forward_power", lambda: _run_extended_candidate("high_forward_power", v, j, base_fit, config)),
    ]
    candidate_specs = [*first_stage_specs, *(diagnostic_specs if bad_base else [])]
    if candidate_specs:
        for name, runner in candidate_specs:
            try:
                model_results.append(runner())
            except Exception as exc:
                model_results.append(
                    {
                        "name": name,
                        "description": "candidate model failed during optimization",
                        "status": "failed",
                        "params": [],
                        "param_names": [],
                        "stats": {},
                        "aic": None,
                        "bic": None,
                        "free_parameter_count": 0,
                        "diagnostics": {"error": str(exc), "selected_for_replacement": False},
                    }
                )

    base = model_results[0]
    candidates = sorted(model_results[1:], key=_rank_candidate)
    results = [base, *candidates]

    try:
        results.append(_run_core_window_fit(v, j, base_fit, config, verbose))
    except Exception as exc:
        results.append(
            {
                "name": "core_window_base",
                "description": "base model fitted only on the trusted core voltage window",
                "status": "failed",
                "params": [],
                "param_names": ["J0", "Rs", "Rsh", "k"],
                "stats": {},
                "aic": None,
                "bic": None,
                "free_parameter_count": 4,
                "diagnostics": {"error": str(exc), "selected_for_replacement": False},
            }
        )
    return results
