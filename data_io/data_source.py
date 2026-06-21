from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_VOLTAGE_START = -0.5
DEFAULT_VOLTAGE_END = 0.3
DEFAULT_VOLTAGE_STEP = 0.01
CSV_ENCODING_CANDIDATES = ("utf-8-sig", "gb18030", "latin-1")
DEFAULT_GRID_ROW_COUNT = 2000
DEFAULT_GRID_COL_COUNT = 2000
MAX_GRID_ROW_COUNT = 5000
MAX_GRID_COL_COUNT = 5000


@dataclass
class DataSelection:
    path: str | Path
    sheet_name: str | int | None = None
    cell_range: str | None = None
    voltage_range: str | None = None
    current_range: str | None = None
    voltage_start: float = DEFAULT_VOLTAGE_START
    voltage_end: float = DEFAULT_VOLTAGE_END
    voltage_step: float = DEFAULT_VOLTAGE_STEP


@dataclass
class DataFileInfo:
    path: Path
    suffix: str
    sheets: list[str]
    selected_sheet: str | int | None
    shape: tuple[int, int]
    preview: list[list[Any]]


@dataclass
class DataGridWindow:
    path: Path
    suffix: str
    sheet_name: str | int | None
    shape: tuple[int, int]
    row_offset: int
    col_offset: int
    rows: list[list[Any]]


@dataclass
class LoadedDataset:
    data_v: np.ndarray
    data_jd: np.ndarray
    selection: DataSelection
    source: dict[str, Any]


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


def _normalize_path(path: str | Path) -> Path:
    data_path = Path(path)
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")
    return data_path


