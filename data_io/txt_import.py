from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path
from typing import Any


Diagnostic = dict[str, Any]


def parse_txt_file(path: str | Path) -> dict[str, Any]:
    data_path = Path(path)
    raw = data_path.read_bytes()
    text, encoding = _decode_text(raw)
    rows = _split_rows(text)
    result = parse_txt_rows(rows, text.splitlines(), filename=data_path.name, encoding=encoding)
    result["path"] = str(data_path)
    return result


def parse_txt_rows(
    rows: list[list[str]],
    lines: list[str],
    *,
    filename: str = "",
    encoding: str = "",
) -> dict[str, Any]:
    diagnostics: list[Diagnostic] = []
    if not rows:
        return {
            "filename": filename,
            "encoding": encoding,
            "format": "unknown",
            "total_blocks": 0,
            "ok_blocks": 0,
            "failed_blocks": 0,
            "diagnostics": [
                {
                    "level": "error",
                    "message": "TXT file is empty or could not be split into rows.",
                    "excerpt": "",
                }
            ],
            "blocks": [],
        }

    wide = _parse_wide_result_table(rows, diagnostics)
    if wide:
        blocks = wide
        parser_format = "wide_result_table"
    else:
        blocks = _parse_vertical_tables(rows, diagnostics)
        parser_format = "vertical_tables" if blocks else "unknown"

    if not blocks:
        diagnostics.append(
            {
                "level": "error",
                "message": "No JV blocks were recognized. Expected a result header containing voltage plus I/J columns.",
                "excerpt": _excerpt_from_lines(lines, 0, 12),
            }
        )

    ok_blocks = sum(1 for block in blocks if block.get("status") == "ok")
    failed_blocks = len(blocks) - ok_blocks
    diagnostics.append(
        {
            "level": "info" if ok_blocks else "warning",
            "message": f"Parsed {ok_blocks} usable block(s); {failed_blocks} block(s) need attention.",
        }
    )
    return {
        "filename": filename,
        "encoding": encoding,
        "format": parser_format,
        "total_blocks": len(blocks),
        "ok_blocks": ok_blocks,
        "failed_blocks": failed_blocks,
        "diagnostics": diagnostics,
        "blocks": blocks,
    }


def block_series_rows(
    block: dict[str, Any],
    *,
    voltage_min: float | None = None,
    voltage_max: float | None = None,
    min_points: int = 2,
) -> list[tuple[float, float]]:
    if block.get("status") != "ok":
        raise ValueError("Only successfully parsed blocks can be exported.")
    series = block.get("series") or {}
    voltage = series.get("voltage") or []
    current = series.get("y") or []
    if not voltage or len(voltage) != len(current):
        raise ValueError("Block series is empty or has mismatched voltage/current lengths.")

    if voltage_min is not None and voltage_max is not None:
        lower = min(float(voltage_min), float(voltage_max))
        upper = max(float(voltage_min), float(voltage_max))
    else:
        lower = float(voltage_min) if voltage_min is not None else None
        upper = float(voltage_max) if voltage_max is not None else None
    rows: list[tuple[float, float]] = []
    for v, y in zip(voltage, current, strict=True):
        v_num = float(v)
        y_num = float(y)
        if lower is not None and v_num < lower:
            continue
        if upper is not None and v_num > upper:
            continue
        rows.append((v_num, y_num))

    if len(rows) < min_points:
        if lower is None or upper is None:
            label = "Selected TXT block"
        else:
            label = f"Selected TXT voltage range {lower:g} to {upper:g} V"
        raise ValueError(f"{label} contains {len(rows)} point(s); at least {min_points} are required.")
    return rows


def block_to_csv(
    block: dict[str, Any],
    *,
    voltage_min: float | None = None,
    voltage_max: float | None = None,
    min_points: int = 2,
) -> str:
    rows = block_series_rows(
        block,
        voltage_min=voltage_min,
        voltage_max=voltage_max,
        min_points=min_points,
    )
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for v, y in rows:
        writer.writerow([_format_number(v), _format_number(y)])
    return output.getvalue()


