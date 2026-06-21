/* ==========================================================================
   Records, exports, and fitpack persistence
   ========================================================================== */

async function saveCurrentRecord() {
  validateRecordPayloadInputs();
  const payload = buildRecordPayload();
  setDisabledIfPresent("saveRecordBtn", true);
  setDisabledIfPresent("saveAcceptedRecordBtn", true);
  setStatus("Saving labeled fitting record...");
  try {
    const response = await postJson("/api/records", payload);
    $("recordStatus").textContent = response.record_path;
    $("savePageStatus").textContent = `Saved: ${response.record_path}`;
    toggleRecordForm(false);
    await refreshRecords();
    setStatus("Fitting record saved.");
  } finally {
    setDisabledIfPresent("saveRecordBtn", false);
    setDisabledIfPresent("saveAcceptedRecordBtn", false);
  }
}

function renderRecords(records) {
  $("recordsSummary").textContent = `${records.length} record(s) available.`;
  const recent = records.slice(0, 6);
  if (!recent.length) {
    $("recordsList").innerHTML = "";
    return;
  }
  $("recordsList").innerHTML = recent.map((record) => `
    <div class="record-item">
      <strong>${escapeHtml(record.sample_id || record.saved_at || record.record_id || "record")}</strong>
      <span>${escapeHtml(record.quality || "--")} | ${escapeHtml(record.hypothesis || "none")} | mean ${formatPct(record.mean_error)}</span>
      <span>${escapeHtml(record.fit_strategy || "--")} | m ${record.m ?? "--"} | ${escapeHtml(record.worst_region || "--")}</span>
      <span>${escapeHtml(record.sample_role || "unknown")} | ${escapeHtml(record.comparison_group || "--")}</span>
    </div>
  `).join("");
}

async function refreshRecords() {
  const payload = await getJson("/api/records");
  renderRecords(payload.records || []);
}

function filenameFromDisposition(disposition, fallback) {
  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(disposition || "");
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const match = /filename="?([^";]+)"?/i.exec(disposition || "");
  return match ? match[1] : fallback;
}

function safeDownloadStem(value, fallback) {
  return (String(value || fallback).replace(/[^A-Za-z0-9_.-]+/g, "_").replace(/^_+|_+$/g, "") || fallback);
}

function closeExportMenus() {
  document.querySelectorAll(".export-menu[open]").forEach((menu) => {
    menu.removeAttribute("open");
  });
}

