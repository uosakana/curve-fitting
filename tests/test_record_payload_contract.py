from __future__ import annotations

import unittest

from ml.record_features import flatten_record
from ml.record_schema import SCHEMA_VERSION, normalize_record_payload


class RecordPayloadContractTest(unittest.TestCase):
    def test_normalize_record_reads_top_level_result_series(self) -> None:
        series = {
            "voltage": [-0.1, 0.0, 0.1],
            "measured": [1e-9, 2e-9, 3e-9],
            "fitted": [1.1e-9, 2.1e-9, 3.1e-9],
            "diode": [1e-10, 2e-10, 3e-10],
            "ohmic": [5e-10, 6e-10, 7e-10],
            "nonohmic": [4e-10, 5e-10, 6e-10],
            "relative_error": [10.0, 5.0, 3.0],
        }
        payload = {
            "result": {
                "schema_version": 1,
                "series": series,
                "evaluator_kind": "base_j0_rs_rsh_k",
                "model_context": {"display_fit_source": "strategy_fit"},
                "fit": {
                    "n": 1.4,
                    "m": 2.4,
                    "params": [1e-9, 800.0, 5e7, 2e-8],
                    "stats": {"mean": 6.0, "max": 12.0},
                    "diagnostics": {},
                },
            },
            "labels": {"accepted": True, "quality": "good"},
        }

        record = normalize_record_payload(payload, record_id="rec-1", saved_at="2026-06-01T00:00:00")
        row = flatten_record(record)

        self.assertEqual(record["component_series"]["point_count"], 3)
        self.assertEqual(record["result"]["fit"]["series"]["voltage"], series["voltage"])
        self.assertEqual(record["result"]["series"]["voltage"], series["voltage"])
        self.assertEqual(row["curve_points"], 3)
        self.assertEqual(row["evaluator_kind"], "base_j0_rs_rsh_k")
        self.assertEqual(row["display_fit_source"], "strategy_fit")
        self.assertEqual(row["n"], 1.4)

    def test_flatten_legacy_v2_record_infers_selected_summary(self) -> None:
        series = {
            "voltage": [-0.1, 0.0, 0.1],
            "measured": [1e-9, 2e-9, 3e-9],
            "fitted": [1.1e-9, 2.1e-9, 3.1e-9],
            "diode": [1e-10, 2e-10, 3e-10],
            "ohmic": [5e-10, 6e-10, 7e-10],
            "nonohmic": [4e-10, 5e-10, 6e-10],
        }
        legacy = {
            "schema_version": 2,
            "record_type": "fit_label",
            "record_id": "legacy-1",
            "labels": {"accepted": True, "quality": "acceptable"},
            "analysis_settings": {"fit_strategy": "auto", "scan_m": True},
            "result": {
                "evaluator_kind": "base_j0_rs_rsh_k",
                "fit": {
                    "n": 1.4,
                    "m": 2.4,
                    "params": [1e-9, 800.0, 5e7, 2e-8],
                    "stats": {"mean": 6.0, "max": 12.0},
                    "diagnostics": {"display_fit_source": "strategy_fit"},
                    "series": series,
                },
            },
        }

        row = flatten_record(legacy)

        self.assertEqual(row["product_fit_mode"], "legacy")
        self.assertEqual(row["selected_result_source"], "strategy_fit")
        self.assertEqual(row["selected_series_point_count"], 3.0)
        self.assertEqual(row["candidate_count"], 0.0)

    def test_v3_record_keeps_product_mode_and_candidate_context(self) -> None:
        series = {
            "voltage": [-0.1, 0.0, 0.1],
            "measured": [1e-9, 2e-9, 3e-9],
            "fitted": [1.0e-9, 2.0e-9, 3.0e-9],
            "diode": [1e-10, 2e-10, 3e-10],
            "ohmic": [5e-10, 6e-10, 7e-10],
            "nonohmic": [4e-10, 5e-10, 6e-10],
        }
        fit = {
            "n": 1.3,
            "m": 1.8,
            "params": [1e-9, 800.0, 5e7, 2e-8],
            "stats": {"mean": 2.0, "max": 5.0},
            "diagnostics": {"display_fit_source": "nm_profile"},
            "series": series,
        }
        payload = {
            "analysis_settings": {
                "product_fit_mode": "diagnostic_fit",
                "fit_strategy": "quick_global",
                "sweep_strategies": True,
                "scan_m": True,
                "scan_n": True,
                "compare_models": True,
                "post_fit_models": True,
                "m_values": "1.8,2.4",
                "n_values": "1.1,1.3",
            },
            "result": {
                "schema_version": 1,
                "run_snapshot": {
                    "snapshot_id": "run_test123",
                    "data": {
                        "file_name": "demo.csv",
                        "source_mode": "generated_voltage_current_range",
                        "points": 3,
                        "voltage": {"min": -0.5, "max": 0.3, "span": 0.8},
                    },
                    "analysis": {
                        "settings": {"product_fit_mode": "diagnostic_fit"},
                        "candidate_counts": {"ranked": 2, "post_fit": 1},
                        "current_model": {"source": "nm_profile", "label": "Profile fit"},
                    },
                    "engine": {"random_seed": 12345},
                },
                "product_fit_mode": "diagnostic_fit",
                "evaluator_kind": "base_j0_rs_rsh_k",
                "candidate_selection": {"index": 0, "rank": 1, "source": "nm_profile", "label": "Profile fit"},
                "model_context": {"display_fit_source": "nm_profile"},
                "fit": fit,
                "series": series,
                "candidates": [
                    {
                        "rank": 1,
                        "source": "nm_profile",
                        "label": "Profile fit",
                        "is_primary": False,
                        "diagnostic_only": False,
                        "promotable": True,
                        "stats": {"mean": 2.0, "max": 5.0},
                        "fit": fit,
                    },
                    {
                        "rank": 2,
                        "source": "primary_fit",
                        "label": "Primary fit",
                        "is_primary": True,
                        "stats": {"mean": 6.0, "max": 12.0},
                        "fit": {**fit, "stats": {"mean": 6.0, "max": 12.0}},
                    },
                ],
            },
            "labels": {"accepted": True, "quality": "good", "manual_adjusted": False},
            "ml_assist": {
                "enabled": True,
                "mode": "advisory",
                "status": "ready",
                "phase": "prefit",
                "policy_version": 1,
                "suggested_overrides": {"product_fit_mode": "diagnostic_fit"},
                "applied_overrides": {},
                "models": {"status": "no_models", "predictions": {}},
                "similar": {"status": "ready", "record_count": 2},
                "messages": ["advisory only"],
            },
        }

        record = normalize_record_payload(payload, record_id="rec-2", saved_at="2026-06-01T00:00:00")
        row = flatten_record(record)

        self.assertEqual(record["schema_version"], SCHEMA_VERSION)
        self.assertEqual(record["analysis_settings"]["product_fit_mode"], "diagnostic_fit")
        self.assertTrue(record["analysis_settings"]["scan_n"])
        self.assertTrue(record["analysis_settings"]["post_fit_models"])
        self.assertEqual(record["selected_result"]["candidate_index"], 0)
        self.assertEqual(record["selected_result"]["source"], "nm_profile")
        self.assertEqual(record["candidate_context"]["candidate_count"], 2)
        self.assertEqual(record["candidate_context"]["primary_rank"], 2)
        self.assertEqual(record["candidate_context"]["top_candidate"]["source"], "nm_profile")
        self.assertEqual(record["run_snapshot"]["snapshot_id"], "run_test123")
        self.assertTrue(record["ml_assist"]["enabled"])
        self.assertEqual(record["ml_assist"]["suggested_product_fit_mode"], "diagnostic_fit")
        self.assertEqual(row["product_fit_mode"], "diagnostic_fit")
        self.assertTrue(row["ml_assist_enabled"])
        self.assertEqual(row["ml_assist_suggested_product_fit_mode"], "diagnostic_fit")
        self.assertEqual(row["selected_candidate_index"], 0.0)
        self.assertEqual(row["selected_result_source"], "nm_profile")
        self.assertEqual(row["candidate_count"], 2.0)
        self.assertEqual(row["top_candidate_source"], "nm_profile")
        self.assertEqual(row["run_snapshot_id"], "run_test123")
        self.assertEqual(row["run_points"], 3.0)
        self.assertEqual(row["run_voltage_min"], -0.5)
        self.assertEqual(row["run_voltage_max"], 0.3)
        self.assertEqual(row["run_ranked_candidate_count"], 2.0)
        self.assertEqual(row["run_post_fit_candidate_count"], 1.0)


    def test_training_context_is_normalized_and_flattened(self) -> None:
        series = {
            "voltage": [-0.1, 0.0, 0.1],
            "measured": [1e-9, 2e-9, 3e-9],
            "fitted": [1.0e-9, 2.0e-9, 3.0e-9],
            "diode": [1e-10, 2e-10, 3e-10],
            "ohmic": [5e-10, 6e-10, 7e-10],
            "nonohmic": [4e-10, 5e-10, 6e-10],
        }
        payload = {
            "sample_context": {
                "sample_id": "device-1",
                "batch": "fallback-batch",
                "process": "anneal",
                "training_context": {
                    "device_area_mm2": "0.04",
                    "batch_tag": "pbs-cqd-a",
                    "failure_tags": ["shunt", "noise", "unknown"],
                    "model_feedback": "model_wrong",
                    "process_note": "ligand A, stored 3 days",
                },
            },
            "result": {
                "evaluator_kind": "base_j0_rs_rsh_k",
                "fit": {
                    "n": 1.4,
                    "m": 2.0,
                    "params": [1e-9, 800.0, 5e7, 2e-8],
                    "stats": {"mean": 4.0, "max": 8.0},
                    "diagnostics": {},
                    "series": series,
                },
                "series": series,
            },
            "labels": {"accepted": True, "quality": "acceptable"},
        }

        record = normalize_record_payload(payload, record_id="rec-training", saved_at="2026-06-01T00:00:00")
        row = flatten_record(record)

        training_context = record["sample_context"]["training_context"]
        self.assertEqual(training_context["device_area_mm2"], 0.04)
        self.assertEqual(training_context["batch_tag"], "pbs-cqd-a")
        self.assertEqual(training_context["failure_tags"], ["shunt", "noise"])
        self.assertEqual(training_context["model_feedback"], "model_wrong")
        self.assertEqual(row["device_area_mm2"], 0.04)
        self.assertEqual(row["training_batch_tag"], "pbs-cqd-a")
        self.assertEqual(row["training_failure_tags"], "shunt|noise")
        self.assertEqual(row["training_model_feedback"], "model_wrong")
        self.assertEqual(row["training_process_note"], "ligand A, stored 3 days")


if __name__ == "__main__":
    unittest.main()
