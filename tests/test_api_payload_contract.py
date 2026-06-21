from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np

from app.api_utils import analysis_payload, fit_payload, parse_m_values
from config import load_config
from fit.core import clone_config, evaluate_params
from fit.model import diode_model
from fit.parameter_schema import (
    BASE_EVALUATOR_KIND,
    POST_FIT_EVALUATOR_KIND,
    fit_contract_payload,
    params_meta_from_values,
)
from fit.workflow import AnalysisResult


def _dataset(voltage: np.ndarray, current: np.ndarray) -> SimpleNamespace:
    return SimpleNamespace(
        data_v=voltage,
        data_jd=current,
        source={"path": "synthetic.csv", "mode": "test", "points": int(voltage.size)},
    )


class ApiPayloadContractTest(unittest.TestCase):
    def test_fit_contract_exposes_default_grids(self) -> None:
        contract = fit_contract_payload()

        self.assertEqual(contract["evaluator_kind"], BASE_EVALUATOR_KIND)
        self.assertEqual(contract["parameter_schema"]["parameters"][0]["name"], "J0")
        self.assertGreaterEqual(len(contract["defaults"]["n_values"]), 1)
        self.assertGreaterEqual(len(contract["defaults"]["m_values"]), 1)

    def test_app_contract_endpoint_wraps_contract_payload(self) -> None:
        from app.fastapi_server import app_contract_endpoint

        payload = app_contract_endpoint()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["contract"]["product_name"], "Dark Current Studio")
        self.assertIn("services", payload["contract"])

    def test_product_fit_mode_aliases(self) -> None:
        from app.fastapi_server import normalize_product_fit_mode

        self.assertEqual(normalize_product_fit_mode("fast"), "fast_fit")
        self.assertEqual(normalize_product_fit_mode("diagnostic"), "diagnostic_fit")
        self.assertEqual(normalize_product_fit_mode("auto"), "diagnostic_fit")

    def test_parse_m_values_rejects_non_positive_values(self) -> None:
        with self.assertRaises(ValueError):
            parse_m_values("1.8, 0, 2.4")

    def test_base_fit_payload_exposes_manual_contract(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.3, 0.3, 21)
        params = np.array([1e-9, 800.0, 5e7, 2e-8], dtype=float)
        current = diode_model(voltage, params, config)
        fit = evaluate_params(voltage, current, params, config, params_meta_from_values(params))

        payload = fit_payload(_dataset(voltage, current), fit)

        for key in (
            "dataset",
            "fit",
            "series",
            "diagnostics",
            "model_context",
            "parameter_schema",
            "manual_capability",
            "evaluator_kind",
            "candidates",
        ):
            self.assertIn(key, payload)
        self.assertTrue(payload["manual_capability"]["can_evaluate"])
        self.assertEqual(payload["evaluator_kind"], BASE_EVALUATOR_KIND)
        self.assertEqual(payload["fit"]["series"], payload["series"])
        self.assertEqual(payload["parameter_schema"]["parameters"][0]["name"], "J0")
        self.assertEqual(payload["candidates"][0]["rank"], 1)
        self.assertTrue(payload["candidates"][0]["is_primary"])

    def test_analysis_payload_exposes_ranked_candidates(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.3, 0.3, 21)
        params = np.array([1e-9, 800.0, 5e7, 2e-8], dtype=float)
        current = diode_model(voltage, params, config)
        fit = evaluate_params(voltage, current, params, config, params_meta_from_values(params))
        profiled_config = clone_config(config, n=1.3, m=1.8)
        profiled = evaluate_params(voltage, current, params, profiled_config, params_meta_from_values(params))
        analysis = AnalysisResult(fit=fit, m_scan=[profiled])

        payload = analysis_payload(_dataset(voltage, current), analysis)

        self.assertIn("candidates", payload)
        self.assertGreaterEqual(len(payload["candidates"]), 1)
        self.assertEqual(payload["candidates"][0]["rank"], 1)
        self.assertIn(payload["candidates"][0]["source"], {"primary_fit", "nm_profile"})
        self.assertIn("run_snapshot", payload)
        self.assertTrue(str(payload["run_snapshot"]["snapshot_id"]).startswith("run_"))
        self.assertEqual(payload["run_snapshot"]["data"]["points"], int(voltage.size))
        self.assertEqual(payload["run_snapshot"]["analysis"]["candidate_counts"]["ranked"], len(payload["candidates"]))
        self.assertEqual(payload["run_snapshot"]["engine"]["random_seed"], config.optimization.random_seed)

    def test_analysis_payload_exposes_post_fit_candidate_schema(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.3, 0.3, 21)
        params = np.array([1e-9, 800.0, 5e7, 2e-8], dtype=float)
        current = diode_model(voltage, params, config)
        fit = evaluate_params(voltage, current, params, config, params_meta_from_values(params))
        analysis = AnalysisResult(
            fit=fit,
            post_fit_models=[
                {
                    "name": "clean_double_diode",
                    "status": "ok",
                    "params": np.array([1e-9, 2e-9, 800.0, 5e7], dtype=float),
                    "param_names": ["Jr", "Jd", "Rs", "Rsh"],
                    "stats": {"mean": 0.0, "max": 0.0, "included_points": int(voltage.size)},
                    "diagnostics": {
                        "model_stage": "M4",
                        "selected_for_replacement": False,
                        "fixed_ideality": {"recombination": 2.0, "diffusion": 1.0},
                    },
                    "series": {
                        "voltage": voltage,
                        "measured": current,
                        "fitted": current,
                        "diode": current,
                        "ohmic": np.zeros_like(current),
                        "nonohmic": np.zeros_like(current),
                        "relative_error": np.zeros_like(current),
                        "recombination": current,
                        "diffusion": np.zeros_like(current),
                    },
                }
            ],
        )

        payload = analysis_payload(_dataset(voltage, current), analysis)

        candidate = next(item for item in payload["candidates"] if item["label"] == "clean_double_diode")
        self.assertEqual(candidate["model_context"]["model_stage"], "M4")
        self.assertEqual(candidate["parameter_schema"]["kind"], POST_FIT_EVALUATOR_KIND)
        self.assertEqual(
            [item["name"] for item in candidate["parameter_schema"]["parameters"]],
            ["Jr", "Jd", "Rs", "Rsh"],
        )
        self.assertIn("voltage", candidate["series"])
        self.assertIn("measured", candidate["series"])
        self.assertIn("fitted", candidate["series"])
        self.assertIn("diode", candidate["series"])
        self.assertIn("ohmic", candidate["series"])
        self.assertIn("nonohmic", candidate["series"])
        self.assertIn("recombination", candidate["series"])
        self.assertIn("diffusion", candidate["series"])

    def test_post_fit_payload_disables_manual_evaluate(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.3, 0.3, 21)
        params = np.array([1e-9, 800.0, 5e7, 2e-8], dtype=float)
        current = diode_model(voltage, params, config)
        fit = evaluate_params(voltage, current, params, config, params_meta_from_values(params))
        fit.diagnostics["display_fit_source"] = POST_FIT_EVALUATOR_KIND
        fit.diagnostics["param_names"] = ["J01", "J02", "Rs", "Rsh", "k"]
        fit.fit_results["diagnostics"] = fit.diagnostics

        payload = fit_payload(_dataset(voltage, current), fit)

        self.assertFalse(payload["manual_capability"]["can_evaluate"])
        self.assertEqual(payload["evaluator_kind"], POST_FIT_EVALUATOR_KIND)
        self.assertNotIn("lower", payload["parameter_schema"]["parameters"][0])

    def test_four_parameter_post_fit_payload_does_not_reuse_base_bounds(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.3, 0.3, 21)
        params = np.array([1e-9, 800.0, 5e7, 2e-8], dtype=float)
        current = diode_model(voltage, params, config)
        fit = evaluate_params(voltage, current, params, config, params_meta_from_values(params))
        fit.diagnostics["display_fit_source"] = POST_FIT_EVALUATOR_KIND
        fit.diagnostics["param_names"] = ["Jr", "Jd", "Rs", "Rsh"]
        fit.fit_results["diagnostics"] = fit.diagnostics

        payload = fit_payload(_dataset(voltage, current), fit)

        schema_params = payload["parameter_schema"]["parameters"]
        self.assertEqual([item["name"] for item in schema_params], ["Jr", "Jd", "Rs", "Rsh"])
        self.assertNotIn("lower", schema_params[0])
        self.assertNotIn("scale", schema_params[0])


if __name__ == "__main__":
    unittest.main()
