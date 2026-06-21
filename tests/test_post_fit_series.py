from __future__ import annotations

import unittest

import numpy as np

from config import load_config
from fit.post_fit import double_diode_model, double_diode_series, extended_model, extended_series


class PostFitSeriesTest(unittest.TestCase):
    def test_double_diode_series_exposes_real_components(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.5, 0.3, 81)
        params = np.array([1e-10, 2e-9, 800.0, 5e7, 2e-8], dtype=float)
        current = double_diode_model(voltage, params, config, 1.0, 2.0)

        series = double_diode_series(voltage, current, params, config, 1.0, 2.0)

        np.testing.assert_allclose(series["fitted"], current, rtol=1e-10, atol=1e-30)
        self.assertFalse(np.allclose(series["diode"], series["fitted"], rtol=1e-8, atol=1e-30))
        self.assertGreater(float(np.max(np.abs(series["ohmic"]))), 0.0)
        self.assertGreater(float(np.max(np.abs(series["nonohmic"]))), 0.0)
        self.assertIn("diode_1", series)
        self.assertIn("diode_2", series)
        self.assertIn("v_drop", series)

    def test_extended_series_exposes_extra_current_component(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.5, 0.3, 81)
        params = np.array([1e-9, 800.0, 5e7, 2e-8, 5e-8, 1.0], dtype=float)
        current = extended_model("reverse_trap_saturation", voltage, params, config)

        series = extended_series("reverse_trap_saturation", voltage, current, params, config)

        np.testing.assert_allclose(series["fitted"], current, rtol=1e-10, atol=1e-30)
        self.assertFalse(np.allclose(series["diode"], series["fitted"], rtol=1e-8, atol=1e-30))
        self.assertGreater(float(np.max(np.abs(series["ohmic"]))), 0.0)
        self.assertGreater(float(np.max(np.abs(series["extra_current"]))), 0.0)
        self.assertIn("empirical_nonohmic", series)
        self.assertIn("extended_nonohmic_total", series)
        np.testing.assert_allclose(series["nonohmic"], series["empirical_nonohmic"], rtol=1e-12, atol=1e-30)
        np.testing.assert_allclose(
            series["extended_nonohmic_total"],
            series["empirical_nonohmic"] + series["extra_current"],
            rtol=1e-12,
            atol=1e-30,
        )
        self.assertIn("v_drop", series)

    def test_extended_series_keeps_each_extra_branch_out_of_nonohmic(self) -> None:
        config = load_config()
        voltage = np.linspace(-0.8, 0.4, 121)
        cases = {
            "reverse_field_assisted": np.array([1e-9, 800.0, 5e7, 2e-8, 1e-10, 1.2], dtype=float),
            "reverse_trap_saturation": np.array([1e-9, 800.0, 5e7, 2e-8, 5e-8, 1.0], dtype=float),
            "high_forward_power": np.array([1e-9, 800.0, 5e7, 2e-8, 8e-5, 0.14], dtype=float),
        }

        for kind, params in cases.items():
            with self.subTest(kind=kind):
                current = extended_model(kind, voltage, params, config)
                series = extended_series(kind, voltage, current, params, config)

                np.testing.assert_allclose(series["nonohmic"], series["empirical_nonohmic"], rtol=1e-12, atol=1e-30)
                np.testing.assert_allclose(
                    series["extended_nonohmic_total"],
                    series["nonohmic"] + series["extra_current"],
                    rtol=1e-12,
                    atol=1e-30,
                )
                self.assertGreater(float(np.max(np.abs(series["extra_current"]))), 0.0)


if __name__ == "__main__":
    unittest.main()
