from __future__ import annotations

import contextlib
import copy
import io
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from config import Config, load_config
from fit.initialize_parameters import initialize_parameters
from fit.model import Currents, calculate_currents, diode_model, error_function, relative_errors
from fit.optimization import (
    _copy_params_meta,
    _optimizer_bounds,
    _optimizer_to_params,
    _params_to_optimizer,
    _prepare_params_meta,
    _stats,
    fit_diagnostics,
    perform_fitting,
    run_with_multistart,
)
from fit.parameter_schema import PARAM_NAMES, params_meta_from_values
from fit.region_stats import region_error_stats


@dataclass
class FitResult:
    params: np.ndarray
    fit_results: dict
    currents: Currents
    stats: dict[str, float]
    diagnostics: dict
    config: Config
    params_meta: dict

    @property
    def m(self) -> float:
        return float(self.config.physics.m)

    @property
    def n(self) -> float:
        return float(self.config.physics.n)


@dataclass
class ModelSpec:
    name: str
    free_mask: np.ndarray
    fixed_values: dict[str, float]
    description: str
    stage: str = ""
    category: str = "baseline_chain"
    report_role: str = "baseline_candidate"


@dataclass
class ModelFitResult:
    spec: ModelSpec
    params: np.ndarray
    fit_results: dict
    stats: dict[str, float]
    diagnostics: dict
    aic: float
    bic: float
    free_parameter_count: int
    config: Config
    params_meta: dict


NO_K_BIC_IMPROVEMENT_THRESHOLD = 2.0
NO_K_COMPONENT_THRESHOLD_PCT = 3.0
NO_K_LOWER_BOUND_FACTOR = 1.05
BASELINE_BIC_IMPROVEMENT_THRESHOLD = 2.0
BASELINE_MEAN_WORSEN_TOLERANCE = 0.5
BASELINE_MAX_WORSEN_TOLERANCE = 1.0
BASELINE_REGION_IMPROVEMENT_THRESHOLD = 1.0


def _as_vector(values) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(-1)


@contextlib.contextmanager
def _stdout_policy(verbose: bool):
    if verbose:
        yield
        return
    with contextlib.redirect_stdout(io.StringIO()):
        yield


def clone_config(config: Config | None = None, *, n: float | None = None, m: float | None = None) -> Config:
    cloned = copy.deepcopy(config or load_config())
    if n is not None:
        cloned.physics.n = float(n)
    if m is not None:
        cloned.physics.m = float(m)
    return cloned


def evaluate_params(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    params: np.ndarray,
    config: Config | None = None,
    params_meta: dict | None = None,
) -> FitResult:
    cfg = clone_config(config)
    voltage = _as_vector(data_v)
    current = _as_vector(data_jd)
    params = _as_vector(params)
    predicted = diode_model(voltage, params, cfg)
    fit_results = {
        "JD": predicted,
        "relative_errors": relative_errors(predicted, current),
        "resnorm": float(np.sum((predicted - current) ** 2)),
    }
    if params_meta is None:
        params_meta = params_meta_from_values(params)
    prepared_meta = _prepare_params_meta(params_meta, cfg)
    diagnostics = fit_diagnostics(voltage, current, params, fit_results, prepared_meta, cfg)
    fit_results["diagnostics"] = diagnostics
    currents = calculate_currents(voltage, params, cfg)
    return FitResult(
        params=params,
        fit_results=fit_results,
        currents=currents,
        stats=diagnostics["stats"],
        diagnostics=diagnostics,
        config=cfg,
        params_meta=prepared_meta,
    )


def run_fit(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    config: Config | None = None,
    params_meta: dict | None = None,
    *,
    verbose: bool = True,
) -> FitResult:
    cfg = clone_config(config)
    voltage = _as_vector(data_v)
    current = _as_vector(data_jd)
    with _stdout_policy(verbose):
        meta = _copy_params_meta(params_meta) if params_meta is not None else initialize_parameters(voltage, current, cfg)
        params, fit_results = perform_fitting(voltage, current, meta, cfg)
    diagnostics = fit_results.get("diagnostics")
    if diagnostics is None:
        diagnostics = fit_diagnostics(voltage, current, params, fit_results, meta, cfg)
        fit_results["diagnostics"] = diagnostics
    currents = calculate_currents(voltage, params, cfg)
    return FitResult(
        params=params,
        fit_results=fit_results,
        currents=currents,
        stats=diagnostics["stats"],
        diagnostics=diagnostics,
        config=cfg,
        params_meta=_prepare_params_meta(meta, cfg),
    )


