/* ==========================================================================
   Fit result state and shared DOM helpers
   ========================================================================== */

function currentDisplayResult() {
  return state.displayResult;
}

function currentAcceptedResult() {
  return state.acceptedResult || currentDisplayResult();
}

function arrayMaxAbs(values) {
  return (Array.isArray(values) ? values : []).reduce((maxValue, value) => {
    const numeric = Math.abs(Number(value));
    return Number.isFinite(numeric) ? Math.max(maxValue, numeric) : maxValue;
  }, 0);
}

function arraysNearlyEqual(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length || !left.length) {
    return false;
  }
  let maxDiff = 0;
  for (let index = 0; index < left.length; index += 1) {
    const diff = Math.abs(Number(left[index]) - Number(right[index]));
    if (Number.isFinite(diff)) maxDiff = Math.max(maxDiff, diff);
  }
  const scale = Math.max(arrayMaxAbs(left), arrayMaxAbs(right), 1e-30);
  return maxDiff <= scale * 1e-8;
}

function postFitModelName(result) {
  return (
    result?.model_context?.model_name
    || result?.fit?.diagnostics?.model_name
    || result?.fit?.diagnostics?.model_stage
    || ""
  );
}

function selectedPostFitSource(result) {
  const rows = Array.isArray(result?.post_fit_models) ? result.post_fit_models : [];
  if (!rows.length) return null;
  const modelName = postFitModelName(result);
  return (
    rows.find((row) => row?.name === modelName && row?.diagnostics?.selected_for_replacement)
    || rows.find((row) => row?.name === modelName)
    || rows.find((row) => row?.diagnostics?.selected_for_replacement)
    || null
  );
}

function enrichExtendedSeriesFromPostFit(result, series) {
  if (!series || typeof series !== "object") return;
  const source = selectedPostFitSource(result)?.series;
  if (!source || typeof source !== "object") return;
  if (!Array.isArray(source.fitted) || !arraysNearlyEqual(series.fitted, source.fitted)) return;
  if (Array.isArray(series.voltage) && Array.isArray(source.voltage) && !arraysNearlyEqual(series.voltage, source.voltage)) return;
  [
    "empirical_nonohmic",
    "extra_current",
    "extended_nonohmic_total",
    "v_drop",
  ].forEach((key) => {
    if (!Array.isArray(series[key]) && Array.isArray(source[key]) && source[key].length === source.fitted.length) {
      series[key] = source[key].slice();
    }
  });
}

function normalizeResultSeries(result) {
  if (!result || typeof result !== "object") return result;
  const fit = result.fit;
  if (fit && typeof fit === "object") {
    if (!fit.series && result.series && typeof result.series === "object") {
      fit.series = result.series;
    }
    if (!result.series && fit.series && typeof fit.series === "object") {
      result.series = fit.series;
    }
    enrichExtendedSeriesFromPostFit(result, fit.series);
    enrichExtendedSeriesFromPostFit(result, result.series);
  }
  return result;
}

function setDisplayResult(result, options = {}) {
  const normalized = normalizeResultSeries(result);
  state.displayResult = normalized || null;
  if (options.auto) {
    state.autoFitResult = normalized ? clonePlain(normalized) : null;
    state.selectedCandidateIndex = null;
  }
  if (options.accepted) {
    state.acceptedResult = normalized ? clonePlain(normalized) : null;
  } else if (!options.preserveAccepted) {
    state.acceptedResult = null;
  }
}

function clearFitResultState() {
  state.autoFitResult = null;
  state.displayResult = null;
  state.acceptedResult = null;
  state.manualDraftResult = null;
  state.selectedCandidateIndex = null;
}
