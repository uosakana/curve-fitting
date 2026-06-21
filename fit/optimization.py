from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.optimize import differential_evolution, least_squares

from fit.model import (
    calculate_currents,
    diode_model,
    error_function,
    error_statistics,
    relative_errors,
    valid_error_mask,
)
from fit.parameter_schema import PARAM_NAMES, PARAM_SCALE


def _as_vector(values) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def _copy_params_meta(params_meta: dict) -> dict:
    return {key: value.copy() if isinstance(value, np.ndarray) else value for key, value in params_meta.items()}


def _prepare_params_meta(params_meta: dict, config) -> dict:
    meta = _copy_params_meta(params_meta)
    meta.setdefault("scale_factors", PARAM_SCALE.copy())
    meta.setdefault("param_names", PARAM_NAMES)
    meta["x0"] = np.clip(_as_vector(meta["x0"]), _as_vector(meta["lb"]), _as_vector(meta["ub"]))
    meta["space"] = "log10" if getattr(config.optimization, "use_log_parameters", True) else "scaled"
    return meta


def _params_to_optimizer(params: np.ndarray, params_meta: dict) -> np.ndarray:
    params = np.clip(_as_vector(params), _as_vector(params_meta["lb"]), _as_vector(params_meta["ub"]))
    if params_meta.get("space") == "log10":
        return np.log10(params)
    return params / params_meta["scale_factors"]


def _optimizer_to_params(x: np.ndarray, params_meta: dict) -> np.ndarray:
    x = _as_vector(x)
    if params_meta.get("space") == "log10":
        return np.power(10.0, x)
    return x * params_meta["scale_factors"]