def scan_m_values(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    m_values: Iterable[float],
    config: Config | None = None,
    params_meta: dict | None = None,
    *,
    quick: bool = True,
    warm_start: bool = True,
    verbose: bool = False,
) -> list[FitResult]:
    voltage = _as_vector(data_v)
    current = _as_vector(data_jd)
    base_config = clone_config(config)
    m_grid = [float(value) for value in m_values]
    if not m_grid:
        raise ValueError("m_values cannot be empty.")

    with _stdout_policy(verbose):
        base_meta = _copy_params_meta(params_meta) if params_meta is not None else initialize_parameters(voltage, current, base_config)

    results: list[FitResult] = []
    next_meta = base_meta
    for m_value in m_grid:
        cfg = clone_config(base_config, m=m_value)
        if quick:
            cfg.optimization.staged_fallback = False
            cfg.optimization.max_attempts = 1
            cfg.optimization.max_retries = 0
        result = run_fit(voltage, current, cfg, next_meta, verbose=verbose)
        results.append(result)
        if warm_start:
            next_meta = _copy_params_meta(result.params_meta)
            next_meta["x0"] = result.params.copy()

    return sorted(results, key=lambda item: (item.stats["mean"], item.stats["max"]))


def default_model_specs(params_meta: dict) -> list[ModelSpec]:
    lb = _as_vector(params_meta["lb"])
    ub = _as_vector(params_meta["ub"])
    return [
        ModelSpec(
            name="diode_series_only",
            free_mask=np.array([True, True, False, False]),
            fixed_values={"Rsh": float(ub[2]), "k": float(lb[3])},
            description="diode + Rs only; both leakage terms minimized",
            stage="M0",
            category="baseline_chain",
            report_role="baseline_candidate",
        ),
        ModelSpec(
            name="ohmic_leakage_only",
            free_mask=np.array([True, True, True, False]),
            fixed_values={"k": float(lb[3])},
            description="diode + Rs + ohmic leakage; non-ohmic term held near zero",
            stage="M1",
            category="baseline_chain",
            report_role="baseline_candidate",
        ),
        ModelSpec(
            name="full",
            free_mask=np.array([True, True, True, True]),
            fixed_values={},
            description="diode + Rs + ohmic leakage + non-ohmic leakage",
            stage="M2",
            category="baseline_chain",
            report_role="baseline_candidate",
        ),
        ModelSpec(
            name="nonohmic_leakage_only",
            free_mask=np.array([True, True, False, True]),
            fixed_values={"Rsh": float(ub[2])},
            description="diode + Rs + non-ohmic leakage; ohmic shunt held near zero",
            stage="diagnostic_ablation",
            category="diagnostic_ablation",
            report_role="diagnostic_ablation",
        ),
    ]


def _apply_fixed_values(params: np.ndarray, spec: ModelSpec) -> np.ndarray:
    adjusted = params.copy()
    for name, value in spec.fixed_values.items():
        try:
            idx = PARAM_NAMES.index(name)
        except ValueError as exc:
            raise ValueError(f"Unknown parameter in model spec: {name}") from exc
        adjusted[idx] = float(value)
    return adjusted


def _information_criteria(residuals: np.ndarray, parameter_count: int) -> tuple[float, float]:
    residuals = _as_vector(residuals)
    n = max(1, residuals.size)
    rss = max(float(np.sum(residuals**2)), np.finfo(float).tiny)
    aic = n * np.log(rss / n) + 2.0 * parameter_count
    bic = n * np.log(rss / n) + parameter_count * np.log(n)
    return float(aic), float(bic)


