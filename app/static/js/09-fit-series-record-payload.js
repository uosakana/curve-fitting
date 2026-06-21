/* ==========================================================================
   Fit series, snapshots, and training record payloads
   ========================================================================== */

function cloneNumericArray(values) {
  return (values || []).map((value) => Number(value));
}

function hasCompleteSeries(series, key) {
  const values = series?.[key] || [];
  const voltage = series?.voltage || [];
  return values.length > 0 && values.length === voltage.length;
}

function seriesMaxAbs(series, key) {
  const values = series?.[key] || [];
  return values.reduce((maxValue, value) => {
    const numeric = Math.abs(Number(value));
    return Number.isFinite(numeric) ? Math.max(maxValue, numeric) : maxValue;
  }, 0);
}

function componentHasVisibleSignal(series, key) {
  if (!hasCompleteSeries(series, key)) return false;
  const componentMax = seriesMaxAbs(series, key);
  const referenceMax = Math.max(seriesMaxAbs(series, "fitted"), seriesMaxAbs(series, "measured"), 1e-30);
  return componentMax > Math.max(1e-30, referenceMax * 1e-8);
}

function componentMatchesReference(series, key, referenceKey = "fitted") {
  if (!hasCompleteSeries(series, key) || !hasCompleteSeries(series, referenceKey)) return false;
  const values = series?.[key] || [];
  const reference = series?.[referenceKey] || [];
  let maxDiff = 0;
  for (let index = 0; index < values.length; index += 1) {
    const diff = Math.abs(Number(values[index]) - Number(reference[index]));
    if (Number.isFinite(diff)) maxDiff = Math.max(maxDiff, diff);
  }
  const scale = Math.max(seriesMaxAbs(series, key), seriesMaxAbs(series, referenceKey), 1e-30);
  return maxDiff <= scale * 1e-8;
}

function displaySeriesForComponents(series = {}) {
  const normalized = { ...(series || {}) };
  if (hasCompleteSeries(series, "empirical_nonohmic")) {
    normalized.nonohmic = cloneNumericArray(series.empirical_nonohmic);
  }
  if (
    hasCompleteSeries(series, "extra_current")
    && !hasCompleteSeries(normalized, "extended_nonohmic_total")
    && hasCompleteSeries(normalized, "nonohmic")
  ) {
    const nonohmic = normalized.nonohmic || [];
    normalized.extended_nonohmic_total = cloneNumericArray(series.extra_current)
      .map((value, index) => Number(value) + Number(nonohmic[index] || 0));
  }
  return normalized;
}

function componentColumnsForSeries(series = {}) {
  const columns = componentColumns.slice();
  if (hasCompleteSeries(series, "recombination") && hasCompleteSeries(series, "diffusion")) {
    const diodeIndex = columns.findIndex((column) => column.key === "diode");
    columns.splice(Math.max(0, diodeIndex + 1), 0, ...m4ComponentColumns);
  }
  if (componentHasVisibleSignal(series, "extra_current")) {
    const errorIndex = columns.findIndex((column) => column.key === "relative_error");
    columns.splice(errorIndex >= 0 ? errorIndex : columns.length, 0, ...extendedComponentColumns);
  }
  return columns;
}

function fitLegendItems(series = {}) {
  const normalized = displaySeriesForComponents(series);
  const base = [
    { key: "measured", label: "Measured" },
    { key: "fitted", label: "Fitted" },
  ];
  if (hasCompleteSeries(normalized, "recombination") && hasCompleteSeries(normalized, "diffusion")) {
    return [
      ...base,
      { key: "recombination", label: "Recombination" },
      { key: "diffusion", label: "Diffusion" },
      { key: "ohmic", label: "Ohmic" },
    ];
  }
  return [
    ...base,
    { key: "diode", label: "Diode" },
    { key: "ohmic", label: "Ohmic" },
    { key: "nonohmic", label: "Non-ohmic" },
    ...(componentHasVisibleSignal(normalized, "extra_current")
      ? [{ key: "extraCurrent", label: "Extended branch", color: colors.extraCurrent }]
      : []),
  ];
}

