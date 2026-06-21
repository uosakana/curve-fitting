/* ==========================================================================
   Excel preview and range picker workflow
   ========================================================================== */

const DATA_GRID_ROW_COUNT = 2000;
const DATA_GRID_COL_COUNT = 2000;

function renderPreview(preview) {
  if (!preview || preview.length === 0) {
    $("previewTable").innerHTML = '<div class="preview-empty">No preview.</div>';
    return;
  }
  const colCount = Math.max(...preview.map((row) => row.length));
  const header = Array.from({ length: colCount }, (_, i) => `<th>${indexToExcelColumn(i)}</th>`).join("");
  const rows = preview.map((row) => {
    const cells = Array.from({ length: colCount }, (_, i) => `<td>${row[i] ?? ""}</td>`).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
  $("previewTable").innerHTML = `<table class="preview-table"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table>`;
}

function selectionFromCurrentFields() {
  const col = normalizeExcelColumn($("currentColumn").value);
  const colIndex = excelColumnToIndex(col);
  const startRow = Number($("currentStartRow").value);
  const endRow = Number($("currentEndRow").value);
  if (colIndex === null || !Number.isInteger(startRow) || !Number.isInteger(endRow)) return null;
  if (startRow <= 0 || endRow < startRow) return null;
  return { colIndex, startRow, endRow };
}

function numericGridValue(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (value === null || value === undefined) return null;
  const normalized = String(value).trim().replace(/,/g, "");
  if (!normalized) return null;
  const number = Number(normalized);
  return Number.isFinite(number) ? number : null;
}

function gridValuesForColumn(colIndex, startRow, endRow) {
  const grid = state.dataGrid;
  if (!grid || !Array.isArray(grid.rows)) return null;
  const rowOffset = Number(grid.row_offset || 0);
  const colOffset = Number(grid.col_offset || 0);
  const localCol = colIndex - colOffset;
  if (localCol < 0) return null;
  const values = [];
  for (let row = startRow; row <= endRow; row += 1) {
    const localRow = row - rowOffset - 1;
    const sourceRow = grid.rows[localRow];
    if (!sourceRow || localCol >= sourceRow.length) return null;
    const value = numericGridValue(sourceRow[localCol]);
    if (!Number.isFinite(value)) return null;
    values.push(value);
  }
  return values;
}

function isPlausibleVoltageAxis(values) {
  if (!Array.isArray(values) || values.length < 2 || values.some((value) => !Number.isFinite(value))) return false;
  const diffs = [];
  for (let i = 1; i < values.length; i += 1) {
    const diff = values[i] - values[i - 1];
    if (Math.abs(diff) > 1e-12) diffs.push(diff);
  }
  if (diffs.length < Math.max(1, values.length - 2)) return false;
  const monotonic = diffs.every((value) => value > 0) || diffs.every((value) => value < 0);
  if (!monotonic) return false;

  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const span = maxV - minV;
  const maxAbs = Math.max(...values.map((value) => Math.abs(value)));
  if (span < 0.02 || span > 40 || maxAbs > 25) return false;

  const absDiffs = diffs.map((value) => Math.abs(value));
  const mean = absDiffs.reduce((sum, value) => sum + value, 0) / absDiffs.length;
  const variance = absDiffs.reduce((sum, value) => sum + (value - mean) ** 2, 0) / absDiffs.length;
  if (Math.sqrt(variance) / Math.max(mean, 1e-12) > 0.08) return false;

  const nearZero = Math.min(...values.map((value) => Math.abs(value))) <= Math.max(0.08, span * 0.12);
  const bipolar = minV < 0 && maxV > 0;
  return nearZero || bipolar;
}

function inferVoltageSelectionForCurrent(selection) {
  const grid = state.dataGrid;
  if (!grid || !selection || !Array.isArray(grid.rows)) return null;
  const shape = grid.shape || [grid.rows.length, Math.max(...grid.rows.map((row) => row.length), 0)];
  const totalCols = Number(shape[1] || 0);
  if (!Number.isFinite(totalCols) || totalCols <= 1) return null;
  const candidates = Array.from({ length: totalCols }, (_, index) => index)
    .filter((index) => index !== selection.colIndex)
    .sort((a, b) => {
      const distance = Math.abs(a - selection.colIndex) - Math.abs(b - selection.colIndex);
      if (distance !== 0) return distance;
      if ((a > selection.colIndex) !== (b > selection.colIndex)) return a > selection.colIndex ? 1 : -1;
      return a - b;
    });
  for (const colIndex of candidates) {
    const values = gridValuesForColumn(colIndex, selection.startRow, selection.endRow);
    if (values && isPlausibleVoltageAxis(values)) {
      return { colIndex, startRow: selection.startRow, endRow: selection.endRow };
    }
  }
  return null;
}

function applyInferredVoltageForCurrent(selection) {
  if (state.userVoltageOverride) return false;
  const inferred = inferVoltageSelectionForCurrent(selection);
  if (!inferred) return false;
  $("voltageMode").value = "excel_column";
  $("voltageColumn").value = indexToExcelColumn(inferred.colIndex);
  $("voltageStartRow").value = String(inferred.startRow);
  $("voltageEndRow").value = String(inferred.endRow);
  refreshVoltageModeUi();
  return true;
}

function applySelectionPayload(selection) {
  state.userVoltageOverride = false;
  const current = rangeDetailsFromA1(selection?.current_range);
  if (current) {
    $("currentColumn").value = current.column;
    $("currentStartRow").value = String(current.startRow);
    $("currentEndRow").value = String(current.endRow);
    state.gridSelection = { colIndex: current.colIndex, startRow: current.startRow, endRow: current.endRow };
  }

  const voltage = rangeDetailsFromA1(selection?.voltage_range);
  if (voltage) {
    $("voltageMode").value = "excel_column";
    $("voltageColumn").value = voltage.column;
    $("voltageStartRow").value = String(voltage.startRow);
    $("voltageEndRow").value = String(voltage.endRow);
  } else if (selection?.voltage_start !== null && selection?.voltage_start !== undefined) {
    $("voltageMode").value = "generated";
    $("voltageStart").value = String(selection.voltage_start);
    if (selection.voltage_step !== null && selection.voltage_step !== undefined) {
      $("voltageStep").value = String(selection.voltage_step);
    }
    syncGeneratedVoltageEnd();
  }
  refreshVoltageModeUi();
  return current;
}

function updateDataPickerReadout() {
  const selection = state.gridSelection || selectionFromCurrentFields();
  if (!selection) {
    $("dataPickerSelectionText").textContent = "Click a start cell, then click an end cell in the same column.";
    drawDataPickerPreview();
    return;
  }
  const col = indexToExcelColumn(selection.colIndex);
  const rowCount = selection.endRow - selection.startRow + 1;
  let voltageText = "";
  if (usesExcelVoltage()) {
    const voltage = rangeDetailsFromA1(`${$("voltageColumn").value}${$("voltageStartRow").value}:${$("voltageColumn").value}${$("voltageEndRow").value}`);
    if (voltage) voltageText = ` | V ${voltage.range}`;
  }
  $("dataPickerSelectionText").textContent = `${col}${selection.startRow}:${col}${selection.endRow} | ${rowCount} rows${voltageText}`;
  drawDataPickerPreview();
}

function drawEmptyDataPickerPreview(ctx, width, height, message) {
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "rgba(223, 239, 249, 0.48)";
  ctx.font = "12px Inter, Arial, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(message, width / 2, height / 2);
}

function drawDataPickerPreview() {
  const canvas = $("dataPickerPreviewCanvas");
  const meta = $("dataPickerPreviewMeta");
  if (!canvas || !meta) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  const cssWidth = Math.max(220, Math.round(canvas.clientWidth || 360));
  const cssHeight = Math.max(140, Math.round(canvas.clientHeight || 170));
  const pixelWidth = Math.round(cssWidth * dpr);
  const pixelHeight = Math.round(cssHeight * dpr);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const selection = state.gridSelection || selectionFromCurrentFields();
  if (!selection) {
    meta.textContent = "Select a current range.";
    drawEmptyDataPickerPreview(ctx, cssWidth, cssHeight, "Select a range in the grid");
    return;
  }

  const values = gridValuesForColumn(selection.colIndex, selection.startRow, selection.endRow);
  if (!values || values.length < 2) {
    meta.textContent = "Selection has no numeric preview.";
    drawEmptyDataPickerPreview(ctx, cssWidth, cssHeight, "Need at least two numeric cells");
    return;
  }

  const start = Number($("pickerVoltageStart").value);
  const step = Number($("pickerVoltageStep").value);
  if (!Number.isFinite(start) || !Number.isFinite(step) || step === 0) {
    meta.textContent = "Voltage start/step needed.";
    drawEmptyDataPickerPreview(ctx, cssWidth, cssHeight, "Set voltage start and step");
    return;
  }

  const points = values
    .map((current, index) => ({
      x: start + index * step,
      y: Math.log10(Math.max(Math.abs(current), 1e-30)),
    }))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (points.length < 2) {
    meta.textContent = "Selection has no drawable values.";
    drawEmptyDataPickerPreview(ctx, cssWidth, cssHeight, "No drawable preview");
    return;
  }

  const maxPreviewPoints = 420;
  const stride = Math.max(1, Math.ceil(points.length / maxPreviewPoints));
  const sampled = points.filter((_, index) => index % stride === 0 || index === points.length - 1);
  const minX = Math.min(...sampled.map((point) => point.x));
  const maxX = Math.max(...sampled.map((point) => point.x));
  const minY = Math.min(...sampled.map((point) => point.y));
  const maxY = Math.max(...sampled.map((point) => point.y));
  const spanX = Math.max(maxX - minX, 1e-12);
  const spanY = Math.max(maxY - minY, 1e-12);
  const pad = { left: 28, right: 16, top: 17, bottom: 12 };
  const plotWidth = cssWidth - pad.left - pad.right;
  const plotHeight = cssHeight - pad.top - pad.bottom;
  const xFor = (value) => pad.left + ((value - minX) / spanX) * plotWidth;
  const yFor = (value) => pad.top + plotHeight - ((value - minY) / spanY) * plotHeight;

  ctx.clearRect(0, 0, cssWidth, cssHeight);
  ctx.strokeStyle = "rgba(217, 231, 241, 0.055)";
  ctx.lineWidth = 0.75;
  for (let i = 1; i <= 2; i += 1) {
    const x = pad.left + (plotWidth * i) / 3;
    const y = pad.top + (plotHeight * i) / 3;
    ctx.beginPath();
    ctx.moveTo(x, pad.top);
    ctx.lineTo(x, pad.top + plotHeight);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotWidth, y);
    ctx.stroke();
  }

  const gradient = ctx.createLinearGradient(pad.left, 0, pad.left + plotWidth, 0);
  gradient.addColorStop(0, "#74eee3");
  gradient.addColorStop(0.56, "#9ff7c8");
  gradient.addColorStop(1, "#7fd6ff");
  ctx.beginPath();
  sampled.forEach((point, index) => {
    const x = xFor(point.x);
    const y = yFor(point.y);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = gradient;
  ctx.lineWidth = 2.2;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.shadowColor = "rgba(120, 242, 229, 0.34)";
  ctx.shadowBlur = 10;
  ctx.stroke();
  ctx.shadowBlur = 0;

  meta.textContent = `${values.length} points`;
}

function paintGridSelection() {
  const gridElement = $("dataGrid");
  const selection = state.gridSelection || selectionFromCurrentFields();
  gridElement
    .querySelectorAll(".current-column, .current-selection, .selected-column, .selected-row, .selection-start, .selection-end, .selection-single")
    .forEach((cell) => {
      cell.classList.remove(
        "current-column",
        "current-selection",
        "selected-column",
        "selected-row",
        "selection-start",
        "selection-end",
        "selection-single"
      );
    });
  if (!selection) {
    updateDataPickerReadout();
    return;
  }
  for (let row = selection.startRow; row <= selection.endRow; row += 1) {
    const selectedCell = gridElement.querySelector(`td[data-row="${row}"][data-col="${selection.colIndex}"]`);
    if (selectedCell) {
      selectedCell.classList.add("current-selection");
      if (selection.startRow === selection.endRow) selectedCell.classList.add("selection-single");
      else if (row === selection.startRow) selectedCell.classList.add("selection-start");
      else if (row === selection.endRow) selectedCell.classList.add("selection-end");
    }
  }
  updateDataPickerReadout();
}

function setCurrentSelection(colIndex, startRow, endRow) {
  const low = Math.min(startRow, endRow);
  const high = Math.max(startRow, endRow);
  state.gridSelection = { colIndex, startRow: low, endRow: high };
  $("currentColumn").value = indexToExcelColumn(colIndex);
  $("currentStartRow").value = String(low);
  $("currentEndRow").value = String(high);
  const inferredVoltage = applyInferredVoltageForCurrent(state.gridSelection);
  if (!inferredVoltage) syncGeneratedVoltageEnd();
  updateColumnSuggestions();
  paintGridSelection();
  state.fixedMeasured = null;
  state.plotScale = null;
}

function clearCurrentSelection() {
  state.gridSelection = null;
  $("dataGrid").classList.remove("is-selecting");
  state.gridClickAnchor = null;
  $("currentColumn").value = "";
  $("currentStartRow").value = "";
  $("currentEndRow").value = "";
  updateColumnSuggestions();
  paintGridSelection();
}

function setGeneratedVoltagePreset(start = defaultVoltageWindow.start, step = defaultVoltageWindow.step) {
  $("voltageMode").value = "generated";
  $("voltageStart").value = String(start);
  $("voltageStep").value = String(step);
  $("pickerVoltageStart").value = String(start);
  $("pickerVoltageStep").value = String(step);
  state.userVoltageOverride = true;
  refreshVoltageModeUi();
  syncGeneratedVoltageEnd();
  drawDataPickerPreview();
  syncRunDataSummary();
}

function setDataPickerPresetActive(preset = "") {
  $("dataCoreRangeBtn")?.classList.toggle("active", preset === "core");
  $("dataFullRangeBtn")?.classList.toggle("active", preset === "full");
  $("dataCoreRangeBtn")?.setAttribute("aria-selected", preset === "core" ? "true" : "false");
  $("dataFullRangeBtn")?.setAttribute("aria-selected", preset === "full" ? "true" : "false");
  const control = document.querySelector("#dataPickerOverlay .data-range-tabs");
  if (control) {
    control.dataset.activeRange = preset || "";
    if (preset) requestAnimationFrame(() => syncRangeTabIndicator(control, preset));
  }
}

function syncDataPickerPresetFromVoltage() {
  const start = Number($("pickerVoltageStart")?.value);
  if (Number.isFinite(start) && Math.abs(start + 0.5) < 1e-9) {
    setDataPickerPresetActive("core");
  } else if (Number.isFinite(start) && Math.abs(start + 1) < 1e-9) {
    setDataPickerPresetActive("full");
  } else {
    setDataPickerPresetActive("");
  }
}

function setDataPickerCoreRange() {
  const step = Number($("pickerVoltageStep")?.value || $("voltageStep")?.value || defaultVoltageWindow.step);
  setGeneratedVoltagePreset(-0.5, Number.isFinite(step) && step !== 0 ? step : defaultVoltageWindow.step);
  setDataPickerPresetActive("core");
  pulseControl("dataCoreRangeBtn");
}

function setDataPickerFullRange() {
  const step = Number($("pickerVoltageStep")?.value || $("voltageStep")?.value || defaultVoltageWindow.step);
  setGeneratedVoltagePreset(-1, Number.isFinite(step) && step !== 0 ? step : defaultVoltageWindow.step);
  setDataPickerPresetActive("full");
  pulseControl("dataFullRangeBtn");
}

function cellDisplayValue(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    const abs = Math.abs(value);
    if (abs > 0 && (abs < 1e-4 || abs >= 1e6)) return value.toExponential(3);
    return String(Number(value.toPrecision(8)));
  }
  return String(value);
}

function gridCellClass(rowNumber, colIndex, selection) {
  const classes = [];
  if (
    selection &&
    selection.colIndex === colIndex &&
    rowNumber >= selection.startRow &&
    rowNumber <= selection.endRow
  ) {
    classes.push("current-selection");
    if (selection.startRow === selection.endRow) classes.push("selection-single");
    else if (rowNumber === selection.startRow) classes.push("selection-start");
    else if (rowNumber === selection.endRow) classes.push("selection-end");
  }
  return classes.length ? ` class="${classes.join(" ")}"` : "";
}

function renderDataGrid() {
  const grid = state.dataGrid;
  if (!grid || !grid.rows || !grid.rows.length) {
    $("dataGrid").innerHTML = '<div class="preview-empty">No workbook grid loaded.</div>';
    updateDataPickerReadout();
    return;
  }

  const rows = grid.rows;
  const rowOffset = Number(grid.row_offset || 0);
  const colOffset = Number(grid.col_offset || 0);
  const shape = grid.shape || [rows.length, Math.max(...rows.map((row) => row.length))];
  const loadedCols = Math.max(...rows.map((row) => row.length), 0);
  const selection = state.gridSelection || selectionFromCurrentFields();
  state.gridSelection = selection;

  const headers = Array.from({ length: loadedCols }, (_, index) => {
    const colIndex = colOffset + index;
    return `<th class="grid-col-header" data-col="${colIndex}">${indexToExcelColumn(colIndex)}</th>`;
  }).join("");

  const body = rows.map((row, rowIndex) => {
    const rowNumber = rowOffset + rowIndex + 1;
    const cells = Array.from({ length: loadedCols }, (_, index) => {
      const colIndex = colOffset + index;
      const value = escapeHtml(cellDisplayValue(row[index]));
      const className = gridCellClass(rowNumber, colIndex, selection);
      return `<td${className} data-row="${rowNumber}" data-col="${colIndex}" title="${value}">${value}</td>`;
    }).join("");
    return `<tr><th data-row="${rowNumber}">${rowNumber}</th>${cells}</tr>`;
  }).join("");

  const firstRow = rowOffset + 1;
  const lastRow = rowOffset + rows.length;
  const capped = shape[0] > rows.length || shape[1] > loadedCols || rowOffset > 0
    ? `<span class="grid-cap-note">Showing rows ${firstRow}-${lastRow} of ${shape[0]} and ${loadedCols} of ${shape[1]} columns.</span>`
    : "";
  $("dataGrid").innerHTML = `
    ${capped}
    <div class="data-grid-scroll">
      <table class="data-grid-table">
        <thead><tr><th class="grid-corner"></th>${headers}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
  updateDataPickerReadout();
}

async function loadDataGrid() {
  if (!state.uploadId) return;
  const params = new URLSearchParams({
    upload_id: state.uploadId,
    sheet_name: $("sheetSelect").value,
    row_offset: "0",
    col_offset: "0",
    row_count: String(DATA_GRID_ROW_COUNT),
    col_count: String(DATA_GRID_COL_COUNT),
  });
  const payload = await getJson(`/api/grid?${params.toString()}`);
  state.dataGrid = payload.grid;
  const shape = state.dataGrid.shape || ["?", "?"];
  $("dataPickerMeta").textContent = `${state.selectedFileName || "Workbook"} | ${shape[0]} rows x ${shape[1]} cols`;
  renderDataGrid();
}

function openDataPicker() {
  $("pickerVoltageStart").value = $("voltageStart").value || String(defaultVoltageWindow.start);
  $("pickerVoltageStep").value = $("voltageStep").value || String(defaultVoltageWindow.step);
  syncDataPickerPresetFromVoltage();
  state.gridSelection = selectionFromCurrentFields();
  renderDataGrid();
  setDataPickerVisible(true);
  requestAnimationFrame(drawDataPickerPreview);
}

function applyDataPickerSelection() {
  const selection = state.gridSelection || selectionFromCurrentFields();
  if (!selection) {
    throw new Error("Select a current range from the grid before applying.");
  }
  const start = Number($("pickerVoltageStart").value);
  const step = Number($("pickerVoltageStep").value);
  if (!Number.isFinite(start) || !Number.isFinite(step) || step === 0) {
    throw new Error("Voltage start and step must be numeric, and step cannot be zero.");
  }
  $("voltageMode").value = "generated";
  $("voltageStart").value = String(start);
  $("voltageStep").value = String(step);
  refreshVoltageModeUi();
  syncGeneratedVoltageEnd();
  state.flowReturnStep = null;
  showModelPage();
}

function gridCellFromEvent(event) {
  const target = event.target && event.target.closest ? event.target : document.elementFromPoint(event.clientX, event.clientY);
  const cell = target?.closest?.("td[data-row][data-col]");
  if (!cell || !$("dataGrid").contains(cell)) return null;
  return {
    row: Number(cell.dataset.row),
    col: Number(cell.dataset.col),
  };
}

function gridCellFromPoint(event) {
  const element = document.elementFromPoint(event.clientX, event.clientY);
  const cell = element?.closest?.("td[data-row][data-col]");
  if (!cell || !$("dataGrid").contains(cell)) return null;
  return {
    row: Number(cell.dataset.row),
    col: Number(cell.dataset.col),
  };
}

function startGridSelection(event) {
  const cell = gridCellFromEvent(event);
  if (!cell) return;
  if (event.button !== undefined && event.button !== 0) return;
  event.preventDefault();
  state.gridDragging = true;
  state.gridDragAnchor = cell;
  state.gridDragMoved = false;
  state.gridSuppressClick = false;
  $("dataGrid").classList.add("is-selecting");
  setCurrentSelection(cell.col, cell.row, cell.row);
}

function extendGridSelection(event) {
  if (!state.gridDragging || !state.gridDragAnchor) return;
  const cell = gridCellFromPoint(event) || gridCellFromEvent(event);
  if (!cell) return;
  if (cell.row !== state.gridDragAnchor.row || cell.col !== state.gridDragAnchor.col) {
    state.gridDragMoved = true;
  }
  setCurrentSelection(state.gridDragAnchor.col, state.gridDragAnchor.row, cell.row);
}

function finishGridSelection() {
  state.gridSuppressClick = Boolean(state.gridDragging && state.gridDragMoved);
  state.gridDragging = false;
  state.gridDragAnchor = null;
  state.gridDragMoved = false;
  $("dataGrid").classList.remove("is-selecting");
  if (state.gridSuppressClick) {
    window.setTimeout(() => {
      state.gridSuppressClick = false;
    }, 80);
  }
}

function clickGridSelection(event) {
  const cell = gridCellFromEvent(event);
  if (!cell) return;
  if (state.gridSuppressClick) {
    state.gridSuppressClick = false;
    return;
  }
  const anchor = state.gridClickAnchor;
  if (anchor && anchor.col === cell.col && anchor.row !== cell.row) {
    setCurrentSelection(cell.col, anchor.row, cell.row);
    state.gridClickAnchor = null;
    return;
  }
  setCurrentSelection(cell.col, cell.row, cell.row);
  state.gridClickAnchor = cell;
}

function renderFileInfo(fileInfo) {
  const shape = fileInfo.shape || ["?", "?"];
  $("fileMeta").textContent = `${fileInfo.suffix.toUpperCase()} | ${shape[0]} rows x ${shape[1]} cols`;
  if (!state.selectedFileName) {
    const parts = String(fileInfo.path || "").split(/[\\/]/);
    state.selectedFileName = parts[parts.length - 1] || "Selected file";
  }
  updateFileSelectionUi();
  const select = $("sheetSelect");
  select.innerHTML = '<option value="">First sheet</option>';
  for (const sheet of fileInfo.sheets || []) {
    const opt = document.createElement("option");
    opt.value = sheet;
    opt.textContent = sheet;
    if (sheet === fileInfo.selected_sheet) opt.selected = true;
    select.appendChild(opt);
  }
  renderPreview(fileInfo.preview);
}

async function inspectSelectedFile() {
  const file = $("fileInput").files[0];
  if (!file && !state.uploadId) {
    throw new Error("Choose a data file first.");
  }
  const fd = new FormData();
  if (state.uploadId) {
    fd.append("upload_id", state.uploadId);
  } else if (file) {
    state.selectedFileName = file.name;
    fd.append("file", file);
  }
  fd.append("sheet_name", $("sheetSelect").value);
  setStatus("Inspecting data file...");
  setLoading(true, "Inspecting data...", "Reading workbook structure and preview rows.");
  try {
    const payload = await postForm("/api/inspect", fd);
    state.uploadId = payload.upload_id;
    renderFileInfo(payload.file);
    await loadDataGrid();
    openDataPicker();
    setStatus("File inspected. Select the current range from the grid.");
  } finally {
    setLoading(false);
  }
}

function resetDataFileSession(file) {
  state.uploadId = null;
  state.selectedFileName = file?.name || "";
  clearFitResultState();
  state.fixedMeasured = null;
  state.plotScale = null;
  state.dataGrid = null;
  state.gridSelection = null;
  state.userVoltageOverride = false;
  state.txtImport = null;
  state.txtSelectedBlockIds = new Set();
  state.manualHistory = [];
  state.manualHistoryActiveId = null;
  state.assistantMessages = [];
  cancelPendingLiveEvaluation();
  cancelPendingManualEvaluation();
  renderAssistantMessages();
  updateFileSelectionUi();
  $("fileMeta").textContent = "Inspecting selected file...";
  $("recordStatus").textContent = "No record saved.";
  toggleRecordForm(false);
}

async function handleDataFileSelection() {
  resetDataFileSession($("fileInput").files[0]);
  try {
    if (state.selectedFileName) {
      await inspectSelectedFile();
    }
  } catch (error) {
    showError(error);
  }
}

function handleDataRangeInput(id) {
  state.fixedMeasured = null;
  state.plotScale = null;
  if (id.startsWith("voltage")) {
    state.userVoltageOverride = true;
  }
  if (id.startsWith("current")) {
    state.gridSelection = selectionFromCurrentFields();
    const inferredVoltage = applyInferredVoltageForCurrent(state.gridSelection);
    if (!inferredVoltage) syncGeneratedVoltageEnd();
    updateDataPickerReadout();
    renderDataGrid();
  }
  if (id === "voltageStart" || id === "voltageStep") {
    syncGeneratedVoltageEnd();
    drawDataPickerPreview();
  }
}