def find_block(parsed: dict[str, Any], block_id: str) -> dict[str, Any]:
    for block in parsed.get("blocks") or []:
        if block.get("id") == block_id:
            return block
    raise ValueError(f"TXT block not found: {block_id}")


def _decode_text(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "gb18030", "latin-1"):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        if text.count("\x00") > max(4, len(text) // 50):
            continue
        return text, encoding
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def _split_rows(text: str) -> list[list[str]]:
    sample = "\n".join(text.splitlines()[:20])
    tab_count = sample.count("\t")
    comma_count = sample.count(",")
    semicolon_count = sample.count(";")
    delimiter = "\t"
    if tab_count == 0 and max(comma_count, semicolon_count) > 0:
        delimiter = "," if comma_count >= semicolon_count else ";"

    rows: list[list[str]] = []
    if delimiter:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = [[cell.strip() for cell in row] for row in reader]

    if rows and max((len(row) for row in rows), default=0) > 1:
        return rows

    fallback: list[list[str]] = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in re.split(r"\t|,|;|\s{2,}", line.rstrip())]
        fallback.append(cells)
    return fallback


def _parse_wide_result_table(rows: list[list[str]], diagnostics: list[Diagnostic]) -> list[dict[str, Any]]:
    header_index = _find_wide_header_row(rows)
    if header_index is None:
        diagnostics.append(
            {
                "level": "info",
                "message": "Wide result-table parser did not find a [Result] header; trying vertical table parsing.",
            }
        )
        return []

    header = rows[header_index]
    starts = [col for col, cell in enumerate(header) if _is_voltage_label(cell)]
    starts = [col for col in starts if col > 0 or _has_y_column(header, col, _next_start(starts, col, len(header)))]
    if not starts:
        diagnostics.append(
            {
                "level": "error",
                "line": header_index + 1,
                "message": "Found a result header but no voltage columns were recognized.",
                "excerpt": _excerpt_from_rows(rows, header_index, max(0, header_index - 2), header_index + 4, 0, min(len(header), 12)),
            }
        )
        return []

    blocks: list[dict[str, Any]] = []
    for index, start_col in enumerate(starts, start=1):
        end_col = starts[index] if index < len(starts) else len(header)
        block = _parse_wide_block(rows, header_index, start_col, end_col, index)
        blocks.append(block)

    diagnostics.append(
        {
            "level": "info",
            "line": header_index + 1,
            "message": f"Detected {len(blocks)} column block(s) from the wide [Result] table.",
        }
    )
    return blocks


