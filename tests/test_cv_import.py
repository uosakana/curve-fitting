from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from data_io.cv_import import summarize_cv_file


def write_synthetic_cv(path: Path, point_count: int = 804) -> None:
    rows = []
    for index in range(point_count):
        voltage = -0.5 + index * (1.0 / (point_count - 1))
        raw_capacitance = 1.0e-4 + 2.0e-5 * (1.0 - abs(voltage))
        smooth_capacitance = raw_capacitance * 0.96
        rows.append(f"{voltage:.6g}\t{raw_capacitance:.8e}\t{smooth_capacitance:.8e}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


class CVImportTest(unittest.TestCase):
    def test_cv_file_is_diagnostic_shape_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cv.txt"
            write_synthetic_cv(path)

            summary = summarize_cv_file(path, thickness_nm=300.0, area_cm2=0.045)

        metadata = summary.as_metadata()

        self.assertEqual(summary.point_count, 804)
        self.assertEqual(metadata["frequency_Hz"], 1000.0)
        self.assertEqual(metadata["capacitance_unit"], "F")
        self.assertEqual(metadata["smooth_method"], "30-point Savitzky-Golay")
        self.assertEqual(metadata["capacitance_quality"], "diagnostic_shape_only")
        self.assertEqual(metadata["epsilon_from_cv"], "rejected_for_now")
        self.assertEqual(metadata["field_width_from_cv"], "rejected_for_now")
        self.assertGreater(summary.estimated_epsilon_r_reverse_mid or 0.0, 100.0)


if __name__ == "__main__":
    unittest.main()
