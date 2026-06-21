/* ==========================================================================
   TXT import workflow
   ========================================================================== */

async function importTxtFile(file) {
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  setStatus("Parsing txt file...");
  setLoading(true, "Parsing TXT...", "Detecting blocks, columns, and parser diagnostics.");
  try {
    const payload = await postForm("/api/txt-import/parse", fd);
    state.txtImport = {
      uploadId: payload.upload_id,
      fileName: file.name,
      txt: payload.txt,
    };
    state.txtSelectedBlockIds = new Set();
    const firstOk = (payload.txt.blocks || []).find((block) => block.status === "ok");
    if (firstOk) state.txtSelectedBlockIds.add(firstOk.id);
    state.uploadId = null;
    clearFitResultState();
    state.fixedMeasured = null;
    state.plotScale = null;
    state.dataGrid = null;
    state.gridSelection = null;
    state.txtFitRangeBlockId = null;
    state.txtFitRangeTouched = false;
    renderTxtImport();
    showTxtImportPage();
    setStatus(`TXT parsed: ${payload.txt.ok_blocks || 0} usable block(s).`);
  } finally {
    setLoading(false);
  }
}

function txtBlocks() {
  return state.txtImport?.txt?.blocks || [];
}

function selectedTxtBlocks(options = {}) {
  const requireOk = options.requireOk !== false;
  return txtBlocks().filter((block) => state.txtSelectedBlockIds.has(block.id) && (!requireOk || block.status === "ok"));
}

function txtBlockVoltageBounds(block) {
  const values = (block?.series?.voltage || []).map(Number).filter(Number.isFinite);
  if (!values.length) return null;
  return { min: Math.min(...values), max: Math.max(...values) };
}

function formatTxtRangeInputValue(value) {
  if (!Number.isFinite(Number(value))) return "";
  return String(Number(Number(value).toPrecision(9)));
}

function txtDefaultFitRangeForBlock(block, options = {}) {
  const bounds = txtBlockVoltageBounds(block);
  if (!bounds) return null;
  if (options.full) return bounds;
  const min = Math.max(bounds.min, defaultVoltageWindow.start);
  const max = Math.min(bounds.max, defaultVoltageWindow.end);
  if (min < max) return { min, max };
  return bounds;
}

function setTxtFitRangeInputs(block, options = {}) {
  const bounds = txtDefaultFitRangeForBlock(block, options);
  const minInput = $("txtFitVoltageMin");
  const maxInput = $("txtFitVoltageMax");
  if (!minInput || !maxInput) return;
  minInput.value = bounds ? formatTxtRangeInputValue(bounds.min) : "";
  maxInput.value = bounds ? formatTxtRangeInputValue(bounds.max) : "";
}

function setTxtFitRangePresetActive(preset = "") {
  $("txtFitCoreRangeBtn")?.classList.toggle("active", preset === "core");
  $("txtFitFullRangeBtn")?.classList.toggle("active", preset === "full");
  const control = document.querySelector(".txt-preview-actions");
  if (control) {
    control.dataset.activeRange = preset || "";
    if (preset) requestAnimationFrame(() => syncRangeTabIndicator(control, preset));
  }
}

function syncTxtFitRangeToSelection(options = {}) {
  const blocks = selectedTxtBlocks();
  const minInput = $("txtFitVoltageMin");
  const maxInput = $("txtFitVoltageMax");
  const coreButton = $("txtFitCoreRangeBtn");
  const fullButton = $("txtFitFullRangeBtn");
  if (!minInput || !maxInput) return;

  const disabled = blocks.length !== 1;
  minInput.disabled = disabled;
  maxInput.disabled = disabled;
  if (coreButton) coreButton.disabled = disabled;
  if (fullButton) fullButton.disabled = disabled;
  if (disabled) {
    minInput.value = "";
    maxInput.value = "";
    state.txtFitRangeBlockId = null;
    state.txtFitRangeTouched = false;
    setTxtFitRangePresetActive("");
    return;
  }

  const block = blocks[0];
  const changedBlock = state.txtFitRangeBlockId !== block.id;
  if (options.force || changedBlock || !state.txtFitRangeTouched) {
    setTxtFitRangeInputs(block);
    state.txtFitRangeTouched = false;
    setTxtFitRangePresetActive("core");
  }
  state.txtFitRangeBlockId = block.id;
}