def _parse_wide_block(
    rows: list[list[str]],
    header_index: int,
    start_col: int,
    end_col: int,
    block_index: int,
) -> dict[str, Any]:
    block_id = f"block_{block_index:04d}"
    diagnostics: list[Diagnostic] = []
    header = rows[header_index]
    meta = _metadata_for_block(rows, header_index, start_col, end_col)
    col_map = _columns_for_group(header, start_col, end_col)
    voltage_col = col_map.get("voltage")
    y_col = col_map.get("j") or col_map.get("i") or col_map.get("i_abs")
    if col_map.get("j") is not None:
        y_kind = "J"
    elif col_map.get("i") is not None:
        y_kind = "I"
    else:
        y_kind = "ABS_I"
    eqe_col = col_map.get("eqe")
    dark_col = col_map.get("dark")

    excerpt = _block_excerpt(rows, header_index, start_col, end_col)
    if voltage_col is None:
        diagnostics.append({"level": "error", "message": "No voltage column was recognized in this block."})
    if y_col is None:
        diagnostics.append({"level": "error", "message": "No J or I column was recognized in this block."})
    elif y_kind == "I":
        diagnostics.append({"level": "warning", "message": "Using I column because no J/current-density column was found."})
    elif y_kind == "ABS_I":
        diagnostics.append(
            {
                "level": "warning",
                "message": "Using abs(I) magnitude because no J or signed I column was found; signs will be inferred from voltage polarity.",
            }
        )

    voltage: list[float] = []
    current: list[float] = []
    eqe: list[float | None] = []
    dark: list[float | None] = []
    skipped = 0
    skipped_samples: list[dict[str, Any]] = []

    if voltage_col is not None and y_col is not None:
        data_start = _find_data_start(rows, header_index, start_col, voltage_col, y_col)
        data_started = False
        for row_index in range(data_start, len(rows)):
            row = rows[row_index]
            raw_v = _cell(row, voltage_col)
            raw_y = _cell(row, y_col)
            v = _parse_float(raw_v)
            y = _parse_float(raw_y)
            if v is None and y is None:
                if data_started and len(voltage) >= 2:
                    break
                continue
            if v is None or y is None:
                skipped += 1
                if len(skipped_samples) < 5:
                    skipped_samples.append({"line": row_index + 1, "voltage": raw_v, "current": raw_y})
                continue
            if _breaks_voltage_sequence(voltage, v):
                diagnostics.append(
                    {
                        "level": "warning",
                        "line": row_index + 1,
                        "message": "Stopped block data at a voltage-sequence break; later numeric rows were left out.",
                        "samples": [{"voltage": raw_v, "current": raw_y}],
                    }
                )
                break
            data_started = True
            voltage.append(v)
            current.append(y)
            eqe.append(_parse_float(_cell(row, eqe_col)) if eqe_col is not None else None)
            dark.append(_parse_float(_cell(row, dark_col)) if dark_col is not None else None)

    if skipped:
        diagnostics.append(
            {
                "level": "warning",
                "message": f"Skipped {skipped} row(s) with missing or nonnumeric voltage/current values.",
                "samples": skipped_samples,
            }
        )

    status = "ok"
    if len(voltage) < 2 or len(current) < 2:
        status = "error"
        diagnostics.append(
            {
                "level": "error",
                "message": f"Block has only {len(current)} usable point(s); at least 2 are required.",
                "excerpt": excerpt,
            }
        )

    return _block_payload(
        block_id=block_id,
        index=block_index,
        status=status,
        meta=meta,
        columns={
            "voltage": _cell(header, voltage_col) if voltage_col is not None else "",
            "y": _cell(header, y_col) if y_col is not None else "",
            "y_kind": y_kind if y_col is not None else "",
            "eqe": _cell(header, eqe_col) if eqe_col is not None else "",
            "dark": _cell(header, dark_col) if dark_col is not None else "",
        },
        voltage=voltage,
        current=current,
        eqe=eqe if any(value is not None for value in eqe) else [],
        dark=dark if any(value is not None for value in dark) else [],
        diagnostics=diagnostics,
        raw_excerpt=excerpt if status == "error" or diagnostics else "",
    )


