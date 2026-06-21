/* ==========================================================================
   Fit execution and manual live evaluation
   ========================================================================== */

function setRunBusy(disabled) {
  const manualDisabled = disabled || !currentFitSupportsBaseManualEvaluation();
  setDisabledIfPresent("runBtn", disabled);
  setDisabledIfPresent("optimizeFromParamsBtn", manualDisabled);
  setDisabledIfPresent("saveRecordBtn", disabled);
  setDisabledIfPresent("openRecordFormBtn", disabled);
  setDisabledIfPresent("useFitParamsBtn", manualDisabled);
  setDisabledIfPresent("exportPackageBtn", disabled);
  setDisabledIfPresent("modelRunFitBtn", disabled);
  setDisabledIfPresent("saveAcceptedRecordBtn", disabled);
  setDisabledIfPresent("reviewManualFitBtn", manualDisabled);
  setDisabledIfPresent("manualFitBtn", manualDisabled);
}

function cancelPendingLiveEvaluation() {
  if (state.liveTimer) {
    clearTimeout(state.liveTimer);
    state.liveTimer = null;
  }
  state.evaluateSeq += 1;
}

function cancelPendingManualEvaluation() {
  if (state.manualHistoryTimer) {
    clearTimeout(state.manualHistoryTimer);
    state.manualHistoryTimer = null;
  }
  state.evaluateSeq += 1;
}

async function runAnalysis(options = {}) {
  if (options.useInitialParams && !currentFitSupportsBaseManualEvaluation()) {
    throw new Error(currentManualCapabilityMessage());
  }
  if (!state.uploadId) {
    await inspectSelectedFile();
  }
  cancelPendingLiveEvaluation();
  cancelPendingManualEvaluation();
  setStatus(options.useInitialParams ? "Optimizing from manual parameters..." : "Running analysis...");
  setRunBusy(true);
  setLoading(
    true,
    options.useInitialParams ? "Refitting from current parameters..." : "Running fit...",
    "The plot will update after the current fitting task finishes.",
    { diagnostic: currentFitMode() === "diagnostic_fit" }
  );
  try {
    const payload = await postForm("/api/analyze", buildForm(options));
    const shouldSetAuto = !options.useInitialParams || !state.autoFitResult;
    setDisplayResult(payload.result, { auto: shouldSetAuto });
    state.manualDraftResult = null;
    renderResult(payload.result);
    showResultPage();
    setStatus(options.useInitialParams ? "Optimization from manual parameters complete." : "Analysis complete.");
  } finally {
    setLoading(false);
    setRunBusy(false);
  }
}

function scheduleLiveEvaluation() {
  if (!$("liveAdjustToggle").checked || !state.uploadId || !currentDisplayResult()) return;
  if (!currentFitSupportsBaseManualEvaluation()) return;
  if (state.liveTimer) clearTimeout(state.liveTimer);
  state.liveTimer = setTimeout(() => {
    state.liveTimer = null;
    evaluateManualParams({ live: true }).catch(() => {
      // Intermediate values while typing, such as "1e-", are ignored in live mode.
    });
  }, 450);
}

async function evaluateManualParams(options = {}) {
  const manualTarget = options.target === "manual";
  if (!currentFitSupportsBaseManualEvaluation()) {
    throw new Error(currentManualCapabilityMessage());
  }
  if (!state.uploadId) {
    await inspectSelectedFile();
  }
  const seq = ++state.evaluateSeq;
  if (!options.live) {
    setStatus("Evaluating manual parameters...");
    setRunBusy(true);
  }
  try {
    const fd = buildForm();
    appendManualParams(fd, manualTarget ? "manual" : "edit");
    if (manualTarget) {
      const params = manualParamValues("manual");
      fd.set("param_m", String(params.m));
      const n = currentManualNValue();
      if (n !== null) fd.set("param_n", String(n));
    } else {
      const n = currentManualNValue();
      if (n !== null) fd.set("param_n", String(n));
    }
    const payload = await postForm("/api/evaluate", fd);
    if (options.live && seq !== state.evaluateSeq) return false;
    normalizeResultSeries(payload.result);
    if (options.target === "manual") {
      state.manualDraftResult = payload.result;
      renderManualDraftResult(payload.result);
    } else {
      setDisplayResult(payload.result);
      renderResult(payload.result, { syncEditor: false });
    }
    setStatus(options.live ? "Live parameter adjustment updated." : "Manual parameter evaluation complete.");
    return true;
  } finally {
    if (!options.live) setRunBusy(false);
  }
}
