from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass

import numpy as np

from config import Config
from fit.core import FitResult, clone_config, run_fit
from fit.initialize_parameters import initialize_parameters
from fit.model import calculate_currents, diode_model, error_function, relative_errors
from fit.optimization import (
    _copy_params_meta,
    _optimizer_bounds,
    _optimizer_to_params,
    _params_to_optimizer,
    _prepare_params_meta,
    final_optimization,
    fit_diagnostics,
    fit_negative_region,
    fit_positive_region,
    run_with_multistart,
)
from fit.region_stats import region_error_stats as shared_region_error_stats
from fit.region_stats import region_masks as shared_region_masks


QUICK_GLOBAL = "quick_global"
ROBUST_GLOBAL = "robust_global"
WEIGHTED_REGIONS = "weighted_regions"
STAGED_PHYSICAL = "staged_physical"
CONTINUATION_FIT = "continuation_fit"
STRATEGY_NAMES = {QUICK_GLOBAL, ROBUST_GLOBAL, WEIGHTED_REGIONS, STAGED_PHYSICAL, CONTINUATION_FIT}


@dataclass
class FitStrategyOptions:
    name: str = QUICK_GLOBAL
    reverse_weight: float = 1.5
    near_zero_weight: float = 0.5
    forward_weight: float = 1.0
    high_forward_weight: float = 1.5
    near_zero_width: float = 0.05
    high_forward_threshold: float = 0.3
    robust_loss: str = "soft_l1"
    robust_f_scale: float = 1.0
    continuation_core_negative: float = -0.5
    continuation_core_positive: float = 0.3
    continuation_stages: int = 4
    continuation_min_points: int = 25
    continuation_stage_lambda: float = 0.005
    continuation_final_lambda: float = 0.02
    continuation_anchor_weight: float = 2.5


@dataclass(frozen=True)
class StrategySweepSpec:
    label: str
    options: FitStrategyOptions


def _as_vector(values) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


def composite_fit_score(result: FitResult) -> tuple[float, dict[str, float]]:
    stats = result.stats
    diagnostics = result.diagnostics
    region_stats = diagnostics.get("region_stats", {}) or {}
    worst_region = region_stats.get("worst_region") if isinstance(region_stats, dict) else None
    worst_mean = 0.0
    if worst_region and isinstance(region_stats.get(worst_region), dict):
        value = region_stats[worst_region].get("mean")
        worst_mean = 0.0 if value is None else float(value)
    boundary_penalty = 5.0 * len(diagnostics.get("boundary_hits") or [])
    warning_penalty = 2.0 * len(diagnostics.get("warnings") or [])
    terms = {
        "mean_error": float(stats.get("mean", 0.0)),
        "max_error_penalty": 0.10 * float(stats.get("max", 0.0)),
        "worst_region_penalty": 0.25 * worst_mean,
        "boundary_penalty": boundary_penalty,
        "warning_penalty": warning_penalty,
    }
    return float(sum(terms.values())), terms


def default_strategy_sweep_specs(base: FitStrategyOptions | None = None) -> list[StrategySweepSpec]:
    base = base or FitStrategyOptions()
    return [
        StrategySweepSpec("quick_global", FitStrategyOptions(name=QUICK_GLOBAL)),
        StrategySweepSpec("robust_global", FitStrategyOptions(name=ROBUST_GLOBAL)),
        StrategySweepSpec(
            "continuation_fit",
            FitStrategyOptions(
                name=CONTINUATION_FIT,
                continuation_core_negative=base.continuation_core_negative,
                continuation_core_positive=base.continuation_core_positive,
                continuation_stages=base.continuation_stages,
                continuation_min_points=base.continuation_min_points,
                continuation_stage_lambda=base.continuation_stage_lambda,
                continuation_final_lambda=base.continuation_final_lambda,
                continuation_anchor_weight=base.continuation_anchor_weight,
            ),
        ),
        StrategySweepSpec(
            "weighted_regions",
            FitStrategyOptions(
                name=WEIGHTED_REGIONS,
                reverse_weight=base.reverse_weight,
                near_zero_weight=base.near_zero_weight,
                forward_weight=base.forward_weight,
                high_forward_weight=base.high_forward_weight,
            ),
        ),
        StrategySweepSpec("staged_physical", FitStrategyOptions(name=STAGED_PHYSICAL)),
    ]