def _parse_vertical_tables(rows: list[list[str]], diagnostics: list[Diagnostic]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    start = 0
    chunks: list[tuple[int, list[list[str]]]] = []
    for index, row in enumerate(rows + [[]]):
        if index < len(rows) and any(_cell(row, col) for col in range(len(row))):
            continue
        if index > start:
            chunks.append((start, rows[start:index]))
        start = index + 1

    if not chunks:
        chunks = [(0, rows)]

    for chunk_index, (base_row, chunk) in enumerate(chunks, start=1):
        header_index = _find_vertical_header_row(chunk)
        if header_index is None:
            continue
        header = chunk[header_index]
        col_map = _columns_for_group(header, 0, len(header))
        voltage_col = col_map.get("voltage")
        y_col = col_map.get("j") or col_map.get("i") or col_map.get("i_abs")
        if voltage_col is None or y_col is None:
            continue

        meta = _metadata_from_vertical_chunk(chunk[:header_index])
        voltage: list[float] = []
        current: list[float] = []
        eqe: list[float | None] = []
        eqe_col = col_map.get("eqe")
        skipped = 0
        block_diagnostics: list[Diagnostic] = []
        data_started = False
        for offset, row in enumerate(chunk[header_index + 1 :], start=header_index + 1):
            v = _parse_float(_cell(row, voltage_col))
            y = _parse_float(_cell(row, y_col))
            if v is None and y is None:
                if data_started and len(voltage) >= 2:
                    break
                continue
            if v is None or y is None:
                skipped += 1
                continue
            if _breaks_voltage_sequence(voltage, v):
                block_diagnostics.append(
                    {
                        "level": "warning",
                        "line": base_row + offset + 1,
                        "message": "Stopped block data at a voltage-sequence break; later numeric rows were left out.",
                    }
                )
                break
            data_started = True
            voltage.append(v)
            current.append(y)
            eqe.append(_parse_float(_cell(row, eqe_col)) if eqe_col is not None else None)

        if skipped:
            block_diagnostics.append({"level": "warning", "message": f"Skipped {skipped} nonnumeric row(s)."})
        status = "ok" if len(current) >= 2 else "error"
        if status == "error":
            block_diagnostics.append(
                {
                    "level": "error",
                    "message": f"Block has only {len(current)} usable point(s); at least 2 are required.",
                    "excerpt": _excerpt_from_rows(chunk, header_index, max(0, header_index - 4), min(len(chunk), header_index + 8), 0, len(header)),
                }
            )
        blocks.append(
            _block_payload(
                block_id=f"block_{chunk_index:04d}",
                index=chunk_index,
                status=status,
                meta=meta,
                columns={
                    "voltage": _cell(header, voltage_col),
                    "y": _cell(header, y_col),
                    "y_kind": "J" if col_map.get("j") is not None else "I" if col_map.get("i") is not None else "ABS_I",
                    "eqe": _cell(header, eqe_col) if eqe_col is not None else "",
                    "dark": "",
                },
                voltage=voltage,
                current=current,
                eqe=eqe if any(value is not None for value in eqe) else [],
                dark=[],
                diagnostics=block_diagnostics,
                raw_excerpt="",
            )
        )

    if blocks:
        diagnostics.append({"level": "info", "message": f"Detected {len(blocks)} vertical table block(s)."})
    return blocks


def _block_payload(
    *,
    block_id: str,
    index: int,
    status: str,
    meta: dict[str, Any],
    columns: dict[str, str],
    voltage: list[float],
    current: list[float],
    eqe: list[float | None],
    dark: list[float | None],
    diagnostics: list[Diagnostic],
    raw_excerpt: str,
) -> dict[str, Any]:
    clean_eqe = [value for value in eqe if value is not None]
    clean_dark = [value for value in dark if value is not None]
    summary = {
        "id": block_id,
        "index": index,
        "status": status,
        "name": meta.get("name") or f"Block {index}",
        "mode": meta.get("mode"),
        "lambda_nm": meta.get("lambda_nm"),
        "timestamp": meta.get("timestamp"),
        "point_count": len(current),
        "voltage_range": _range(voltage),
        "current_range": _range(current),
        "eqe_range": _range(clean_eqe),
        "dark_range": _range(clean_dark),
        "columns": columns,
        "diagnostics": diagnostics,
        "raw_excerpt": raw_excerpt,
        "series": {
            "voltage": voltage,
            "y": current,
        },
    }
    if clean_eqe and len(eqe) == len(voltage):
        summary["series"]["eqe"] = eqe
    if clean_dark and len(dark) == len(voltage):
        summary["series"]["dark"] = dark
    return summary


def _find_wide_header_row(rows: list[list[str]]) -> int | None:
    best: tuple[int, int] | None = None
    for index, row in enumerate(rows):
        voltage_count = sum(1 for cell in row if _is_voltage_label(cell))
        y_count = sum(1 for cell in row if _classify_y_label(cell) is not None)
        marker = any(_compact(cell) == "result" for cell in row)
        if voltage_count and y_count and (marker or voltage_count > 1):
            score = voltage_count * 10 + y_count + (50 if marker else 0)
            if best is None or score > best[0]:
                best = (score, index)
    return best[1] if best is not None else None


def _find_vertical_header_row(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows):
        if any(_is_voltage_label(cell) for cell in row) and any(_classify_y_label(cell) is not None for cell in row):
            return index
    return None


def _find_data_start(
    rows: list[list[str]],
    header_index: int,
    start_col: int,
    voltage_col: int,
    y_col: int,
) -> int:
    for index in range(header_index + 1, min(len(rows), header_index + 12)):
        row = rows[index]
        if any(_compact(cell) == "rawdata" for cell in row[: max(1, start_col + 1)]):
            return index
        if _parse_float(_cell(row, voltage_col)) is not None and _parse_float(_cell(row, y_col)) is not None:
            return index
    return header_index + 1


def _metadata_for_block(
    rows: list[list[str]],
    header_index: int,
    start_col: int,
    end_col: int,
) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for row_index in range(0, header_index):
        row = rows[row_index]
        key = _compact(_cell(row, 0))
        if not key:
            if row_index == 0:
                block_number = _first_nonempty(row, start_col, end_col)
                if block_number:
                    meta.setdefault("block_number", block_number)
            continue
        value = _first_nonempty(row, start_col, end_col)
        if not value:
            continue
        if key in {"name", "samplename", "sample", "sampleid", "device", "id"}:
            meta["name"] = value
        elif key == "mode":
            meta["mode"] = _normalize_mode(value)
        elif key in {"timestamp", "time", "datetime", "date"} or "timestamp" in key:
            meta["timestamp"] = value
        elif "wavelength" in key or "lambda" in key or "\u03bb" in str(_cell(row, 0)).lower():
            meta["lambda_nm"] = _parse_float(value)
        elif key in {"area", "areacm2"}:
            meta["area_cm2"] = _parse_float(value)
    return meta


def _metadata_from_vertical_chunk(rows: list[list[str]]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for row in rows:
        compact_cells = [cell for cell in row if cell.strip()]
        if len(compact_cells) < 2:
            continue
        key = _compact(compact_cells[0].split(":", 1)[0])
        if ":" in compact_cells[0] and len(compact_cells) == 1:
            value = compact_cells[0].split(":", 1)[1].strip()
        else:
            value = compact_cells[1].strip()
        if not value:
            continue
        if key in {"name", "samplename", "sample", "sampleid", "device", "id"}:
            meta["name"] = value
        elif key == "mode":
            meta["mode"] = _normalize_mode(value)
        elif key in {"timestamp", "time", "datetime", "date"} or "timestamp" in key:
            meta["timestamp"] = value
        elif "wavelength" in key or "lambda" in key or "\u03bb" in compact_cells[0].lower():
            meta["lambda_nm"] = _parse_float(value)
    return meta


def _columns_for_group(header: list[str], start_col: int, end_col: int) -> dict[str, int]:
    columns: dict[str, int] = {}
    for col in range(start_col, end_col):
        label = _cell(header, col)
        if _is_voltage_label(label):
            columns.setdefault("voltage", col)
            continue
        y_kind = _classify_y_label(label)
        if y_kind is not None:
            columns.setdefault(y_kind.lower(), col)
            continue
        if _is_eqe_label(label):
            columns.setdefault("eqe", col)
            continue
        if _is_dark_label(label):
            columns.setdefault("dark", col)
    return columns


def _next_start(starts: list[int], col: int, fallback: int) -> int:
    for start in starts:
        if start > col:
            return start
    return fallback


def _has_y_column(header: list[str], start_col: int, end_col: int) -> bool:
    return any(_classify_y_label(_cell(header, col)) is not None for col in range(start_col, end_col))


def _is_voltage_label(label: str) -> bool:
    compact = _compact(label)
    return compact in {"v", "volt", "voltage", "voltv", "voltagev"} or compact.startswith("volt")


def _classify_y_label(label: str) -> str | None:
    raw = str(label).lower()
    compact = _compact(label)
    if not compact or "semilog" in compact or "log" in compact:
        return None
    if "eqe" in compact or "response" in compact or "responsivity" in compact:
        return None
    if "dark" in compact:
        return None
    if "abs" in compact or "absolute" in compact or "magnitude" in compact:
        if "i" in compact or "current" in compact:
            return "I_ABS"
        return None
    if compact in {"j", "ja", "jacm2", "macm2"} or compact.startswith("jacm") or "currentdensity" in compact:
        return "J"
    if re.search(r"\bj\b", raw) and ("cm" in raw or "density" in raw):
        return "J"
    if compact in {"i", "ia", "current", "currenta"}:
        return "I"
    if re.search(r"\bi\s*\(?a\)?", raw):
        return "I"
    return None


def _is_eqe_label(label: str) -> bool:
    compact = _compact(label)
    return "eqe" in compact or "lightresponse" in compact or "responsivity" in compact


def _is_dark_label(label: str) -> bool:
    return "dark" in _compact(label)


def _normalize_mode(value: str) -> str | None:
    lowered = str(value).strip().lower()
    if "dark" in lowered:
        return "dark"
    if "light" in lowered or "illum" in lowered:
        return "light"
    return lowered or None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "na", "n/a", "none", "null"}:
        return None
    text = text.replace(",", "")
    match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text)
    if not match:
        return None
    try:
        numeric = float(match.group(0))
    except ValueError:
        return None
    return numeric if math.isfinite(numeric) else None