function parseTxtFitVoltageInput(id, label, options = {}) {
  const raw = ($(id)?.value || "").trim();
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    if (options.strict) throw new Error(`${label} must be a finite voltage value.`);
    return null;
  }
  return value;
}

function currentTxtFitVoltageRange(block, options = {}) {
  const minValue = parseTxtFitVoltageInput("txtFitVoltageMin", "Minimum fit voltage", options);
  const maxValue = parseTxtFitVoltageInput("txtFitVoltageMax", "Maximum fit voltage", options);
  if (minValue === null && maxValue === null) return null;
  const requestedLower = Math.min(
    minValue === null ? maxValue : minValue,
    maxValue === null ? minValue : maxValue,
  );
  const requestedUpper = Math.max(
    minValue === null ? maxValue : minValue,
    maxValue === null ? minValue : maxValue,
  );
  const bounds = txtBlockVoltageBounds(block);
  const lower = minValue === null ? bounds?.min : requestedLower;
  const upper = maxValue === null ? bounds?.max : requestedUpper;
  const voltage = (block?.series?.voltage || []).map(Number);
  const selectedCount = voltage.filter((value) => {
    if (!Number.isFinite(value)) return false;
    if (minValue !== null && maxValue !== null) return value >= requestedLower && value <= requestedUpper;
    if (minValue !== null) return value >= minValue;
    return value <= maxValue;
  }).length;
  const label = minValue === null
    ? `<= ${formatSci(maxValue)} V`
    : maxValue === null
      ? `>= ${formatSci(minValue)} V`
      : `${formatSci(requestedLower)} to ${formatSci(requestedUpper)} V`;
  return {
    voltage_min: minValue === null ? null : (maxValue === null ? minValue : requestedLower),
    voltage_max: maxValue === null ? null : (minValue === null ? maxValue : requestedUpper),
    lower,
    upper,
    selectedCount,
    label,
  };
}

function formatRange(range) {
  if (!range || range.length !== 2) return "--";
  return `${formatSci(range[0])} to ${formatSci(range[1])}`;
}

function formatTxtLambda(value) {
  if (value === null || value === undefined || value === "") return "--";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? String(Math.round(numeric)) : String(value);
}

function isDarkTxtBlock(block) {
  return /\bdark\b/i.test([block?.mode, block?.name, block?.id].filter(Boolean).join(" "));
}

function isLightTxtBlock(block) {
  return /\b(light|illum|photo)\b/i.test([block?.mode, block?.name, block?.id].filter(Boolean).join(" "));
}

function txtCurrentAtVoltage(block, targetVoltage = -0.5) {
  const voltage = (block?.series?.voltage || []).map(Number);
  const current = (block?.series?.y || []).map(Number);
  const epsilon = Math.max(1e-9, Math.abs(targetVoltage) * 1e-9);
  let previous = null;

  for (let index = 0; index < voltage.length; index += 1) {
    const v = voltage[index];
    const j = current[index];
    if (!Number.isFinite(v) || !Number.isFinite(j)) continue;
    if (Math.abs(v - targetVoltage) <= epsilon) return j;

    if (previous && (previous.v - targetVoltage) * (v - targetVoltage) < 0 && v !== previous.v) {
      const ratio = (targetVoltage - previous.v) / (v - previous.v);
      return previous.j + ratio * (j - previous.j);
    }
    previous = { v, j };
  }
  return null;
}

function txtOpenCircuitVoltage(block) {
  const voltage = (block?.series?.voltage || []).map(Number);
  const current = (block?.series?.y || []).map(Number);
  let previous = null;

  for (let index = 0; index < voltage.length; index += 1) {
    const v = voltage[index];
    const j = current[index];
    if (!Number.isFinite(v) || !Number.isFinite(j)) continue;
    if (j === 0) return v;

    if (previous && previous.j * j < 0 && j !== previous.j) {
      const ratio = -previous.j / (j - previous.j);
      return previous.v + ratio * (v - previous.v);
    }
    previous = { v, j };
  }
  return null;
}

function formatTxtOpenCircuitVoltage(block) {
  const value = txtOpenCircuitVoltage(block);
  if (!Number.isFinite(value)) return "--";
  return `${Number(value.toPrecision(4))} V`;
}