def _optimizer_bounds(params_meta: dict, mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    if params_meta.get("space") == "log10":
        lb = np.log10(params_meta["lb"])
        ub = np.log10(params_meta["ub"])
    else:
        lb = params_meta["lb"] / params_meta["scale_factors"]
        ub = params_meta["ub"] / params_meta["scale_factors"]
    if mask is None:
        return lb, ub
    return lb[mask], ub[mask]


def _scaled_bounds(params_meta: dict[str, np.ndarray], mask: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    return _optimizer_bounds(params_meta, mask)


def _stats(data_v: np.ndarray, data_jd: np.ndarray, predicted: np.ndarray, config) -> dict[str, float]:
    return error_statistics(
        data_v,
        data_jd,
        predicted,
        voltage_zero_atol=config.fitting.voltage_zero_atol,
        current_noise_floor=config.fitting.current_noise_floor,
    )


def _fit_meets_target(stats: dict[str, float], config) -> bool:
    return (
        stats["mean"] < config.optimization.target_rel_error
        and stats["max"] < config.optimization.target_max_error
    )


def _least_squares(
    fun: Callable[[np.ndarray], np.ndarray],
    start: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    max_nfev: int,
    tol: float,
    optcfg=None,
):
    start = np.clip(_as_vector(start), lb, ub)
    loss = getattr(optcfg, "least_squares_loss", "linear") if optcfg is not None else "linear"
    f_scale = float(getattr(optcfg, "loss_f_scale", 1.0)) if optcfg is not None else 1.0
    return least_squares(
        fun,
        x0=start,
        bounds=(lb, ub),
        method="trf",
        loss=loss,
        f_scale=f_scale,
        ftol=tol,
        xtol=tol,
        gtol=tol,
        x_scale="jac",
        max_nfev=max_nfev,
    )


def run_with_multistart(
    fun: Callable[[np.ndarray], np.ndarray],
    x0: np.ndarray,
    lb: np.ndarray,
    ub: np.ndarray,
    optcfg,
    *,
    max_nfev: int = 8000,
    tol: float = 1e-10,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, float]:
    x0 = _as_vector(x0)
    lb = _as_vector(lb)
    ub = _as_vector(ub)
    n_start = max(1, int(optcfg.multistart_points))
    rng = rng or np.random.default_rng(optcfg.random_seed)

    starts = [np.clip(x0, lb, ub)]
    for _ in range(n_start - 1):
        starts.append(lb + rng.random(size=x0.shape) * (ub - lb))

    best_x = starts[0]
    best_resnorm = np.inf
    for start in starts:
        try:
            result = _least_squares(fun, start, lb, ub, max_nfev=max_nfev, tol=tol, optcfg=optcfg)
        except Exception:
            continue
        resnorm = 2.0 * result.cost
        if np.isfinite(resnorm) and resnorm < best_resnorm:
            best_x = result.x
            best_resnorm = resnorm
    return best_x, float(best_resnorm)


def _residual_norm(fun: Callable[[np.ndarray], np.ndarray], x: np.ndarray) -> float:
    residuals = _as_vector(fun(_as_vector(x)))
    return float(np.sum(residuals**2))


def run_with_differential_evolution(
    fun: Callable[[np.ndarray], np.ndarray],
    lb: np.ndarray,
    ub: np.ndarray,
    optcfg,
    *,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, float]:
    lb = _as_vector(lb)
    ub = _as_vector(ub)
    bounds = [(float(lo), float(hi)) for lo, hi in zip(lb, ub, strict=False)]
    rng = rng or np.random.default_rng(optcfg.random_seed)
    seed = int(rng.integers(0, np.iinfo(np.int32).max))

    result = differential_evolution(
        lambda x: _residual_norm(fun, x),
        bounds=bounds,
        strategy="best1bin",
        maxiter=max(1, int(getattr(optcfg, "de_maxiter", 35))),
        popsize=max(4, int(getattr(optcfg, "de_popsize", 8))),
        tol=max(1e-6, float(getattr(optcfg, "de_tol", 0.02))),
        mutation=getattr(optcfg, "de_mutation", (0.5, 1.0)),
        recombination=float(getattr(optcfg, "de_recombination", 0.7)),
        polish=False,
        seed=seed,
    )
    return _as_vector(result.x), float(result.fun)


def fit_negative_region(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    x0_scaled: np.ndarray,
    params_meta: dict[str, np.ndarray],
    config,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    print("\nStage 1: optimizing Rsh and non-ohmic coefficient k...")
    neg_idx = np.where(data_v < -0.1)[0]
    if neg_idx.size:
        param_mask = np.array([False, False, True, True])
        neg_v = data_v[neg_idx]
        neg_jd = data_jd[neg_idx]
        fun = lambda x: error_function(
            x,
            neg_v,
            neg_jd,
            params_meta,
            config,
            config.regularization.prior,
            param_mask,
            x0_scaled,
            None,
            4.0,
        )
        lb, ub = _scaled_bounds(params_meta, param_mask)
        x_opt, _ = run_with_multistart(fun, x0_scaled[param_mask], lb, ub, config.optimization, rng=rng)
        x0_scaled = x0_scaled.copy()
        x0_scaled[param_mask] = x_opt
        x_actual = _optimizer_to_params(x0_scaled, params_meta)
        fit_jd = diode_model(neg_v, x_actual, config)
        rel = relative_errors(fit_jd, neg_jd)
        print(f"Negative region: mean relative error = {np.mean(rel):.2f}%, max = {np.max(rel):.2f}%")
        print(f"Optimized Rsh = {x_actual[2]:.6e} Ohm")
        print(f"Optimized k = {x_actual[3]:.6e}")

    x_all = _optimizer_to_params(x0_scaled, params_meta)
    fit_all = diode_model(data_v, x_all, config)
    return x0_scaled, relative_errors(fit_all, data_jd) / 100.0


def fit_positive_region(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    x0_scaled: np.ndarray,
    params_meta: dict[str, np.ndarray],
    config,
    prev_errors: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    print("\nStage 2: optimizing positive-voltage regions...")
    x0_scaled = x0_scaled.copy()

    valid = valid_error_mask(
        data_v,
        data_jd,
        voltage_zero_atol=config.fitting.voltage_zero_atol,
        current_noise_floor=config.fitting.current_noise_floor,
    )
    low_pos_idx = np.where((data_v > config.fitting.voltage_zero_atol) & (data_v <= 0.15) & valid)[0]
    high_pos_idx = np.where((data_v > 0.15) & valid)[0]

    if low_pos_idx.size:
        print("Optimizing low positive-voltage region (0 to 0.15 V)...")
        param_mask = np.array([True, False, False, False])
        fun = lambda x: error_function(
            x,
            data_v[low_pos_idx],
            data_jd[low_pos_idx],
            params_meta,
            config,
            config.regularization.prior,
            param_mask,
            x0_scaled,
            prev_errors[low_pos_idx],
            4.0,
        )
        lb, ub = _scaled_bounds(params_meta, param_mask)
        x_opt, _ = run_with_multistart(fun, x0_scaled[param_mask], lb, ub, config.optimization, rng=rng)
        x0_scaled[param_mask] = x_opt
        fit_all = diode_model(data_v, _optimizer_to_params(x0_scaled, params_meta), config)
        prev_errors = relative_errors(fit_all, data_jd) / 100.0
        fit_low = diode_model(data_v[low_pos_idx], _optimizer_to_params(x0_scaled, params_meta), config)
        rel = relative_errors(fit_low, data_jd[low_pos_idx])
        print(f"Low positive region: mean relative error = {np.mean(rel):.2f}%, max = {np.max(rel):.2f}%")
        print(f"Optimized J0 = {_optimizer_to_params(x0_scaled, params_meta)[0]:.6e} A")

    if high_pos_idx.size:
        print("Optimizing high positive-voltage region (>0.15 V)...")
        param_mask = np.array([False, True, False, False])
        fun = lambda x: error_function(
            x,
            data_v[high_pos_idx],
            data_jd[high_pos_idx],
            params_meta,
            config,
            config.regularization.prior,
            param_mask,
            x0_scaled,
            prev_errors[high_pos_idx],
            4.0,
        )
        lb, ub = _scaled_bounds(params_meta, param_mask)
        x_opt, _ = run_with_multistart(fun, x0_scaled[param_mask], lb, ub, config.optimization, rng=rng)
        x0_scaled[param_mask] = x_opt
        if _optimizer_to_params(x0_scaled, params_meta)[1] <= 0.0:
            fixed = _optimizer_to_params(x0_scaled, params_meta)
            fixed[1] = params_meta["lb"][1]
            x0_scaled = _params_to_optimizer(fixed, params_meta)
        fit_all = diode_model(data_v, _optimizer_to_params(x0_scaled, params_meta), config)
        prev_errors = relative_errors(fit_all, data_jd) / 100.0
        fit_high = diode_model(data_v[high_pos_idx], _optimizer_to_params(x0_scaled, params_meta), config)
        rel = relative_errors(fit_high, data_jd[high_pos_idx])
        print(f"High positive region: mean relative error = {np.mean(rel):.2f}%, max = {np.max(rel):.2f}%")
        print(f"Optimized Rs = {_optimizer_to_params(x0_scaled, params_meta)[1]:.6e} Ohm")

    pos_idx = np.where((data_v > config.fitting.voltage_zero_atol) & valid)[0]
    if pos_idx.size:
        print("\nJoint positive-region optimization...")
        param_mask = np.array([True, True, False, False])
        fun = lambda x: error_function(
            x,
            data_v[pos_idx],
            data_jd[pos_idx],
            params_meta,
            config,
            config.regularization.prior,
            param_mask,
            x0_scaled,
            prev_errors[pos_idx],
            4.0,
        )
        lb, ub = _scaled_bounds(params_meta, param_mask)
        x_opt, _ = run_with_multistart(fun, x0_scaled[param_mask], lb, ub, config.optimization, rng=rng)
        x0_scaled[param_mask] = x_opt
        if _optimizer_to_params(x0_scaled, params_meta)[1] <= 0.0:
            fixed = _optimizer_to_params(x0_scaled, params_meta)
            fixed[1] = params_meta["lb"][1]
            x0_scaled = _params_to_optimizer(fixed, params_meta)
        fit_pos = diode_model(data_v[pos_idx], _optimizer_to_params(x0_scaled, params_meta), config)
        rel = relative_errors(fit_pos, data_jd[pos_idx])
        x_actual = _optimizer_to_params(x0_scaled, params_meta)
        print(f"Positive region: mean relative error = {np.mean(rel):.2f}%, max = {np.max(rel):.2f}%")
        print(f"Optimized J0 = {x_actual[0]:.6e} A")
        print(f"Optimized Rs = {x_actual[1]:.6e} Ohm")

    fit_all = diode_model(data_v, _optimizer_to_params(x0_scaled, params_meta), config)
    return x0_scaled, relative_errors(fit_all, data_jd) / 100.0


def _final_pass(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    x0_scaled: np.ndarray,
    params_meta: dict[str, np.ndarray],
    config,
    rng: np.random.Generator,
    *,
    max_nfev: int,
    tol: float,
) -> tuple[np.ndarray, dict]:
    fun = lambda x: error_function(x, data_v, data_jd, params_meta, config, config.regularization.prior)
    lb, ub = _scaled_bounds(params_meta)

    print("\nStage 3: full-region bounded least-squares fit...")
    x_lm, resnorm_lm = run_with_multistart(fun, x0_scaled, lb, ub, config.optimization, max_nfev=max_nfev, tol=tol, rng=rng)
    params_lm = _optimizer_to_params(x_lm, params_meta)
    params_lm[1] = max(params_lm[1], params_meta["lb"][1])
    x_lm = _params_to_optimizer(params_lm, params_meta)
    jd_lm = diode_model(data_v, params_lm, config)
    stats_lm = _stats(data_v, data_jd, jd_lm, config)

    print("\nStage 4: local refinement from the best full-region result...")
    refine = _least_squares(fun, x_lm, lb, ub, max_nfev=max_nfev, tol=min(tol, 1e-12), optcfg=config.optimization)
    if refine.success:
        x_tr = refine.x
        resnorm_tr = 2.0 * refine.cost
    else:
        x_tr = x_lm
        resnorm_tr = resnorm_lm
    params_tr = _optimizer_to_params(x_tr, params_meta)
    params_tr[1] = max(params_tr[1], params_meta["lb"][1])
    x_tr = _params_to_optimizer(params_tr, params_meta)
    jd_tr = diode_model(data_v, params_tr, config)
    stats_tr = _stats(data_v, data_jd, jd_tr, config)

    print("\nComparing full-region passes:")
    print(f"First pass: mean relative error = {stats_lm['mean']:.2f}%, max = {stats_lm['max']:.2f}%")
    print(f"Refinement: mean relative error = {stats_tr['mean']:.2f}%, max = {stats_tr['max']:.2f}%")

    if stats_lm["mean"] <= stats_tr["mean"]:
        best_scaled = x_lm
        best_params = params_lm
        best_jd = jd_lm
        best_resnorm = resnorm_lm
    else:
        best_scaled = x_tr
        best_params = params_tr
        best_jd = jd_tr
        best_resnorm = resnorm_tr

    fit_results = {
        "JD": best_jd,
        "resnorm": float(best_resnorm),
        "relative_errors": relative_errors(best_jd, data_jd),
    }
    return best_params, fit_results


def _maybe_enhance_positive_region(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    optimized_params: np.ndarray,
    fit_results: dict,
    params_meta: dict[str, np.ndarray],
    config,
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict]:
    rel = fit_results["relative_errors"]
    valid = valid_error_mask(
        data_v,
        data_jd,
        voltage_zero_atol=config.fitting.voltage_zero_atol,
        current_noise_floor=config.fitting.current_noise_floor,
    )
    neg_idx = (data_v < 0.0) & valid
    pos_idx = (data_v > 0.0) & valid
    if not (np.any(neg_idx) and np.any(pos_idx)):
        return optimized_params, fit_results

    neg_mean = float(np.mean(rel[neg_idx]))
    pos_mean = float(np.mean(rel[pos_idx]))
    if not (pos_mean > 2.0 * neg_mean and pos_mean > 10.0):
        return optimized_params, fit_results

    print("\nPositive region is weak; trying J0/Rs-only enhancement...")
    param_mask = np.array([True, True, False, False])
    x0_scaled = _params_to_optimizer(optimized_params, params_meta)
    fun = lambda x: error_function(
        x,
        data_v,
        data_jd,
        params_meta,
        config,
        config.regularization.prior,
        param_mask,
        x0_scaled,
        rel,
        4.0,
    )
    lb, ub = _scaled_bounds(params_meta, param_mask)
    x_pos, _ = run_with_multistart(fun, x0_scaled[param_mask], lb, ub, config.optimization, max_nfev=3000, tol=1e-12, rng=rng)
    enhanced_scaled = x0_scaled.copy()
    enhanced_scaled[param_mask] = x_pos
    enhanced_params = _optimizer_to_params(enhanced_scaled, params_meta)
    enhanced_jd = diode_model(data_v, enhanced_params, config)
    enhanced_rel = relative_errors(enhanced_jd, data_jd)

    print(f"Before: positive mean = {pos_mean:.2f}%, negative mean = {neg_mean:.2f}%")
    print(f"After:  positive mean = {np.mean(enhanced_rel[pos_idx]):.2f}%, negative mean = {np.mean(enhanced_rel[neg_idx]):.2f}%")
    if np.mean(enhanced_rel[pos_idx]) < pos_mean and np.mean(enhanced_rel[neg_idx]) < 2.0 * neg_mean:
        fit_results = {
            "JD": enhanced_jd,
            "resnorm": float(np.sum(error_function(enhanced_scaled, data_v, data_jd, params_meta, config) ** 2)),
            "relative_errors": enhanced_rel,
        }
        return enhanced_params, fit_results
    return optimized_params, fit_results


def identifiability_diagnostics(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    params: np.ndarray,
    params_meta: dict,
    config,
) -> dict:
    voltage = _as_vector(data_v)
    current = _as_vector(data_jd)
    params = _as_vector(params)
    lb = _as_vector(params_meta["lb"])
    ub = _as_vector(params_meta["ub"])

    baseline_predicted = diode_model(voltage, params, config)
    baseline_stats = _stats(voltage, current, baseline_predicted, config)
    perturbation_factors = {
        "J0": (0.5, 2.0),
        "Rs": (0.5, 2.0),
        "Rsh": (0.2, 5.0),
        "k": (0.2, 5.0),
    }

    by_parameter: dict[str, dict] = {}
    weak_parameters: list[str] = []
    strong_parameters: list[str] = []

    for idx, name in enumerate(PARAM_NAMES):
        perturbations: list[dict] = []
        max_mean_delta = 0.0
        max_relative_delta = 0.0

        for factor in perturbation_factors.get(name, (0.5, 2.0)):
            trial = params.copy()
            trial[idx] = float(np.clip(params[idx] * factor, lb[idx], ub[idx]))
            if np.isclose(trial[idx], params[idx]):
                continue
            try:
                predicted = diode_model(voltage, trial, config)
                stats = _stats(voltage, current, predicted, config)
                mean_delta = abs(float(stats["mean"]) - float(baseline_stats["mean"]))
            except Exception:
                stats = {"mean": float("inf"), "max": float("inf")}
                mean_delta = float("inf")

            relative_delta = mean_delta / max(1.0, float(baseline_stats["mean"]))
            max_mean_delta = max(max_mean_delta, mean_delta)
            max_relative_delta = max(max_relative_delta, relative_delta)
            perturbations.append(
                {
                    "factor": float(factor),
                    "value": float(trial[idx]),
                    "mean_error": float(stats["mean"]) if np.isfinite(stats["mean"]) else None,
                    "max_error": float(stats["max"]) if np.isfinite(stats["max"]) else None,
                    "mean_delta": float(mean_delta) if np.isfinite(mean_delta) else None,
                }
            )

        near_lower = params[idx] <= lb[idx] * (1.0 + config.fitting.boundary_relative_tol)
        near_upper = params[idx] >= ub[idx] / (1.0 + config.fitting.boundary_relative_tol)

        if not np.isfinite(max_mean_delta):
            classification = "unstable"
        elif max_mean_delta < 0.3 and max_relative_delta < 0.25:
            classification = "weak"
        elif max_mean_delta < 1.5 and max_relative_delta < 1.0:
            classification = "moderate"
        else:
            classification = "strong"

        if classification in {"weak", "moderate"} and (near_lower or near_upper):
            classification = "boundary_limited"
        if classification in {"weak", "boundary_limited"}:
            weak_parameters.append(name)
        if classification == "strong":
            strong_parameters.append(name)

        by_parameter[name] = {
            "classification": classification,
            "max_mean_delta": float(max_mean_delta) if np.isfinite(max_mean_delta) else None,
            "relative_sensitivity": float(max_relative_delta) if np.isfinite(max_relative_delta) else None,
            "at_lower_bound": bool(near_lower),
            "at_upper_bound": bool(near_upper),
            "perturbations": perturbations,
        }

    return {
        "baseline_mean_error": float(baseline_stats["mean"]),
        "baseline_max_error": float(baseline_stats["max"]),
        "weak_parameters": weak_parameters,
        "strong_parameters": strong_parameters,
        "by_parameter": by_parameter,
    }


def fit_diagnostics(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    params: np.ndarray,
    fit_results: dict,
    params_meta: dict,
    config,
) -> dict:
    currents = calculate_currents(data_v, params, config)
    valid = valid_error_mask(
        data_v,
        data_jd,
        voltage_zero_atol=config.fitting.voltage_zero_atol,
        current_noise_floor=config.fitting.current_noise_floor,
    )
    if not np.any(valid):
        valid = np.isfinite(data_v) & np.isfinite(data_jd)

    denom = np.abs(currents.total[valid]) + np.finfo(float).eps
    component_percent = {
        "diode": float(np.mean(np.abs(currents.diode[valid]) / denom) * 100.0),
        "ohmic": float(np.mean(np.abs(currents.ohmic[valid]) / denom) * 100.0),
        "nonohmic": float(np.mean(np.abs(currents.nonohmic[valid]) / denom) * 100.0),
    }

    region = (data_v >= -0.5) & (data_v <= -0.3) & valid
    if not np.any(region):
        region = (data_v < 0.0) & valid
    mean_ohmic = float(np.mean(np.abs(currents.ohmic[region]))) if np.any(region) else 0.0
    mean_nonohmic = float(np.mean(np.abs(currents.nonohmic[region]))) if np.any(region) else 0.0
    leakage_ratio = mean_nonohmic / (mean_ohmic + np.finfo(float).eps)

    boundary_hits: list[dict[str, str | float]] = []
    tol = config.fitting.boundary_relative_tol
    for name, value, lb, ub in zip(PARAM_NAMES, params, params_meta["lb"], params_meta["ub"]):
        if value <= lb * (1.0 + tol):
            boundary_hits.append({"parameter": name, "side": "lower", "value": float(value), "bound": float(lb)})
        elif value >= ub / (1.0 + tol):
            boundary_hits.append({"parameter": name, "side": "upper", "value": float(value), "bound": float(ub)})

    stats = _stats(data_v, data_jd, fit_results["JD"], config)
    identifiability = identifiability_diagnostics(data_v, data_jd, params, params_meta, config)
    warnings: list[str] = []
    for hit in boundary_hits:
        parameter = str(hit["parameter"])
        side = str(hit["side"])
        if parameter == "k" and side == "lower":
            k_info = (identifiability.get("by_parameter") or {}).get("k", {})
            sensitivity = k_info.get("max_mean_delta")
            if component_percent["nonohmic"] < 1.0 or (sensitivity is not None and float(sensitivity) < 0.3):
                warnings.append(
                    "k is at the lower bound because the non-ohmic branch is effectively unused; "
                    "increasing k has little effect near this solution, so interpret this as a no-k/weak-k fit rather than a request to raise k."
                )
                continue
        warnings.append(
            f"{parameter} reached the {side} bound; this parameter may be weakly identifiable."
        )
    if leakage_ratio > 1e3:
        warnings.append(
            "Non-ohmic leakage is much larger than ohmic leakage in the negative-voltage region; "
            "interpret Rsh and k together rather than separately."
        )
    if stats["excluded_points"] > 0:
        warnings.append(
            f"{int(stats['excluded_points'])} near-zero/noise-floor point(s) were excluded from aggregate error metrics."
        )

    initialization = params_meta.get("initialization")
    if initialization:
        requested = initialization.get("requested_method")
        selected = initialization.get("selected")
        if requested and selected and selected != requested:
            warnings.append(
                f"Initialization switched from requested {requested} to {selected} because it gave a better starting score."
            )

    for name in identifiability.get("weak_parameters", []):
        warnings.append(f"{name} is weakly identifiable around the current solution; avoid over-interpreting it.")

    return {
        "stats": stats,
        "component_percent": component_percent,
        "negative_leakage_nonohmic_to_ohmic": float(leakage_ratio),
        "boundary_hits": boundary_hits,
        "warnings": warnings,
        "initialization": initialization,
        "identifiability": identifiability,
    }


def _print_diagnostics(diagnostics: dict) -> None:
    stats = diagnostics["stats"]
    print("\nFit diagnostics:")
    print(f"Effective points in error statistics: {int(stats['included_points'])}")
    if stats["excluded_points"] > 0:
        print(f"Excluded near-zero/noise-floor points: {int(stats['excluded_points'])}")
    component = diagnostics["component_percent"]
    print(
        "Mean absolute component share: "
        f"diode {component['diode']:.2f}%, "
        f"ohmic {component['ohmic']:.2f}%, "
        f"non-ohmic {component['nonohmic']:.2f}%"
    )
    print(
        "Negative-region non-ohmic/ohmic leakage ratio: "
        f"{diagnostics['negative_leakage_nonohmic_to_ohmic']:.2e}"
    )
    for warning in diagnostics["warnings"]:
        print(f"Warning: {warning}")


def _should_run_de_fallback(stats: dict[str, float], diagnostics: dict, config) -> bool:
    if not getattr(config.optimization, "use_de_fallback", False):
        return False
    if float(stats.get("mean", np.inf)) >= float(getattr(config.optimization, "de_trigger_mean_error", np.inf)):
        return True
    if float(stats.get("max", np.inf)) >= float(getattr(config.optimization, "de_trigger_max_error", np.inf)):
        return True
    if diagnostics.get("boundary_hits"):
        return True
    return False


def _run_de_fallback(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    params_meta: dict[str, np.ndarray],
    config,
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict]:
    fun = lambda x: error_function(x, data_v, data_jd, params_meta, config, config.regularization.prior)
    lb, ub = _scaled_bounds(params_meta)

    print("\nMetaheuristic fallback: Differential Evolution global search...")
    x_de, resnorm_de = run_with_differential_evolution(fun, lb, ub, config.optimization, rng=rng)
    refine = _least_squares(fun, x_de, lb, ub, max_nfev=12000, tol=1e-12, optcfg=config.optimization)
    if refine.success:
        x_best = refine.x
        resnorm_best = 2.0 * refine.cost
    else:
        x_best = x_de
        resnorm_best = resnorm_de

    params = _optimizer_to_params(x_best, params_meta)
    params[1] = max(params[1], params_meta["lb"][1])
    predicted = diode_model(data_v, params, config)
    fit_results = {
        "JD": predicted,
        "resnorm": float(resnorm_best),
        "relative_errors": relative_errors(predicted, data_jd),
    }
    diagnostics = fit_diagnostics(data_v, data_jd, params, fit_results, params_meta, config)
    diagnostics["de_fallback"] = {
        "attempted": True,
        "used": True,
        "de_resnorm": float(resnorm_de),
        "refined_resnorm": float(resnorm_best),
    }
    fit_results["diagnostics"] = diagnostics
    return params, fit_results


def _maybe_apply_de_fallback(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    params: np.ndarray,
    fit_results: dict,
    params_meta: dict[str, np.ndarray],
    config,
    rng: np.random.Generator,
) -> tuple[np.ndarray, dict]:
    diagnostics = fit_results.get("diagnostics")
    if diagnostics is None:
        diagnostics = fit_diagnostics(data_v, data_jd, params, fit_results, params_meta, config)
        fit_results["diagnostics"] = diagnostics

    if not _should_run_de_fallback(diagnostics["stats"], diagnostics, config):
        diagnostics["de_fallback"] = {"attempted": False, "used": False}
        fit_results["diagnostics"] = diagnostics
        return params, fit_results

    de_params, de_fit = _run_de_fallback(data_v, data_jd, params_meta, config, rng)
    current_stats = diagnostics["stats"]
    de_stats = de_fit["diagnostics"]["stats"]
    mean_improvement = float(current_stats["mean"]) - float(de_stats["mean"])
    max_improvement = float(current_stats["max"]) - float(de_stats["max"])
    threshold = float(config.optimization.min_retry_improvement)

    if mean_improvement > threshold or (abs(mean_improvement) <= threshold and max_improvement > threshold):
        de_fit["diagnostics"]["de_fallback"]["selected_over_previous"] = True
        print("Using Differential Evolution fallback result because it improved the aggregate error.")
        return de_params, de_fit

    diagnostics["de_fallback"] = {
        "attempted": True,
        "used": False,
        "candidate_mean_error": float(de_stats["mean"]),
        "candidate_max_error": float(de_stats["max"]),
        "selected_over_previous": False,
    }
    fit_results["diagnostics"] = diagnostics
    print("Keeping the existing fit; Differential Evolution fallback did not improve the aggregate error.")
    return params, fit_results


def final_optimization(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    x0_scaled: np.ndarray,
    params_meta: dict[str, np.ndarray],
    config,
    rng: np.random.Generator,
    *,
    max_attempts: int | None = None,
) -> tuple[np.ndarray, dict]:
    current_start = x0_scaled.copy()
    params_meta = _copy_params_meta(params_meta)
    diagnostic_bounds = _copy_params_meta(params_meta)
    best_params = None
    best_fit = None
    best_stats = None
    attempt_limit = max(1, int(max_attempts or config.optimization.max_attempts))

    for attempt in range(1, attempt_limit + 1):
        if attempt > 1:
            print(f"\nRetrying global optimization ({attempt}/{attempt_limit})...")
        max_nfev = 8000 * attempt
        optimized_params, fit_results = _final_pass(
            data_v,
            data_jd,
            current_start,
            params_meta,
            config,
            rng,
            max_nfev=max_nfev,
            tol=1e-10,
        )
        optimized_params, fit_results = _maybe_enhance_positive_region(
            data_v, data_jd, optimized_params, fit_results, params_meta, config, rng
        )

        currents = calculate_currents(data_v, optimized_params, config)
        valid = valid_error_mask(
            data_v,
            data_jd,
            voltage_zero_atol=config.fitting.voltage_zero_atol,
            current_noise_floor=config.fitting.current_noise_floor,
        )
        region = (data_v >= -0.5) & (data_v <= -0.3) & valid
        if not np.any(region):
            region = (data_v < 0.0) & valid
        if np.any(region):
            mean_ohmic = float(np.mean(np.abs(currents.ohmic[region])))
            mean_nonohmic = float(np.mean(np.abs(currents.nonohmic[region])))
            ratio = mean_nonohmic / (mean_ohmic + np.finfo(float).eps)
        else:
            ratio = 0.0
        if ratio > 1e3 and attempt <= config.optimization.max_retries and attempt < attempt_limit:
            print(f"Warning: non-ohmic/ohmic ratio is {ratio:.2e}; tightening k upper bound and retrying.")
            params_meta["ub"][3] = min(params_meta["ub"][3], optimized_params[3])

        rel = fit_results["relative_errors"]
        stats = _stats(data_v, data_jd, fit_results["JD"], config)
        print("\nRelative error statistics:")
        print(f"Max relative error: {stats['max']:.2f}%")
        print(f"Mean relative error: {stats['mean']:.2f}%")
        print(f"Median relative error: {stats['median']:.2f}%")
        if "negative_mean" in stats:
            print(f"Negative-voltage mean relative error: {stats['negative_mean']:.2f}%")
        if "positive_mean" in stats:
            print(f"Positive-voltage mean relative error: {stats['positive_mean']:.2f}%")

        previous_best_mean = best_stats["mean"] if best_stats is not None else np.inf
        if best_fit is None or stats["mean"] < previous_best_mean:
            best_params = optimized_params
            best_fit = fit_results
            best_stats = stats

        if _fit_meets_target(stats, config):
            print(
                f"Convergence target reached: {config.optimization.target_rel_error:.2f}% / "
                f"{config.optimization.target_max_error:.2f}%"
            )
            break
        if (
            attempt > 1
            and previous_best_mean - stats["mean"] < config.optimization.min_retry_improvement
        ):
            print("Stopping retries because the last attempt did not materially improve the fit.")
            break
        current_start = _params_to_optimizer(optimized_params, params_meta)

    assert best_params is not None and best_fit is not None
    rel = best_fit["relative_errors"]
    valid = valid_error_mask(
        data_v,
        data_jd,
        voltage_zero_atol=config.fitting.voltage_zero_atol,
        current_noise_floor=config.fitting.current_noise_floor,
    )
    max_idx = np.where(valid)[0][int(np.argmax(rel[valid]))] if np.any(valid) else int(np.argmax(rel))
    print("\nLargest-error point:")
    print(f"Voltage: {data_v[max_idx]:.3f} V")
    print(f"Measured current: {data_jd[max_idx]:.3e} A")
    print(f"Fitted current: {best_fit['JD'][max_idx]:.3e} A")
    print(f"Relative error: {rel[max_idx]:.2f}%")

    print("\nFitted parameters:")
    print(f"J0  = {best_params[0]:.6e} A")
    print(f"Rs  = {best_params[1]:.6e} Ohm")
    print(f"Rsh = {best_params[2]:.6e} Ohm")
    print(f"k   = {best_params[3]:.6e}")
    diagnostics = fit_diagnostics(data_v, data_jd, best_params, best_fit, diagnostic_bounds, config)
    best_fit["diagnostics"] = diagnostics
    _print_diagnostics(diagnostics)
    return best_params, best_fit


def perform_fitting(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    params_meta: dict[str, np.ndarray],
    config,
) -> tuple[np.ndarray, dict]:
    params_meta = _prepare_params_meta(params_meta, config)
    if params_meta["x0"][1] <= 0.0:
        params_meta["x0"][1] = max(params_meta["lb"][1], abs(params_meta["x0"][1]))
    x0_scaled = _params_to_optimizer(params_meta["x0"], params_meta)

    print("\nInitial parameters:")
    print(f"J0 = {params_meta['x0'][0]:.6e} A")
    print(f"Rs = {params_meta['x0'][1]:.6e} Ohm")
    print(f"Rsh = {params_meta['x0'][2]:.6e} Ohm")
    print(f"k = {params_meta['x0'][3]:.6e}")
    print(f"Optimization parameter space: {params_meta['space']}")

    rng = np.random.default_rng(config.optimization.random_seed)
    print("\nFast path: direct full-region fit from Lambert W/history parameters...")
    fast_params, fast_fit = final_optimization(data_v, data_jd, x0_scaled, params_meta, config, rng, max_attempts=1)
    fast_stats = fast_fit["diagnostics"]["stats"]
    if _fit_meets_target(fast_stats, config) or not config.optimization.staged_fallback:
        return _maybe_apply_de_fallback(data_v, data_jd, fast_params, fast_fit, params_meta, config, rng)

    print("\nFast path did not meet the target; running staged physical fallback...")
    staged_start = _params_to_optimizer(params_meta["x0"], params_meta)
    staged_start, rel_errors = fit_negative_region(data_v, data_jd, staged_start, params_meta, config, rng)
    staged_start, _ = fit_positive_region(data_v, data_jd, staged_start, params_meta, config, rel_errors, rng)
    fallback_attempts = min(2, max(1, config.optimization.max_attempts))
    staged_params, staged_fit = final_optimization(
        data_v,
        data_jd,
        staged_start,
        params_meta,
        config,
        rng,
        max_attempts=fallback_attempts,
    )
    staged_stats = staged_fit["diagnostics"]["stats"]

    mean_improvement = fast_stats["mean"] - staged_stats["mean"]
    max_improvement = fast_stats["max"] - staged_stats["max"]
    if (
        mean_improvement > config.optimization.min_retry_improvement
        or (abs(mean_improvement) <= config.optimization.min_retry_improvement and max_improvement > config.optimization.min_retry_improvement)
    ):
        print("\nUsing staged fallback result because it improved the aggregate error.")
        return _maybe_apply_de_fallback(data_v, data_jd, staged_params, staged_fit, params_meta, config, rng)

    print("\nUsing fast-path result; staged fallback did not improve the aggregate error.")
    return _maybe_apply_de_fallback(data_v, data_jd, fast_params, fast_fit, params_meta, config, rng)