def _range(values: list[float]) -> list[float] | None:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    if not clean:
        return None
    return [min(clean), max(clean)]


def _breaks_voltage_sequence(existing: list[float], next_value: float) -> bool:
    if len(existing) < 4:
        return False
    diffs = [abs(existing[index] - existing[index - 1]) for index in range(1, len(existing))]
    diffs = [diff for diff in diffs[-12:] if diff > 1e-12 and math.isfinite(diff)]
    if len(diffs) < 3:
        return False
    ordered = sorted(diffs)
    expected = ordered[len(ordered) // 2]
    if expected <= 0:
        return False
    actual = abs(float(next_value) - existing[-1])
    tolerance = max(expected * 0.45, 1e-9)
    return actual > expected + tolerance or actual < max(0.0, expected - tolerance)


def _format_number(value: Any) -> str:
    numeric = float(value)
    return f"{numeric:.12g}"


def _compact(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _cell(row: list[str], col: int | None) -> str:
    if col is None or col < 0 or col >= len(row):
        return ""
    return str(row[col]).strip()


def _first_nonempty(row: list[str], start_col: int, end_col: int) -> str:
    for col in range(start_col, min(end_col, len(row))):
        value = _cell(row, col)
        if value:
            return value
    return ""


def _excerpt_from_lines(lines: list[str], start: int, count: int) -> str:
    end = min(len(lines), start + count)
    return "\n".join(f"{index + 1}: {_truncate(lines[index], 240)}" for index in range(start, end))


def _excerpt_from_rows(
    rows: list[list[str]],
    anchor: int,
    start: int,
    end: int,
    col_start: int,
    col_end: int,
) -> str:
    parts: list[str] = []
    for row_index in range(max(0, start), min(len(rows), end)):
        row = rows[row_index]
        cells = [_cell(row, col) for col in range(col_start, min(col_end, max(len(row), col_start)))]
        prefix = ">" if row_index == anchor else " "
        parts.append(f"{prefix}{row_index + 1}: {_truncate(chr(9).join(cells), 240)}")
    return "\n".join(parts)


def _block_excerpt(rows: list[list[str]], header_index: int, start_col: int, end_col: int) -> str:
    col_start = max(0, start_col - 1)
    col_end = min(end_col, start_col + 7)
    return _excerpt_from_rows(
        rows,
        header_index,
        max(0, header_index - 6),
        min(len(rows), header_index + 8),
        col_start,
        col_end,
    )


def _truncate(text: str, limit: int) -> str:
    clean = text.replace("\r", "")
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."