function formatTxtCurrentAtVoltage(block, targetVoltage = -0.5) {
  const value = txtCurrentAtVoltage(block, targetVoltage);
  if (!Number.isFinite(value)) return "--";
  const nanoamps = value * 1e9;
  const abs = Math.abs(nanoamps);
  if (abs > 0 && (abs < 0.01 || abs >= 10000)) return `${nanoamps.toExponential(2)} nA`;
  return `${Number(nanoamps.toPrecision(3))} nA`;
}

function txtBlockSubtitle(block) {
  const parts = [
    block.mode || "unknown",
    block.lambda_nm === null || block.lambda_nm === undefined ? null : `${formatTxtLambda(block.lambda_nm)} nm`,
  ].filter(Boolean);
  return parts.join(" | ");
}

function renderTxtImport() {
  const parsed = state.txtImport?.txt;
  if (!parsed) return;
  $("txtImportMeta").textContent = `${state.txtImport.fileName || parsed.filename || "TXT"} | ${parsed.format} | ${parsed.ok_blocks || 0}/${parsed.total_blocks || 0} usable`;
  $("txtBlockCount").textContent = `${parsed.total_blocks || 0} parsed`;
  syncTxtFitRangeToSelection();
  syncTxtScaleButtons();
  renderTxtBlockList();
  renderTxtDiagnostics();
  drawTxtPreview();
}

function renderTxtBlockList() {
  const blocks = txtBlocks();
  if (!blocks.length) {
    $("txtBlockList").innerHTML = '<div class="preview-empty">No txt blocks parsed.</div>';
    return;
  }
  $("txtBlockList").innerHTML = blocks.map((block) => {
    const checked = state.txtSelectedBlockIds.has(block.id) ? "checked" : "";
    const disabled = block.status === "ok" ? "" : "disabled";
    const selected = checked ? " is-selected" : "";
    const hasError = block.status === "ok" ? "" : " has-error";
    const warningCount = (block.diagnostics || []).filter((item) => item.level !== "info").length;
    const warning = warningCount ? `<div class="txt-block-warning">${warningCount} diagnostic item(s)</div>` : "";
    const lambdaText = block.lambda_nm === null || block.lambda_nm === undefined
      ? "-- nm"
      : `${formatTxtLambda(block.lambda_nm)} nm`;
    const modeText = block.mode || block.status || "unknown";
    const blockMetric = isDarkTxtBlock(block)
      ? `<div class="txt-block-current">@-0.5V ${escapeHtml(formatTxtCurrentAtVoltage(block, -0.5))}</div>`
      : isLightTxtBlock(block)
        ? `<div class="txt-block-current">Voc ${escapeHtml(formatTxtOpenCircuitVoltage(block))}</div>`
        : `<div class="txt-block-current">${escapeHtml(block.status || "unknown")}</div>`;
    return `
      <label class="txt-block-row${selected}${hasError}" data-txt-row="${escapeHtml(block.id)}">
        <input data-txt-block="${escapeHtml(block.id)}" type="checkbox" ${checked} ${disabled} />
        <div class="txt-block-main">
          <div class="txt-block-title">
            <strong>${escapeHtml(block.name || block.id)}</strong>
            <span class="txt-block-lambda">${escapeHtml(lambdaText)}</span>
            <span class="txt-block-mode">${escapeHtml(modeText)}</span>
          </div>
          <div class="txt-block-meta">
            <span>V ${escapeHtml(formatRange(block.voltage_range))}</span>
            <span>${block.point_count || 0} pts</span>
          </div>
          <div class="txt-block-ranges">
            ${blockMetric}
          </div>
          ${warning}
        </div>
      </label>
    `;
  }).join("");
}

