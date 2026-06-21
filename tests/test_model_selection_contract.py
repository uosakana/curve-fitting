from __future__ import annotations

import unittest

import numpy as np

from fit.core import ModelFitResult, ModelSpec, build_model_selection_contract


def _region(mean: float) -> dict:
    return {
        "reverse": {"mean": mean, "max": mean * 2.0, "count": 10.0},
        "near_zero": {"mean": mean, "max": mean * 2.0, "count": 5.0},
        "forward": {"mean": mean, "max": mean * 2.0, "count": 10.0},
        "high_forward": {"mean": mean, "max": mean * 2.0, "count": 10.0},
        "worst_region": "reverse",
    }


def _spec(name: str, stage: str, category: str = "baseline_chain") -> ModelSpec:
    return ModelSpec(
        name=name,
        free_mask=np.array([True, True, True, True]),
        fixed_values={},
        description=name,
        stage=stage,
        category=category,
        report_role="diagnostic_ablation" if category == "diagnostic_ablation" else "baseline_candidate",
    )


def _fit(
    name: str,
    stage: str,
    *,
    bic: float,
    aic: float,
    mean: float,
    max_error: float,
    region_mean: float,
    category: str = "baseline_chain",
    nested: dict | None = None,
) -> ModelFitResult:
    diagnostics = {"region_stats": _region(region_mean)}
    if nested is not None:
        diagnostics["nested_no_k_selection"] = nested
    return ModelFitResult(
        spec=_spec(name, stage, category),
        params=np.ones(4),
        fit_results={},
        stats={"mean": mean, "max": max_error},
        diagnostics=diagnostics,
        aic=aic,
        bic=bic,
        free_parameter_count=4,
        config=None,
        params_meta={},
    )


class ModelSelectionContractTest(unittest.TestCase):
    def test_diagnostic_ablation_cannot_be_recommended_baseline(self) -> None:
        nested = {"downgraded": False}
        rows = [
            _fit("diode_series_only", "M0", bic=100.0, aic=98.0, mean=20.0, max_error=40.0, region_mean=20.0),
            _fit("ohmic_leakage_only", "M1", bic=80.0, aic=78.0, mean=15.0, max_error=30.0, region_mean=12.0),
            _fit("full", "M2", bic=70.0, aic=68.0, mean=13.0, max_error=28.0, region_mean=9.0, nested=nested),
            _fit(
                "nonohmic_leakage_only",
                "diagnostic_ablation",
                bic=10.0,
                aic=8.0,
                mean=5.0,
                max_error=15.0,
                region_mean=5.0,
                category="diagnostic_ablation",
            ),
        ]

        contract = build_model_selection_contract(rows)

        self.assertEqual(contract["recommended_model"], "full")
        self.assertEqual(contract["recommended_stage"], "M2")
        self.assertEqual(contract["diagnostic_ablation_models"][0]["name"], "nonohmic_leakage_only")
        self.assertNotIn(
            "nonohmic_leakage_only",
            {item["name"] for item in contract["baseline_candidates"]},
        )

    def test_m2_no_k_fallback_reports_m3_on_m1_parameterization(self) -> None:
        nested = {"downgraded": True, "selected_stage": "M3", "reasons": ["k is near its lower bound"]}
        rows = [
            _fit("diode_series_only", "M0", bic=100.0, aic=98.0, mean=20.0, max_error=40.0, region_mean=20.0),
            _fit("ohmic_leakage_only", "M1", bic=80.0, aic=78.0, mean=15.0, max_error=30.0, region_mean=12.0),
            _fit("full", "M2", bic=70.0, aic=68.0, mean=13.0, max_error=28.0, region_mean=9.0, nested=nested),
        ]

        contract = build_model_selection_contract(rows)

        self.assertEqual(contract["recommended_model"], "ohmic_leakage_only")
        self.assertEqual(contract["recommended_stage"], "M3")
        self.assertFalse(contract["decisions"]["M1_to_M2"]["accepted"])
        self.assertIn("m2_to_m3_no_k_fallback", contract["decisions"]["M1_to_M2"]["blockers"])

    def test_complex_baseline_step_rejects_large_max_error_regression(self) -> None:
        nested = {"downgraded": False}
        rows = [
            _fit("diode_series_only", "M0", bic=100.0, aic=98.0, mean=20.0, max_error=40.0, region_mean=20.0),
            _fit("ohmic_leakage_only", "M1", bic=80.0, aic=78.0, mean=15.0, max_error=80.0, region_mean=12.0),
            _fit("full", "M2", bic=70.0, aic=68.0, mean=13.0, max_error=28.0, region_mean=9.0, nested=nested),
        ]

        contract = build_model_selection_contract(rows)

        self.assertEqual(contract["recommended_model"], "diode_series_only")
        self.assertEqual(contract["recommended_stage"], "M0")
        self.assertFalse(contract["decisions"]["M0_to_M1"]["accepted"])
        self.assertFalse(contract["decisions"]["M0_to_M1"]["criteria"]["max_error_not_worse"])


if __name__ == "__main__":
    unittest.main()
