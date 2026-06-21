from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from openpyxl import Workbook

from data_io.data_source import DataSelection, inspect_file, load_dataset, read_grid_window


class CsvImportTests(unittest.TestCase):
    def test_gb18030_csv_can_be_inspected_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "V1-DAY4-Data[2022-2-26_9-53-13].csv"
            path.write_bytes(
                "\n".join(
                    [
                        "序列,Voltage(V),Current(A)",
                        "No.1,-0.1,-1e-9",
                        "No.2,0.0,2e-9",
                    ]
                ).encode("gb18030")
            )

            info = inspect_file(path)
            grid = read_grid_window(path, row_count=20, col_count=3)
            dataset = load_dataset(DataSelection(path=path, voltage_range="B2:B3", current_range="C2:C3"))

        self.assertEqual(info.shape, (3, 3))
        self.assertEqual(info.preview[0][0], "序列")
        self.assertEqual(len(grid.rows), 3)
        np.testing.assert_allclose(dataset.data_v, [-0.1, 0.0])
        np.testing.assert_allclose(dataset.data_jd, [-1e-9, 2e-9])

    def test_grid_window_allows_deep_table_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "deep-header.csv"
            lines = [f"meta {index},," for index in range(350)]
            lines.extend(["序列,Voltage(V),Current(A)"])
            lines.extend(f"No.{index},{index / 10:.1f},{index}e-9" for index in range(1, 701))
            path.write_text("\n".join(lines), encoding="utf-8")

            grid = read_grid_window(path, row_count=1200, col_count=3)

        self.assertEqual(len(grid.rows), 1051)
        self.assertEqual(grid.rows[350][1], "Voltage(V)")
        self.assertEqual(grid.rows[-1][0], "No.700")

    def test_xlsx_grid_window_loads_wide_columns_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "workbook.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "test2"
            sheet.append([f"col-{index}" for index in range(1, 1047)])
            sheet.append(list(range(1, 1047)))
            workbook.save(path)

            grid = read_grid_window(path, sheet_name="test2")

        self.assertEqual(len(grid.rows), 2)
        self.assertEqual(len(grid.rows[0]), 1046)
        self.assertEqual(grid.rows[0][1045], "col-1046")
        self.assertEqual(grid.rows[1][1045], 1046)


if __name__ == "__main__":
    unittest.main()
