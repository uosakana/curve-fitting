from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from config import Config
from fit.core import (
    FitResult,
    ModelFitResult,
    clone_config,
    compare_models as compare_model_specs,
    diagnostic_ablation_candidates,
    evaluate_params,
    recommended_baseline_model,
    scan_m_values,
)
from fit.model import Currents, relative_errors
from fit.parameter_schema import DEFAULT_M_VALUES, DEFAULT_N_VALUES
from fit.post_fit import run_clean_double_diode_rescue, run_post_fit_models
from fit.strategy import FitStrategyOptions, run_fit_strategy, run_strategy_sweep
from fit.advice import build_fit_advice


DISPLAY_SWITCH_MEAN_WORSEN_TOLERANCE = 0.5
DISPLAY_SWITCH_MAX_WORSEN_TOLERANCE = 1.0


@dataclass
class AnalysisOptions:
    run_fit: bool = True
    fit_strategy: str = "quick_global"
    sweep_strategies: bool = False
    reverse_weight: float = 1.5
    near_zero_weight: float = 0.5
    forward_weight: float = 1.0
    high_forward_weight: float = 1.5
    scan_m: bool = False
    scan_n: bool = False
    use_best_m_after_scan: bool = True
    compare_models: bool = False
    m_values: tuple[float, ...] = DEFAULT_M_VALUES
    n_values: tuple[float, ...] = DEFAULT_N_VALUES
    quick_m_scan: bool = True
    warm_start_m_scan: bool = True
    post_fit_models: bool = True
    fit_verbose: bool = False
    analysis_verbose: bool = False


@dataclass
class AnalysisResult:
    fit: FitResult | None = None
    strategy_sweep: list[FitResult] = field(default_factory=list)
    m_scan: list[FitResult] = field(default_factory=list)
    model_comparison: list[ModelFitResult] = field(default_factory=list)
    post_fit_models: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    advice: list[dict] = field(default_factory=list)
    config: Config | None = None
    params_meta: dict | None = None


def _meta_with_start(params_meta: dict | None, fit: FitResult | None) -> dict | None:
    if fit is None:
        return params_meta
    meta = {key: value.copy() if isinstance(value, np.ndarray) else value for key, value in fit.params_meta.items()}
    meta["x0"] = fit.params.copy()
    return meta


def _strategy_options(opts: AnalysisOptions) -> FitStrategyOptions:
    return FitStrategyOptions(
        name=opts.fit_strategy,
        reverse_weight=opts.reverse_weight,
        near_zero_weight=opts.near_zero_weight,
        forward_weight=opts.forward_weight,
        high_forward_weight=opts.high_forward_weight,
    )


def _scan_exponents_with_strategy(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    opts: AnalysisOptions,
    config: Config,
    params_meta: dict | None,
) -> list[FitResult]:
    m_grid = [float(value) for value in opts.m_values] if opts.scan_m else [float(config.physics.m)]
    n_grid = [float(value) for value in opts.n_values] if opts.scan_n else [float(config.physics.n)]
    if not m_grid:
        raise ValueError("m_values cannot be empty.")
    if not n_grid:
        raise ValueError("n_values cannot be empty.")

    results: list[FitResult] = []
    next_meta = params_meta
    for n_value in n_grid:
        for m_value in m_grid:
            cfg = clone_config(config, n=n_value, m=m_value)
            if opts.quick_m_scan:
                cfg.optimization.max_attempts = 1
                cfg.optimization.max_retries = 0
                if opts.fit_strategy != "staged_physical":
                    cfg.optimization.staged_fallback = False
            fit = run_fit_strategy(
                data_v,
                data_jd,
                cfg,
                next_meta,
                _strategy_options(opts),
                verbose=opts.analysis_verbose,
            )
            fit.diagnostics["exponent_profile"] = {
                "n": float(n_value),
                "m": float(m_value),
                "n_bounds": [min(n_grid), max(n_grid)],
                "m_bounds": [min(m_grid), max(m_grid)],
            }
            fit.fit_results["diagnostics"] = fit.diagnostics
            results.append(fit)
            if opts.warm_start_m_scan:
                next_meta = _meta_with_start(next_meta, fit)

    return sorted(results, key=lambda item: (item.stats["mean"], item.stats["max"]))