@contextlib.contextmanager
def _stdout_policy(verbose: bool):
    if verbose:
        yield
        return
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def normalize_strategy_name(name: str | None) -> str:
    normalized = (name or QUICK_GLOBAL).strip().lower().replace("-", "_")
    if normalized not in STRATEGY_NAMES:
        raise ValueError(f"Unknown fit strategy: {name!r}")
    return normalized


def region_masks(voltage: np.ndarray, options: FitStrategyOptions) -> dict[str, np.ndarray]:
    return shared_region_masks(
        voltage,
        near_zero_width=options.near_zero_width,
        high_forward_threshold=options.high_forward_threshold,
    )


def region_weights(voltage: np.ndarray, options: FitStrategyOptions) -> np.ndarray:
    weights = np.ones_like(_as_vector(voltage), dtype=float)
    masks = region_masks(voltage, options)
    weights[masks["reverse"]] = max(0.0, float(options.reverse_weight))
    weights[masks["near_zero"]] = max(0.0, float(options.near_zero_weight))
    weights[masks["forward"]] = max(0.0, float(options.forward_weight))
    weights[masks["high_forward"]] = max(0.0, float(options.high_forward_weight))
    return weights


def region_error_stats(
    voltage: np.ndarray,
    measured: np.ndarray,
    predicted: np.ndarray,
    config: Config,
    options: FitStrategyOptions,
) -> dict[str, dict[str, float | None] | str | None]:
    return shared_region_error_stats(
        voltage,
        measured,
        predicted,
        config,
        near_zero_width=options.near_zero_width,
        high_forward_threshold=options.high_forward_threshold,
    )


def _prepare_meta(
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    params_meta: dict | None,
    verbose: bool,
) -> dict:
    with _stdout_policy(verbose):
        meta = _copy_params_meta(params_meta) if params_meta is not None else initialize_parameters(voltage, current, config)
    return _prepare_params_meta(meta, config)


def _build_result(
    voltage: np.ndarray,
    current: np.ndarray,
    params: np.ndarray,
    fit_results: dict,
    params_meta: dict,
    config: Config,
    options: FitStrategyOptions,
) -> FitResult:
    diagnostics = fit_results.get("diagnostics")
    if diagnostics is None:
        diagnostics = fit_diagnostics(voltage, current, params, fit_results, params_meta, config)
        fit_results["diagnostics"] = diagnostics
    diagnostics["strategy"] = normalize_strategy_name(options.name)
    diagnostics["region_weights"] = {
        "reverse": float(options.reverse_weight),
        "near_zero": float(options.near_zero_weight),
        "forward": float(options.forward_weight),
        "high_forward": float(options.high_forward_weight),
    }
    diagnostics["region_stats"] = region_error_stats(voltage, current, fit_results["JD"], config, options)
    currents = calculate_currents(voltage, params, config)
    return FitResult(
        params=_as_vector(params),
        fit_results=fit_results,
        currents=currents,
        stats=diagnostics["stats"],
        diagnostics=diagnostics,
        config=config,
        params_meta=_prepare_params_meta(params_meta, config),
    )


def _meta_from_result(result: FitResult) -> dict:
    meta = _copy_params_meta(result.params_meta)
    meta["x0"] = result.params.copy()
    return meta


def _continuation_stage_windows(voltage: np.ndarray, options: FitStrategyOptions) -> list[tuple[float, float]]:
    v = _as_vector(voltage)
    min_v = float(np.min(v))
    max_v = float(np.max(v))
    core_low = max(min_v, float(options.continuation_core_negative))
    core_high = min(max_v, float(options.continuation_core_positive))
    if core_low >= core_high:
        core_low = min_v
        core_high = max_v

    stage_count = max(2, int(options.continuation_stages))
    low_values = np.linspace(core_low, min_v, stage_count)
    high_values = np.linspace(core_high, max_v, stage_count)
    windows: list[tuple[float, float]] = []
    for low, high in zip(low_values, high_values, strict=False):
        window = (float(min(low, high)), float(max(low, high)))
        if not windows or any(abs(window[i] - windows[-1][i]) > 1e-12 for i in (0, 1)):
            windows.append(window)
    if windows[-1] != (min_v, max_v):
        windows.append((min_v, max_v))
    return windows


