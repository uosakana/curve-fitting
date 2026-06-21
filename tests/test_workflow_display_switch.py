from __future__ import annotations

import unittest

import numpy as np

from config import load_config
from fit.core import ModelFitResult, ModelSpec, evaluate_params
from fit.model import diode_model
from fit.parameter_schema import params_meta_from_values
from fit.workflow import (
    _annotate_blocked_display_switch,
    _display_switch_allowed,
    _fit_from_recommended_baseline,
)


class WorkflowDisplaySwitchTest(unittest.TestCase):
    def test_recommended_m_model_becomes_displayed_fit(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.3, 0.3, 21)
        selected_params = np.array([1e-9, 800.0, 5e7, 2e-8], dtype=float)
        current = diode_model(voltage, selected_params, config)
        params_meta = params_meta_from_values(selected_params)
        previous_fit = evaluate_params(voltage, current, selected_params, config, params_meta)
        previous_fit.diagnostics["strategy"] = "quick_global"
        selected = ModelFitResult(
            spec=ModelSpec(
                name="full",
                free_mask=np.array([True, True, True, True]),
                fixed_values={},
                description="full model",
                stage="M2",
            ),
            params=selected_params,
            fit_results={},
            stats={"mean": 0.0, "max": 0.0},
            diagnostics={
                "recommended_baseline_stage": "M2",
                "model_selection": {"recommended_stage": "M2"},
            },
            aic=-100.0,
            bic=-90.0,
            free_parameter_count=4,
            config=config,
            params_meta=params_meta,
        )

        displayed = _fit_from_recommended_baseline(voltage, current, selected, config, previous_fit)

        self.assertEqual(displayed.diagnostics["display_fit_source"], "m_model_recommended_baseline")
        self.assertEqual(displayed.diagnostics["recommended_baseline_stage"], "M2")
        self.assertEqual(displayed.diagnostics["strategy"], "quick_global")
        self.assertLess(displayed.stats["mean"], 1e-9)

    def test_recommended_m_model_does_not_replace_better_strategy_fit(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.3, 0.3, 21)
        current = diode_model(voltage, np.array([1e-9, 800.0, 5e7, 2e-8], dtype=float), config)
        params_meta = params_meta_from_values(np.array([1e-9, 800.0, 5e7, 2e-8], dtype=float))
        previous_fit = evaluate_params(voltage, current, params_meta["x0"], config, params_meta)
        previous_fit.stats["mean"] = 5.0
        previous_fit.stats["max"] = 10.0
        candidate_fit = evaluate_params(voltage, current, params_meta["x0"], config, params_meta)
        candidate_fit.stats["mean"] = 8.0
        candidate_fit.stats["max"] = 14.0
        selected = ModelFitResult(
            spec=ModelSpec(
                name="ohmic_leakage_only",
                free_mask=np.array([True, True, True, False]),
                fixed_values={"k": 1e-10},
                description="ohmic model",
                stage="M1",
            ),
            params=params_meta["x0"],
            fit_results={},
            stats=candidate_fit.stats,
            diagnostics={"recommended_baseline_stage": "M1", "model_selection": {"recommended_stage": "M1"}},
            aic=-10.0,
            bic=-8.0,
            free_parameter_count=3,
            config=config,
            params_meta=params_meta,
        )

        self.assertFalse(_display_switch_allowed(previous_fit, candidate_fit))
        _annotate_blocked_display_switch(previous_fit, candidate_fit, selected)

        self.assertFalse(previous_fit.diagnostics["display_fit_switched"])
        self.assertTrue(previous_fit.diagnostics["m_model_display_switch_blocked"])
        self.assertEqual(previous_fit.diagnostics["recommended_baseline_stage"], "M1")


if __name__ == "__main__":
    unittest.main()
