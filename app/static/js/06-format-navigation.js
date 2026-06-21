/* ==========================================================================
   Formatting, navigation, and input parsing
   ========================================================================== */

function formatSci(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toExponential(3);
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${Number(value).toFixed(2)}%`;
}

function formatFixed(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(digits);
}

function formatCompactNumber(value, digits = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  const number = Number(value);
  const abs = Math.abs(number);
  if (abs > 0 && (abs < 0.001 || abs >= 10000)) return number.toExponential(2);
  return Number(number.toFixed(digits)).toString();
}

function formatExponentPair(row) {
  if (!row) return "--";
  const ideality = row.diagnostics?.fixed_ideality || row.fit?.diagnostics?.fixed_ideality;
  if (ideality?.recombination != null && ideality?.diffusion != null) {
    return `${Number(ideality.recombination).toFixed(2)}/${Number(ideality.diffusion).toFixed(2)}`;
  }
  const n = Number(row.n ?? row.fit?.n ?? row.diagnostics?.m_profile?.display_n ?? 1.4);
  const m = Number(row.m ?? row.fit?.m ?? row.diagnostics?.m_profile?.display_m ?? 2.4);
  return `${n.toFixed(2)}/${m.toFixed(2)}`;
}

function parseFiniteText(id, label) {
  const raw = String($(id).value ?? "").trim();
  if (!raw) {
    throw new Error(`${label} must be numeric.`);
  }
  const value = Number(raw);
  if (!Number.isFinite(value)) {
    throw new Error(`${label} must be numeric.`);
  }
  return value;
}

function indexToExcelColumn(index) {
  let n = index + 1;
  let label = "";
  while (n > 0) {
    n -= 1;
    label = String.fromCharCode(65 + (n % 26)) + label;
    n = Math.floor(n / 26);
  }
  return label;
}

function excelColumnToIndex(label) {
  let index = 0;
  const normalized = normalizeExcelColumn(label);
  for (const char of normalized) {
    index = index * 26 + (char.charCodeAt(0) - 64);
  }
  return normalized ? index - 1 : null;
}

function normalizeExcelColumn(value) {
  return String(value || "").replace(/[^A-Za-z]/g, "").toUpperCase();
}

function updateColumnSuggestionsFor(inputId, datalistId) {
  const input = $(inputId);
  const normalized = normalizeExcelColumn(input.value);
  if (input.value !== normalized) input.value = normalized;

  const suggestions = normalized
    ? Array.from({ length: 26 }, (_, i) => `${normalized}${String.fromCharCode(65 + i)}`)
    : Array.from({ length: 52 }, (_, i) => indexToExcelColumn(i));

  $(datalistId).innerHTML = suggestions
    .map((value) => `<option value="${value}"></option>`)
    .join("");
}

function updateColumnSuggestions() {
  updateColumnSuggestionsFor("currentColumn", "excelColumnSuggestions");
  updateColumnSuggestionsFor("voltageColumn", "excelVoltageColumnSuggestions");
}

function setHidden(id, hidden) {
  $(id).classList.toggle("hidden", hidden);
}

function currentFitMode() {
  const modelPage = $("modelPage");
  const modelMode = $("modelFitMode");
  if (modelPage && modelMode && !modelPage.classList.contains("hidden")) {
    return modelMode.value || "fast_fit";
  }
  return $("fitMode").value || "fast_fit";
}

function isDiagnosticFitMode() {
  return currentFitMode() === "diagnostic_fit";
}

function mlAssistEnabled() {
  return Boolean($("mlAssistToggle")?.checked);
}

function mlAssistMode() {
  return $("mlAssistMode")?.value || "advisory";
}

function usesExcelVoltage() {
  return $("voltageMode").value === "excel_column";
}

function refreshVoltageModeUi() {
  setHidden("generatedVoltageGroup", usesExcelVoltage());
  setHidden("excelVoltageGroup", !usesExcelVoltage());
}

function visibleFlowStep() {
  if (!$("savePage").classList.contains("hidden")) return "save";
  if (!$("manualPage").classList.contains("hidden")) return "manual";
  if (!$("resultPage").classList.contains("hidden")) return "review";
  if (!$("modelPage").classList.contains("hidden")) return "fit";
  if (!$("dataPickerOverlay").classList.contains("hidden")) return "data";
  return "home";
}

function flowStepAvailable(step) {
  if (step === "data") return true;
  if (step === "fit") return Boolean(selectionFromCurrentFields());
  if (step === "review") return Boolean(currentDisplayResult()?.fit);
  if (step === "manual") return Boolean(currentDisplayResult()?.fit);
  if (step === "save") return Boolean(currentAcceptedResult()?.fit);
  return false;
}

function updateFlowSteppers(step = visibleFlowStep()) {
  state.flowStep = step;
}

function animateFlowPage(id) {
  const element = $(id);
  if (!element) return;
  element.classList.remove("flow-enter");
  void element.offsetWidth;
  element.classList.add("flow-enter");
}

function setDataPickerVisible(visible) {
  setHidden("dataPickerOverlay", !visible);
  if (visible) {
    setHidden("homePage", true);
    setHidden("txtImportPage", true);
    setHidden("modelPage", true);
    setHidden("resultPage", true);
    setHidden("manualPage", true);
    setHidden("savePage", true);
    setHidden("appShell", true);
    updateFlowSteppers("data");
    animateFlowPage("dataPickerOverlay");
  }
}

function showHomePage() {
  resetWorkspaceForHome();
  state.flowReturnStep = null;
  setHidden("homePage", false);
  setHidden("txtImportPage", true);
  setHidden("modelPage", true);
  setHidden("resultPage", true);
  setHidden("manualPage", true);
  setHidden("savePage", true);
  setHidden("appShell", true);
  setHidden("dataPickerOverlay", true);
  updateFlowSteppers("home");
  setStatus("Load JV/I-V data to begin.");
}

function resetWorkspaceForHome() {
  clearTimeout(closeSavePage.timer);
  clearFitResultState();
  state.uploadId = null;
  state.fixedMeasured = null;
  state.plotScale = null;
  state.dataGrid = null;
  state.gridSelection = null;
  state.gridDragging = false;
  state.gridDragMoved = false;
  state.gridSuppressClick = false;
  state.gridClickAnchor = null;
  state.userVoltageOverride = false;
  state.manualDraftResult = null;
  state.manualHistory = [];
  state.manualHistoryActiveId = null;
  state.reviewCandidates = [];
  state.reviewOverlayEnabled = false;
  state.reviewCandidatePreviewIndex = 0;
  state.selectedCandidateIndex = null;
  state.txtImport = null;
  state.txtSelectedBlockIds = new Set();
  state.txtFitRangeBlockId = null;
  state.txtFitRangeTouched = false;
  state.selectedDeviceLayerId = null;
  state.deviceOrientation = "normal";
  state.deviceLayers = cloneDevicePreset("normal");
  state.selectedFileName = "";
  state.assistantMessages = [];
  cancelPendingLiveEvaluation();
  cancelPendingManualEvaluation();

  ["fileInput", "txtInput", "fitpackInput"].forEach((id) => {
    if ($(id)) $(id).value = "";
  });
  if ($("saveMemberName")) $("saveMemberName").value = "";
  if ($("saveAgingDays")) $("saveAgingDays").value = "0";
  if ($("saveQuality")) $("saveQuality").value = "acceptable";
  if ($("saveHypothesis")) $("saveHypothesis").value = "None";
  if ($("saveLeakageSituation")) $("saveLeakageSituation").value = "normal";
  if ($("saveModelSituation")) $("saveModelSituation").value = "current_model_ok";
  if ($("saveModelFeedback")) $("saveModelFeedback").value = "uncertain";
  if ($("saveSampleId")) $("saveSampleId").value = "";
  if ($("saveBatch")) $("saveBatch").value = "";
  ["saveDeviceArea", "saveBatchTag", "saveProcessNote"].forEach((id) => {
    if ($(id)) $(id).value = "";
  });
  document.querySelectorAll("[data-save-failure-tag]").forEach((input) => {
    input.checked = false;
  });
  document.querySelector(".save-training-context")?.removeAttribute("open");
  setDeviceStructureChecked(false);
  $("deviceStack")?.classList.remove("is-expanded", "is-switching", "is-invalid-shake");
  $("savePage")?.classList.remove("is-visible", "is-closing");
  setHidden("saveSuccessOverlay", true);
  setTextIfPresent("savePageStatus", "No record saved.");
  setTextIfPresent("recordStatus", "No record saved.");
  setTextIfPresent("recordsSummary", "No records loaded.");
  if ($("recordsList")) $("recordsList").innerHTML = "";
  document.querySelectorAll("[data-accept-reason], [data-evidence], [data-next-action]").forEach((input) => {
    input.checked = false;
  });
  if ($("labelAccepted")) $("labelAccepted").checked = false;
  if ($("labelManualAdjusted")) $("labelManualAdjusted").checked = false;
  if ($("labelQuality")) $("labelQuality").value = "acceptable";
  if ($("labelHypothesis")) $("labelHypothesis").value = "none";
  if ($("labelMainIssue")) $("labelMainIssue").value = "none";
  if ($("comparisonGroup")) $("comparisonGroup").value = "";
  if ($("sampleId")) $("sampleId").value = "";
  if ($("sampleBatch")) $("sampleBatch").value = "";
  ["currentColumn", "currentStartRow", "currentEndRow", "voltageColumn", "voltageStartRow", "voltageEndRow"].forEach((id) => {
    if ($(id)) $(id).value = "";
  });
  if ($("voltageMode")) $("voltageMode").value = "generated";
  if ($("voltageStart")) $("voltageStart").value = String(defaultVoltageWindow.start);
  if ($("voltageEnd")) $("voltageEnd").value = String(defaultVoltageWindow.end);
  if ($("voltageStep")) $("voltageStep").value = String(defaultVoltageWindow.step);
  if ($("fitMode")) $("fitMode").value = "fast_fit";
  if ($("modelFitMode")) $("modelFitMode").value = "fast_fit";
  if ($("mlAssistToggle")) $("mlAssistToggle").checked = false;
  if ($("mlAssistMode")) $("mlAssistMode").value = "advisory";
  if ($("reverseWeight")) $("reverseWeight").value = "1.5";
  if ($("nearZeroWeight")) $("nearZeroWeight").value = "0.5";
  if ($("forwardWeight")) $("forwardWeight").value = "1.0";
  if ($("highForwardWeight")) $("highForwardWeight").value = "1.5";
  refreshVoltageModeUi();
  refreshFitModeUi();
  setRunFitMode("fast_fit");
  renderDeviceStack();
  renderDeviceLayerEditor();
  renderAssistantMessages();
  updateFileSelectionUi();
}

function syncTxtScaleButtons() {
  document.querySelectorAll("[data-txt-scale]").forEach((button) => {
    button.classList.toggle("active", button.dataset.txtScale === state.txtScale);
  });
  const control = document.querySelector(".txt-import-page .segmented-control");
  if (control) {
    control.dataset.activeScale = state.txtScale;
    requestAnimationFrame(() => syncTxtScaleTabIndicator(state.txtScale));
  }
}

function showTxtImportPage() {
  setHidden("homePage", true);
  setHidden("txtImportPage", false);
  setHidden("modelPage", true);
  setHidden("resultPage", true);
  setHidden("manualPage", true);
  setHidden("savePage", true);
  setHidden("appShell", true);
  setHidden("dataPickerOverlay", true);
  setStatus("Review parsed txt blocks.");
  syncTxtScaleButtons();
  requestAnimationFrame(drawTxtPreview);
}

function modelSummaryText() {
  const selection = selectionFromCurrentFields();
  if (!selection) return "No data range selected.";
  if (usesExcelVoltage()) {
    const voltage = rangeFromFields("voltageColumn", "voltageStartRow", "voltageEndRow", "Voltage");
    const voltageText = voltage?.range || "voltage column not set";
    return `${indexToExcelColumn(selection.colIndex)}${selection.startRow}:${indexToExcelColumn(selection.colIndex)}${selection.endRow} | voltage ${voltageText}`;
  }
  const voltageStart = $("voltageStart").value || "--";
  const voltageStep = $("voltageStep").value || "--";
  return `${indexToExcelColumn(selection.colIndex)}${selection.startRow}:${indexToExcelColumn(selection.colIndex)}${selection.endRow} | voltage start ${voltageStart}, step ${voltageStep}`;
}

function compactRunFileName(name) {
  const text = String(name || "Selected data").split(/[\\/]/).pop();
  return text.length > 34 ? `${text.slice(0, 17)}...${text.slice(-13)}` : text;
}

function formatRunVoltage(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "--";
  return String(Number(numeric.toPrecision(5)));
}

function runVoltageSummaryText() {
  if (usesExcelVoltage()) {
    const voltage = rangeDetailsFromA1(
      `${$("voltageColumn").value}${$("voltageStartRow").value}:${$("voltageColumn").value}${$("voltageEndRow").value}`
    );
    if (!voltage) return "Excel column";
    const values = gridValuesForColumn(voltage.colIndex, voltage.startRow, voltage.endRow);
    if (values && values.length) {
      const min = Math.min(...values);
      const max = Math.max(...values);
      return `${formatRunVoltage(min)} to ${formatRunVoltage(max)} V`;
    }
    return voltage.range;
  }

  const start = Number($("voltageStart").value);
  const end = Number($("voltageEnd").value);
  if (Number.isFinite(start) && Number.isFinite(end)) {
    return `${formatRunVoltage(start)} to ${formatRunVoltage(end)} V`;
  }
  return "--";
}

function syncRunDataSummary() {
  const selection = selectionFromCurrentFields();
  const points = selection ? selection.endRow - selection.startRow + 1 : null;
  setTextIfPresent("runFileSummary", compactRunFileName(state.selectedFileName || state.txtImport?.fileName || ""));
  setTextIfPresent("runPointSummary", points ? String(points) : "--");
  setTextIfPresent("runVoltageSummary", runVoltageSummaryText());
}

function syncModelControlsFromFitControls() {
  $("modelFitMode").value = $("fitMode").value;
  $("modelScanMToggle").checked = false;
  $("modelCompareModelsToggle").checked = isDiagnosticFitMode();
  $("modelPostFitDiagnosticsToggle").checked = isDiagnosticFitMode();
}

function syncFitControlsFromModelControls() {
  $("fitMode").value = $("modelFitMode").value;
  $("scanMToggle").checked = false;
  refreshFitModeUi();
}

function syncRunProtocolSummary() {
  const mode = $("modelFitMode")?.value || "fast_fit";
  setTextIfPresent("runModeSummary", mode === "diagnostic_fit" ? "Diagnostic" : "Fast");
  setTextIfPresent("runModelSummary", $("modelCompareModelsToggle")?.checked ? "Enabled" : "Off");
  setTextIfPresent("runPostFitSummary", $("modelPostFitDiagnosticsToggle")?.checked ? "On" : "Off");
  syncRunModeTabs(mode);
  syncRunDataSummary();
}

function syncRunModeTabs(mode = $("modelFitMode")?.value || "fast_fit") {
  const diagnostic = mode === "diagnostic_fit";
  const hint = diagnostic
    ? "Super mode opens the slower diagnostic family and physical rescue candidates."
    : "Fast mode ranks the baseline family and keeps the run compact.";
  document.querySelectorAll("[data-run-mode]").forEach((button) => {
    const active = button.dataset.runMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  setTextIfPresent("runModeHint", hint);
  $("modelPage")?.classList.toggle("diagnostic-mode", diagnostic);
  const tabs = document.querySelector(".run-mode-tabs");
  if (tabs) {
    tabs.classList.toggle("is-super", diagnostic);
    tabs.dataset.runMode = mode;
    requestAnimationFrame(() => syncRunModeTabIndicator(mode));
  }
}

function syncRunModeTabIndicator(buttonOrMode, options = {}) {
  const tabs = document.querySelector(".run-mode-tabs");
  if (!tabs) return;
  const button = typeof buttonOrMode === "string"
    ? tabs.querySelector(`[data-run-mode="${buttonOrMode}"]`)
    : buttonOrMode;
  if (!button) return;
  const tabsRect = tabs.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const next = {
    x: buttonRect.left - tabsRect.left,
    y: buttonRect.top - tabsRect.top,
    w: buttonRect.width,
    h: buttonRect.height,
  };
  const previousX = parseFloat(tabs.style.getPropertyValue("--run-tab-x"));
  const previousW = parseFloat(tabs.style.getPropertyValue("--run-tab-w"));
  const prefix = options.hover ? "--run-hover" : "--run-tab";
  tabs.style.setProperty(`${prefix}-x`, `${next.x}px`);
  tabs.style.setProperty(`${prefix}-y`, `${next.y}px`);
  tabs.style.setProperty(`${prefix}-w`, `${next.w}px`);
  tabs.style.setProperty(`${prefix}-h`, `${next.h}px`);
  if (options.hover) {
    tabs.classList.add("is-hovering");
    return;
  }
  if (Number.isFinite(previousX) && Number.isFinite(previousW)) {
    const trailX = Math.min(previousX, next.x);
    const trailRight = Math.max(previousX + previousW, next.x + next.w);
    tabs.style.setProperty("--run-trail-x", `${trailX}px`);
    tabs.style.setProperty("--run-trail-y", `${next.y}px`);
    tabs.style.setProperty("--run-trail-w", `${trailRight - trailX}px`);
    tabs.style.setProperty("--run-trail-h", `${next.h}px`);
    tabs.classList.remove("is-moving");
    requestAnimationFrame(() => {
      tabs.classList.add("is-moving");
      clearTimeout(syncRunModeTabIndicator.timer);
      syncRunModeTabIndicator.timer = setTimeout(() => tabs.classList.remove("is-moving"), 340);
    });
  }
}

function clearRunModeTabHover() {
  document.querySelector(".run-mode-tabs")?.classList.remove("is-hovering");
}

function rangeTabButton(control, preset) {
  if (!control) return null;
  if (preset === "core") return control.querySelector("#dataCoreRangeBtn, #txtFitCoreRangeBtn");
  if (preset === "full") return control.querySelector("#dataFullRangeBtn, #txtFitFullRangeBtn");
  return control.querySelector("button.active");
}

function syncRangeTabIndicator(controlOrSelector, buttonOrPreset, options = {}) {
  const control = typeof controlOrSelector === "string"
    ? document.querySelector(controlOrSelector)
    : controlOrSelector;
  if (!control) return;
  const button = typeof buttonOrPreset === "string"
    ? rangeTabButton(control, buttonOrPreset)
    : buttonOrPreset;
  if (!button) return;
  const controlRect = control.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const next = {
    x: buttonRect.left - controlRect.left,
    y: buttonRect.top - controlRect.top,
    w: buttonRect.width,
    h: buttonRect.height,
  };
  const previousX = parseFloat(control.style.getPropertyValue("--range-tab-x"));
  const previousW = parseFloat(control.style.getPropertyValue("--range-tab-w"));
  const prefix = options.hover ? "--range-hover" : "--range-tab";
  control.style.setProperty(`${prefix}-x`, `${next.x}px`);
  control.style.setProperty(`${prefix}-y`, `${next.y}px`);
  control.style.setProperty(`${prefix}-w`, `${next.w}px`);
  control.style.setProperty(`${prefix}-h`, `${next.h}px`);
  if (options.hover) {
    control.classList.add("is-hovering");
    return;
  }
  if (Number.isFinite(previousX) && Number.isFinite(previousW)) {
    const trailX = Math.min(previousX, next.x);
    const trailRight = Math.max(previousX + previousW, next.x + next.w);
    control.style.setProperty("--range-trail-x", `${trailX}px`);
    control.style.setProperty("--range-trail-y", `${next.y}px`);
    control.style.setProperty("--range-trail-w", `${trailRight - trailX}px`);
    control.style.setProperty("--range-trail-h", `${next.h}px`);
    control.classList.remove("is-moving");
    requestAnimationFrame(() => {
      control.classList.add("is-moving");
      clearTimeout(control._rangeTabTimer);
      control._rangeTabTimer = setTimeout(() => control.classList.remove("is-moving"), 340);
    });
  }
}

function clearRangeTabHover(selector) {
  document.querySelector(selector)?.classList.remove("is-hovering");
}

function txtScaleButton(control, scale) {
  if (!control) return null;
  if (typeof scale === "string") return control.querySelector(`[data-txt-scale="${scale}"]`);
  return control.querySelector("button.active");
}

function syncTxtScaleTabIndicator(buttonOrScale, options = {}) {
  const control = document.querySelector(".txt-import-page .segmented-control");
  if (!control) return;
  const button = typeof buttonOrScale === "string" ? txtScaleButton(control, buttonOrScale) : buttonOrScale;
  if (!button) return;
  const controlRect = control.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const next = {
    x: buttonRect.left - controlRect.left,
    y: buttonRect.top - controlRect.top,
    w: buttonRect.width,
    h: buttonRect.height,
  };
  const previousX = parseFloat(control.style.getPropertyValue("--txt-scale-tab-x"));
  const previousW = parseFloat(control.style.getPropertyValue("--txt-scale-tab-w"));
  const prefix = options.hover ? "--txt-scale-hover" : "--txt-scale-tab";
  control.style.setProperty(`${prefix}-x`, `${next.x}px`);
  control.style.setProperty(`${prefix}-y`, `${next.y}px`);
  control.style.setProperty(`${prefix}-w`, `${next.w}px`);
  control.style.setProperty(`${prefix}-h`, `${next.h}px`);
  if (options.hover) {
    control.classList.add("is-hovering");
    return;
  }
  if (Number.isFinite(previousX) && Number.isFinite(previousW)) {
    const trailX = Math.min(previousX, next.x);
    const trailRight = Math.max(previousX + previousW, next.x + next.w);
    control.style.setProperty("--txt-scale-trail-x", `${trailX}px`);
    control.style.setProperty("--txt-scale-trail-y", `${next.y}px`);
    control.style.setProperty("--txt-scale-trail-w", `${trailRight - trailX}px`);
    control.style.setProperty("--txt-scale-trail-h", `${next.h}px`);
    control.classList.remove("is-moving");
    requestAnimationFrame(() => {
      control.classList.add("is-moving");
      clearTimeout(control._txtScaleTabTimer);
      control._txtScaleTabTimer = setTimeout(() => control.classList.remove("is-moving"), 340);
    });
  }
}

function clearTxtScaleTabHover() {
  document.querySelector(".txt-import-page .segmented-control")?.classList.remove("is-hovering");
}

function syncReviewSideTabIndicator(buttonOrPanel, options = {}) {
  const tabs = document.querySelector(".review-side-tabs");
  if (!tabs) return;
  const button = typeof buttonOrPanel === "string"
    ? tabs.querySelector(`[data-review-panel="${buttonOrPanel}"]`)
    : buttonOrPanel;
  if (!button) return;
  const tabsRect = tabs.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const next = {
    x: buttonRect.left - tabsRect.left,
    y: buttonRect.top - tabsRect.top,
    w: buttonRect.width,
    h: buttonRect.height,
  };
  const previousX = parseFloat(tabs.style.getPropertyValue("--review-tab-x"));
  const previousW = parseFloat(tabs.style.getPropertyValue("--review-tab-w"));
  const prefix = options.hover ? "--review-hover" : "--review-tab";
  tabs.style.setProperty(`${prefix}-x`, `${next.x}px`);
  tabs.style.setProperty(`${prefix}-y`, `${next.y}px`);
  tabs.style.setProperty(`${prefix}-w`, `${next.w}px`);
  tabs.style.setProperty(`${prefix}-h`, `${next.h}px`);
  if (options.hover) {
    tabs.classList.add("is-hovering");
    return;
  }
  if (Number.isFinite(previousX) && Number.isFinite(previousW)) {
    const trailX = Math.min(previousX, next.x);
    const trailRight = Math.max(previousX + previousW, next.x + next.w);
    tabs.style.setProperty("--review-trail-x", `${trailX}px`);
    tabs.style.setProperty("--review-trail-y", `${next.y}px`);
    tabs.style.setProperty("--review-trail-w", `${trailRight - trailX}px`);
    tabs.style.setProperty("--review-trail-h", `${next.h}px`);
    tabs.classList.remove("is-moving");
    requestAnimationFrame(() => {
      tabs.classList.add("is-moving");
      clearTimeout(syncReviewSideTabIndicator.timer);
      syncReviewSideTabIndicator.timer = setTimeout(() => tabs.classList.remove("is-moving"), 320);
    });
  }
}

function clearReviewSideTabHover() {
  document.querySelector(".review-side-tabs")?.classList.remove("is-hovering");
}

function setRunFitMode(mode) {
  if (!mode || !$("modelFitMode")) return;
  $("modelFitMode").value = mode;
  handleFitModeChange("modelFitMode");
}

const motionScrambleChars =
  "!@#$%^&*()_+-=[]{}|;:,.<>?/~`" +
  "\u2591\u2592\u2593\u2588\u2580\u2584\u25a0\u25a1\u25aa\u25ab" +
  "\u25cf\u25cb\u25c6\u25c7\u25c8\u25ca\u203b\u2020\u2021";

function randomScrambleChar(chars = motionScrambleChars) {
  return chars[Math.floor(Math.random() * chars.length)];
}

function clearScrambleRender(element) {
  if (!element) return;
  if (element._scrambleFrame) cancelAnimationFrame(element._scrambleFrame);
  if (element._scrambleInterval) clearInterval(element._scrambleInterval);
  if (element._scrambleTimeout) clearTimeout(element._scrambleTimeout);
  element._scrambleFrame = null;
  element._scrambleInterval = null;
  element._scrambleTimeout = null;
}

function clearScrambleAnimation(element) {
  if (!element) return;
  clearScrambleRender(element);
  if (element._scrambleLoop) clearInterval(element._scrambleLoop);
  element._scrambleLoop = null;
}

function scrambleTextElement(element, finalText, options = {}) {
  if (!element) return;
  const text = finalText || element.dataset.scrambleText || element.textContent || "";
  const chars = options.chars || motionScrambleChars;
  const duration = options.duration ?? 1000;
  const interval = options.interval ?? 50;
  clearScrambleRender(element);

  const writeRandomText = () => {
    element.textContent = Array.from(text)
      .map((char) => (char === " " ? " " : randomScrambleChar(chars)))
      .join("");
  };

  writeRandomText();
  element._scrambleInterval = setInterval(writeRandomText, interval);
  element._scrambleTimeout = setTimeout(() => {
    clearScrambleRender(element);
    element.textContent = text;
  }, duration);
}

function setScrambleLoop(element, active) {
  if (!element) return;
  const text = element.dataset.scrambleText || element.textContent || "";
  const words = (element.dataset.scrambleWords || text)
    .split(",")
    .map((word) => word.trim())
    .filter(Boolean);
  if (!active) {
    clearScrambleAnimation(element);
    element.textContent = text;
    return;
  }
  if (element._scrambleLoop) return;
  let wordIndex = Math.max(0, words.indexOf(text));
  const runNextScramble = () => {
    const word = words[wordIndex] || text;
    scrambleTextElement(element, word, { duration: 1000, interval: 50, chars: motionScrambleChars });
    wordIndex = (wordIndex + 1) % Math.max(words.length, 1);
  };
  runNextScramble();
  element._scrambleLoop = setInterval(runNextScramble, 2000);
}

function setRunProtocolDialogVisible(visible) {
  setHidden("runProtocolDialog", !visible);
  syncRunProtocolSummary();
}

function setReviewSidePanel(panelName) {
  const target = panelName || "candidates";
  const current = document.querySelector('[data-review-panel-content]:not(.hidden):not(.is-panel-ghost)');
  document.querySelectorAll("[data-review-panel]").forEach((button) => {
    button.classList.toggle("active", button.dataset.reviewPanel === target);
    button.setAttribute("aria-selected", button.dataset.reviewPanel === target ? "true" : "false");
  });
  document.querySelectorAll("[data-review-panel-content]").forEach((panel) => {
    const active = panel.dataset.reviewPanelContent === target;
    if (active) {
      panel.classList.remove("hidden", "is-panel-ghost");
    } else if (panel !== current || panel.dataset.reviewPanelContent === target) {
      panel.classList.add("hidden");
      panel.classList.remove("is-panel-ghost");
    }
  });
  if (current && current.dataset.reviewPanelContent !== target) {
    current.classList.remove("hidden");
    current.classList.add("is-panel-ghost");
    clearTimeout(current._reviewGhostTimer);
    current._reviewGhostTimer = setTimeout(() => {
      current.classList.add("hidden");
      current.classList.remove("is-panel-ghost");
    }, 320);
  }
  syncReviewSideTabIndicator(target);
}

function showModelPage() {
  syncModelControlsFromFitControls();
  syncRunProtocolSummary();
  $("modelDataSummary").textContent = modelSummaryText();
  setHidden("homePage", true);
  setHidden("txtImportPage", true);
  setHidden("modelPage", false);
  setHidden("resultPage", true);
  setHidden("manualPage", true);
  setHidden("savePage", true);
  setHidden("appShell", true);
  setHidden("dataPickerOverlay", true);
  updateFlowSteppers("fit");
  animateFlowPage("modelPage");
  setStatus("Ready to run fit.");
}

function showResultPage() {
  const result = currentDisplayResult();
  setHidden("homePage", true);
  setHidden("txtImportPage", true);
  setHidden("modelPage", true);
  setHidden("resultPage", false);
  setHidden("manualPage", true);
  setHidden("savePage", true);
  setHidden("dataPickerOverlay", true);
  setHidden("appShell", true);
  setHidden("fitDecisionPanel", !(result && result.fit));
  updateFlowSteppers("review");
  animateFlowPage("resultPage");
  requestAnimationFrame(() => syncReviewSideTabIndicator(document.querySelector(".review-side-tabs button.active")));
  if (result) requestAnimationFrame(() => renderReviewResult(result));
}

function showManualPage() {
  cancelPendingLiveEvaluation();
  cancelPendingManualEvaluation();
  const source = currentDisplayResult();
  state.manualDraftResult = source ? clonePlain(source) : null;
  syncManualInputsFromResult(state.manualDraftResult);
  syncHiddenManualInputs();
  renderManualHistory();
  $("manualLiveStatus").textContent = summarizeManualFit(state.manualDraftResult);
  setHidden("homePage", true);
  setHidden("txtImportPage", true);
  setHidden("modelPage", true);
  setHidden("resultPage", true);
  setHidden("manualPage", false);
  setHidden("savePage", true);
  setHidden("dataPickerOverlay", true);
  setHidden("appShell", true);
  updateFlowSteppers("manual");
  animateFlowPage("manualPage");
  if (state.manualDraftResult?.fit?.series) {
    requestAnimationFrame(() => renderManualDraftResult(state.manualDraftResult));
  }
}

function manualDisplayResult(result) {
  const next = clonePlain(result);
  next.display_mode = "manual";
  next.candidate_selection = {
    source: "manual_fit",
    label: "Manual fit",
    manual_checkpoint_count: state.manualHistory.length,
  };
  next.model_context = {
    ...(next.model_context || {}),
    display_fit_source: "manual_fit",
  };
  if (next.fit) {
    next.fit.diagnostics = {
      ...(next.fit.diagnostics || {}),
      display_fit_source: "manual_fit",
      manual_adjusted: true,
    };
  }
  return normalizeResultSeries(next);
}

function acceptManualDraft() {
  cancelPendingManualEvaluation();
  if (state.manualDraftResult?.fit) {
    setDisplayResult(manualDisplayResult(state.manualDraftResult), { accepted: true });
    state.manualDraftResult = null;
    renderResult(currentDisplayResult(), { syncEditor: false });
  }
  showSavePage();
}

function showSavePage() {
  const page = $("savePage");
  const previousStep = visibleFlowStep();
  if (previousStep !== "save") {
    state.flowReturnStep = productFlowSteps.some((step) => step.id === previousStep) ? previousStep : "review";
  }
  if (!state.acceptedResult && currentDisplayResult()?.fit) {
    state.acceptedResult = clonePlain(currentDisplayResult());
  }
  clearTimeout(closeSavePage.timer);
  updateSaveSystemQuality();
  setHidden("savePage", false);
  page.classList.remove("is-closing");
  page.classList.remove("is-visible");
  requestAnimationFrame(() => page.classList.add("is-visible"));
  updateFlowSteppers("save");
  animateFlowPage("savePage");
  setTextIfPresent("savePageStatus", "");
  syncDeviceStackLabels();
  syncDeviceOrientationUi();
  syncSaveCustomSelects?.();
  renderDeviceLayerEditor();
}

function closeSavePage() {
  const page = $("savePage");
  if (!page || page.classList.contains("hidden")) return;
  page.classList.remove("is-visible");
  page.classList.add("is-closing");
  setHidden("saveSuccessOverlay", true);
  closeDeviceLayerEditor();
  state.flowReturnStep = null;
  clearTimeout(closeSavePage.timer);
  closeSavePage.timer = window.setTimeout(() => {
    setHidden("savePage", true);
    page.classList.remove("is-closing");
    $("deviceStack")?.classList.remove("is-expanded");
    updateFlowSteppers(visibleFlowStep());
  }, 380);
}

function syncDiagnosticInternalToggles(mode, compareId, postId) {
  const diagnostic = mode === "diagnostic_fit";
  const compare = $(compareId);
  const post = $(postId);
  if (compare) compare.checked = diagnostic;
  if (post) post.checked = diagnostic;
  setDisabledIfPresent(compareId, true);
  setDisabledIfPresent(postId, true);
}

function refreshFitModeUi() {
  $("scanMToggle").checked = false;
  $("modelScanMToggle").checked = false;
  syncDiagnosticInternalToggles($("fitMode").value, "compareModelsToggle", "postFitDiagnosticsToggle");
  syncDiagnosticInternalToggles($("modelFitMode").value, "modelCompareModelsToggle", "modelPostFitDiagnosticsToggle");
  setDisabledIfPresent("mlAssistMode", !mlAssistEnabled());
  setHidden("mValuesField", true);
  syncRunProtocolSummary();
}

function handleFitModeChange(sourceId) {
  if (sourceId === "modelFitMode") {
    $("fitMode").value = $("modelFitMode").value;
  } else if (sourceId === "fitMode") {
    $("modelFitMode").value = $("fitMode").value;
  }
  refreshFitModeUi();
}

function updateFileSelectionUi() {
  const hasFile = Boolean(state.selectedFileName);
  setHidden("filePickerRow", hasFile);
  setHidden("fileSelectionRow", !hasFile);
  setHidden("changeFileBtn", !hasFile);
  $("selectedFileName").textContent = hasFile ? state.selectedFileName : "No file selected.";
  $("selectedFileHint").textContent = hasFile
    ? "File loaded. Change File to select another dataset."
    : "Choose a data file to continue.";
}

function toggleRecordForm(visible) {
  setHidden("recordForm", !visible);
  $("openRecordFormBtn").textContent = visible ? "Record Form Open" : "Prepare Save";
}

function renderAssistantMessages() {
  const html = !state.assistantMessages.length
    ? `
      <div class="assistant-message assistant-bot">
        <strong>Local chat</strong>
        <span>You can ask about limiting voltage regions, weak parameters, or model candidates.</span>
      </div>
    `
    : state.assistantMessages.map((item) => `
    <div class="assistant-message ${item.role === "user" ? "assistant-user" : "assistant-bot"}">
      <strong>${item.role === "user" ? "You" : "Assistant"}</strong>
      <span>${escapeHtml(item.text || "")}</span>
    </div>
  `).join("");
  setHtmlIfPresent("assistantMessages", html);
}

function resetAssistantConversation() {
  state.assistantMessages = [];
  renderAssistantMessages();
}

function wheelFactor(event) {
  if (event.shiftKey) return 1.01;
  if (event.altKey) return 1.2;
  return 1.05;
}

function adjustParameterByWheel(event, inputId) {
  const input = $(inputId);
  const current = Number(input.value);
  if (!Number.isFinite(current) || current <= 0) return;
  event.preventDefault();
  let next;
  if (inputId === "editM") {
    const delta = event.shiftKey ? 0.005 : event.altKey ? 0.1 : 0.02;
    next = event.deltaY < 0 ? current + delta : current - delta;
    if (next <= 0) next = delta;
    input.value = Number(next).toFixed(4).replace(/\.?0+$/, "");
  } else {
    const factor = wheelFactor(event);
    next = event.deltaY < 0 ? current * factor : current / factor;
    input.value = formatParamInput(next);
  }
  scheduleLiveEvaluation();
}

function adjustManualParameterByWheel(event, inputId) {
  const input = $(inputId);
  const current = Number(input.value);
  if (!Number.isFinite(current) || current <= 0) return;
  event.preventDefault();
  let next;
  const intensity = Math.min(8, Math.max(0.25, Math.abs(event.deltaY) / 80));
  if (inputId === "manualM") {
    const delta = 0.01 * intensity;
    next = event.deltaY < 0 ? current + delta : current - delta;
    if (next <= 0) next = delta;
    input.value = Number(next).toFixed(4).replace(/\.?0+$/, "");
  } else {
    const factor = Math.pow(1.025, intensity);
    next = event.deltaY < 0 ? current * factor : current / factor;
    input.value = formatParamInput(next);
  }
  syncHiddenManualInputs();
  scheduleManualLiveEvaluation(`Wheel ${manualParamControls.find((item) => item.input === inputId)?.name || "parameter"}`);
}

function rangeFromFields(columnId, startId, endId, label) {
  const col = normalizeExcelColumn($(columnId).value);
  const start = $(startId).value.trim();
  const end = $(endId).value.trim();
  if (!col && !start && !end) return "";
  if (!col || !start || !end) {
    throw new Error(`${label} range requires column, start row, and end row.`);
  }
  if (!/^[1-9]\d*$/.test(start) || !/^[1-9]\d*$/.test(end)) {
    throw new Error(`${label} start/end rows must be positive integers.`);
  }
  if (Number(end) < Number(start)) {
    throw new Error(`${label} end row must be greater than or equal to start row.`);
  }
  $(columnId).value = col;
  return {
    range: `${col}${Number(start)}:${col}${Number(end)}`,
    startRow: Number(start),
    endRow: Number(end),
    count: Number(end) - Number(start) + 1,
  };
}

function rangeDetailsFromA1(range) {
  const match = /^([A-Za-z]+)(\d+):([A-Za-z]+)(\d+)$/.exec(String(range || "").trim());
  if (!match || match[1].toUpperCase() !== match[3].toUpperCase()) return null;
  const startRow = Number(match[2]);
  const endRow = Number(match[4]);
  if (!Number.isInteger(startRow) || !Number.isInteger(endRow) || startRow <= 0 || endRow < startRow) return null;
  return {
    column: match[1].toUpperCase(),
    colIndex: excelColumnToIndex(match[1]),
    startRow,
    endRow,
    count: endRow - startRow + 1,
    range: `${match[1].toUpperCase()}${startRow}:${match[1].toUpperCase()}${endRow}`,
  };
}

function currentRangeDetails() {
  const details = rangeFromFields("currentColumn", "currentStartRow", "currentEndRow", "Current");
  if (!details) return { range: "", startRow: null, endRow: null, count: 0 };
  return details;
}

function voltageRangeFromFields(current) {
  if (!usesExcelVoltage()) return "";
  if (!current.range) {
    throw new Error("Excel voltage source requires a current range.");
  }
  const voltage = rangeFromFields("voltageColumn", "voltageStartRow", "voltageEndRow", "Voltage");
  if (!voltage) {
    throw new Error("Excel voltage source requires column, start row, and end row.");
  }
  if (voltage.count !== current.count) {
    throw new Error(
      `Voltage range has ${voltage.count} rows, but current range has ${current.count} rows.`
    );
  }
  return voltage.range;
}

function voltageSettingsFromFields(current) {
  if (usesExcelVoltage()) return null;
  const start = Number($("voltageStart").value);
  const end = Number($("voltageEnd").value);
  const step = Number($("voltageStep").value);
  if (![start, end, step].every(Number.isFinite)) {
    throw new Error("Generated voltage start/end/step must be numeric.");
  }
  if (step === 0) {
    throw new Error("Generated voltage step cannot be zero.");
  }
  if ((end - start) * step < 0) {
    throw new Error("Generated voltage step must move from start toward end.");
  }

  if (current.range) {
    const expected = Math.round((end - start) / step) + 1;
    if (expected !== current.count) {
      throw new Error(
        `Generated voltage has ${expected} points, but current range has ${current.count} rows.`
      );
    }
  }
  return { start, end, step };
}

function dataSelectionFromFields() {
  const current = currentRangeDetails();
  return {
    currentRange: current.range,
    voltageRange: voltageRangeFromFields(current),
    generatedVoltage: voltageSettingsFromFields(current),
  };
}

function syncGeneratedVoltageEnd() {
  if (usesExcelVoltage()) return;
  let current;
  try {
    current = currentRangeDetails();
  } catch {
    return;
  }
  if (!current.range || !current.count) return;
  const start = Number($("voltageStart").value);
  const step = Number($("voltageStep").value);
  if (!Number.isFinite(start) || !Number.isFinite(step) || step === 0) return;
  $("voltageEnd").value = Number((start + step * (current.count - 1)).toFixed(12));
}