def _fit_strategy_name(fit: FitResult | None, fallback: str) -> str:
    if fit is None:
        return fallback
    diagnostics = fit.diagnostics or {}
    return str(diagnostics.get("strategy") or diagnostics.get("strategy_preset") or fallback)


def _m_profile_improves_display(reference: FitResult, candidate: FitResult) -> bool:
    mean_delta = float(candidate.stats["mean"]) - float(reference.stats["mean"])
    max_delta = float(candidate.stats["max"]) - float(reference.stats["max"])
    return (
        mean_delta < -0.05
        and max_delta <= DISPLAY_SWITCH_MAX_WORSEN_TOLERANCE
    )


def _annotate_m_profile_decision(
    fit: FitResult,
    *,
    reference: FitResult | None,
    best_scan: FitResult | None,
    used_for_display: bool,
) -> None:
    if best_scan is None:
        return
    reference_stats = None if reference is None else reference.stats
    mean_improvement = None
    max_delta = None
    if reference is not None:
        mean_improvement = float(reference.stats["mean"]) - float(best_scan.stats["mean"])
        max_delta = float(best_scan.stats["max"]) - float(reference.stats["max"])
    profile = best_scan.diagnostics.get("exponent_profile") or {}
    fit.diagnostics["m_profile"] = {
        "status": "used_for_display" if used_for_display else "diagnostic_only",
        "best_m": float(best_scan.m),
        "best_n": float(best_scan.n),
        "display_m": float(fit.m),
        "display_n": float(fit.n),
        "best_stats": best_scan.stats,
        "reference_stats": reference_stats,
        "mean_improvement": mean_improvement,
        "max_delta": max_delta,
        "n_bounds": profile.get("n_bounds"),
        "m_bounds": profile.get("m_bounds"),
    }
    fit.fit_results["diagnostics"] = fit.diagnostics


def _fit_from_recommended_baseline(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    selected_baseline: ModelFitResult,
    config: Config,
    previous_fit: FitResult | None,
) -> FitResult:
    displayed = evaluate_params(
        data_v,
        data_jd,
        selected_baseline.params,
        config,
        selected_baseline.params_meta,
    )
    recommended_stage = (
        selected_baseline.diagnostics.get("recommended_baseline_stage")
        or selected_baseline.spec.stage
    )
    model_selection = (
        selected_baseline.diagnostics.get("model_selection")
        or selected_baseline.diagnostics.get("baseline_selection")
    )
    previous_diagnostics = previous_fit.diagnostics if previous_fit is not None else {}
    displayed.diagnostics.update(
        {
            "strategy": previous_diagnostics.get("strategy"),
            "strategy_preset": previous_diagnostics.get("strategy_preset"),
            "display_fit_source": "m_model_recommended_baseline",
            "display_fit_switched": True,
            "source_fit_stats": None if previous_fit is None else previous_fit.stats,
            "model_stage": selected_baseline.spec.stage,
            "model_category": selected_baseline.spec.category,
            "report_role": selected_baseline.spec.report_role,
            "selected_for_baseline": True,
            "recommended_baseline_stage": recommended_stage,
            "baseline_selection": model_selection,
            "model_selection": model_selection,
            "information_criteria": {
                "aic": selected_baseline.aic,
                "bic": selected_baseline.bic,
                "free_parameter_count": selected_baseline.free_parameter_count,
            },
        }
    )
    displayed.fit_results["diagnostics"] = displayed.diagnostics
    return displayed


def _display_switch_allowed(previous_fit: FitResult | None, candidate_fit: FitResult) -> bool:
    if previous_fit is None:
        return True
    mean_delta = float(candidate_fit.stats["mean"]) - float(previous_fit.stats["mean"])
    max_delta = float(candidate_fit.stats["max"]) - float(previous_fit.stats["max"])
    return (
        mean_delta <= DISPLAY_SWITCH_MEAN_WORSEN_TOLERANCE
        and max_delta <= DISPLAY_SWITCH_MAX_WORSEN_TOLERANCE
    )