def _continuation_anchor_weights(
    voltage: np.ndarray,
    core_window: tuple[float, float],
    options: FitStrategyOptions,
) -> np.ndarray:
    v = _as_vector(voltage)
    weights = np.ones_like(v, dtype=float)
    mask = (v >= core_window[0]) & (v <= core_window[1])
    weights[mask] = max(1.0, float(options.continuation_anchor_weight))
    return weights


def _weighted_fit_with_prior(
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    params_meta: dict | None,
    point_weights: np.ndarray,
    options: FitStrategyOptions,
    verbose: bool,
) -> FitResult:
    cfg = clone_config(config)
    meta = _prepare_meta(voltage, current, cfg, params_meta, verbose)
    x0 = _params_to_optimizer(meta["x0"], meta)
    fun = lambda x: error_function(
        x,
        voltage,
        current,
        meta,
        cfg,
        cfg.regularization.prior,
        point_weights=point_weights,
    )
    lb, ub = _optimizer_bounds(meta)
    rng = np.random.default_rng(cfg.optimization.random_seed)
    with _stdout_policy(verbose):
        x_opt, resnorm = run_with_multistart(fun, x0, lb, ub, cfg.optimization, max_nfev=8000, tol=1e-10, rng=rng)
    params = _optimizer_to_params(x_opt, meta)
    predicted = diode_model(voltage, params, cfg)
    fit_results = {
        "JD": predicted,
        "resnorm": float(resnorm),
        "relative_errors": relative_errors(predicted, current),
    }
    return _build_result(voltage, current, params, fit_results, meta, cfg, options)


def _quick_global(
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    params_meta: dict | None,
    options: FitStrategyOptions,
    verbose: bool,
) -> FitResult:
    cfg = clone_config(config)
    cfg.optimization.staged_fallback = False
    cfg.optimization.max_attempts = 1
    cfg.optimization.max_retries = 0
    result = run_fit(voltage, current, cfg, params_meta, verbose=verbose)
    result.diagnostics["strategy"] = QUICK_GLOBAL
    result.diagnostics["region_weights"] = {
        "reverse": 1.0,
        "near_zero": 1.0,
        "forward": 1.0,
        "high_forward": 1.0,
    }
    result.diagnostics["region_stats"] = region_error_stats(
        voltage,
        current,
        result.fit_results["JD"],
        result.config,
        FitStrategyOptions(name=QUICK_GLOBAL, reverse_weight=1.0, near_zero_weight=1.0, forward_weight=1.0, high_forward_weight=1.0),
    )
    result.fit_results["diagnostics"] = result.diagnostics
    return result


def _robust_global(
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    params_meta: dict | None,
    options: FitStrategyOptions,
    verbose: bool,
) -> FitResult:
    cfg = clone_config(config)
    cfg.optimization.staged_fallback = False
    cfg.optimization.max_attempts = 1
    cfg.optimization.max_retries = 0
    cfg.optimization.least_squares_loss = options.robust_loss
    cfg.optimization.loss_f_scale = max(1e-12, float(options.robust_f_scale))
    result = run_fit(voltage, current, cfg, params_meta, verbose=verbose)
    result.diagnostics["strategy"] = ROBUST_GLOBAL
    result.diagnostics["robust_loss"] = cfg.optimization.least_squares_loss
    result.diagnostics["loss_f_scale"] = cfg.optimization.loss_f_scale
    result.diagnostics["region_weights"] = {
        "reverse": 1.0,
        "near_zero": 1.0,
        "forward": 1.0,
        "high_forward": 1.0,
    }
    result.diagnostics["region_stats"] = region_error_stats(
        voltage,
        current,
        result.fit_results["JD"],
        result.config,
        FitStrategyOptions(name=ROBUST_GLOBAL, reverse_weight=1.0, near_zero_weight=1.0, forward_weight=1.0, high_forward_weight=1.0),
    )
    result.fit_results["diagnostics"] = result.diagnostics
    return result