function renderFitLegend(series = {}, legendId = "fitLegend", overlays = []) {
  const legend = $(legendId);
  if (!legend) return;
  const items = [
    ...fitLegendItems(series),
    ...overlays.map((item) => ({ key: "overlay", label: item.label, color: item.color })),
  ];
  legend.innerHTML = items
    .map((item) => {
      const style = item.color ? ` style="background:${escapeHtml(item.color)}"` : "";
      return `<span><i class="swatch ${item.key}"${style}></i>${escapeHtml(item.label)}</span>`;
    })
    .join("");
}

function renderFitLegends(series = {}) {
  renderFitLegend(series, "fitLegend");
  renderFitLegend(series, "reviewFitLegend");
}

function componentSeriesPayload(result = currentAcceptedResult()) {
  const normalized = normalizeResultSeries(result);
  const series = displaySeriesForComponents(normalized?.fit?.series || normalized?.series || {});
  const data = {};
  const columns = componentColumnsForSeries(series);
  columns.forEach((column) => {
    data[column.key] = cloneNumericArray(series[column.key]);
  });

  const requiredLengths = requiredComponentKeys.map((key) => data[key].length);
  if (requiredLengths.some((length) => length <= 0)) {
    throw new Error("Current fit has no complete current-component series. Run or evaluate the fit again before saving.");
  }

  const pointCount = requiredLengths[0];
  if (!requiredLengths.every((length) => length === pointCount)) {
    throw new Error("Current fit component arrays have inconsistent lengths. Run or evaluate the fit again before saving.");
  }

  Object.keys(data).forEach((key) => {
    data[key] = data[key].length === pointCount ? data[key].slice() : data[key].slice(0, pointCount);
  });

  return {
    point_count: pointCount,
    columns: columns.map((column) => ({ ...column })),
    data,
  };
}

function datasetKey(result) {
  const dataset = result.dataset || {};
  return JSON.stringify({
    path: dataset.path,
    sheet_name: dataset.sheet_name,
    cell_range: dataset.cell_range,
    voltage_range: dataset.voltage_range,
    current_range: dataset.current_range,
    voltage_start: dataset.voltage_start,
    voltage_end: dataset.voltage_end,
    voltage_step: dataset.voltage_step,
    points: dataset.points,
  });
}

function buildPlotScale(voltage, measured) {
  const absMeasured = cloneNumericArray(measured)
    .map((y) => Math.abs(y))
    .filter((y) => Number.isFinite(y) && y > 0);
  const xValues = cloneNumericArray(voltage).filter(Number.isFinite);
  if (!absMeasured.length || !xValues.length) return null;

  const minMeasured = Math.min(...absMeasured);
  const maxMeasured = Math.max(...absMeasured);
  let minX = Math.min(...xValues);
  let maxX = Math.max(...xValues);
  if (minX === maxX) {
    minX -= 0.5;
    maxX += 0.5;
  }
  return {
    minX,
    maxX,
    minLog: Math.min(-11, Math.floor(Math.log10(Math.max(minMeasured, 1e-20)))),
    maxLog: Math.max(-3, Math.ceil(Math.log10(maxMeasured))),
    linearMinY: Math.min(...cloneNumericArray(measured).filter(Number.isFinite)),
    linearMaxY: Math.max(...cloneNumericArray(measured).filter(Number.isFinite)),
  };
}

function lockMeasuredSeries(result) {
  const fit = result.fit;
  if (!fit || !fit.series) return;
  const key = datasetKey(result);
  if (!state.fixedMeasured || state.fixedMeasured.key !== key) {
    state.fixedMeasured = {
      key,
      voltage: cloneNumericArray(fit.series.voltage),
      measured: cloneNumericArray(fit.series.measured),
    };
    state.plotScale = buildPlotScale(state.fixedMeasured.voltage, state.fixedMeasured.measured);
  }
  fit.series.voltage = state.fixedMeasured.voltage.slice();
  fit.series.measured = state.fixedMeasured.measured.slice();
}