def _annotate_blocked_display_switch(
    fit: FitResult,
    candidate_fit: FitResult,
    selected_baseline: ModelFitResult,
) -> None:
    model_selection = (
        selected_baseline.diagnostics.get("model_selection")
        or selected_baseline.diagnostics.get("baseline_selection")
    )
    recommended_stage = (
        selected_baseline.diagnostics.get("recommended_baseline_stage")
        or selected_baseline.spec.stage
    )
    fit.diagnostics.update(
        {
            "display_fit_source": "strategy_fit",
            "display_fit_switched": False,
            "m_model_display_switch_blocked": True,
            "m_model_display_switch_blocked_reason": "recommended M-model baseline worsened the current displayed fit",
            "m_model_candidate_stats": candidate_fit.stats,
            "recommended_baseline_stage": recommended_stage,
            "baseline_selection": model_selection,
            "model_selection": model_selection,
        }
    )
    fit.fit_results["diagnostics"] = fit.diagnostics


def _fit_needs_rescue(fit: FitResult, config: Config) -> bool:
    mean_error = float(fit.stats.get("mean", np.inf))
    max_error = float(fit.stats.get("max", np.inf))
    return (
        mean_error >= float(config.fitting.post_model_trigger_mean_error)
        or max_error >= float(config.fitting.post_model_trigger_max_error)
    )


def _selected_post_fit_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in candidates
            if item.get("status") == "ok"
            and (item.get("diagnostics") or {}).get("selected_for_replacement")
        ),
        None,
    )


def _fit_from_post_fit_candidate(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    candidate: dict[str, Any],
    base_fit: FitResult,
    config: Config,
) -> FitResult:
    series = candidate.get("series") or {}
    if "fitted" not in series:
        raise ValueError(f"Post-fit candidate {candidate.get('name', '<unknown>')} does not include fitted series.")

    fitted = np.asarray(series["fitted"], dtype=float).reshape(-1)
    diode = np.asarray(series.get("diode", np.zeros_like(fitted)), dtype=float).reshape(-1)
    ohmic = np.asarray(series.get("ohmic", np.zeros_like(fitted)), dtype=float).reshape(-1)
    nonohmic = np.asarray(series.get("nonohmic", np.zeros_like(fitted)), dtype=float).reshape(-1)
    rel = np.asarray(series.get("relative_error", relative_errors(fitted, data_jd)), dtype=float).reshape(-1)
    recombination = np.asarray(series.get("recombination", []), dtype=float).reshape(-1)
    diffusion = np.asarray(series.get("diffusion", []), dtype=float).reshape(-1)
    empirical_nonohmic = np.asarray(series.get("empirical_nonohmic", []), dtype=float).reshape(-1)
    extra_current = np.asarray(series.get("extra_current", []), dtype=float).reshape(-1)
    extended_nonohmic_total = np.asarray(series.get("extended_nonohmic_total", []), dtype=float).reshape(-1)
    v_drop = np.asarray(series.get("v_drop", []), dtype=float).reshape(-1)

    diagnostics = copy.deepcopy(candidate.get("diagnostics") or {})
    warnings = list(diagnostics.get("warnings") or [])
    if recombination.size == fitted.size and diffusion.size == fitted.size:
        denom = np.abs(recombination) + np.abs(diffusion) + np.abs(ohmic) + np.finfo(float).eps
        component_percent = {
            "recombination": float(np.mean(np.abs(recombination) / denom) * 100.0),
            "diffusion": float(np.mean(np.abs(diffusion) / denom) * 100.0),
            "ohmic": float(np.mean(np.abs(ohmic) / denom) * 100.0),
            "nonohmic": 0.0,
        }
        diagnostics["component_percent"] = component_percent
        weak_branches = [
            name
            for name in ("recombination", "diffusion")
            if component_percent[name] < 10.0
        ]
        if weak_branches:
            warnings.append(
                "M4 branch decomposition is weak for "
                f"{', '.join(weak_branches)}; trust the total fit more than the small branch magnitude."
            )
    diagnostics.update(
        {
            "display_fit_source": "post_fit_model",
            "display_fit_switched": True,
            "source_fit_stats": copy.deepcopy(base_fit.stats),
            "param_names": list(candidate.get("param_names") or []),
            "model_stage": diagnostics.get("model_stage") or candidate.get("name"),
            "model_name": candidate.get("name"),
            "warnings": warnings,
            "information_criteria": {
                "aic": candidate.get("aic"),
                "bic": candidate.get("bic"),
                "free_parameter_count": candidate.get("free_parameter_count"),
            },
        }
    )
    fit_results = {
        "JD": fitted,
        "relative_errors": rel,
        "resnorm": float(np.sum((fitted - np.asarray(data_jd, dtype=float).reshape(-1)) ** 2)),
        "diagnostics": diagnostics,
    }
    if recombination.size == fitted.size:
        fit_results["recombination"] = recombination
    if diffusion.size == fitted.size:
        fit_results["diffusion"] = diffusion
    if empirical_nonohmic.size == fitted.size:
        fit_results["empirical_nonohmic"] = empirical_nonohmic
    if extra_current.size == fitted.size:
        fit_results["extra_current"] = extra_current
    if extended_nonohmic_total.size == fitted.size:
        fit_results["extended_nonohmic_total"] = extended_nonohmic_total
    if v_drop.size == fitted.size:
        fit_results["v_drop"] = v_drop
    summed = diode + ohmic + nonohmic
    if extra_current.size == fitted.size:
        summed = summed + extra_current
    currents = Currents(
        total=fitted,
        diode=diode,
        ohmic=ohmic,
        nonohmic=nonohmic,
        summed=summed,
    )
    params_meta = {
        key: value.copy() if isinstance(value, np.ndarray) else copy.deepcopy(value)
        for key, value in base_fit.params_meta.items()
    }
    raw_params = candidate.get("params")
    params = np.asarray([] if raw_params is None else raw_params, dtype=float).reshape(-1)
    params_meta["x0"] = params.copy()
    return FitResult(
        params=params,
        fit_results=fit_results,
        currents=currents,
        stats=copy.deepcopy(candidate.get("stats") or {}),
        diagnostics=diagnostics,
        config=copy.deepcopy(config),
        params_meta=params_meta,
    )