def _weighted_regions(
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    params_meta: dict | None,
    options: FitStrategyOptions,
    verbose: bool,
) -> FitResult:
    cfg = clone_config(config)
    meta = _prepare_meta(voltage, current, cfg, params_meta, verbose)
    x0 = _params_to_optimizer(meta["x0"], meta)
    point_weights = region_weights(voltage, options)
    fun = lambda x: error_function(
        x,
        voltage,
        current,
        meta,
        cfg,
        cfg.regularization.prior,
        point_weights=point_weights,
    )
    lb, ub = _optimizer_bounds(meta)
    rng = np.random.default_rng(cfg.optimization.random_seed)
    with _stdout_policy(verbose):
        x_opt, resnorm = run_with_multistart(fun, x0, lb, ub, cfg.optimization, max_nfev=8000, tol=1e-10, rng=rng)
    params = _optimizer_to_params(x_opt, meta)
    predicted = diode_model(voltage, params, cfg)
    fit_results = {
        "JD": predicted,
        "resnorm": float(resnorm),
        "relative_errors": relative_errors(predicted, current),
    }
    return _build_result(voltage, current, params, fit_results, meta, cfg, options)


def _staged_physical(
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    params_meta: dict | None,
    options: FitStrategyOptions,
    verbose: bool,
) -> FitResult:
    cfg = clone_config(config)
    cfg.optimization.staged_fallback = True
    meta = _prepare_meta(voltage, current, cfg, params_meta, verbose)
    x0 = _params_to_optimizer(meta["x0"], meta)
    rng = np.random.default_rng(cfg.optimization.random_seed)
    with _stdout_policy(verbose):
        staged_start, rel_errors = fit_negative_region(voltage, current, x0, meta, cfg, rng)
        staged_start, _ = fit_positive_region(voltage, current, staged_start, meta, cfg, rel_errors, rng)
        params, fit_results = final_optimization(
            voltage,
            current,
            staged_start,
            meta,
            cfg,
            rng,
            max_attempts=max(1, min(3, int(cfg.optimization.max_attempts))),
    )
    return _build_result(voltage, current, params, fit_results, meta, cfg, options)


