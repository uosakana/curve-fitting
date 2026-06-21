"""Numerical fitting package for the Python I-V workflow."""

from fit.core import (
    FitResult,
    ModelFitResult,
    ModelSpec,
    build_model_selection_contract,
    diagnostic_ablation_candidates,
    baseline_model_candidates,
    compare_models,
    evaluate_params,
    recommended_baseline_model,
    run_fit,
    scan_m_values,
)
from fit.parameter_schema import (
    BASE_EVALUATOR_KIND,
    DEFAULT_M_VALUES,
    DEFAULT_N_VALUES,
    PARAM_NAMES,
    params_meta_from_values,
)
from fit.workflow import AnalysisOptions, AnalysisResult, run_analysis

__all__ = [
    "AnalysisOptions",
    "AnalysisResult",
    "BASE_EVALUATOR_KIND",
    "DEFAULT_M_VALUES",
    "DEFAULT_N_VALUES",
    "FitResult",
    "ModelFitResult",
    "ModelSpec",
    "PARAM_NAMES",
    "baseline_model_candidates",
    "build_model_selection_contract",
    "compare_models",
    "diagnostic_ablation_candidates",
    "evaluate_params",
    "params_meta_from_values",
    "recommended_baseline_model",
    "run_fit",
    "run_analysis",
    "scan_m_values",
]