def _normalize_sheet_name(sheet_name: str | int | None) -> str | int | None:
    if isinstance(sheet_name, str) and sheet_name.strip().isdigit():
        return int(sheet_name.strip())
    return sheet_name


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    last_error: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODING_CANDIDATES:
        try:
            return pd.read_csv(path, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return pd.read_csv(path, **kwargs)


def _read_table(path: Path, cell_range: str | None, sheet_name: str | int | None = None) -> np.ndarray:
    start_row, nrows, start_col, end_col = _parse_range(cell_range)
    suffix = path.suffix.lower()
    usecols = None
    if start_col is not None and end_col is not None:
        usecols = list(range(start_col, end_col + 1))

    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(
            path,
            header=None,
            sheet_name=0 if sheet_name is None else _normalize_sheet_name(sheet_name),
            usecols=usecols,
            skiprows=start_row or 0,
            nrows=nrows,
        )
    elif suffix == ".csv":
        if sheet_name is not None:
            raise ValueError("CSV files do not support sheet selection.")
        frame = _read_csv(path, header=None, usecols=usecols, skiprows=start_row or 0, nrows=nrows)
    else:
        raise ValueError(f"Unsupported data file type: {path.suffix}")
    return frame.to_numpy(dtype=float)


def _json_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if pd.isna(value):
        return None
    return value


def _preview_rows(frame: pd.DataFrame) -> list[list[Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return [[_json_cell(value) for value in row] for row in clean.itertuples(index=False, name=None)]


def inspect_file(
    path: str | Path,
    *,
    sheet_name: str | int | None = None,
    preview_rows: int = 10,
    preview_cols: int = 8,
) -> DataFileInfo:
    data_path = _normalize_path(path)
    suffix = data_path.suffix.lower()

    if suffix in {".xlsx", ".xls"}:
        with pd.ExcelFile(data_path) as book:
            selected = book.sheet_names[0] if sheet_name is None else _normalize_sheet_name(sheet_name)
            sheets = list(book.sheet_names)
        full = pd.read_excel(data_path, header=None, sheet_name=selected)
        preview = full.iloc[:preview_rows, :preview_cols]
        return DataFileInfo(
            path=data_path,
            suffix=suffix,
            sheets=sheets,
            selected_sheet=selected,
            shape=tuple(full.shape),
            preview=_preview_rows(preview),
        )

    if suffix == ".csv":
        full = _read_csv(data_path, header=None)
        preview = full.iloc[:preview_rows, :preview_cols]
        return DataFileInfo(
            path=data_path,
            suffix=suffix,
            sheets=[],
            selected_sheet=None,
            shape=tuple(full.shape),
            preview=_preview_rows(preview),
        )

    raise ValueError(f"Unsupported data file type: {data_path.suffix}")


def read_grid_window(
    path: str | Path,
    *,
    sheet_name: str | int | None = None,
    row_offset: int = 0,
    col_offset: int = 0,
    row_count: int = DEFAULT_GRID_ROW_COUNT,
    col_count: int = DEFAULT_GRID_COL_COUNT,
) -> DataGridWindow:
    data_path = _normalize_path(path)
    suffix = data_path.suffix.lower()
    row_offset = max(0, int(row_offset))
    col_offset = max(0, int(col_offset))
    row_count = min(MAX_GRID_ROW_COUNT, max(1, int(row_count)))
    col_count = min(MAX_GRID_COL_COUNT, max(1, int(col_count)))

    if suffix in {".xlsx", ".xls"}:
        with pd.ExcelFile(data_path) as book:
            selected = book.sheet_names[0] if sheet_name is None else _normalize_sheet_name(sheet_name)
        full = pd.read_excel(data_path, header=None, sheet_name=selected)
    elif suffix == ".csv":
        if sheet_name is not None:
            raise ValueError("CSV files do not support sheet selection.")
        selected = None
        full = _read_csv(data_path, header=None)
    else:
        raise ValueError(f"Unsupported data file type: {data_path.suffix}")

    window = full.iloc[row_offset : row_offset + row_count, col_offset : col_offset + col_count]
    return DataGridWindow(
        path=data_path,
        suffix=suffix,
        sheet_name=selected,
        shape=tuple(full.shape),
        row_offset=row_offset,
        col_offset=col_offset,
        rows=_preview_rows(window),
    )


def _generated_voltage(count: int, start: float, end: float, step: float) -> np.ndarray:
    if step == 0.0:
        raise ValueError("voltage_step cannot be zero.")

    span = end - start
    if span == 0.0:
        expected = 1
    elif span * step < 0.0:
        raise ValueError("voltage_step sign must move from voltage_start toward voltage_end.")
    else:
        expected = int(round(span / step)) + 1

    if expected <= 0:
        raise ValueError("Generated voltage range must contain at least one point.")

    actual_end = start + step * (expected - 1)
    tolerance = max(abs(step) * 1e-6, 1e-12)
    if not np.isclose(actual_end, end, atol=tolerance, rtol=0.0):
        raise ValueError(
            "Voltage start/end/step do not form an exact grid: "
            f"start={start}, end={end}, step={step}."
        )

    if expected != count:
        raise ValueError(
            "Generated voltage length does not match current data length: "
            f"{expected} voltage points from {start:g} to {end:g} step {step:g}, "
            f"but current range has {count} points."
        )

    return np.round(start + step * np.arange(expected, dtype=float), 12)


def _looks_like_voltage_column(current: np.ndarray, voltage: np.ndarray) -> bool:
    current = np.asarray(current, dtype=float).reshape(-1)
    voltage = np.asarray(voltage, dtype=float).reshape(-1)
    if current.size < 8 or current.size != voltage.size:
        return False
    if not np.all(np.isfinite(current)) or not np.all(np.isfinite(voltage)):
        return False

    voltage_step = np.diff(voltage)
    current_step = np.diff(current)
    if current_step.size == 0 or not np.all(np.isfinite(current_step)):
        return False

    if np.allclose(current, voltage, rtol=0.02, atol=max(np.max(np.abs(voltage_step)) * 2, 0.02)):
        return True

    nonzero_step = current_step[np.abs(current_step) > 1e-12]
    if nonzero_step.size < max(3, current.size - 3):
        return False

    monotonic = np.all(nonzero_step > 0.0) or np.all(nonzero_step < 0.0)
    if not monotonic:
        return False

    current_span = float(np.ptp(current))
    voltage_span = float(np.ptp(voltage))
    if current_span <= 0.0 or voltage_span <= 0.0:
        return False

    step_mean = float(np.mean(np.abs(nonzero_step)))
    step_rel_std = float(np.std(np.abs(nonzero_step)) / max(step_mean, 1e-12))
    corr = float(np.corrcoef(current, voltage)[0, 1])
    span_ratio = current_span / voltage_span
    endpoint_tol = max(0.03, 0.05 * voltage_span)

    same_endpoints = (
        abs(float(current[0] - voltage[0])) <= endpoint_tol
        and abs(float(current[-1] - voltage[-1])) <= endpoint_tol
    )
    bounded = float(np.max(np.abs(current))) <= max(5.0, 2.0 * float(np.max(np.abs(voltage))))
    similar_span = 0.7 <= span_ratio <= 1.3
    return abs(corr) >= 0.995 and step_rel_std <= 0.25 and similar_span and same_endpoints and bounded


def _dominant_fraction(values: np.ndarray, predicate) -> float | None:
    selected = np.asarray(values, dtype=float).reshape(-1)
    if selected.size == 0:
        return None
    return float(np.mean(predicate(selected)))


def _normalize_current_sign(voltage: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    v = np.asarray(voltage, dtype=float).reshape(-1)
    j = np.asarray(current, dtype=float).reshape(-1)
    normalized = j.copy()
    info: dict[str, Any] = {
        "expected": "signed_current: reverse bias V<0 should have J<0",
        "action": "none",
        "message": "Current signs already match the internal signed-current convention or were left unchanged.",
    }
    if v.size != j.size or v.size < 2 or not np.all(np.isfinite(v)) or not np.all(np.isfinite(j)):
        info["action"] = "skipped"
        info["message"] = "Current sign normalization skipped because the data are incomplete or non-finite."
        return normalized, info

    max_abs = float(np.max(np.abs(j))) if j.size else 0.0
    threshold = max(max_abs * 1e-8, 1e-15)
    valid = (np.abs(v) > 1e-12) & (np.abs(j) > threshold)
    if int(np.sum(valid)) < max(2, min(6, v.size // 3)):
        info["action"] = "skipped"
        info["message"] = "Current sign normalization skipped because too few nonzero signed points were available."
        return normalized, info

    sign_agreement = np.sign(v[valid]) == np.sign(j[valid])
    agreement = float(np.mean(sign_agreement))
    info["sign_voltage_agreement"] = agreement

    neg = valid & (v < 0.0)
    pos = valid & (v > 0.0)
    neg_positive = _dominant_fraction(j[neg], lambda values: values > 0.0)
    pos_negative = _dominant_fraction(j[pos], lambda values: values < 0.0)
    info["reverse_positive_fraction"] = neg_positive
    info["forward_negative_fraction"] = pos_negative

    same_positive = bool(np.all(j[valid] > 0.0))
    same_negative = bool(np.all(j[valid] < 0.0))
    if same_positive or same_negative:
        signed = np.sign(v) * np.abs(normalized)
        signed[v == 0.0] = normalized[v == 0.0]
        normalized = signed
        info["action"] = "signed_by_voltage"
        info["message"] = "Current appeared to be stored as a one-sided magnitude; signs were assigned from voltage polarity."
        return normalized, info

    if agreement >= 0.8:
        return normalized, info

    if agreement <= 0.2:
        normalized = -normalized
        info["action"] = "flip_all"
        info["message"] = "Current sign was globally flipped so V<0 maps to J<0 and V>0 maps to J>0."
        return normalized, info

    if neg_positive is not None and neg_positive >= 0.8 and (pos_negative is None or pos_negative < 0.5):
        normalized[v < 0.0] = -np.abs(normalized[v < 0.0])
        info["action"] = "reverse_magnitude_to_negative"
        info["message"] = "Reverse-bias current looked like a positive magnitude; V<0 points were converted to negative current."
        return normalized, info

    if pos_negative is not None and pos_negative >= 0.8 and (neg_positive is None or neg_positive < 0.5):
        normalized[v > 0.0] = np.abs(normalized[v > 0.0])
        info["action"] = "forward_magnitude_to_positive"
        info["message"] = "Forward-bias current looked like a negative magnitude; V>0 points were converted to positive current."
        return normalized, info

    info["action"] = "ambiguous"
    info["message"] = "Current sign pattern was ambiguous; values were left unchanged."
    return normalized, info


def _table_to_dataset(raw: np.ndarray, selection: DataSelection) -> tuple[np.ndarray, np.ndarray, str]:
    table = np.asarray(raw, dtype=float)
    if table.ndim != 2:
        table = table.reshape(-1, 1)

    if table.shape[1] >= 2 and table.shape[0] > 1:
        return table[:, 0].reshape(-1), table[:, 1].reshape(-1), "two_column_voltage_current"

    current = table.reshape(-1)
    voltage = _generated_voltage(
        current.size,
        selection.voltage_start,
        selection.voltage_end,
        selection.voltage_step,
    )
    return voltage, current, "generated_voltage_current_only"


def _validate_selection(selection: DataSelection) -> None:
    if selection.cell_range and (selection.voltage_range or selection.current_range):
        raise ValueError("Use either cell_range or voltage/current ranges, not both.")
    if selection.voltage_range and not selection.current_range:
        raise ValueError("voltage_range requires current_range.")
    if selection.voltage_step == 0.0:
        raise ValueError("voltage_step cannot be zero.")


def load_dataset(selection: DataSelection) -> LoadedDataset:
    _validate_selection(selection)
    data_path = _normalize_path(selection.path)
    source_voltage_range = selection.voltage_range
    voltage_inference: dict[str, Any] | None = None

    if selection.current_range:
        current = _read_table(data_path, selection.current_range, selection.sheet_name).reshape(-1)
        if selection.voltage_range:
            voltage = _read_table(data_path, selection.voltage_range, selection.sheet_name).reshape(-1)
            mode = "separate_voltage_current_ranges"
        else:
            voltage = _generated_voltage(
                current.size,
                selection.voltage_start,
                selection.voltage_end,
                selection.voltage_step,
            )
            mode = "generated_voltage_current_range"
            voltage_inference = {
                "action": "generated",
                "message": "No explicit voltage range was submitted; generated voltage settings were used.",
            }
            if _looks_like_voltage_column(current, voltage):
                raise ValueError(
                    "Selected current range looks like a voltage column. "
                    "Choose the JV current column and keep generated voltage for the x-axis."
                )
    else:
        raw = _read_table(data_path, selection.cell_range, selection.sheet_name)
        voltage, current, mode = _table_to_dataset(raw, selection)

    current, sign_info = _normalize_current_sign(voltage, current)
    validate_input_data(voltage, current)
    return LoadedDataset(
        data_v=voltage,
        data_jd=current,
        selection=selection,
        source={
            "path": str(data_path),
            "suffix": data_path.suffix.lower(),
            "sheet_name": selection.sheet_name,
            "cell_range": selection.cell_range,
            "voltage_range": source_voltage_range,
            "current_range": selection.current_range,
            "voltage_start": selection.voltage_start,
            "voltage_end": selection.voltage_end,
            "voltage_step": selection.voltage_step,
            "mode": mode,
            "voltage_inference": voltage_inference,
            "current_sign_convention": sign_info,
            "points": int(current.size),
        },
    )


def validate_input_data(v: np.ndarray, jd: np.ndarray) -> None:
    voltage = np.asarray(v)
    current = np.asarray(jd)
    if voltage.size == 0 or current.size == 0:
        raise ValueError("Input data cannot be empty.")
    if voltage.size != current.size:
        raise ValueError("Voltage and current arrays must have the same length.")
    if not np.issubdtype(voltage.dtype, np.number) or not np.issubdtype(current.dtype, np.number):
        raise TypeError("Input data must be numeric.")
    if np.any(np.isnan(voltage)) or np.any(np.isnan(current)):
        raise ValueError("Input data contains NaN values.")
    if np.any(np.isinf(voltage)) or np.any(np.isinf(current)):
        raise ValueError("Input data contains infinite values.")