def _continuation_fit(
    voltage: np.ndarray,
    current: np.ndarray,
    config: Config,
    params_meta: dict | None,
    options: FitStrategyOptions,
    verbose: bool,
) -> FitResult:
    cfg = clone_config(config)
    windows = _continuation_stage_windows(voltage, options)
    core_window = windows[0]
    stage_results: list[dict[str, float | int | str]] = []
    last_result: FitResult | None = None
    next_meta = _copy_params_meta(params_meta) if params_meta is not None else None
    stage_template = FitStrategyOptions(
        name=ROBUST_GLOBAL,
        robust_loss=options.robust_loss,
        robust_f_scale=options.robust_f_scale,
    )

    for stage_index, (low, high) in enumerate(windows[:-1], start=1):
        mask = (voltage >= low) & (voltage <= high)
        point_count = int(np.sum(mask))
        if point_count < max(8, int(options.continuation_min_points)):
            continue

        stage_cfg = clone_config(cfg)
        stage_cfg.optimization.use_de_fallback = False
        stage_cfg.optimization.staged_fallback = False
        stage_cfg.optimization.max_attempts = 1
        stage_cfg.optimization.max_retries = 0
        if last_result is not None:
            stage_cfg.regularization.prior = last_result.params.copy()
            stage_cfg.regularization.lambda_ = max(0.0, float(options.continuation_stage_lambda))
            next_meta = _meta_from_result(last_result)

        stage_fit = run_fit_strategy(
            voltage[mask],
            current[mask],
            stage_cfg,
            next_meta,
            stage_template,
            verbose=verbose,
        )
        stage_results.append(
            {
                "stage": int(stage_index),
                "window_low": float(low),
                "window_high": float(high),
                "points": point_count,
                "mean_error": float(stage_fit.stats.get("mean", np.nan)),
                "max_error": float(stage_fit.stats.get("max", np.nan)),
            }
        )
        last_result = stage_fit
        next_meta = _meta_from_result(stage_fit)

    if last_result is None:
        fallback = _robust_global(voltage, current, cfg, params_meta, options, verbose)
        fallback.diagnostics["strategy"] = CONTINUATION_FIT
        fallback.diagnostics["continuation"] = {
            "core_window": {"low": float(core_window[0]), "high": float(core_window[1])},
            "stages": [],
            "anchor_weight": float(options.continuation_anchor_weight),
            "stage_regularization": float(options.continuation_stage_lambda),
            "final_regularization": float(options.continuation_final_lambda),
            "fallback_reason": "not_enough_points_in_core_window",
        }
        fallback.fit_results["diagnostics"] = fallback.diagnostics
        return fallback

    final_cfg = clone_config(cfg)
    final_cfg.regularization.prior = last_result.params.copy()
    final_cfg.regularization.lambda_ = max(0.0, float(options.continuation_final_lambda))
    final_meta = _meta_from_result(last_result)
    point_weights = _continuation_anchor_weights(voltage, core_window, options)
    result = _weighted_fit_with_prior(voltage, current, final_cfg, final_meta, point_weights, options, verbose)
    result.diagnostics["strategy"] = CONTINUATION_FIT
    result.diagnostics["continuation"] = {
        "core_window": {"low": float(core_window[0]), "high": float(core_window[1])},
        "stages": stage_results,
        "anchor_weight": float(options.continuation_anchor_weight),
        "stage_regularization": float(options.continuation_stage_lambda),
        "final_regularization": float(options.continuation_final_lambda),
    }
    result.fit_results["diagnostics"] = result.diagnostics
    return result


def run_fit_strategy(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    config: Config | None = None,
    params_meta: dict | None = None,
    options: FitStrategyOptions | None = None,
    *,
    verbose: bool = False,
) -> FitResult:
    opts = options or FitStrategyOptions()
    opts.name = normalize_strategy_name(opts.name)
    voltage = _as_vector(data_v)
    current = _as_vector(data_jd)
    cfg = clone_config(config)

    if opts.name == QUICK_GLOBAL:
        return _quick_global(voltage, current, cfg, params_meta, opts, verbose)
    if opts.name == ROBUST_GLOBAL:
        return _robust_global(voltage, current, cfg, params_meta, opts, verbose)
    if opts.name == WEIGHTED_REGIONS:
        return _weighted_regions(voltage, current, cfg, params_meta, opts, verbose)
    if opts.name == STAGED_PHYSICAL:
        return _staged_physical(voltage, current, cfg, params_meta, opts, verbose)
    if opts.name == CONTINUATION_FIT:
        return _continuation_fit(voltage, current, cfg, params_meta, opts, verbose)
    raise ValueError(f"Unknown fit strategy: {opts.name!r}")


def run_strategy_sweep(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    config: Config | None = None,
    params_meta: dict | None = None,
    base_options: FitStrategyOptions | None = None,
    *,
    verbose: bool = False,
) -> list[FitResult]:
    voltage = _as_vector(data_v)
    current = _as_vector(data_jd)
    cfg = clone_config(config)
    base_meta = _prepare_meta(voltage, current, cfg, params_meta, verbose)
    results: list[FitResult] = []
    for spec in default_strategy_sweep_specs(base_options):
        meta = _copy_params_meta(base_meta)
        fit = run_fit_strategy(voltage, current, cfg, meta, spec.options, verbose=verbose)
        score, terms = composite_fit_score(fit)
        fit.diagnostics["strategy_preset"] = spec.label
        fit.diagnostics["composite_score"] = score
        fit.diagnostics["score_terms"] = terms
        fit.fit_results["diagnostics"] = fit.diagnostics
        results.append(fit)
    return sorted(results, key=lambda item: (item.stats["mean"], item.stats["max"], item.diagnostics.get("composite_score", np.inf)))