function currentDataSelectionPayload() {
  const selection = dataSelectionFromFields();
  const voltage = selection.generatedVoltage || {};
  return {
    upload_id: state.uploadId,
    sheet_name: $("sheetSelect").value,
    cell_range: "",
    voltage_range: selection.voltageRange,
    current_range: selection.currentRange,
    voltage_start: voltage.start ?? null,
    voltage_end: voltage.end ?? null,
    voltage_step: voltage.step ?? null,
  };
}

function currentAnalysisSettingsPayload() {
  const fitMode = currentFitMode();
  const diagnosticMode = fitMode === "diagnostic_fit";
  const scanM = diagnosticMode;
  return {
    product_fit_mode: fitMode,
    fit_strategy: "quick_global",
    sweep_strategies: diagnosticMode,
    scan_m: scanM,
    scan_n: scanM,
    use_best_m_after_scan: true,
    compare_models: diagnosticMode,
    post_fit_models: diagnosticMode,
    ml_assist_enabled: mlAssistEnabled(),
    ml_assist_mode: mlAssistMode(),
    m_values: scanM ? internalMProfileValues : "",
    n_values: scanM ? internalNProfileValues : "",
    region_weights: {
      reverse: Number($("reverseWeight").value),
      near_zero: Number($("nearZeroWeight").value),
      forward: Number($("forwardWeight").value),
      high_forward: Number($("highForwardWeight").value),
    },
  };
}

function deviceStackPayload() {
  return state.deviceLayers.map((layer, index) => ({
    index,
    role: layer.role || "modifier",
    name: String(layer.name || "").trim(),
    thickness_nm: String(layer.thickness_nm || "").trim(),
    absorption_peak_nm: String(layer.absorption_peak_nm || "").trim(),
  })).filter((layer) => layer.name);
}

function deviceStackText(layers = deviceStackPayload()) {
  return layers.map((layer) => layer.name).join(" / ");
}

function agingDaysValue() {
  const value = Number($("saveAgingDays")?.value || 0);
  return Number.isFinite(value) ? Math.max(0, Math.round(value)) : 0;
}

function optionalTextValue(id) {
  return String($(id)?.value || "").trim();
}

function currentTrainingContextPayload() {
  const deviceArea = Number(optionalTextValue("saveDeviceArea"));
  const failureTags = Array.from(document.querySelectorAll("[data-save-failure-tag]:checked"))
    .map((item) => item.dataset.saveFailureTag)
    .filter(Boolean);
  return {
    device_area_mm2: Number.isFinite(deviceArea) && deviceArea > 0 ? deviceArea : null,
    batch_tag: optionalTextValue("saveBatchTag"),
    failure_tags: failureTags,
    model_feedback: optionalTextValue("saveModelFeedback") || "uncertain",
    process_note: optionalTextValue("saveProcessNote"),
  };
}

function currentSampleContextPayload() {
  const stack = deviceStackPayload();
  const agingDays = agingDaysValue();
  const trainingContext = currentTrainingContextPayload();
  const processParts = [];
  if (agingDays) processParts.push(`aging ${agingDays} day(s)`);
  if (trainingContext.process_note) processParts.push(trainingContext.process_note);
  return {
    sample_id: $("sampleId").value.trim(),
    batch: trainingContext.batch_tag || $("sampleBatch").value.trim(),
    role: "unknown",
    structure: deviceStackText(stack),
    process: processParts.join(" | "),
    expected_outcome: agingDays ? "aging_test" : "",
    comparison_group: $("comparisonGroup").value.trim(),
    device_stack: stack,
    aging_days: agingDays,
    training_context: trainingContext,
  };
}