def fit_model_spec(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    spec: ModelSpec,
    config: Config | None = None,
    params_meta: dict | None = None,
    *,
    verbose: bool = False,
) -> ModelFitResult:
    cfg = clone_config(config)
    voltage = _as_vector(data_v)
    current = _as_vector(data_jd)
    with _stdout_policy(verbose):
        meta = _copy_params_meta(params_meta) if params_meta is not None else initialize_parameters(voltage, current, cfg)
    meta = _prepare_params_meta(meta, cfg)
    start_params = _apply_fixed_values(meta["x0"], spec)
    x0 = _params_to_optimizer(start_params, meta)
    mask = np.asarray(spec.free_mask, dtype=bool)
    if mask.size != len(PARAM_NAMES):
        raise ValueError(f"free_mask must contain {len(PARAM_NAMES)} entries.")

    fun = lambda x: error_function(
        x,
        voltage,
        current,
        meta,
        cfg,
        cfg.regularization.prior,
        mask,
        x0,
    )
    lb, ub = _optimizer_bounds(meta, mask)
    rng = np.random.default_rng(cfg.optimization.random_seed)
    with _stdout_policy(verbose):
        x_opt, resnorm = run_with_multistart(fun, x0[mask], lb, ub, cfg.optimization, max_nfev=8000, tol=1e-10, rng=rng)

    x_full = x0.copy()
    x_full[mask] = x_opt
    params = _optimizer_to_params(x_full, meta)
    params = _apply_fixed_values(params, spec)
    predicted = diode_model(voltage, params, cfg)
    fit_results = {
        "JD": predicted,
        "resnorm": float(resnorm),
        "relative_errors": relative_errors(predicted, current),
    }
    diagnostics = fit_diagnostics(voltage, current, params, fit_results, meta, cfg)
    diagnostics["region_stats"] = region_error_stats(voltage, current, predicted, cfg)
    diagnostics["model_stage"] = spec.stage
    diagnostics["model_category"] = spec.category
    diagnostics["report_role"] = spec.report_role
    fit_results["diagnostics"] = diagnostics
    residuals = error_function(x_opt, voltage, current, meta, cfg, cfg.regularization.prior, mask, x0)
    free_count = int(np.sum(mask))
    aic, bic = _information_criteria(residuals, free_count)
    result_meta = _copy_params_meta(meta)
    result_meta["x0"] = params.copy()
    diagnostics["information_criteria"] = {
        "aic": aic,
        "bic": bic,
        "free_parameter_count": free_count,
    }
    return ModelFitResult(
        spec=spec,
        params=params,
        fit_results=fit_results,
        stats=diagnostics["stats"],
        diagnostics=diagnostics,
        aic=aic,
        bic=bic,
        free_parameter_count=free_count,
        config=cfg,
        params_meta=result_meta,
    )


def _annotate_nested_no_k_selection(
    results: list[ModelFitResult],
    params_meta: dict,
) -> None:
    by_name = {item.spec.name: item for item in results}
    full = by_name.get("full")
    no_k = by_name.get("ohmic_leakage_only")
    if full is None or no_k is None:
        return

    lb = _as_vector(params_meta["lb"])
    k_lower = float(lb[3])
    k_value = float(full.params[3])
    k_lower_bound_ratio = k_value / max(k_lower, np.finfo(float).tiny)
    component = full.diagnostics.get("component_percent") or {}
    nonohmic_pct = component.get("nonohmic")
    try:
        nonohmic_pct_value = float(nonohmic_pct)
    except (TypeError, ValueError):
        nonohmic_pct_value = np.inf

    bic_improvement = float(no_k.bic - full.bic)
    criteria = {
        "k_near_lower_bound": bool(k_value <= k_lower * NO_K_LOWER_BOUND_FACTOR),
        "nonohmic_component_low": bool(nonohmic_pct_value <= NO_K_COMPONENT_THRESHOLD_PCT),
        "bic_improvement_small": bool(bic_improvement < NO_K_BIC_IMPROVEMENT_THRESHOLD),
    }
    reasons: list[str] = []
    if criteria["k_near_lower_bound"]:
        reasons.append("k is near its lower bound")
    if criteria["nonohmic_component_low"]:
        reasons.append(f"non-ohmic contribution is <= {NO_K_COMPONENT_THRESHOLD_PCT:g}%")
    if criteria["bic_improvement_small"]:
        reasons.append(f"full model improves BIC by < {NO_K_BIC_IMPROVEMENT_THRESHOLD:g}")

    downgraded = any(criteria.values())
    selected_model = "ohmic_leakage_only" if downgraded else "full"
    selected_stage = "M3" if downgraded else "M2"
    decision = {
        "rule": "M2_to_M3_no_k",
        "downgraded": bool(downgraded),
        "selected_model": selected_model,
        "selected_stage": selected_stage,
        "m2_model": "full",
        "m3_equivalent_model": "ohmic_leakage_only",
        "bic_improvement_full_vs_no_k": bic_improvement,
        "k_lower_bound_ratio": k_lower_bound_ratio,
        "nonohmic_component_pct": None if not np.isfinite(nonohmic_pct_value) else nonohmic_pct_value,
        "criteria": criteria,
        "reasons": reasons,
    }
    for item in results:
        item.diagnostics["nested_no_k_selection"] = decision
        item.diagnostics["selected_for_nested_model"] = bool(item.spec.name == selected_model)


