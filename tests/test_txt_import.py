import unittest

from data_io.txt_import import block_series_rows, block_to_csv, parse_txt_rows


def _block():
    return {
        "status": "ok",
        "series": {
            "voltage": [-1.0, -0.5, 0.0, 0.5, 1.0],
            "y": [1e-9, 2e-9, 3e-9, 4e-9, 5e-9],
        },
    }


class TxtImportExportTests(unittest.TestCase):
    def test_block_series_rows_filters_voltage_range(self):
        rows = block_series_rows(_block(), voltage_min=-0.5, voltage_max=0.5)

        self.assertEqual(rows, [(-0.5, 2e-9), (0.0, 3e-9), (0.5, 4e-9)])

    def test_block_to_csv_accepts_reversed_bounds(self):
        csv_text = block_to_csv(_block(), voltage_min=0.5, voltage_max=-0.5)

        self.assertEqual(csv_text.splitlines(), ["-0.5,2e-09", "0,3e-09", "0.5,4e-09"])

    def test_block_series_rows_allows_single_sided_bounds(self):
        rows = block_series_rows(_block(), voltage_max=0.0)

        self.assertEqual(rows, [(-1.0, 1e-9), (-0.5, 2e-9), (0.0, 3e-9)])

    def test_block_series_rows_rejects_empty_selection(self):
        with self.assertRaises(ValueError):
            block_series_rows(_block(), voltage_min=2.0, voltage_max=3.0)

    def test_abs_i_column_is_marked_when_no_signed_current_exists(self):
        parsed = parse_txt_rows(
            [
                ["Voltage(V)", "abs(I)"],
                ["-0.1", "1e-9"],
                ["0.0", "2e-9"],
                ["0.1", "3e-9"],
            ],
            ["Voltage(V)\tabs(I)", "-0.1\t1e-9", "0.0\t2e-9", "0.1\t3e-9"],
        )

        block = parsed["blocks"][0]
        self.assertEqual(block["columns"]["y_kind"], "ABS_I")
        self.assertIn("abs(I)", block["columns"]["y"])

    def test_headerless_numeric_txt_is_not_treated_as_jv_export(self):
        parsed = parse_txt_rows(
            [
                ["-0.5", "1e-9", "2e-9"],
                ["-0.4", "1.5e-9", "2.5e-9"],
                ["-0.3", "2e-9", "3e-9"],
            ],
            ["-0.5\t1e-9\t2e-9", "-0.4\t1.5e-9\t2.5e-9", "-0.3\t2e-9\t3e-9"],
        )

        self.assertEqual(parsed["format"], "unknown")
        self.assertEqual(parsed["ok_blocks"], 0)
        self.assertEqual(parsed["blocks"], [])


if __name__ == "__main__":
    unittest.main()