function csvCell(value) {
  if (value === null || value === undefined || (typeof value === "number" && Number.isNaN(value))) return "";
  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function componentSeriesCsv(componentSeries) {
  const columns = componentSeries.columns || componentColumns;
  const data = componentSeries.data || {};
  const lines = [columns.map((column) => csvCell(column.label)).join(",")];
  for (let index = 0; index < componentSeries.point_count; index += 1) {
    lines.push(columns.map((column) => csvCell(data[column.key]?.[index])).join(","));
  }
  return lines.join("\r\n");
}

function exportComponentsCsv() {
  const componentSeries = componentSeriesPayload();
  const blob = new Blob([componentSeriesCsv(componentSeries)], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  const sample = $("saveSampleId")?.value.trim() || currentSampleContextPayload().sample_id || "fit-components";
  link.href = URL.createObjectURL(blob);
  link.download = `${safeDownloadStem(sample, "fit-components")}_components.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
  setStatus("Component CSV export started.");
}

async function postJsonBlob(url, payload, fallbackName) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let message = "Download failed.";
    try {
      const body = await response.json();
      message = body.detail || body.error || message;
    } catch {
      message = await response.text();
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  const link = document.createElement("a");
  const objectUrl = URL.createObjectURL(blob);
  link.href = objectUrl;
  link.download = filenameFromDisposition(response.headers.get("content-disposition"), fallbackName);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

async function exportComponentsXlsx() {
  const componentSeries = componentSeriesPayload();
  const sampleContext = currentSampleContextPayload();
  const sample = $("saveSampleId")?.value.trim() || sampleContext.sample_id || "fit-components";
  await postJsonBlob(
    "/api/export/components-xlsx",
    {
      component_series: componentSeries,
      sample_context: sampleContext,
      sample_name: sample,
    },
    `${safeDownloadStem(sample, "fit-components")}_components.xlsx`,
  );
  setStatus("Component XLSX export started.");
}

async function downloadBlob(url, fallbackName) {
  const response = await fetch(url);
  if (!response.ok) {
    let message = "Download failed.";
    try {
      const payload = await response.json();
      message = payload.detail || payload.error || message;
    } catch {
      message = await response.text();
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  const link = document.createElement("a");
  const objectUrl = URL.createObjectURL(blob);
  link.href = objectUrl;
  link.download = filenameFromDisposition(response.headers.get("content-disposition"), fallbackName);
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

async function exportDataPackage() {
  $("exportPackageBtn").disabled = true;
  setStatus("Building offline data package...");
  try {
    await downloadBlob("/api/records/package", "jv_fit_records.zip");
    $("recordsSummary").textContent = "Offline data package export started.";
    setStatus("Offline data package ready.");
  } finally {
    $("exportPackageBtn").disabled = false;
  }
}

function buildFitpackPayload() {
  const result = currentAcceptedResult();
  if (!result || !result.fit) {
    throw new Error("Run a fit before exporting a fitpack.");
  }
  let dataSelection = {};
  let analysisSettings = {};
  try {
    dataSelection = currentDataSelectionPayload();
    analysisSettings = currentAnalysisSettingsPayload();
  } catch {
    dataSelection = result.dataset || {};
  }
  return {
    type: "jv-fitpack",
    schema_version: 1,
    exported_at: new Date().toISOString(),
    data_selection: dataSelection,
    analysis_settings: analysisSettings,
    manual_history: manualHistoryPayload(),
    manual_checkpoints: clonePlain(state.manualHistory),
    auto_fit_baseline: clonePlain(state.autoFitResult || result),
    run_snapshot: clonePlain(result.run_snapshot || {}),
    record_context: {
      sample_context: currentSampleContextPayload(),
      labels: currentLabelPayload(),
      fit_delta: fitDeltaPayload(),
      training_summary: trainingSummaryPayload(),
    },
    result,
  };
}

function exportFitpack() {
  const payload = buildFitpackPayload();
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  const sample = currentSampleContextPayload().sample_id || "fit-session";
  link.href = URL.createObjectURL(blob);
  link.download = `${safeDownloadStem(sample, "fit-session")}.fitpack.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
  setStatus("Fitpack export started.");
}

function exportComponentsCsvFromMenu() {
  closeExportMenus();
  try {
    exportComponentsCsv();
  } catch (error) {
    showError(error);
  }
}

function exportComponentsXlsxFromMenu() {
  closeExportMenus();
  exportComponentsXlsx().catch(showError);
}

function exportFitpackFromMenu() {
  closeExportMenus();
  try {
    exportFitpack();
  } catch (error) {
    showError(error);
  }
}

function exportDataPackageFromMenu() {
  closeExportMenus();
  exportDataPackage().catch(showError);
}

function restoreSelectionFromFitpack(selection) {
  if (!selection) return;
  if (selection.current_range) {
    const match = /^([A-Za-z]+)(\d+):([A-Za-z]+)(\d+)$/.exec(selection.current_range);
    if (match && match[1].toUpperCase() === match[3].toUpperCase()) {
      $("currentColumn").value = match[1].toUpperCase();
      $("currentStartRow").value = match[2];
      $("currentEndRow").value = match[4];
    }
  }
  if (selection.voltage_start !== null && selection.voltage_start !== undefined) {
    $("voltageStart").value = String(selection.voltage_start);
  }
  if (selection.voltage_step !== null && selection.voltage_step !== undefined) {
    $("voltageStep").value = String(selection.voltage_step);
  }
  syncGeneratedVoltageEnd();
}

function restoreManualHistoryFromFitpack(payload) {
  const checkpoints = Array.isArray(payload.manual_checkpoints) ? payload.manual_checkpoints : [];
  if (!checkpoints.length && Array.isArray(payload.manual_history)) {
    state.manualHistory = payload.manual_history
      .filter((item) => item && item.params)
      .map((item, index) => ({
        ...item,
        id: `record_${Date.now()}_${index}`,
        created_at: item.created_at || "Imported",
        starred: Boolean(item.starred),
        result: null,
      }))
      .slice(0, 24);
    state.manualHistoryActiveId = null;
    return;
  }
  state.manualHistory = checkpoints
    .filter((item) => item && item.params && item.result?.fit)
    .map((item, index) => ({
      ...item,
      id: item.id || `fitpack_${Date.now()}_${index}`,
      created_at: item.created_at || "Imported",
      starred: Boolean(item.starred),
    }))
    .slice(0, 24);
  state.manualHistoryActiveId = state.manualHistory[0]?.id || null;
}

async function importFitpackFile(file) {
  if (!file) return;
  setStatus("Opening saved fit file...");
  const text = await file.text();
  const payload = JSON.parse(text);
  const isFitpack = payload.type === "jv-fitpack";
  if (!isFitpack) {
    throw new Error("Only .fitpack.json files can be reopened here. Training record JSON is for dataset collection and is not a restorable session file.");
  }
  if (!payload.result || !payload.result.fit) {
    throw new Error("This fitpack does not contain a saved fit result.");
  }
  normalizeResultSeries(payload.result);
  normalizeResultSeries(payload.auto_fit_baseline);
  setDisplayResult(payload.result);
  state.autoFitResult = clonePlain(payload.auto_fit_baseline || payload.result);
  state.acceptedResult = clonePlain(payload.result);
  state.manualDraftResult = null;
  state.fixedMeasured = null;
  state.plotScale = null;
  state.txtImport = null;
  state.txtSelectedBlockIds = new Set();
  state.assistantMessages = [];
  restoreSelectionFromFitpack(payload.data_selection || payload.result.dataset);
  restoreManualHistoryFromFitpack(payload);
  renderAssistantMessages();
  renderResult(currentDisplayResult());
  showResultPage();
  setStatus("Fitpack loaded.");
}
