/* ==========================================================================
   Backend request builders
   ========================================================================== */

function buildForm(options = {}) {
  const selection = dataSelectionFromFields();
  const fitMode = currentFitMode();
  const diagnosticMode = fitMode === "diagnostic_fit";
  const scanM = diagnosticMode;
  const useStrategySweep = diagnosticMode;
  const fd = new FormData();
  fd.append("upload_id", state.uploadId || "");
  fd.append("sheet_name", $("sheetSelect").value);
  fd.append("cell_range", "");
  fd.append("voltage_range", selection.voltageRange);
  fd.append("current_range", selection.currentRange);
  if (selection.generatedVoltage) {
    fd.append("voltage_start", String(selection.generatedVoltage.start));
    fd.append("voltage_end", String(selection.generatedVoltage.end));
    fd.append("voltage_step", String(selection.generatedVoltage.step));
  }
  fd.append("product_fit_mode", fitMode);
  fd.append("mode", diagnosticMode ? "analyze" : "fit");
  fd.append("fit_strategy", "quick_global");
  fd.append("sweep_strategies", useStrategySweep ? "true" : "false");
  fd.append("reverse_weight", $("reverseWeight").value);
  fd.append("near_zero_weight", $("nearZeroWeight").value);
  fd.append("forward_weight", $("forwardWeight").value);
  fd.append("high_forward_weight", $("highForwardWeight").value);
  fd.append("scan_m", scanM ? "true" : "false");
  fd.append("scan_n", scanM ? "true" : "false");
  fd.append("use_best_m_after_scan", "true");
  fd.append("compare_models", diagnosticMode ? "true" : "false");
  fd.append("post_fit_models", diagnosticMode ? "true" : "false");
  fd.append("ml_assist_enabled", mlAssistEnabled() ? "true" : "false");
  fd.append("ml_assist_mode", mlAssistMode());
  fd.append("m_values", scanM ? internalMProfileValues : "");
  fd.append("n_values", scanM ? internalNProfileValues : "");
  fd.append("param_m", manualMValue());
  if (options.useInitialParams) {
    fd.append("use_initial_params", "true");
    appendManualParams(fd);
  }
  return fd;
}

async function postForm(url, form) {
  const response = await fetch(url, { method: "POST", body: form });
  const payload = await response.json();
  if (!payload.ok) {
    throw new Error(payload.error || payload.detail || "Request failed.");
  }
  return payload;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!data.ok) {
    throw new Error(data.error || data.detail || "Request failed.");
  }
  return data;
}

async function getJson(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!data.ok) {
    throw new Error(data.error || data.detail || "Request failed.");
  }
  return data;
}
