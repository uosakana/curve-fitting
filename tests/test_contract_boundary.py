from __future__ import annotations

import unittest
from pathlib import Path

from contracts import APP_CONTRACT_VERSION, app_contract_payload


class ContractBoundaryTest(unittest.TestCase):
    def test_app_contract_exposes_stable_fit_result_boundary(self) -> None:
        contract = app_contract_payload()

        self.assertEqual(contract["schema_version"], APP_CONTRACT_VERSION)
        self.assertEqual(contract["product_name"], "Dark Current Studio")
        self.assertEqual(
            set(contract["fit_result"]["required_top_level"]),
            {
                "dataset",
                "fit",
                "series",
                "diagnostics",
                "model_context",
                "parameter_schema",
                "manual_capability",
                "evaluator_kind",
                "candidates",
            },
        )
        self.assertEqual(contract["manual_evaluate"]["authority_field"], "manual_capability.can_evaluate")
        self.assertIn("fit_contract", contract)
        self.assertIn("strategy_fit", contract["fit_result"]["candidate_sources"])

    def test_service_contract_names_http_and_desktop_methods(self) -> None:
        services = {item["id"]: item for item in app_contract_payload()["services"]}

        self.assertIn("analyze_fit", services)
        self.assertEqual(services["analyze_fit"]["http"]["path"], "/api/analyze")
        self.assertEqual(services["analyze_fit"]["desktop"], "analyzeFit")
        self.assertIn("evaluate_manual_params", services)
        self.assertIn("assistant_chat", services)

    def test_app_services_do_not_import_fastapi(self) -> None:
        root = Path(__file__).resolve().parents[1] / "app_services"
        for path in root.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("fastapi", text.lower(), path.name)


if __name__ == "__main__":
    unittest.main()