function currentLabelPayload() {
  const evidence = Array.from(document.querySelectorAll("[data-evidence]:checked"))
    .map((el) => el.dataset.evidence);
  const acceptReasons = Array.from(document.querySelectorAll("[data-accept-reason]:checked"))
    .map((el) => el.dataset.acceptReason);
  const nextActions = Array.from(document.querySelectorAll("[data-next-action]:checked"))
    .map((el) => el.dataset.nextAction);
  const customHypothesis = saveHypothesisCustomNote();
  const member = normalizedSaveMemberName();
  const leakage = $("saveLeakageSituation")?.value || "";
  const modelSituation = $("saveModelSituation")?.value || "";
  const trainingContext = currentTrainingContextPayload();
  const notes = [];
  if (member) notes.push(`Member: ${member}`);
  if (leakage) notes.push(`Leakage: ${leakage}`);
  if (modelSituation) notes.push(`Model: ${modelSituation}`);
  if (trainingContext.model_feedback && trainingContext.model_feedback !== "uncertain") notes.push(`Model feedback: ${trainingContext.model_feedback}`);
  if (trainingContext.failure_tags.length) notes.push(`Failure tags: ${trainingContext.failure_tags.join(", ")}`);
  if (customHypothesis) notes.push(`Self label: ${customHypothesis}`);
  return {
    accepted: $("labelAccepted").checked,
    manual_adjusted: $("labelManualAdjusted").checked,
    quality: $("labelQuality").value,
    confidence: "medium",
    hypothesis: $("labelHypothesis").value,
    external_evidence: evidence,
    accept_reasons: acceptReasons,
    main_issue: $("labelMainIssue").value,
    next_actions: nextActions,
    notes: notes.join(" | "),
  };
}

function fitSnapshot(result) {
  const fit = result?.fit || {};
  const params = fit.params || [];
  return {
    params: {
      J0: Number(params[0]),
      Rs: Number(params[1]),
      Rsh: Number(params[2]),
      k: Number(params[3]),
      m: Number(fit.m),
    },
    stats: {
      mean: Number(fit.stats?.mean),
      max: Number(fit.stats?.max),
      median: Number(fit.stats?.median),
    },
    diagnostics: {
      worst_region: fit.diagnostics?.region_stats?.worst_region || null,
      boundary_hit_count: (fit.diagnostics?.boundary_hits || []).length,
      warning_count: (fit.diagnostics?.warnings || []).length,
    },
  };
}

function logDelta(finalValue, initialValue) {
  if (!Number.isFinite(finalValue) || !Number.isFinite(initialValue) || finalValue <= 0 || initialValue <= 0) return null;
  return Math.log10(finalValue / initialValue);
}

function fitDeltaPayload() {
  const initial = fitSnapshot(state.autoFitResult || currentDisplayResult());
  const final = fitSnapshot(currentAcceptedResult());
  const paramNames = ["J0", "Rs", "Rsh", "k"];
  const parameterChanges = paramNames.map((name) => {
    const before = initial.params[name];
    const after = final.params[name];
    const delta = logDelta(after, before);
    return {
      parameter: name,
      initial: before,
      final: after,
      log10_ratio: delta,
      direction: delta === null ? "unknown" : delta > 0 ? "increased" : delta < 0 ? "decreased" : "unchanged",
    };
  });
  parameterChanges.push({
    parameter: "m",
    initial: initial.params.m,
    final: final.params.m,
    delta: Number.isFinite(final.params.m) && Number.isFinite(initial.params.m) ? final.params.m - initial.params.m : null,
    direction:
      Number.isFinite(final.params.m) && Number.isFinite(initial.params.m)
        ? final.params.m > initial.params.m ? "increased" : final.params.m < initial.params.m ? "decreased" : "unchanged"
        : "unknown",
  });
  const ranked = parameterChanges
    .map((item) => ({
      ...item,
      magnitude: Math.abs(item.log10_ratio ?? item.delta ?? 0),
    }))
    .sort((a, b) => b.magnitude - a.magnitude);
  return {
    initial,
    final,
    parameter_changes: parameterChanges,
    dominant_changes: ranked.slice(0, 3).map(({ magnitude, ...item }) => item),
    stats_delta: {
      mean: Number.isFinite(final.stats.mean) && Number.isFinite(initial.stats.mean) ? final.stats.mean - initial.stats.mean : null,
      max: Number.isFinite(final.stats.max) && Number.isFinite(initial.stats.max) ? final.stats.max - initial.stats.max : null,
    },
    manual_checkpoint_count: state.manualHistory.length,
  };
}

