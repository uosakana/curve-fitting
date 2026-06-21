from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from app_services.fit_service import evaluate_file, normalize_product_fit_mode
from config import load_config
from fit.model import diode_model


class AppServicesContractTest(unittest.TestCase):
    def test_product_fit_mode_aliases_remain_available_from_service_and_http_layer(self) -> None:
        from app.fastapi_server import normalize_product_fit_mode as http_normalize

        self.assertEqual(normalize_product_fit_mode("fast"), "fast_fit")
        self.assertEqual(normalize_product_fit_mode("diagnostic"), "diagnostic_fit")
        self.assertEqual(http_normalize("auto"), "diagnostic_fit")

    def test_evaluate_file_accepts_payload_without_fastapi_request_objects(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.2, 0.2, 9)
        params = np.array([1e-9, 800.0, 5e7, 2e-8], dtype=float)
        current = diode_model(voltage, params, config)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "series.csv"
            lines = ["voltage,current"]
            lines.extend(f"{v},{j}" for v, j in zip(voltage, current))
            path.write_text("\n".join(lines), encoding="utf-8")

            result = evaluate_file(
                path,
                {
                    "cell_range": "A2:B10",
                    "param_j0": "1e-9",
                    "param_rs": "800",
                    "param_rsh": "5e7",
                    "param_k": "2e-8",
                },
            )

        self.assertIn("fit", result)
        self.assertIn("series", result)
        self.assertEqual(result["dataset"]["points"], 9)
        self.assertTrue(result["manual_capability"]["can_evaluate"])


if __name__ == "__main__":
    unittest.main()

