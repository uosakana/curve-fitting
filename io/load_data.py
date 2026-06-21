from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from data_io import DataSelection, load_dataset, validate_input_data as _validate_input_data


SAMPLE_JD = np.array(
    [
        -1.96e-07,
        -1.88e-07,
        -1.79e-07,
        -1.71e-07,
        -1.63e-07,
        -1.57e-07,
        -1.50e-07,
        -1.45e-07,
        -1.39e-07,
        -1.32e-07,
        -1.26e-07,
        -1.21e-07,
        -1.16e-07,
        -1.12e-07,
        -1.07e-07,
        -1.02e-07,
        -9.86e-08,
        -9.52e-08,
        -9.14e-08,
        -8.81e-08,
        -8.54e-08,
        -8.27e-08,
        -8.00e-08,
        -7.78e-08,
        -7.51e-08,
        -7.30e-08,
        -7.12e-08,
        -7.18e-08,
        -7.26e-08,
        -6.93e-08,
        -6.97e-08,
        -6.65e-08,
        -6.70e-08,
        -6.38e-08,
        -6.43e-08,
        -6.12e-08,
        -6.22e-08,
        -6.12e-08,
        -6.01e-08,
        -5.88e-08,
        -5.73e-08,
        -5.58e-08,
        -5.38e-08,
        -5.15e-08,
        -4.86e-08,
        -4.49e-08,
        -4.01e-08,
        -3.39e-08,
        -2.57e-08,
        -1.47e-08,
        4.57e-12,
        1.95e-08,
        4.60e-08,
        8.53e-08,
        1.32e-07,
        1.95e-07,
        2.77e-07,
        3.87e-07,
        5.32e-07,
        7.25e-07,
        9.81e-07,
        1.31e-06,
        1.76e-06,
        2.34e-06,
        3.11e-06,
        4.10e-06,
        5.37e-06,
        7.00e-06,
        9.05e-06,
        1.15e-05,
        1.46e-05,
        1.84e-05,
        2.28e-05,
        2.80e-05,
        3.40e-05,
        4.09e-05,
        4.87e-05,
        5.74e-05,
        6.68e-05,
        7.70e-05,
        8.77e-05,
    ],
    dtype=float,
)


def sample_data() -> tuple[np.ndarray, np.ndarray]:
    return np.arange(-0.5, 0.3001, 0.01, dtype=float), SAMPLE_JD.copy()


def _excel_col_to_index(col: str) -> int:
    idx = 0
    for char in col.upper():
        idx = idx * 26 + (ord(char) - ord("A") + 1)
    return idx - 1


def _parse_range(cell_range: str | None) -> tuple[int | None, int | None, int | None, int | None]:
    if not cell_range:
        return None, None, None, None
    match = re.fullmatch(r"\s*([A-Za-z]+)(\d+)\s*:\s*([A-Za-z]+)(\d+)\s*", cell_range)
    if not match:
        raise ValueError(f"Unsupported range format: {cell_range!r}. Expected for example A1:A81.")
    col1, row1, col2, row2 = match.groups()
    start_col = _excel_col_to_index(col1)
    end_col = _excel_col_to_index(col2)
    start_row = int(row1) - 1
    end_row = int(row2) - 1
    if end_row < start_row or end_col < start_col:
        raise ValueError(f"Invalid cell range: {cell_range!r}")
    return start_row, end_row - start_row + 1, start_col, end_col


def _read_table(path: Path, cell_range: str | None) -> np.ndarray:
    start_row, nrows, start_col, end_col = _parse_range(cell_range)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        usecols = None
        if start_col is not None and end_col is not None:
            usecols = list(range(start_col, end_col + 1))
        frame = pd.read_excel(path, header=None, usecols=usecols, skiprows=start_row or 0, nrows=nrows)
    elif suffix == ".csv":
        usecols = None
        if start_col is not None and end_col is not None:
            usecols = list(range(start_col, end_col + 1))
        frame = pd.read_csv(path, header=None, usecols=usecols, skiprows=start_row or 0, nrows=nrows)
    else:
        raise ValueError(f"Unsupported data file type: {path.suffix}")
    return frame.to_numpy(dtype=float)


def load_data(path: str | Path | None = None, cell_range: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    if path is None:
        raise ValueError("No data file provided. Pass a data path or call sample_data() explicitly for demos/tests.")

    dataset = load_dataset(DataSelection(path=path, cell_range=cell_range))
    return dataset.data_v, dataset.data_jd


def validate_input_data(v: np.ndarray, jd: np.ndarray) -> None:
    _validate_input_data(v, jd)