function trainingSummaryPayload() {
  const delta = fitDeltaPayload();
  const trainingContext = currentTrainingContextPayload();
  return {
    device_stack: deviceStackPayload(),
    aging_days: agingDaysValue(),
    training_context: trainingContext,
    failure_tags: trainingContext.failure_tags,
    model_feedback: trainingContext.model_feedback,
    manual_adjusted: state.manualHistory.length > 0,
    manual_checkpoint_count: state.manualHistory.length,
    dominant_parameter_changes: delta.dominant_changes,
    final_worst_region: delta.final.diagnostics.worst_region,
    final_quality: $("labelQuality").value,
    recommended_training_use: $("labelQuality").value === "reject" ? "exclude_or_negative_example" : "candidate_training_example",
  };
}

function buildRecordPayload() {
  const result = currentAcceptedResult();
  if (!result || !result.fit) {
    throw new Error("Run or evaluate a fit before saving a record.");
  }
  return {
    created_at: new Date().toISOString(),
    data_selection: currentDataSelectionPayload(),
    sample_context: currentSampleContextPayload(),
    analysis_settings: currentAnalysisSettingsPayload(),
    manual_parameters: manualParamValues(),
    manual_history: manualHistoryPayload(),
    fit_delta: fitDeltaPayload(),
    training_summary: trainingSummaryPayload(),
    component_series: componentSeriesPayload(),
    labels: currentLabelPayload(),
    ml_assist: result.ml_assist || null,
    run_snapshot: clonePlain(result.run_snapshot || {}),
    result,
  };
}

function manualHistoryPayload() {
  return state.manualHistory.map((item) => ({
    trigger: item.trigger,
    created_at: item.created_at,
    starred: Boolean(item.starred),
    params: item.params,
    summary: item.summary,
    stats: item.result?.fit?.stats || {},
    diagnostics: {
      region_stats: item.result?.fit?.diagnostics?.region_stats || {},
      boundary_hits: item.result?.fit?.diagnostics?.boundary_hits || [],
      warnings: item.result?.fit?.diagnostics?.warnings || [],
    },
  }));
}

function validateRecordPayloadInputs() {
  if (!$("labelAccepted").checked) {
    throw new Error("Mark Accepted fit before saving a training record.");
  }
  if (!document.querySelector("[data-accept-reason]:checked")) {
    throw new Error("Select at least one acceptance reason before saving the training record.");
  }
}


function buildAssistantPayload(question) {
  const result = currentDisplayResult();
  if (!result || !result.fit) {
    throw new Error("Run a fit before asking the local assistant.");
  }
  return {
    question,
    result,
    history: state.assistantMessages.slice(-8),
  };
}

async function sendAssistantQuestion(questionInputId = "assistantQuestion", sendButtonId = "assistantSendBtn") {
  const input = $(questionInputId);
  const question = String(input.value || "").trim();
  if (!question) return;
  const button = $(sendButtonId);
  if (button) button.disabled = true;
  state.assistantMessages.push({ role: "user", text: question });
  input.value = "";
  renderAssistantMessages();
  try {
    const payload = await postJson("/api/assistant/chat", buildAssistantPayload(question));
    state.assistantMessages.push({ role: "assistant", text: payload.answer || payload.message || "No answer." });
    renderAssistantMessages();
  } finally {
    if (button) button.disabled = false;
  }
}