def _promote_selected_post_fit_candidate(
    result: AnalysisResult,
    data_v: np.ndarray,
    data_jd: np.ndarray,
    candidate: dict[str, Any] | None,
    base_fit: FitResult,
    config: Config,
) -> FitResult | None:
    if candidate is None:
        return None
    promoted = _fit_from_post_fit_candidate(data_v, data_jd, candidate, base_fit, config)
    result.fit = promoted
    result.config = promoted.config
    result.params_meta = promoted.params_meta
    return promoted


def interpret_analysis(result: AnalysisResult) -> list[str]:
    notes: list[str] = []

    if result.fit is not None:
        strategy = result.fit.diagnostics.get("strategy")
        if strategy:
            notes.append(f"Fit strategy used: {strategy}.")
        if result.fit.diagnostics.get("display_fit_source") == "m_model_recommended_baseline":
            notes.append(
                "Displayed fit was switched to the recommended M-model baseline "
                f"{result.fit.diagnostics.get('recommended_baseline_stage', '--')}."
            )
        elif result.fit.diagnostics.get("display_fit_source") == "post_fit_model":
            notes.append(
                "Displayed fit was switched to the selected post-fit model "
                f"{result.fit.diagnostics.get('model_name', '--')}."
            )
        elif result.fit.diagnostics.get("m_model_display_switch_blocked"):
            stats = result.fit.diagnostics.get("m_model_candidate_stats") or {}
            notes.append(
                "M-model selection was kept diagnostic because the recommended baseline would worsen "
                f"the displayed fit (candidate mean {float(stats.get('mean', 0.0)):.2f}%, "
                f"max {float(stats.get('max', 0.0)):.2f}%)."
            )
        continuation = result.fit.diagnostics.get("continuation", {})
        if isinstance(continuation, dict) and continuation.get("stages"):
            core = continuation.get("core_window", {})
            notes.append(
                "Continuation fit expanded from "
                f"{core.get('low', '--')} V to {core.get('high', '--')} V "
                f"before the final full-range pass."
            )
        for warning in result.fit.diagnostics.get("warnings", []):
            notes.append(warning)
        region_stats = result.fit.diagnostics.get("region_stats", {})
        worst_region = region_stats.get("worst_region") if isinstance(region_stats, dict) else None
        if worst_region:
            notes.append(f"Worst voltage region by mean error: {worst_region}.")

    if result.strategy_sweep:
        best = result.strategy_sweep[0]
        preset = best.diagnostics.get("strategy_preset") or best.diagnostics.get("strategy")
        score = best.diagnostics.get("composite_score")
        if score is not None:
            notes.append(f"Best strategy sweep candidate is {preset} with composite score {float(score):.2f}.")
        else:
            notes.append(f"Best strategy sweep candidate is {preset}.")

    if result.m_scan:
        best_m = result.m_scan[0]
        reference = result.fit
        if reference is not None and (
            abs(best_m.m - reference.m) > 1e-12
            or abs(best_m.n - reference.n) > 1e-12
        ):
            improvement = reference.stats["mean"] - best_m.stats["mean"]
            if improvement > 0.5:
                notes.append(
                    f"Bounded n/m profiling improved mean error by {improvement:.2f}% "
                    f"at n={best_m.n:.3g}, m={best_m.m:.3g}; "
                    "the fixed ideality or non-ohmic exponent may be limiting the mechanism fit."
                )
        if reference is not None and abs(best_m.m - reference.m) <= 1e-12 and abs(best_m.n - reference.n) <= 1e-12:
            notes.append(f"Final fit uses the best profiled n/m values: n={best_m.n:.3g}, m={best_m.m:.3g}.")
        notes.append(
            f"Best exponent-profile candidate is n={best_m.n:.3g}, m={best_m.m:.3g} "
            f"(mean {best_m.stats['mean']:.2f}%, max {best_m.stats['max']:.2f}%)."
        )

    if result.model_comparison:
        baseline_model = recommended_baseline_model(result.model_comparison) or result.model_comparison[0]
        baseline_stage = baseline_model.diagnostics.get("recommended_baseline_stage") or baseline_model.spec.stage
        notes.append(
            f"Recommended baseline model is {baseline_stage} ({baseline_model.spec.name}): "
            f"{baseline_model.spec.description}."
        )
        ablations = diagnostic_ablation_candidates(result.model_comparison)
        if ablations:
            notes.append(
                "Diagnostic ablation models were run separately and were not eligible to replace the M0-M3 baseline."
            )
        full_model = next((item for item in result.model_comparison if item.spec.stage == "M2"), None)
        if full_model is not None:
            nested = full_model.diagnostics.get("nested_no_k_selection") or {}
            if nested:
                selected = nested.get("selected_model")
                bic_delta = float(nested.get("bic_improvement_full_vs_no_k") or 0.0)
                nonohmic_pct = nested.get("nonohmic_component_pct")
                if nested.get("downgraded"):
                    reasons = ", ".join(nested.get("reasons") or ["non-ohmic term is not well supported"])
                    notes.append(
                        "Nested leakage selection downgrades M2 to the no-k equivalent "
                        f"M3 ({selected}) because {reasons}; "
                        f"full-vs-no-k BIC improvement is {bic_delta:+.2f}."
                    )
                elif nonohmic_pct is not None:
                    notes.append(
                        "Nested leakage selection keeps M2 full leakage: "
                        f"non-ohmic contribution is {float(nonohmic_pct):.2f}% and "
                        f"full-vs-no-k BIC improvement is {bic_delta:+.2f}."
                    )
    elif result.fit is not None:
        notes.append(
            "M-model diagnostics were not run; enable M-model diagnostics to rank M0-M3 leakage models "
            "and run first-stage M4/M8 candidates."
        )

    model_candidates = [
        model
        for model in result.post_fit_models
        if model.get("name") not in {"base_reference", "core_window_base"} and model.get("status") == "ok"
    ]
    selected_candidates = [
        model
        for model in model_candidates
        if (model.get("diagnostics") or {}).get("selected_for_replacement")
    ]
    if selected_candidates:
        best_selected = selected_candidates[0]
        stats = best_selected.get("stats") or {}
        diagnostics = best_selected.get("diagnostics") or {}
        notes.append(
            f"Post-fit model candidate selected: {best_selected.get('name')} "
            f"(mean {float(stats.get('mean', 0.0)):.2f}%, max {float(stats.get('max', 0.0)):.2f}%, "
            f"BIC improvement {float(diagnostics.get('bic_improvement') or 0.0):+.2f})."
        )
    elif model_candidates:
        non_legacy_candidates = [
            model
            for model in model_candidates
            if (model.get("diagnostics") or {}).get("publication_confidence") != "diagnostic_only_legacy_k_mixed"
        ]
        ranking_pool = non_legacy_candidates or model_candidates
        best_bic = min(
            ranking_pool,
            key=lambda item: float(item.get("bic")) if item.get("bic") is not None else float("inf"),
        )
        best_mean = max(
            ranking_pool,
            key=lambda item: float((item.get("diagnostics") or {}).get("mean_improvement") or -float("inf")),
        )
        bic_diag = best_bic.get("diagnostics") or {}
        mean_diag = best_mean.get("diagnostics") or {}
        notes.append(
            "No post-fit model candidate cleared the replacement threshold; "
            f"best non-legacy BIC candidate is {best_bic.get('name')} "
            f"(BIC delta {float(bic_diag.get('bic_improvement') or 0.0):+.2f})."
        )
        notes.append(
            f"Best non-legacy mean-error improvement candidate is {best_mean.get('name')} "
            f"(mean delta {float(mean_diag.get('mean_improvement') or 0.0):+.2f}%, "
            f"max delta {float(mean_diag.get('max_improvement') or 0.0):+.2f}%)."
        )
        if len(non_legacy_candidates) != len(model_candidates):
            notes.append("Legacy double-diode+k candidates remain diagnostic-only and are excluded from replacement ranking.")

    for model in result.post_fit_models:
        name = model.get("name")
        diagnostics = model.get("diagnostics") or {}
        if name == "clean_double_diode" and model.get("status") == "ok":
            evidence = diagnostics.get("forward_semilog_two_slope_evidence") or {}
            status = "selected" if diagnostics.get("selected_for_replacement") else "diagnostic-only"
            notes.append(
                "Clean M4 double-diode candidate is "
                f"{status}; forward semilog evidence: {evidence.get('reason', 'not_checked')}."
            )
        if name == "core_window_base" and model.get("status") == "ok":
            window = diagnostics.get("window") or {}
            core_stats = diagnostics.get("core_stats") or {}
            full_stats = diagnostics.get("full_extrapolation_stats") or {}
            failures = diagnostics.get("failure_regions") or []
            notes.append(
                "Core-window fit "
                f"({float(window.get('low', -0.5)):.3g} to {float(window.get('high', 0.3)):.3g} V) "
                f"has mean {float(core_stats.get('mean', 0.0)):.2f}% and max {float(core_stats.get('max', 0.0)):.2f}%; "
                f"full extrapolation mean {float(full_stats.get('mean', 0.0)):.2f}%."
            )
            if diagnostics.get("model_limited"):
                notes.append(
                    "The base model is locally valid in the core window but model-limited over the full range; "
                    f"failure region(s): {', '.join(failures)}."
                )

    deduped: list[str] = []
    for note in notes:
        if note not in deduped:
            deduped.append(note)
    return deduped


