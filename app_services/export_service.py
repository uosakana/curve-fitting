from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from openpyxl import Workbook

from app.api_utils import safe_name


def _xlsx_cell_value(value: Any):
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    return numeric if math.isfinite(numeric) else None


def component_workbook_bytes(component_series: dict, sample_context: dict | None = None) -> bytes:
    columns = component_series.get("columns") or []
    data = component_series.get("data") or {}
    point_count = int(component_series.get("point_count") or 0)
    if point_count <= 0:
        raise ValueError("Component series is empty. Run a fit before exporting XLSX.")
    if not columns:
        raise ValueError("Component series has no column definitions.")
    if not isinstance(data, dict):
        raise ValueError("Component series data must be an object keyed by column.")

    keys: list[str] = []
    labels: list[str] = []
    for index, column in enumerate(columns, start=1):
        if not isinstance(column, dict):
            raise ValueError(f"Component column {index} is invalid.")
        key = str(column.get("key") or "").strip()
        if not key:
            raise ValueError(f"Component column {index} has no key.")
        keys.append(key)
        labels.append(str(column.get("label") or key))
        values = data.get(key)
        if not isinstance(values, list) or len(values) < point_count:
            raise ValueError(f"Component column {key!r} has fewer than {point_count} point(s).")

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "components"
    sheet.append(labels)
    sheet.freeze_panes = "A2"
    for row_index in range(point_count):
        sheet.append([_xlsx_cell_value(data[key][row_index]) for key in keys])
    for column_cells in sheet.columns:
        header = str(column_cells[0].value or "")
        sheet.column_dimensions[column_cells[0].column_letter].width = min(max(len(header) + 2, 14), 28)

    if isinstance(sample_context, dict) and sample_context:
        metadata = workbook.create_sheet("metadata")
        metadata.append(["field", "value"])
        for key in ("sample_id", "batch", "structure", "process", "comparison_group", "aging_days"):
            value = sample_context.get(key)
            if value not in (None, ""):
                metadata.append([key, str(value)])
        metadata.append(["point_count", point_count])
        metadata.column_dimensions["A"].width = 22
        metadata.column_dimensions["B"].width = 48

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def components_xlsx_export(payload: dict[str, Any]) -> tuple[bytes, str, str]:
    sample_context = payload.get("sample_context") or {}
    content = component_workbook_bytes(payload.get("component_series") or {}, sample_context)
    sample_id = ""
    if isinstance(sample_context, dict):
        sample_id = str(sample_context.get("sample_id") or "").strip()
    sample_id = sample_id or str(payload.get("sample_name") or "").strip() or "fit-components"
    utf8_filename = f"{safe_name(sample_id)}_components.xlsx"
    ascii_stem = safe_name(sample_id).encode("ascii", errors="ignore").decode("ascii").strip("._")
    ascii_filename = f"{ascii_stem or 'fit-components'}_components.xlsx"
    return content, utf8_filename, ascii_filename