function renderTxtDiagnostics() {
  const parsed = state.txtImport?.txt;
  if (!parsed) return;
  const items = [...(parsed.diagnostics || [])];
  for (const block of txtBlocks()) {
    const blockItems = (block.diagnostics || []).filter((item) => item.level !== "info");
    for (const item of blockItems) {
      items.push({
        ...item,
        message: `${block.name || block.id}: ${item.message || "Parser diagnostic"}`,
        excerpt: item.excerpt || block.raw_excerpt || "",
      });
    }
  }
  if (!items.length) {
    $("txtDiagnosticsList").innerHTML = '<div class="preview-empty">No diagnostics yet.</div>';
    return;
  }
  $("txtDiagnosticsList").innerHTML = items.slice(0, 80).map((item) => {
    const level = item.level || "info";
    const line = item.line ? ` line ${item.line}` : "";
    const samples = item.samples
      ? `<pre>${escapeHtml(JSON.stringify(item.samples, null, 2))}</pre>`
      : "";
    const excerpt = item.excerpt ? `<pre>${escapeHtml(item.excerpt)}</pre>` : "";
    return `
      <div class="txt-diagnostic-item ${escapeHtml(level)}">
        <strong>${escapeHtml(level.toUpperCase())}${escapeHtml(line)}</strong>
        <span>${escapeHtml(item.message || "")}</span>
        ${samples || excerpt}
      </div>
    `;
  }).join("");
}

function updateTxtSelectionFromInputs() {
  const next = new Set();
  document.querySelectorAll("[data-txt-block]").forEach((input) => {
    if (input.checked && !input.disabled) next.add(input.dataset.txtBlock);
  });
  state.txtSelectedBlockIds = next;
  syncTxtFitRangeToSelection({ force: true });
  renderTxtBlockList();
  renderTxtDiagnostics();
  drawTxtPreview();
}

function txtTransformFactory(blocks) {
  const allY = blocks.flatMap((block) => block.series?.y || []).filter(Number.isFinite);
  const positives = allY.map((value) => Math.abs(value)).filter((value) => value > 0);
  const maxAbs = positives.length ? Math.max(...positives) : 1;
  const minPositive = positives.length ? Math.min(...positives) : 1e-12;
  const linthresh = Math.max(minPositive, maxAbs * 1e-4, 1e-14);
  if (state.txtScale === "log_abs") {
    const floor = Math.max(minPositive * 0.2, 1e-30);
    return {
      label: "log abs current",
      y: (value) => Math.log10(Math.max(Math.abs(value), floor)),
      tick: (value) => `1e${Math.round(value)}`,
    };
  }
  if (state.txtScale === "symlog") {
    return {
      label: "signed log current",
      y: (value) => Math.sign(value) * Math.log10(1 + Math.abs(value) / linthresh),
      tick: (value) => formatSci(Math.sign(value) * linthresh * (10 ** Math.abs(value) - 1)),
    };
  }
  return {
    label: "current",
    y: (value) => value,
    tick: (value) => formatSci(value),
  };
}