def run_analysis(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    options: AnalysisOptions | None = None,
    config: Config | None = None,
    params_meta: dict | None = None,
) -> AnalysisResult:
    opts = options or AnalysisOptions()
    cfg = clone_config(config)
    result = AnalysisResult(config=cfg, params_meta=params_meta)

    fit_result: FitResult | None = None
    if opts.run_fit and opts.sweep_strategies:
        result.strategy_sweep = run_strategy_sweep(
            data_v,
            data_jd,
            cfg,
            params_meta,
            _strategy_options(opts),
            verbose=opts.fit_verbose,
        )
        fit_result = result.strategy_sweep[0]
        result.fit = fit_result
        result.config = fit_result.config
        result.params_meta = fit_result.params_meta
        if (opts.scan_m or opts.scan_n) and fit_result is not None:
            scan_strategy = _fit_strategy_name(fit_result, opts.fit_strategy)
            scan_opts = replace(opts, fit_strategy=scan_strategy)
            scan_meta = _meta_with_start(params_meta, fit_result)
            result.m_scan = _scan_exponents_with_strategy(data_v, data_jd, scan_opts, cfg, scan_meta)
            best_scan = result.m_scan[0] if result.m_scan else None
            if (
                opts.use_best_m_after_scan
                and best_scan is not None
                and _m_profile_improves_display(fit_result, best_scan)
            ):
                final_config = clone_config(cfg, n=best_scan.n, m=best_scan.m)
                final_meta = _meta_with_start(params_meta, best_scan)
                profiled_fit = run_fit_strategy(
                    data_v,
                    data_jd,
                    final_config,
                    final_meta,
                    _strategy_options(scan_opts),
                    verbose=opts.fit_verbose,
                )
                if _display_switch_allowed(fit_result, profiled_fit):
                    _annotate_m_profile_decision(
                        profiled_fit,
                        reference=fit_result,
                        best_scan=best_scan,
                        used_for_display=True,
                    )
                    fit_result = profiled_fit
                    result.fit = fit_result
                    result.config = fit_result.config
                    result.params_meta = fit_result.params_meta
                else:
                    _annotate_m_profile_decision(
                        fit_result,
                        reference=fit_result,
                        best_scan=best_scan,
                        used_for_display=False,
                    )
            elif best_scan is not None:
                _annotate_m_profile_decision(
                    fit_result,
                    reference=fit_result,
                    best_scan=best_scan,
                    used_for_display=False,
                )
    elif opts.run_fit and (opts.scan_m or opts.scan_n):
        result.m_scan = _scan_exponents_with_strategy(data_v, data_jd, opts, cfg, params_meta)
        best_scan = result.m_scan[0]
        final_config = clone_config(cfg, n=best_scan.n, m=best_scan.m)
        final_meta = _meta_with_start(params_meta, best_scan) if opts.use_best_m_after_scan else params_meta
        fit_result = run_fit_strategy(
            data_v,
            data_jd,
            final_config,
            final_meta,
            _strategy_options(opts),
            verbose=opts.fit_verbose,
        )
        result.fit = fit_result
        result.config = fit_result.config
        result.params_meta = fit_result.params_meta
    elif opts.run_fit:
        fit_result = run_fit_strategy(
            data_v,
            data_jd,
            cfg,
            params_meta,
            _strategy_options(opts),
            verbose=opts.fit_verbose,
        )
        result.fit = fit_result
        result.config = fit_result.config
        result.params_meta = fit_result.params_meta

    analysis_meta = _meta_with_start(params_meta, fit_result)
    analysis_config = result.config or cfg
    selected_baseline: ModelFitResult | None = None

    if (opts.scan_m or opts.scan_n) and not result.m_scan and not opts.sweep_strategies:
        result.m_scan = _scan_exponents_with_strategy(data_v, data_jd, opts, analysis_config, analysis_meta)

    if opts.compare_models:
        result.model_comparison = compare_model_specs(
            data_v,
            data_jd,
            analysis_config,
            analysis_meta,
            verbose=opts.analysis_verbose,
        )
        selected_baseline = recommended_baseline_model(result.model_comparison)
        if selected_baseline is not None:
            candidate_fit = _fit_from_recommended_baseline(
                data_v,
                data_jd,
                selected_baseline,
                analysis_config,
                result.fit,
            )
            if _display_switch_allowed(result.fit, candidate_fit):
                fit_result = candidate_fit
                result.fit = fit_result
                result.config = fit_result.config
                result.params_meta = fit_result.params_meta
                analysis_config = result.config
                analysis_meta = _meta_with_start(params_meta, fit_result)
            elif result.fit is not None:
                _annotate_blocked_display_switch(result.fit, candidate_fit, selected_baseline)
                fit_result = result.fit

    if opts.post_fit_models and fit_result is not None:
        post_fit_reference = fit_result
        if selected_baseline is not None:
            post_fit_reference = fit_result
        result.post_fit_models = run_post_fit_models(
            data_v,
            data_jd,
            post_fit_reference,
            analysis_config,
            verbose=opts.analysis_verbose,
        )
        selected_post = _selected_post_fit_candidate(result.post_fit_models)
        promoted = _promote_selected_post_fit_candidate(
            result,
            data_v,
            data_jd,
            selected_post,
            post_fit_reference,
            analysis_config,
        )
        if promoted is not None:
            fit_result = promoted
    elif opts.compare_models and fit_result is not None and _fit_needs_rescue(fit_result, analysis_config):
        rescue = run_clean_double_diode_rescue(
            data_v,
            data_jd,
            fit_result,
            analysis_config,
            verbose=opts.analysis_verbose,
        )
        result.post_fit_models = [rescue]
        promoted = _promote_selected_post_fit_candidate(
            result,
            data_v,
            data_jd,
            rescue if (rescue.get("diagnostics") or {}).get("selected_for_replacement") else None,
            fit_result,
            analysis_config,
        )
        if promoted is not None:
            fit_result = promoted

    result.notes = interpret_analysis(result)
    result.advice = build_fit_advice(result.fit, result.model_comparison, result.m_scan) if result.fit is not None else []
    return result