def baseline_model_candidates(results: Iterable[ModelFitResult]) -> list[ModelFitResult]:
    return [
        item
        for item in results
        if item.spec.category == "baseline_chain" and item.spec.stage in {"M0", "M1", "M2"}
    ]


def diagnostic_ablation_candidates(results: Iterable[ModelFitResult]) -> list[ModelFitResult]:
    return [item for item in results if item.spec.category == "diagnostic_ablation"]


def _rank_baseline_candidate(item: ModelFitResult) -> tuple[float, float, float, float]:
    return (float(item.bic), float(item.aic), float(item.stats["mean"]), float(item.stats["max"]))


def _safe_float(value, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if np.isfinite(number) else default


def _region_mean(item: ModelFitResult, region_name: str) -> float | None:
    region_stats = item.diagnostics.get("region_stats") or {}
    if not isinstance(region_stats, dict):
        return None
    row = region_stats.get(region_name)
    if not isinstance(row, dict):
        return None
    return _safe_float(row.get("mean"))


def _transition_decision(
    *,
    rule: str,
    from_item: ModelFitResult | None,
    to_item: ModelFitResult | None,
    target_regions: tuple[str, ...],
    blocked: bool = False,
    blockers: list[str] | None = None,
) -> dict:
    blockers = list(blockers or [])
    if from_item is None or to_item is None:
        return {
            "rule": rule,
            "from_stage": None if from_item is None else from_item.spec.stage,
            "to_stage": None if to_item is None else to_item.spec.stage,
            "accepted": False,
            "blocked": True,
            "blockers": blockers + ["missing_candidate"],
            "criteria": {},
            "reasons": ["required model candidate is missing"],
        }

    bic_improvement = float(from_item.bic - to_item.bic)
    aic_improvement = float(from_item.aic - to_item.aic)
    mean_improvement = float(from_item.stats["mean"] - to_item.stats["mean"])
    max_improvement = float(from_item.stats["max"] - to_item.stats["max"])
    region_improvements: dict[str, float | None] = {}
    for region_name in target_regions:
        before = _region_mean(from_item, region_name)
        after = _region_mean(to_item, region_name)
        region_improvements[region_name] = None if before is None or after is None else float(before - after)

    target_region_improved = any(
        value is not None and value >= BASELINE_REGION_IMPROVEMENT_THRESHOLD
        for value in region_improvements.values()
    )
    criteria = {
        "bic_improvement_at_least_2": bool(bic_improvement >= BASELINE_BIC_IMPROVEMENT_THRESHOLD),
        "mean_error_not_worse": bool(mean_improvement >= -BASELINE_MEAN_WORSEN_TOLERANCE),
        "max_error_not_worse": bool(max_improvement >= -BASELINE_MAX_WORSEN_TOLERANCE),
        "target_region_improved": bool(target_region_improved),
        "not_blocked": not blocked,
    }
    accepted = bool(
        criteria["bic_improvement_at_least_2"]
        and criteria["mean_error_not_worse"]
        and criteria["max_error_not_worse"]
        and criteria["not_blocked"]
    )
    reasons: list[str] = []
    if accepted:
        reasons.append(f"{to_item.spec.stage} improves BIC by {bic_improvement:.2f}.")
        if target_region_improved:
            reasons.append(f"{to_item.spec.stage} improves target region error.")
    else:
        for key, ok in criteria.items():
            if not ok:
                reasons.append(key)
        reasons.extend(blockers)

    return {
        "rule": rule,
        "from_model": from_item.spec.name,
        "from_stage": from_item.spec.stage,
        "to_model": to_item.spec.name,
        "to_stage": to_item.spec.stage,
        "accepted": accepted,
        "blocked": bool(blocked),
        "blockers": blockers,
        "bic_improvement": bic_improvement,
        "aic_improvement": aic_improvement,
        "mean_improvement": mean_improvement,
        "max_improvement": max_improvement,
        "target_regions": list(target_regions),
        "region_mean_improvements": region_improvements,
        "criteria": criteria,
        "reasons": reasons,
    }


def build_model_selection_contract(results: Iterable[ModelFitResult]) -> dict:
    all_results = list(results)
    baseline = baseline_model_candidates(all_results)
    diagnostic = diagnostic_ablation_candidates(all_results)
    by_stage = {item.spec.stage: item for item in baseline}
    m0 = by_stage.get("M0")
    m1 = by_stage.get("M1")
    m2 = by_stage.get("M2")
    nested = (m2.diagnostics.get("nested_no_k_selection") if m2 is not None else None) or {}
    m0_to_m1 = _transition_decision(
        rule="M0_to_M1_add_ohmic_shunt",
        from_item=m0,
        to_item=m1,
        target_regions=("reverse", "near_zero"),
    )
    m2_blockers = ["m2_to_m3_no_k_fallback"] if nested.get("downgraded") else []
    m1_to_m2 = _transition_decision(
        rule="M1_to_M2_add_nonohmic_leakage",
        from_item=m1,
        to_item=m2,
        target_regions=("reverse", "high_forward"),
        blocked=bool(nested.get("downgraded")),
        blockers=m2_blockers,
    )

    selected = m0
    selected_stage = "M0"
    reason = "m0_default"
    path = ["M0"] if m0 is not None else []
    if m1 is not None and m0_to_m1.get("accepted"):
        selected = m1
        selected_stage = "M1"
        reason = "m0_to_m1_accepted"
        path.append("M1")
    if selected is m1 and m2 is not None:
        if nested.get("downgraded"):
            selected = m1
            selected_stage = "M3"
            reason = "m2_to_m3_no_k_fallback"
            path.append("M3")
        elif m1_to_m2.get("accepted"):
            selected = m2
            selected_stage = "M2"
            reason = "m1_to_m2_accepted"
            path.append("M2")

    bic_best = sorted(baseline, key=_rank_baseline_candidate)[0] if baseline else None
    selected_summary = None if selected is None else _candidate_summary(selected)
    if selected_summary is not None:
        selected_summary["reported_stage"] = selected_stage
    ranked_baseline = [_candidate_summary(item) for item in sorted(baseline, key=_rank_baseline_candidate)]
    ranked_ablations = [
        _candidate_summary(item)
        for item in sorted(diagnostic, key=lambda item: (item.bic, item.stats["mean"], item.stats["max"]))
    ]
    return {
        "version": 1,
        "rule": "M0_M1_M2_baseline_chain_with_M3_no_k",
        "recommended_model": None if selected is None else selected.spec.name,
        "recommended_baseline_model": None if selected is None else selected.spec.name,
        "recommended_stage": selected_stage if selected is not None else None,
        "recommended_category": "baseline_chain" if selected is not None else None,
        "reason": reason,
        "selection_path": path,
        "recommended": selected_summary,
        "bic_best_baseline": None if bic_best is None else _candidate_summary(bic_best),
        "baseline_candidates": ranked_baseline,
        "ranked_baseline_candidates": ranked_baseline,
        "diagnostic_ablation_models": ranked_ablations,
        "decisions": {
            "M0_to_M1": m0_to_m1,
            "M1_to_M2": m1_to_m2,
            "M2_to_M3_no_k": nested,
        },
        "m3_no_k_decision": nested,
        "notes": [
            "Diagnostic ablation models are excluded from recommended baseline eligibility.",
            "M3 is represented by the M1 no-k parameterization when M2's k branch is not supported.",
        ],
    }


def recommended_baseline_model(results: Iterable[ModelFitResult]) -> ModelFitResult | None:
    candidates = baseline_model_candidates(results)
    if not candidates:
        return None
    contract = next(
        (
            item.diagnostics.get("model_selection")
            for item in candidates
            if isinstance(item.diagnostics.get("model_selection"), dict)
        ),
        None,
    )
    if contract:
        selected_name = contract.get("recommended_model")
        selected = next((item for item in candidates if item.spec.name == selected_name), None)
        if selected is not None:
            return selected
    by_stage = {item.spec.stage: item for item in candidates}
    best = sorted(candidates, key=_rank_baseline_candidate)[0]
    m2 = by_stage.get("M2")
    m1 = by_stage.get("M1")
    nested = (m2.diagnostics.get("nested_no_k_selection") if m2 is not None else None) or {}
    if best.spec.stage == "M2" and nested.get("downgraded") and m1 is not None:
        return m1
    return best


def _candidate_summary(item: ModelFitResult) -> dict[str, float | str]:
    return {
        "name": item.spec.name,
        "stage": item.spec.stage,
        "bic": float(item.bic),
        "aic": float(item.aic),
        "mean": float(item.stats["mean"]),
        "max": float(item.stats["max"]),
    }


def _annotate_baseline_selection(results: list[ModelFitResult]) -> None:
    baseline = baseline_model_candidates(results)
    if not baseline:
        return
    contract = build_model_selection_contract(results)
    selected_name = contract.get("recommended_model")
    selected = next((item for item in baseline if item.spec.name == selected_name), None)
    if selected is None:
        return
    for item in results:
        item.diagnostics["model_selection"] = contract
        item.diagnostics["baseline_selection"] = contract
        item.diagnostics["selected_for_baseline"] = bool(item is selected)
        if item is selected:
            item.diagnostics["recommended_baseline_stage"] = contract.get("recommended_stage")


def compare_models(
    data_v: np.ndarray,
    data_jd: np.ndarray,
    config: Config | None = None,
    params_meta: dict | None = None,
    specs: Iterable[ModelSpec] | None = None,
    *,
    verbose: bool = False,
) -> list[ModelFitResult]:
    cfg = clone_config(config)
    voltage = _as_vector(data_v)
    current = _as_vector(data_jd)
    with _stdout_policy(verbose):
        meta = _copy_params_meta(params_meta) if params_meta is not None else initialize_parameters(voltage, current, cfg)
    meta = _prepare_params_meta(meta, cfg)
    model_specs = list(specs) if specs is not None else default_model_specs(meta)
    results = [
        fit_model_spec(voltage, current, spec, cfg, meta, verbose=verbose)
        for spec in model_specs
    ]
    _annotate_nested_no_k_selection(results, meta)
    _annotate_baseline_selection(results)
    selected = recommended_baseline_model(results)
    selected_name = selected.spec.name if selected is not None else None
    baseline_rank = sorted(baseline_model_candidates(results), key=_rank_baseline_candidate)
    diagnostic_rank = sorted(diagnostic_ablation_candidates(results), key=lambda item: (item.bic, item.stats["mean"], item.stats["max"]))
    ordered: list[ModelFitResult] = []
    if selected is not None:
        ordered.append(selected)
    ordered.extend(item for item in baseline_rank if item.spec.name != selected_name)
    ordered.extend(diagnostic_rank)
    ordered_ids = {id(item) for item in ordered}
    remaining = [item for item in results if id(item) not in ordered_ids]
    ordered.extend(sorted(remaining, key=lambda item: (item.bic, item.stats["mean"], item.stats["max"])))
    return ordered
