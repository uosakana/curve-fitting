/* ==========================================================================
   Parameter payload and manual capability helpers
   ========================================================================== */

function parsePositiveInput(id, label) {
  const value = Number($(id).value);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`${label} must be a positive numeric value.`);
  }
  return value;
}

function paramValuesFromInputs(ids) {
  return {
    j0: parsePositiveInput(ids.j0, "J0"),
    rs: parsePositiveInput(ids.rs, "Rs"),
    rsh: parsePositiveInput(ids.rsh, "Rsh"),
    k: parsePositiveInput(ids.k, "k"),
    m: parsePositiveInput(ids.m, "m"),
  };
}

function manualParamValues(source = "edit") {
  if (source === "manual") {
    return paramValuesFromInputs({
      j0: "manualJ0",
      rs: "manualRs",
      rsh: "manualRsh",
      k: "manualK",
      m: "manualM",
    });
  }
  return paramValuesFromInputs({
    j0: "editJ0",
    rs: "editRs",
    rsh: "editRsh",
    k: "editK",
    m: "editM",
  });
}


function manualMValue() {
  const raw = $("editM").value.trim();
  if (!raw) return "";
  return String(parsePositiveInput("editM", "m"));
}

function appendManualParams(form, source = "edit") {
  const params = manualParamValues(source);
  form.append("param_j0", String(params.j0));
  form.append("param_rs", String(params.rs));
  form.append("param_rsh", String(params.rsh));
  form.append("param_k", String(params.k));
}

function formatParamInput(value) {
  return Number(value).toExponential(6);
}

function paramNamesFromDiagnostics(diagnostics = {}) {
  const names = Array.isArray(diagnostics.param_names) ? diagnostics.param_names : [];
  return names.length >= 4
    ? names.slice(0, 4).map((item) => String(item || "").trim() || "--")
    : defaultParamNamesFromContract();
}

function fitUsesStandardParams(diagnostics = {}) {
  const names = paramNamesFromDiagnostics(diagnostics).map((item) => item.toLowerCase());
  return ["j0", "rs", "rsh", "k"].every((name, index) => names[index] === name);
}

function currentManualSourceResult() {
  return !$("manualPage")?.classList.contains("hidden") && state.manualDraftResult
    ? state.manualDraftResult
    : currentDisplayResult();
}

function currentManualNValue() {
  const source = currentManualSourceResult();
  const n = Number(source?.fit?.n);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function currentFitSupportsBaseManualEvaluation() {
  const source = currentManualSourceResult();
  const capability = source?.manual_capability;
  return Boolean(capability && capability.can_evaluate === true);
}

function currentManualCapabilityMessage() {
  const source = currentManualSourceResult();
  const capability = source?.manual_capability;
  if (capability && capability.reason) return String(capability.reason);
  if (!capability) {
    return "Manual live evaluation is disabled because this result payload does not declare manual_capability.can_evaluate.";
  }
  return "Manual live evaluation is disabled for this displayed model because it cannot be reproduced by the base J0/Rs/Rsh/k evaluator.";
}

function syncParamLabels(names) {
  const labels = names.length >= 4 ? names : ["J0", "Rs", "Rsh", "k"];
  setTextIfPresent("editLabelJ0", labels[0]);
  setTextIfPresent("editLabelRs", labels[1]);
  setTextIfPresent("editLabelRsh", labels[2]);
  setTextIfPresent("editLabelK", labels[3]);
  setTextIfPresent("manualLabelJ0", labels[0]);
  setTextIfPresent("manualLabelRs", labels[1]);
  setTextIfPresent("manualLabelRsh", labels[2]);
  setTextIfPresent("manualLabelK", labels[3]);
}

function updateManualParamAvailability(diagnostics = {}) {
  const standard = fitUsesStandardParams(diagnostics);
  const baseManual = standard && currentFitSupportsBaseManualEvaluation();
  const message = standard
    ? "Wheel up increases the active parameter. Wheel down decreases it."
    : "Manual refit is disabled for this promoted model because its parameters are not J0/Rs/Rsh/k.";
  const blockedMessage = baseManual ? message : currentManualCapabilityMessage();
  setTextIfPresent("manualLiveStatus", baseManual ? $("manualLiveStatus")?.textContent || "" : blockedMessage);
  ["editJ0", "editRs", "editRsh", "editK", "editM", "manualJ0", "manualRs", "manualRsh", "manualK", "manualM"].forEach((id) => {
    setDisabledIfPresent(id, !baseManual);
  });
  setDisabledIfPresent("liveAdjustToggle", !baseManual);
  setDisabledIfPresent("optimizeFromParamsBtn", !baseManual);
  setDisabledIfPresent("useFitParamsBtn", !baseManual);
  setDisabledIfPresent("reviewManualFitBtn", !baseManual);
  setDisabledIfPresent("manualFitBtn", !baseManual);
  ["optimizeFromParamsBtn", "useFitParamsBtn", "reviewManualFitBtn", "manualFitBtn"].forEach((id) => {
    const element = $(id);
    if (element) element.title = baseManual ? "" : blockedMessage;
  });
}

function syncParamInputs(params, m, diagnostics = {}) {
  const names = paramNamesFromDiagnostics(diagnostics);
  syncParamLabels(names);
  $("editJ0").value = Number(params[0]).toExponential(6);
  $("editRs").value = Number(params[1]).toExponential(6);
  $("editRsh").value = Number(params[2]).toExponential(6);
  $("editK").value = Number(params[3]).toExponential(6);
  $("editM").value = Number(m).toFixed(6).replace(/\.?0+$/, "");
  updateManualParamAvailability(diagnostics);
}
