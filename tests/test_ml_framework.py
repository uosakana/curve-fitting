from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ml.model_inference import predict_with_local_models
from ml.fit_assist import build_prefit_ml_assist
from ml.model_bundle import list_model_bundles
from ml.record_schema import normalize_record_payload
from ml.similar_records import find_similar_records
from ml.training_tasks import list_task_payloads, tasks_for_phase


def _series(scale: float = 1.0) -> dict:
    return {
        "voltage": [-0.1, 0.0, 0.1],
        "measured": [scale * 1e-9, scale * 2e-9, scale * 3e-9],
        "fitted": [scale * 1.1e-9, scale * 2.1e-9, scale * 3.1e-9],
        "diode": [scale * 1e-10, scale * 2e-10, scale * 3e-10],
        "ohmic": [scale * 5e-10, scale * 6e-10, scale * 7e-10],
        "nonohmic": [scale * 4e-10, scale * 5e-10, scale * 6e-10],
    }


def _record_payload(record_id: str, *, quality: str, scale: float = 1.0) -> dict:
    series = _series(scale)
    return normalize_record_payload(
        {
            "analysis_settings": {"product_fit_mode": "diagnostic_fit", "fit_strategy": "quick_global", "scan_m": True},
            "sample_context": {"sample_id": record_id, "role": "target"},
            "labels": {"accepted": True, "quality": quality, "hypothesis": "leakage_reduced"},
            "result": {
                "product_fit_mode": "diagnostic_fit",
                "evaluator_kind": "base_j0_rs_rsh_k",
                "fit": {
                    "n": 1.4,
                    "m": 2.4,
                    "params": [1e-9, 800.0, 5e7, 2e-8],
                    "stats": {"mean": 5.0 * scale, "max": 12.0 * scale},
                    "diagnostics": {"strategy": "quick_global", "region_stats": {"worst_region": "near_zero"}},
                    "series": series,
                },
                "series": series,
            },
        },
        record_id=record_id,
        saved_at="2026-06-01T00:00:00",
    )


class MlFrameworkTest(unittest.TestCase):
    def test_tasks_are_split_by_phase(self) -> None:
        self.assertEqual(set(tasks_for_phase("prefit")), {"strategy", "scan_m"})
        self.assertEqual(set(tasks_for_phase("postfit")), {"quality", "hypothesis"})
        payloads = list_task_payloads("prefit")
        self.assertTrue(all(item["phase"] == "prefit" for item in payloads))

    def test_similar_records_returns_neighbors_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record_dir = Path(tmp)
            for index, quality in enumerate(["good", "poor"], start=1):
                record = _record_payload(f"rec-{index}", quality=quality, scale=float(index))
                (record_dir / f"fit_record_{index}.json").write_text(
                    json.dumps(record, ensure_ascii=False),
                    encoding="utf-8",
                )

            current = {"result": _record_payload("current", quality="good", scale=1.0)["result"]}
            response = find_similar_records(current, record_dir=record_dir, phase="postfit", limit=1)

            self.assertEqual(response["status"], "ready")
            self.assertEqual(response["record_count"], 2)
            self.assertEqual(len(response["neighbors"]), 1)
            self.assertIn("quality_counts", response["summary"])
            self.assertEqual(response["neighbors"][0]["record_id"], "rec-1")

    def test_model_prediction_without_artifacts_is_non_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            response = predict_with_local_models(
                {"result": _record_payload("current", quality="good")["result"]},
                model_dir=tmp,
                phase="postfit",
            )

            self.assertEqual(response["status"], "no_models")
            self.assertEqual(response["predictions"], {})

    def test_fit_assist_disabled_does_not_apply_overrides(self) -> None:
        response = build_prefit_ml_assist(
            [-0.1, 0.0, 0.1],
            [1e-9, 2e-9, 3e-9],
            {"product_fit_mode": "fast_fit", "fit_strategy": "quick_global"},
            enabled=False,
            mode="quality",
        )

        self.assertEqual(response["status"], "disabled")
        self.assertEqual(response["applied_overrides"], {})

    def test_empty_bundle_registry_is_non_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list_model_bundles(tmp), [])


if __name__ == "__main__":
    unittest.main()
