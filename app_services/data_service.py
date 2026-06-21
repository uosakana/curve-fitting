from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.api_utils import (
    json_compatible,
    none_if_blank,
    optional_float,
    serialize_file_info,
    serialize_grid_window,
)
from data_io import (
    block_series_rows,
    block_to_csv,
    find_block,
    inspect_file,
    parse_txt_file,
    read_grid_window,
)


SaveUpload = Callable[[str | None, bytes], tuple[str, Path]]


def inspect_data_file(file_path: str | Path, *, sheet_name: str = "") -> dict[str, Any]:
    info = inspect_file(file_path, sheet_name=none_if_blank(sheet_name))
    return serialize_file_info(info)


def read_data_grid(
    file_path: str | Path,
    *,
    sheet_name: str = "",
    row_offset: int = 0,
    col_offset: int = 0,
    row_count: int = 2000,
    col_count: int = 2000,
) -> dict[str, Any]:
    window = read_grid_window(
        file_path,
        sheet_name=none_if_blank(sheet_name),
        row_offset=row_offset,
        col_offset=col_offset,
        row_count=row_count,
        col_count=col_count,
    )
    return serialize_grid_window(window)


def parse_txt_upload(file_path: str | Path) -> dict[str, Any]:
    return json_compatible(parse_txt_file(file_path))


def activate_txt_block(file_path: str | Path, payload: dict[str, Any], save_upload: SaveUpload) -> dict[str, Any]:
    block_id = str(payload.get("block_id") or "").strip()
    if not block_id:
        raise ValueError("TXT block_id is required.")

    parsed = parse_txt_file(file_path)
    block = find_block(parsed, block_id)
    voltage_min = optional_float(payload.get("voltage_min"))
    voltage_max = optional_float(payload.get("voltage_max"))
    rows = block_series_rows(block, voltage_min=voltage_min, voltage_max=voltage_max)
    csv_text = block_to_csv(block, voltage_min=voltage_min, voltage_max=voltage_max)
    csv_name = f"{Path(file_path).stem}_{block_id}.csv"
    generated_upload_id, generated_path = save_upload(csv_name, csv_text.encode("utf-8"))
    point_count = len(rows)
    activated_voltage = [row[0] for row in rows]
    return {
        "upload_id": generated_upload_id,
        "file": inspect_data_file(generated_path),
        "selection": {
            "voltage_range": f"A1:A{point_count}",
            "current_range": f"B1:B{point_count}",
            "cell_range": "",
            "sheet_name": "",
        },
        "block": json_compatible(
            {
                **block,
                "point_count": point_count,
                "voltage_range": [min(activated_voltage), max(activated_voltage)] if activated_voltage else None,
                "fit_voltage_range": {
                    "requested_min": voltage_min,
                    "requested_max": voltage_max,
                },
            }
        ),
    }