function drawTxtPreview() {
  const canvas = $("txtPreviewCanvas");
  if (!canvas || $("txtImportPage").classList.contains("hidden")) return;
  const prepared = prepareCanvas(canvas);
  if (!prepared) return;
  const { ctx, width, height } = prepared;
  const previousChartColors = {
    grid: colors.grid,
    fineGrid: colors.fineGrid,
    text: colors.text,
    muted: colors.muted,
  };
  Object.assign(colors, {
    grid: "rgba(148, 163, 184, 0.12)",
    fineGrid: "rgba(148, 163, 184, 0.04)",
    text: "#f2fbff",
    muted: "rgba(217, 231, 241, 0.58)",
  });
  try {
  const blocks = selectedTxtBlocks();
  if (!blocks.length) {
    ctx.fillStyle = colors.muted;
    ctx.font = typeof chartFont === "function" ? chartFont(13, 430) : "430 13px Inter, Microsoft YaHei, PingFang SC, Arial, sans-serif";
    ctx.fillText("Select one or more usable blocks to preview.", 24, 34);
    return;
  }

  const transform = txtTransformFactory(blocks);
  const series = blocks.map((block) => {
    const voltage = (block.series?.voltage || []).map(Number);
    const y = (block.series?.y || []).map(Number);
    return { block, voltage, y, ty: y.map(transform.y) };
  });
  const allX = series.flatMap((item) => item.voltage).filter(Number.isFinite);
  const allY = series.flatMap((item) => item.ty).filter(Number.isFinite);
  if (!allX.length || !allY.length) return;

  let minX = Math.min(...allX);
  let maxX = Math.max(...allX);
  let minY = Math.min(...allY);
  let maxY = Math.max(...allY);
  if (minX === maxX) {
    minX -= 0.5;
    maxX += 0.5;
  }
  if (minY === maxY) {
    const pad = Math.abs(minY || 1) * 0.08;
    minY -= pad;
    maxY += pad;
  } else {
    const pad = (maxY - minY) * 0.08;
    minY -= pad;
    maxY += pad;
  }

  const denseYAxis = state.txtScale === "linear" || state.txtScale === "symlog";
  const leftAxis = denseYAxis ? 112 : 84;
  const rightPad = 36;
  const box = { left: leftAxis, top: 42, width: width - leftAxis - rightPad, height: height - 116 };
  const scale = {
    x: (x) => box.left + ((x - minX) / (maxX - minX)) * box.width,
    y: (y) => box.top + (1 - ((y - minY) / (maxY - minY))) * box.height,
  };
  drawAxes(ctx, box, {
    x: "Voltage (V)",
    y: transform.label,
    title: "TXT JV preview",
    yOffset: denseYAxis ? 88 : 52,
  });
  drawXTicks(ctx, box, minX, maxX, 3);
  drawLinearYTicks(ctx, box, minY, maxY, denseYAxis ? 3 : 4, transform.tick);

  const fitRange = blocks.length === 1 ? currentTxtFitVoltageRange(blocks[0]) : null;
  if (fitRange && Number.isFinite(fitRange.lower) && Number.isFinite(fitRange.upper)) {
    const left = Math.max(box.left, Math.min(box.left + box.width, scale.x(fitRange.lower)));
    const right = Math.max(box.left, Math.min(box.left + box.width, scale.x(fitRange.upper)));
    ctx.fillStyle = "rgba(37, 99, 235, 0.08)";
    ctx.fillRect(Math.min(left, right), box.top, Math.abs(right - left), box.height);
  }

  const palette = ["#74eee3", "#9ff7c8", "#7fd6ff", "#f5b44c", "#c7a8ff", "#fb6a4a", "#90ba48", "#df42e3"];
  withClip(ctx, box, () => {
    series.forEach((item, index) => {
      drawLinearLine(ctx, item.voltage, item.ty, scale, palette[index % palette.length], {
        lineWidth: blocks.length > 12 ? 1.1 : 1.7,
      });
    });
  });
  const rangeText = fitRange ? ` | fit V ${fitRange.label} | ${fitRange.selectedCount} pts` : "";
  } finally {
    Object.assign(colors, previousChartColors);
  }
}

async function activateSelectedTxtBlock() {
  const blocks = selectedTxtBlocks();
  if (blocks.length !== 1) {
    throw new Error("Select exactly one usable txt block before sending it to the fit workflow.");
  }
  const block = blocks[0];
  const fitRange = currentTxtFitVoltageRange(block, { strict: true });
  setLoading(true, "Preparing block...", "Converting the selected txt block into the existing CSV import flow.");
  try {
    const payload = await postJson("/api/txt-import/activate", {
      upload_id: state.txtImport?.uploadId,
      block_id: block.id,
      voltage_min: fitRange?.voltage_min ?? null,
      voltage_max: fitRange?.voltage_max ?? null,
    });
    const activatedBlock = payload.block || block;
    state.uploadId = payload.upload_id;
    state.selectedFileName = `${block.name || block.id}.csv`;
    clearFitResultState();
    state.fixedMeasured = null;
    state.plotScale = null;
    state.dataGrid = null;
    state.manualHistory = [];
    state.manualHistoryActiveId = null;
    renderFileInfo(payload.file);
    applySelectionPayload(payload.selection || {
      voltage_range: `A1:A${block.point_count || 0}`,
      current_range: `B1:B${block.point_count || 0}`,
      cell_range: "",
      sheet_name: "",
    });
    refreshVoltageModeUi();
    updateColumnSuggestions();
    await loadDataGrid();
    const rangeText = activatedBlock.voltage_range ? ` | V ${formatRange(activatedBlock.voltage_range)}` : "";
    const pointText = activatedBlock.point_count ? ` | ${activatedBlock.point_count} pts` : "";
    setStatus(`TXT block ready: ${block.name || block.id}${rangeText}${pointText}.`);
    showModelPage();
  } finally {
    setLoading(false);
  }
}
