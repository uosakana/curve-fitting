/* ==========================================================================
   Result rendering and manual draft history
   ========================================================================== */

function renderWorkbenchMetrics(fit, scan = []) {
  $("meanError").textContent = formatPct(fit.stats.mean);
  $("maxError").textContent = formatPct(fit.stats.max);
  $("pointsCount").textContent = String(Math.trunc(fit.stats.included_points || 0));
  $("bestM").textContent = scan.length ? formatExponentPair(scan[0]) : formatExponentPair(fit);
}

function syncResultParameterEditor(fit, options = {}) {
  if (options.syncEditor === false) return;
  syncParamInputs(fit.params, fit.m, fit.diagnostics || {});
}

function renderResultDiagnostics(result, fit, scan = []) {
  renderAssistant(result.notes, result.advice);
  renderRegionStats(fit.diagnostics?.region_stats);
  renderCoreDiagnostics(fit.diagnostics);
  renderDeepStrategySummary(result);
  renderStrategyTable(result.strategy_sweep || []);
  renderScanTable(scan);
  renderModelTable(
    result.model_comparison || [],
    result.post_fit_models || [],
    result.recommended_baseline_model || null,
    result.diagnostic_ablation_models || [],
  );
  updateDiagnosticVisibility(result);
}

function markResultUnsaved(options = {}) {
  if (options.markUnsaved !== false) {
    $("recordStatus").textContent = "Current result not saved.";
  }
}

function renderResult(result, options = {}) {
  normalizeResultSeries(result);
  lockMeasuredSeries(result);
  const fit = result.fit;
  const scan = result.m_scan || [];
  renderWorkbenchMetrics(fit, scan);
  syncResultParameterEditor(fit, options);
  renderFitLegends(fit.series || {});
  renderResultDiagnostics(result, fit, scan);
  markResultUnsaved(options);
  redrawActiveView();
}

function renderReviewMetrics(fit, scan = []) {
  $("reviewMeanError").textContent = formatPct(fit.stats.mean);
  $("reviewMaxError").textContent = formatPct(fit.stats.max);
  $("reviewPointsCount").textContent = String(Math.trunc(fit.stats.included_points || 0));
  $("reviewBestM").textContent = scan.length ? formatExponentPair(scan[0]) : formatExponentPair(fit);
}


function hasReviewCandidateBasis(result) {
  return Boolean(
    result?.fit
    && ((result?.candidates || []).length || (result?.post_fit_models || []).length)
  );
}

function reviewRunIdentity(result) {
  return result?.run_snapshot?.snapshot_id || result?.dataset || "";
}

function reviewBaseResult(result = currentDisplayResult()) {
  if (hasReviewCandidateBasis(state.autoFitResult)) {
    const autoId = reviewRunIdentity(state.autoFitResult);
    const resultId = reviewRunIdentity(result);
    if (!result || !autoId || !resultId || autoId === resultId || result?.candidate_selection) {
      return state.autoFitResult;
    }
  }
  if (hasReviewCandidateBasis(result)) return result;
  return state.autoFitResult || result;
}

function seriesFingerprintValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toExponential(6) : String(value ?? "");
}

function seriesSampleFingerprint(series) {
  const fitted = Array.isArray(series?.fitted) ? series.fitted : [];
  const voltage = Array.isArray(series?.voltage) ? series.voltage : [];
  if (!fitted.length) return "";
  const indexes = Array.from(new Set([
    0,
    Math.floor(fitted.length / 2),
    fitted.length - 1,
  ]));
  const fittedSamples = indexes.map((index) => seriesFingerprintValue(fitted[index]));
  const voltageSamples = indexes.map((index) => seriesFingerprintValue(voltage[index]));
  return [fitted.length, ...voltageSamples, ...fittedSamples].join("|");
}

function reviewOverlayItems(result) {
  if (!state.reviewOverlayEnabled) return [];
  const baseResult = reviewBaseResult(result) || result;
  const allCandidates = reviewCandidatePool(baseResult);
  const active = allCandidates[activeCandidateIndex(result, allCandidates)];
  const activeKey = active ? candidateKey(active) : "";
  const activeFingerprint = seriesSampleFingerprint(result?.fit?.series || {});
  const seenFingerprints = new Set(activeFingerprint ? [activeFingerprint] : []);
  const overlays = [];
  allCandidates.forEach((candidate) => {
    if (overlays.length >= overlayColors.length) return;
    if (!candidateCanView(candidate, baseResult)) return;
    if (candidateKey(candidate) === activeKey || candidate?.is_primary) return;
    const series = candidateSeriesForDisplay(candidate, baseResult);
    const fingerprint = seriesSampleFingerprint(series);
    if (fingerprint && seenFingerprints.has(fingerprint)) return;
    if (fingerprint) seenFingerprints.add(fingerprint);
    overlays.push({
      label: candidate.label || candidateSourceLabel(candidate.source),
      color: overlayColors[overlays.length % overlayColors.length],
      series,
    });
  });
  return overlays;
}

function renderReviewSeries(result) {
  const fit = result?.fit || {};
  const overlays = reviewOverlayItems(result);
  renderFitLegend(fit.series || {}, "reviewFitLegend", overlays);
  drawFitChart(fit.series, "reviewFitCanvas", { overlays });
}

function candidateHasRenderableFit(candidate, baseResult = currentDisplayResult()) {
  const series = candidateSeriesForDisplay(candidate, baseResult);
  return Boolean(
    hasCompleteSeries(series, "fitted")
    && hasCompleteSeries(series, "measured")
    && hasRenderableFitComponents(series)
  );
}

function candidateSeriesForDisplay(candidate, baseResult) {
  const baseSeries = baseResult?.fit?.series || baseResult?.series || {};
  const series = clonePlain(candidate?.fit?.series || candidate?.series || {});
  if (!series.voltage && baseSeries.voltage) series.voltage = clonePlain(baseSeries.voltage);
  if (!series.measured && baseSeries.measured) series.measured = clonePlain(baseSeries.measured);
  if (arraysNearlyEqual(series.fitted, baseSeries.fitted)) {
    [
      "empirical_nonohmic",
      "extra_current",
      "extended_nonohmic_total",
      "v_drop",
    ].forEach((key) => {
      if (!series[key] && baseSeries[key]) series[key] = clonePlain(baseSeries[key]);
    });
  }
  if (!hasCompleteSeries(series, "diode") && hasCompleteSeries(series, "recombination") && hasCompleteSeries(series, "diffusion")) {
    const recombination = series.recombination || [];
    const diffusion = series.diffusion || [];
    series.diode = recombination.map((value, index) => Number(value) + Number(diffusion[index] || 0));
  }
  return displaySeriesForComponents(series);
}

function hasRenderableFitComponents(series = {}) {
  if (hasCompleteSeries(series, "recombination") && hasCompleteSeries(series, "diffusion")) {
    return ["recombination", "diffusion", "ohmic"].some((key) => componentHasVisibleSignal(series, key));
  }
  const hasVisibleComponent = ["diode", "ohmic", "nonohmic"].some((key) => componentHasVisibleSignal(series, key));
  const placeholderComponents = (
    componentMatchesReference(series, "diode", "fitted")
    && !componentHasVisibleSignal(series, "ohmic")
    && !componentHasVisibleSignal(series, "nonohmic")
  );
  return hasVisibleComponent && !placeholderComponents;
}

function candidateSeriesScore(candidate, baseResult) {
  const series = candidateSeriesForDisplay(candidate, baseResult);
  let score = 0;
  if (hasCompleteSeries(series, "measured")) score += 10;
  if (hasCompleteSeries(series, "fitted")) score += 10;
  if (hasCompleteSeries(series, "diode")) score += 20;
  if (hasCompleteSeries(series, "ohmic")) score += 20;
  if (hasCompleteSeries(series, "nonohmic")) score += 20;
  if (hasCompleteSeries(series, "recombination")) score += 30;
  if (hasCompleteSeries(series, "diffusion")) score += 30;
  if (candidate?.fit?.series) score += 4;
  if (candidate?.series) score += 2;
  return score;
}

function candidateCanView(candidate, baseResult = currentDisplayResult()) {
  return Boolean(candidateHasRenderableFit(candidate, baseResult));
}

function candidateKey(candidate) {
  return [
    candidate?.source || "",
    candidate?.label || "",
    candidate?.model_context?.model_name || "",
    candidate?.model_context?.model_stage || "",
  ].join("::");
}

function postFitRowToReviewCandidate(row, index) {
  const diagnostics = row?.diagnostics || {};
  const paramNames = Array.isArray(row?.param_names) && row.param_names.length
    ? row.param_names
    : Array.from({ length: row?.params?.length || 0 }, (_, itemIndex) => `p${itemIndex + 1}`);
  return {
    source: "post_fit_diagnostic",
    label: row?.name || diagnostics.model_stage || `Post-fit ${index + 1}`,
    reason: diagnostics.selection_reason || "Physical diagnostic candidate.",
    is_primary: false,
    diagnostic_only: !Boolean(diagnostics.selected_for_replacement),
    promotable: Boolean(diagnostics.selected_for_replacement),
    n: row?.n,
    m: row?.m,
    params: row?.params,
    stats: row?.stats || {},
    diagnostics,
    model_context: {
      model_stage: diagnostics.model_stage,
      model_name: row?.name,
    },
    parameter_schema: {
      kind: "post_fit_model",
      parameters: paramNames.map((name, paramIndex) => {
        const value = Number(row?.params?.[paramIndex]);
        const item = { name };
        if (Number.isFinite(value)) item.value = value;
        return item;
      }),
      exponents: {
        n: Number(row?.n ?? diagnostics?.fixed_ideality?.recombination ?? 1.4),
        m: Number(row?.m ?? diagnostics?.fixed_ideality?.diffusion ?? 2.4),
      },
    },
    manual_capability: {
      can_evaluate: false,
      evaluator_kind: "post_fit_model",
      reason: "Post-fit candidates are displayed as read-only diagnostic curves.",
    },
    evaluator_kind: "post_fit_model",
    fit: null,
    series: row?.series,
  };
}

function reviewCandidatePool(result) {
  const merged = [];
  const seen = new Map();
  const add = (candidate) => {
    if (!candidate) return;
    const key = candidateKey(candidate);
    const existingIndex = seen.get(key);
    if (existingIndex !== undefined) {
      const existing = merged[existingIndex];
      if (candidateSeriesScore(candidate, result) > candidateSeriesScore(existing, result)) {
        merged[existingIndex] = {
          ...candidate,
          rank: candidate.rank || existing.rank,
        };
      }
      return;
    }
    seen.set(key, merged.length);
    merged.push(candidate);
  };
  (result?.candidates || []).forEach(add);
  (result?.post_fit_models || []).map(postFitRowToReviewCandidate).forEach((candidate) => {
    const displaySeries = candidateSeriesForDisplay(candidate, result);
    if (hasCompleteSeries(displaySeries, "fitted") && hasCompleteSeries(displaySeries, "measured")) add(candidate);
  });
  merged.forEach((candidate, index) => {
    if (!candidate.rank) candidate.rank = index + 1;
  });
  return merged.slice(0, 8);
}

function isManualDisplayResult(result) {
  return result?.display_mode === "manual" || result?.candidate_selection?.source === "manual_fit";
}

function activeCandidateIndex(result, candidates) {
  if (isManualDisplayResult(result)) return null;
  const selected = Number(result?.candidate_selection?.index);
  if (Number.isInteger(selected) && selected >= 0 && selected < candidates.length) {
    return selected;
  }
  const source = result?.candidate_selection?.source;
  const label = result?.candidate_selection?.label;
  if (source || label) {
    const selectedByIdentity = candidates.findIndex((candidate) => (
      (!source || candidate?.source === source) && (!label || candidate?.label === label)
    ));
    if (selectedByIdentity >= 0) return selectedByIdentity;
  }
  const primaryIndex = candidates.findIndex((candidate) => candidate?.is_primary);
  return primaryIndex >= 0 ? primaryIndex : null;
}

function candidateSourceLabel(source) {
  const labels = {
    primary_fit: "Primary",
    strategy_fit: "Primary",
    strategy_sweep: "Strategy",
    nm_profile: "n/m profile",
    baseline_family: "M-model",
    diagnostic_ablation: "Ablation",
    post_fit_model: "Post-fit",
    post_fit_diagnostic: "Post-fit",
    m_model_recommended_baseline: "M-model",
    manual_fit: "Manual",
  };
  return labels[source] || source || "Candidate";
}

function candidateModeText(candidate, active = false, baseResult = currentDisplayResult()) {
  if (active) return "current";
  if (candidate.is_primary) return "primary";
  if (!candidateHasRenderableFit(candidate, baseResult)) return "summary only";
  if (candidate.diagnostic_only) return "diagnostic view";
  if (candidate.promotable) return "promotable";
  return "viewable";
}

function candidateTypeBadge(candidate) {
  const label = String(candidate?.label || candidate?.model_context?.model_name || "").toLowerCase();
  const stage = String(candidate?.model_context?.model_stage || "").toUpperCase();
  if (candidate?.is_primary) return { text: "Primary", className: "primary" };
  if (stage === "M4" || label.includes("clean_double")) return { text: "M4 physical", className: "physical" };
  if (label.includes("double")) return { text: "Double", className: "physical" };
  if (label.includes("forward") || label.includes("trap")) return { text: "Region diagnostic", className: "region" };
  if (candidate?.source === "nm_profile") return { text: "n/m profile", className: "profile" };
  if (candidate?.source === "baseline_family") return { text: "M-model", className: "model" };
  return { text: candidateSourceLabel(candidate?.source), className: "neutral" };
}

function candidateStatusBadges(candidate, active = false, baseResult = currentDisplayResult()) {
  const badges = [];
  if (active) badges.push({ text: "Current", className: "current" });
  if (candidateCanView(candidate, baseResult)) badges.push({ text: "Viewable", className: "viewable" });
  else badges.push({ text: "Summary only", className: "summary" });
  if (candidate?.promotable) badges.push({ text: "Promotable", className: "promotable" });
  if (candidate?.diagnostic_only) badges.push({ text: "Diagnostic only", className: "diagnostic" });
  return badges;
}

function candidateWorstRegion(candidate) {
  const diagnostics = candidateDiagnostics(candidate);
  return diagnostics?.region_stats?.worst_region || diagnostics?.base_region_stats?.worst_region || "--";
}

function candidateDiagnostics(candidate) {
  return candidate?.fit?.diagnostics || candidate?.diagnostics || {};
}

function humanizeDiagnosticKey(key) {
  const labels = {
    bic_improvement_at_least_6: "BIC improvement",
    mean_error_improved: "mean error improvement",
    max_error_not_worse: "max error not worse",
    parameters_not_at_bounds: "parameters not at bounds",
    core_region_not_sacrificed: "core region not sacrificed",
    auto_replacement_allowed: "auto replacement evidence",
    missing_forward_semilog_two_slope_evidence: "missing forward semilog two-slope evidence",
  };
  return labels[key] || String(key || "").replace(/_/g, " ");
}

function candidateFailedChecks(diagnostics) {
  const criteria = diagnostics?.selection_criteria || {};
  return Object.entries(criteria)
    .filter(([, value]) => value === false)
    .map(([key]) => humanizeDiagnosticKey(key));
}

function candidateExplanationItems(candidate) {
  const diagnostics = candidateDiagnostics(candidate);
  const items = [];
  const failed = candidateFailedChecks(diagnostics);
  const worst = candidateWorstRegion(candidate);
  const evidence = diagnostics?.forward_semilog_two_slope_evidence || {};
  const warnings = diagnostics?.warnings || [];
  const boundaryHits = diagnostics?.boundary_hits || [];
  const reason = candidate?.reason || diagnostics?.selection_reason || diagnostics?.display_reason || "";

  if (diagnostics?.selected_for_replacement || candidate?.promotable) {
    items.push("Selected as a promotable replacement candidate; still needs review before accepting.");
  } else if (candidate?.diagnostic_only) {
    items.push("Diagnostic-only: viewable for comparison, but not selected as the final reproducible model.");
  } else if (candidate?.is_primary) {
    items.push("Primary displayed fit from the current run.");
  } else if (reason) {
    items.push(reason);
  }

  if (reason && !items.includes(reason)) {
    items.push(reason);
  }
  if (failed.length) {
    items.push(`Not promoted because: ${failed.slice(0, 3).join(", ")}.`);
  } else if (diagnostics?.publication_confidence) {
    items.push(`Confidence: ${String(diagnostics.publication_confidence).replace(/_/g, " ")}.`);
  } else if (diagnostics?.physical_confidence) {
    items.push(`Physical confidence: ${String(diagnostics.physical_confidence).replace(/_/g, " ")}.`);
  }

  if (evidence && evidence.has_evidence === false && evidence.reason) {
    items.push(`Forward evidence: ${humanizeDiagnosticKey(evidence.reason)}.`);
  }
  if (boundaryHits.length) {
    items.push(`${boundaryHits.length} parameter boundary hit(s); inspect fitted parameters.`);
  }
  if (worst !== "--") {
    items.push(`Worst region: ${worst}.`);
  }
  if (warnings.length) {
    items.push(String(warnings[0]));
  }
  if (!items.length) {
    items.push("Candidate generated by the current diagnostic run.");
  }
  return items.slice(0, 5);
}

function candidateExplanationHtml(candidate) {
  return `<ul class="review-candidate-reasons">${candidateExplanationItems(candidate)
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("")}</ul>`;
}


function candidateBadgeHtml(badge) {
  return `<span class="candidate-badge ${escapeHtml(badge.className)}">${escapeHtml(badge.text)}</span>`;
}

function positiveModulo(value, modulo) {
  return ((value % modulo) + modulo) % modulo;
}

function reviewCandidateDisplayEntries(candidates) {
  return candidates.map((candidate, originalIndex) => ({ candidate, originalIndex }));
}

function reviewCandidateStackLayout(count, expandedIndex, focusIndex = 0) {
  const collapsedHeight = 78;
  const expandedHeight = 286;
  const stackedStep = 54;
  const beforeStep = 54;
  const afterStep = 48;
  const safeExpanded = Number.isInteger(expandedIndex)
    ? Math.max(-1, Math.min(count - 1, expandedIndex))
    : -1;
  if (safeExpanded < 0) {
    const safeFocus = count ? Math.max(0, Math.min(count - 1, Number(focusIndex) || 0)) : 0;
    const positions = Array.from({ length: count }, (_, index) => ({
      y: index * stackedStep,
      height: collapsedHeight,
      expanded: false,
      layer: count + 2 - Math.abs(index - safeFocus),
      depth: Math.abs(index - safeFocus),
      scale: Math.max(0.88, 1 - Math.abs(index - safeFocus) * 0.032),
      opacity: Math.max(0.5, 1 - Math.abs(index - safeFocus) * 0.085),
    }));
    const height = positions.reduce((max, item) => Math.max(max, item.y + item.height), 0);
    return { positions, height };
  }
  const expandedTop = safeExpanded * beforeStep;
  const positions = Array.from({ length: count }, (_, index) => {
    const expanded = index === safeExpanded;
    const y = index < safeExpanded
      ? index * beforeStep
      : expanded
        ? expandedTop
        : expandedTop + expandedHeight + (index - safeExpanded - 1) * afterStep;
    return {
      y,
      height: expanded ? expandedHeight : collapsedHeight,
      expanded,
      layer: count - Math.abs(index - safeExpanded),
      depth: Math.abs(index - safeExpanded),
      scale: expanded ? 1 : Math.max(0.9, 1 - Math.abs(index - safeExpanded) * 0.026),
      opacity: expanded ? 1 : Math.max(0.56, 1 - Math.abs(index - safeExpanded) * 0.075),
    };
  });
  const height = positions.reduce((max, item) => Math.max(max, item.y + item.height), 0);
  return { positions, height };
}

function reviewCandidateStyleValues(stackItem) {
  const depth = Number(stackItem?.depth || 0);
  return {
    y: Number(stackItem?.y || 0).toFixed(1),
    layer: Number(stackItem?.layer || 1),
    scale: Number(stackItem?.scale || 1).toFixed(3),
    opacity: Number(stackItem?.opacity || 1).toFixed(3),
    depth,
    flipScale: (Number(stackItem?.scale || 1) * 0.95).toFixed(3),
    saturation: Math.max(0.76, 1 - depth * 0.05).toFixed(3),
    brightness: Math.max(0.82, 1 - depth * 0.035).toFixed(3),
  };
}

function candidateRowHtml(candidate, index, activeIndex, baseResult, expandedIndex, stackItem) {
  const rank = candidate.rank || index + 1;
  const label = candidate.label || candidateSourceLabel(candidate.source);
  const stats = candidate.stats || {};
  const exponent = Number.isFinite(Number(candidate.n)) || Number.isFinite(Number(candidate.m))
    ? `${Number.isFinite(Number(candidate.n)) ? Number(candidate.n).toFixed(2) : "--"}/${Number.isFinite(Number(candidate.m)) ? Number(candidate.m).toFixed(2) : "--"}`
    : "";
  const manual = candidate.manual_capability?.can_evaluate ? "manual ok" : "manual off";
  const active = index === activeIndex;
  const expanded = index === expandedIndex;
  const typeBadge = candidateTypeBadge(candidate);
  const typeClass = `candidate-${String(typeBadge.className || "neutral").replace(/[^a-z0-9_-]/gi, "")}`;
  const statusBadges = candidateStatusBadges(candidate, active, baseResult);
  const badges = [typeBadge, ...statusBadges];
  const viewButton = candidateCanView(candidate, baseResult)
    ? active
      ? '<button class="secondary review-candidate-view" type="button" disabled>Current</button>'
      : `<button class="secondary review-candidate-view" type="button" data-candidate-action="view" data-candidate-index="${index}">View</button>`
    : "";
  const style = reviewCandidateStyleValues(stackItem);
  return `
    <div
      class="review-candidate-item ${typeClass} ${active ? "active" : ""} ${expanded ? "is-expanded" : "is-collapsed"}"
      data-candidate-index="${index}"
      data-candidate-depth="${style.depth}"
      role="button"
      tabindex="0"
      style="--candidate-y:${style.y}px; --candidate-layer:${style.layer}; --candidate-scale:${style.scale}; --candidate-flip-scale:${style.flipScale}; --candidate-opacity:${style.opacity}; --candidate-depth:${style.depth}; --candidate-saturation:${style.saturation}; --candidate-brightness:${style.brightness}"
    >
      <div class="review-candidate-main">
        <div class="review-candidate-preview">
          <div class="review-candidate-title">
            <strong>#${rank}</strong>
            <span class="review-candidate-preview-label">${escapeHtml(label)}</span>
            <span>${expanded ? badges.map(candidateBadgeHtml).join("") : candidateBadgeHtml(typeBadge)}</span>
          </div>
          <div class="review-candidate-mini">
            <span><em>Mean</em>${formatPct(stats.mean)}</span>
            ${expanded ? `<span><em>Max</em>${formatPct(stats.max)}</span>` : ""}
          </div>
        </div>
        <div class="review-candidate-details" aria-hidden="${expanded ? "false" : "true"}">
          <div class="review-candidate-stats">
            <span><em>Worst</em>${escapeHtml(candidateWorstRegion(candidate))}</span>
            ${exponent ? `<span><em>Exponent</em>${escapeHtml(exponent)}</span>` : ""}
            <span><em>View</em>${escapeHtml(candidateModeText(candidate, active, baseResult))}</span>
            <span><em>Manual</em>${escapeHtml(manual)}</span>
          </div>
          ${candidateExplanationHtml(candidate)}
        </div>
      </div>
      ${viewButton}
    </div>
  `;
}

function reviewCurrentModelText(result) {
  const selection = result?.candidate_selection || {};
  const diagnostics = result?.fit?.diagnostics || {};
  const modelContext = result?.model_context || {};
  const fallbackSource = diagnostics.display_fit_source || "";
  const label =
    selection.label ||
    diagnostics.candidate_label ||
    diagnostics.model_name ||
    modelContext.model_name ||
    (fallbackSource && !String(fallbackSource).startsWith("post_fit") ? candidateSourceLabel(fallbackSource) : "Current fit");
  const source = candidateSourceLabel(selection.source || diagnostics.candidate_source || diagnostics.display_fit_source);
  return { label, source };
}

function updateReviewCurrentModel(result) {
  const element = $("reviewCurrentModel");
  if (!element) return;
  const model = reviewCurrentModelText(result);
  element.innerHTML = `<strong>${escapeHtml(model.label)}</strong>`;
}

function snapshotModeLabel(snapshot, result) {
  const settings = snapshot?.analysis?.settings || {};
  const mode = settings.product_fit_mode || result?.product_fit_mode || "";
  if (mode === "diagnostic_fit") return "Diagnostic Fit";
  if (mode === "fast_fit") return "Fast Fit";
  return settings.fit_strategy || "--";
}

function snapshotRangeText(range, unit = "") {
  if (!range || range.min === null || range.min === undefined || range.max === null || range.max === undefined) return "--";
  const suffix = unit ? ` ${unit}` : "";
  return `${formatCompactNumber(range.min)} to ${formatCompactNumber(range.max)}${suffix}`;
}

function snapshotItemHtml(label, value, title = "") {
  const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
  return `<div${titleAttr}><span>${escapeHtml(label)}</span><strong>${escapeHtml(value || "--")}</strong></div>`;
}

function renderReviewSnapshot(result) {
  const card = $("reviewSnapshotCard");
  const idElement = $("reviewSnapshotId");
  const grid = $("reviewSnapshotGrid");
  if (!card || !idElement || !grid) return;
  const snapshot = result?.run_snapshot;
  if (!snapshot) {
    card.classList.add("is-empty");
    idElement.textContent = "--";
    grid.innerHTML = [
      snapshotItemHtml("File", "--"),
      snapshotItemHtml("Range", "--"),
      snapshotItemHtml("Mode", "--"),
      snapshotItemHtml("Candidates", "--"),
    ].join("");
    return;
  }
  card.classList.remove("is-empty");
  const data = snapshot.data || {};
  const counts = snapshot.analysis?.candidate_counts || {};
  const engine = snapshot.engine || {};
  const snapshotId = String(snapshot.snapshot_id || "--").replace(/^run_/, "");
  const candidateText = `${counts.ranked ?? 0} ranked / ${counts.post_fit ?? 0} post`;
  const pointText = `${data.points ?? "--"} pts`;
  idElement.textContent = snapshotId;
  grid.innerHTML = [
    snapshotItemHtml("File", data.file_name || "--", data.path || ""),
    snapshotItemHtml("Voltage", snapshotRangeText(data.voltage, "V")),
    snapshotItemHtml("Points", pointText),
    snapshotItemHtml("Mode", snapshotModeLabel(snapshot, result)),
    snapshotItemHtml("Candidates", candidateText),
    snapshotItemHtml("Seed", engine.random_seed ?? "--"),
  ].join("");
}

function renderReviewMlStatus(result) {
  const card = $("reviewMlCard");
  const status = $("reviewMlStatus");
  const grid = $("reviewMlGrid");
  if (!card || !status || !grid) return;
  const assist = result?.ml_assist || {};
  const models = assist.models || {};
  const similar = assist.similar || {};
  const suggested = assist.suggested_overrides?.product_fit_mode || assist.suggested_product_fit_mode || "";
  const applied = assist.applied_overrides?.product_fit_mode || assist.applied_product_fit_mode || "";
  const enabled = Boolean(assist.enabled);
  const statusText = enabled ? (assist.status || "ready") : "disabled";
  card.classList.toggle("is-disabled", !enabled);
  status.textContent = statusText;
  grid.innerHTML = [
    snapshotItemHtml("Models", models.status || assist.model_status || "not requested"),
    snapshotItemHtml("Similar", similar.record_count !== undefined ? `${similar.record_count} records` : "not requested"),
    snapshotItemHtml("Suggest", suggested || "--"),
    snapshotItemHtml("Policy", applied ? `applied ${applied}` : (assist.mode || "advisory")),
  ].join("");
}

function renderReviewCandidates(result) {
  const baseResult = reviewBaseResult(result) || result;
  const candidates = reviewCandidatePool(baseResult);
  state.reviewCandidates = candidates;
  const list = $("reviewCandidateList");
  const summary = $("reviewCandidateSummary");
  if (!list || !summary) return;
  if (!candidates.length) {
    summary.textContent = "No candidates yet.";
    list.innerHTML = '<div class="review-candidate-empty">Run Diagnostic Fit to rank candidates.</div>';
    list.style.removeProperty("--candidate-stack-height");
    state.selectedCandidateIndex = null;
    state.reviewCandidatePreviewIndex = 0;
    return;
  }
  const mode = (baseResult.product_fit_mode || result.product_fit_mode) === "diagnostic_fit" ? "Diagnostic Fit" : "Fast Fit";
  const activeIndex = activeCandidateIndex(result, candidates);
  const manualNote = isManualDisplayResult(result) ? " | manual displayed" : "";
  const viewableCount = candidates.filter((candidate) => candidateCanView(candidate, baseResult)).length;
  const storedValue = state.selectedCandidateIndex;
  const storedIndex = Number(storedValue);
  const expandedIndex = storedValue === -1 || storedValue === null || storedValue === undefined
    ? -1
    : Number.isInteger(storedIndex) && storedIndex >= 0 && storedIndex < candidates.length
      ? storedIndex
      : -1;
  state.selectedCandidateIndex = expandedIndex;
  const entries = reviewCandidateDisplayEntries(candidates);
  const previewIndex = positiveModulo(Number(state.reviewCandidatePreviewIndex) || 0, candidates.length);
  state.reviewCandidatePreviewIndex = previewIndex;
  const focusIndex = expandedIndex >= 0 ? expandedIndex : previewIndex;
  const stack = reviewCandidateStackLayout(entries.length, expandedIndex, focusIndex);
  summary.textContent = `${mode}${manualNote} | ${viewableCount}/${candidates.length} viewable`;
  list.style.setProperty("--candidate-stack-height", `${stack.height}px`);
  list.innerHTML = entries
    .map((entry, displayIndex) => candidateRowHtml(
      entry.candidate,
      entry.originalIndex,
      activeIndex,
      baseResult,
      expandedIndex,
      stack.positions[displayIndex]
    ))
    .join("");
  const overlayButton = $("reviewOverlayToggleBtn");
  if (overlayButton) {
    overlayButton.classList.toggle("active", state.reviewOverlayEnabled);
    overlayButton.setAttribute("aria-pressed", state.reviewOverlayEnabled ? "true" : "false");
    overlayButton.disabled = viewableCount < 2;
  }
}

function applyReviewCandidatePreviewFocus(focusIndex) {
  const candidates = state.reviewCandidates || [];
  const list = $("reviewCandidateList");
  const result = currentDisplayResult();
  if (!list || !candidates.length || !result?.fit) return false;
  const items = Array.from(list.querySelectorAll(".review-candidate-item[data-candidate-index]"));
  if (items.length !== candidates.length) {
    renderReviewCandidates(result);
    return false;
  }
  const nextFocus = positiveModulo(focusIndex, candidates.length);
  state.reviewCandidatePreviewIndex = nextFocus;
  state.selectedCandidateIndex = -1;
  const stack = reviewCandidateStackLayout(candidates.length, -1, nextFocus);
  list.style.setProperty("--candidate-stack-height", `${stack.height}px`);
  list.classList.remove("is-wheel-flipping", "is-wheel-leaving", "is-wheel-entering");
  list.classList.add("is-preview-shifting");
  clearTimeout(list._candidateShiftTimer);
  list._candidateShiftTimer = setTimeout(() => {
    list.classList.remove("is-preview-shifting");
  }, 420);

  items.forEach((item) => {
    const index = Number(item.dataset.candidateIndex);
    if (!Number.isInteger(index)) return;
    const style = reviewCandidateStyleValues(stack.positions[index]);
    item.dataset.candidateDepth = String(style.depth);
    item.classList.remove("is-expanded");
    item.classList.add("is-collapsed");
    item.style.setProperty("--candidate-y", `${style.y}px`);
    item.style.setProperty("--candidate-layer", String(style.layer));
    item.style.setProperty("--candidate-scale", style.scale);
    item.style.setProperty("--candidate-flip-scale", style.flipScale);
    item.style.setProperty("--candidate-opacity", style.opacity);
    item.style.setProperty("--candidate-depth", String(style.depth));
    item.style.setProperty("--candidate-saturation", style.saturation);
    item.style.setProperty("--candidate-brightness", style.brightness);
    const details = item.querySelector(".review-candidate-details");
    if (details) details.setAttribute("aria-hidden", "true");
  });
  return true;
}

function currentReviewCandidateFocusIndex() {
  const candidates = state.reviewCandidates || [];
  if (!candidates.length) return 0;
  const expanded = Number(state.selectedCandidateIndex);
  if (Number.isInteger(expanded) && expanded >= 0 && expanded < candidates.length) return expanded;
  return positiveModulo(Number(state.reviewCandidatePreviewIndex) || 0, candidates.length);
}

function animateReviewCandidateToIndex(targetIndex, options = {}) {
  const candidates = state.reviewCandidates || [];
  const list = $("reviewCandidateList");
  if (!list || !candidates.length) return false;
  const target = Math.max(0, Math.min(candidates.length - 1, Number(targetIndex)));
  if (!Number.isInteger(target)) return false;
  if (list._candidateTravelPending) {
    list._candidateQueuedIndex = target;
    return true;
  }

  let current = currentReviewCandidateFocusIndex();
  state.selectedCandidateIndex = -1;
  if (current === target) {
    applyReviewCandidatePreviewFocus(target);
    if (options.expand) {
      state.selectedCandidateIndex = target;
      renderReviewCandidates(currentDisplayResult());
    }
    return true;
  }

  const direction = target > current ? 1 : -1;
  list._candidateTravelPending = true;
  delete list._candidateQueuedIndex;

  const step = () => {
    current += direction;
    applyReviewCandidatePreviewFocus(current);
    if (current !== target) {
      clearTimeout(list._candidateTravelTimer);
      list._candidateTravelTimer = setTimeout(step, options.delay || 96);
      return;
    }
    list._candidateTravelPending = false;
    const queued = list._candidateQueuedIndex;
    delete list._candidateQueuedIndex;
    if (Number.isInteger(queued) && queued !== target) {
      animateReviewCandidateToIndex(queued, options);
    } else if (options.expand) {
      state.selectedCandidateIndex = target;
      renderReviewCandidates(currentDisplayResult());
    }
  };

  step();
  return true;
}

function scheduleReviewCandidateHoverFocus(index) {
  const list = $("reviewCandidateList");
  const candidates = state.reviewCandidates || [];
  if (!list || !candidates.length) return;
  if (Number(state.selectedCandidateIndex) >= 0) return;
  const target = Number(index);
  if (!Number.isInteger(target) || target < 0 || target >= candidates.length) return;
  const current = currentReviewCandidateFocusIndex();
  if (current === target && Number(state.selectedCandidateIndex) < 0) return;
  clearTimeout(list._candidateHoverTimer);
  list._candidateHoverTimer = setTimeout(() => {
    animateReviewCandidateToIndex(target, { delay: 82 });
  }, 70);
}


function flipReviewCandidateByWheel(direction) {
  const candidates = state.reviewCandidates || [];
  const result = currentDisplayResult();
  if (!candidates.length || !result?.fit) return false;
  const current = Number(state.selectedCandidateIndex);
  const fromIndex = Number.isInteger(current) && current >= 0 && current < candidates.length
    ? current
    : Number(state.reviewCandidatePreviewIndex) || 0;
  return applyReviewCandidatePreviewFocus(fromIndex + direction);
}

function normalizedWheelDelta(event) {
  const raw = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
  const factor = event.deltaMode === 1 ? 18 : event.deltaMode === 2 ? 80 : 1;
  return raw * factor;
}

function resultFromCandidate(baseResult, candidate, index) {
  if (!candidateCanView(candidate, baseResult)) {
    throw new Error("This candidate has no renderable series.");
  }
  const next = clonePlain(baseResult);
  const fit = clonePlain(candidate.fit || baseResult?.fit || {});
  const series = candidateSeriesForDisplay(candidate, baseResult);
  if (!hasCompleteSeries(series, "fitted") || !hasCompleteSeries(series, "measured")) {
    throw new Error("This candidate has no renderable measured/fitted series.");
  }
  if (candidate.n !== null && candidate.n !== undefined) fit.n = candidate.n;
  if (candidate.m !== null && candidate.m !== undefined) fit.m = candidate.m;
  if (candidate.params) fit.params = clonePlain(candidate.params);
  if (candidate.stats) fit.stats = clonePlain(candidate.stats);
  fit.series = series;
  const candidateDiagnosticsValue = candidateDiagnostics(candidate);
  fit.diagnostics = {
    ...(fit.diagnostics || {}),
    ...clonePlain(candidateDiagnosticsValue),
    candidate_source: candidate.source,
    candidate_label: candidate.label,
    candidate_rank: candidate.rank || index + 1,
    display_fit_source: candidate.source === "post_fit_diagnostic"
      ? "post_fit_model"
      : fit.diagnostics?.display_fit_source || candidate.source || "candidate",
    display_fit_switched: true,
  };
  next.fit = fit;
  next.series = series;
  next.model_context = clonePlain(candidate.model_context || next.model_context || {});
  next.parameter_schema = clonePlain(candidate.parameter_schema || next.parameter_schema || {});
  next.manual_capability = clonePlain(candidate.manual_capability || next.manual_capability || {});
  next.evaluator_kind = candidate.evaluator_kind || next.evaluator_kind;
  delete next.display_mode;
  next.candidate_selection = {
    index,
    rank: candidate.rank || index + 1,
    source: candidate.source,
    label: candidate.label,
  };
  return normalizeResultSeries(next);
}

function viewCandidate(index) {
  const displayResult = currentDisplayResult();
  const baseResult = reviewBaseResult(displayResult);
  const candidates = reviewCandidatePool(baseResult);
  const candidate = candidates[index] || state.reviewCandidates?.[index] || baseResult?.candidates?.[index];
  if (!candidate) {
    showError(new Error("Candidate is no longer available."));
    return;
  }
  try {
    const next = resultFromCandidate(baseResult, candidate, index);
    state.reviewCandidatePreviewIndex = index;
    state.selectedCandidateIndex = -1;
    state.manualDraftResult = null;
    setDisplayResult(next);
    renderResult(next, { syncEditor: true, markUnsaved: true });
    renderReviewResult(next);
    setStatus(`Viewing candidate #${candidate.rank || index + 1}: ${candidate.label || candidateSourceLabel(candidate.source)}.`);
  } catch (error) {
    showError(error);
  }
}

function renderReviewResult(result) {
  normalizeResultSeries(result);
  if (!result || !result.fit) return;
  const fit = result.fit;
  const scan = result.m_scan || [];
  $("reviewDataSummary").textContent = modelSummaryText();
  updateReviewCurrentModel(result);
  renderReviewSnapshot(result);
  renderReviewMlStatus(result);
renderReviewMetrics(fit, scan);
renderReviewSeries(result);
  renderReviewCandidates(result);
}

function syncManualInputsFromResult(result = currentDisplayResult()) {
  normalizeResultSeries(result);
  const fit = result?.fit;
  if (!fit) return;
  const diagnostics = fit.diagnostics || {};
  syncParamLabels(paramNamesFromDiagnostics(diagnostics));
  $("manualJ0").value = Number(fit.params[0]).toExponential(6);
  $("manualRs").value = Number(fit.params[1]).toExponential(6);
  $("manualRsh").value = Number(fit.params[2]).toExponential(6);
  $("manualK").value = Number(fit.params[3]).toExponential(6);
  $("manualM").value = Number(fit.m).toFixed(6).replace(/\.?0+$/, "");
  updateManualParamAvailability(diagnostics);
  updateManualParamDeltas();
}

function renderManualDraftResult(result) {
  normalizeResultSeries(result);
  if (!result?.fit) return;
  lockMeasuredSeries(result);
  drawFitChart(result.fit.series, "manualFitCanvas", { overlays: manualCheckpointOverlayItems(result) });
  $("manualSummary").textContent = `Current mean ${formatPct(result.fit.stats.mean)}, max ${formatPct(result.fit.stats.max)}.`;
  $("manualLiveStatus").textContent = summarizeManualFit(result);
  updateManualParamDeltas();
}

function manualParamsSnapshot() {
  return {
    j0: Number($("manualJ0").value),
    rs: Number($("manualRs").value),
    rsh: Number($("manualRsh").value),
    k: Number($("manualK").value),
    m: Number($("manualM").value),
  };
}

function manualBaselineParams() {
  const fit = currentDisplayResult()?.fit || state.autoFitResult?.fit || {};
  const params = fit.params || [];
  return {
    j0: Number(params[0]),
    rs: Number(params[1]),
    rsh: Number(params[2]),
    k: Number(params[3]),
    m: Number(fit.m),
  };
}

function safeManualParamValues() {
  const values = {};
  for (const control of manualParamControls) {
    values[control.key] = Number($(control.input)?.value);
  }
  return values;
}

function formatManualDelta(key, current, baseline) {
  if (!Number.isFinite(current) || !Number.isFinite(baseline)) return { text: "not numeric", direction: "neutral" };
  if (key === "m") {
    const delta = current - baseline;
    if (Math.abs(delta) < 1e-9) return { text: "base", direction: "neutral" };
    return { text: `${delta > 0 ? "+" : ""}${delta.toFixed(3)} vs base`, direction: delta > 0 ? "up" : "down" };
  }
  if (current <= 0 || baseline <= 0) {
    const delta = current - baseline;
    if (Math.abs(delta) < Math.max(Math.abs(baseline), 1) * 1e-9) return { text: "base", direction: "neutral" };
    return { text: `${delta > 0 ? "+" : ""}${formatSci(delta)} vs base`, direction: delta > 0 ? "up" : "down" };
  }
  const logDelta = Math.log10(current / baseline);
  if (Math.abs(logDelta) < 0.001) return { text: "base", direction: "neutral" };
  return { text: `${logDelta > 0 ? "+" : ""}${logDelta.toFixed(2)} log vs base`, direction: logDelta > 0 ? "up" : "down" };
}

function updateManualParamDeltas() {
  const baseline = manualBaselineParams();
  const current = safeManualParamValues();
  for (const control of manualParamControls) {
    const element = $(control.delta);
    if (!element) continue;
    const delta = formatManualDelta(control.key, current[control.key], baseline[control.key]);
    element.textContent = delta.text;
    element.dataset.direction = delta.direction;
  }
}

function syncHiddenManualInputs() {
  $("editJ0").value = $("manualJ0").value;
  $("editRs").value = $("manualRs").value;
  $("editRsh").value = $("manualRsh").value;
  $("editK").value = $("manualK").value;
  $("editM").value = $("manualM").value;
}

function clonePlain(value) {
  return JSON.parse(JSON.stringify(value));
}

function summarizeManualFit(result) {
  const fit = result?.fit;
  if (!fit) return "No fit.";
  const quality = suggestedQualityFromFit(fit);
  const worst = fit.diagnostics?.region_stats?.worst_region || "--";
  return `${quality.value} | mean ${formatPct(fit.stats.mean)} | max ${formatPct(fit.stats.max)} | worst ${worst}`;
}

function manualCheckpointOverlayItems(result = state.manualDraftResult) {
  const item = state.manualHistory.find((entry) => entry.id === state.manualHistoryActiveId);
  const series = item?.result?.fit?.series;
  if (!result?.fit?.series || !series?.fitted?.length) return [];
  return [{
    label: `Checkpoint ${item.created_at || ""}`.trim(),
    color: "#f5d28e",
    series,
  }];
}

function addManualHistory(trigger, result = state.manualDraftResult || currentDisplayResult()) {
  if (!result?.fit) return;
  const item = {
    id: `manual_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    trigger,
    params: manualParamsSnapshot(),
    result: clonePlain(result),
    summary: summarizeManualFit(result),
    created_at: new Date().toLocaleTimeString(),
    starred: false,
  };
  state.manualHistory.unshift(item);
  state.manualHistory = state.manualHistory.slice(0, 24);
  state.manualHistoryActiveId = item.id;
  renderManualHistory();
}

async function addManualCheckpointFromCurrent() {
  cancelPendingManualEvaluation();
  if (!currentFitSupportsBaseManualEvaluation()) {
    $("manualLiveStatus").textContent = currentManualCapabilityMessage();
    return;
  }
  $("manualLiveStatus").textContent = "Evaluating checkpoint...";
  const evaluated = await evaluateManualParams({ target: "manual" });
  if (!evaluated || !state.manualDraftResult?.fit) return;
  addManualHistory("Manual checkpoint", state.manualDraftResult);
  renderManualDraftResult(state.manualDraftResult);
  const summary = summarizeManualFit(state.manualDraftResult);
  $("manualLiveStatus").textContent = summary;
  $("manualLiveStatus").title = `Added checkpoint. ${summary}`;
}

function manualHistoryItemHtml(item, index) {
  const starred = Boolean(item.starred);
  return `
    <div class="manual-history-item ${item.id === state.manualHistoryActiveId ? "active" : ""} ${starred ? "is-starred" : ""}" role="button" tabindex="0" data-history-id="${item.id}">
      <span
        class="manual-history-star"
        role="button"
        tabindex="0"
        aria-label="${starred ? "Unstar checkpoint" : "Star checkpoint"}"
        aria-pressed="${starred ? "true" : "false"}"
        data-history-star="${item.id}"
      >${starred ? "&#11088;" : "&#9734;"}</span>
      <strong>${index + 1}. ${escapeHtml(item.trigger)} <small>${escapeHtml(item.created_at)}</small></strong>
      <span>${escapeHtml(item.summary)}</span>
      <span class="manual-history-param-row">
        <em>J0 ${formatSci(item.params.j0)}</em>
        <em>Rs ${formatSci(item.params.rs)}</em>
        <em>Rsh ${formatSci(item.params.rsh)}</em>
        <em>k ${formatSci(item.params.k)}</em>
        <em>m ${Number(item.params.m).toFixed(3)}</em>
      </span>
    </div>
  `;
}

function renderManualHistory() {
  const list = $("manualHistoryList");
  if (!state.manualHistory.length) {
    list.innerHTML = '';
    return;
  }
  list.innerHTML = state.manualHistory.map(manualHistoryItemHtml).join("");
}

function restoreManualHistory(id) {
  const item = state.manualHistory.find((entry) => entry.id === id);
  if (!item) return;
  if (!item.result?.fit) {
    $("manualSummary").textContent = `Imported checkpoint metadata only: ${item.summary || "no saved curve state"}`;
    return;
  }
  state.manualDraftResult = clonePlain(item.result);
  state.manualHistoryActiveId = item.id;
  renderManualDraftResult(state.manualDraftResult);
  syncManualInputsFromResult(state.manualDraftResult);
  renderManualHistory();
  $("manualSummary").textContent = `Restored checkpoint: ${item.summary}`;
}

function toggleManualHistoryStar(id) {
  const item = state.manualHistory.find((entry) => entry.id === id);
  if (!item) return;
  item.starred = !item.starred;
  renderManualHistory();
}

function clearManualHistory() {
  state.manualHistory = [];
  state.manualHistoryActiveId = null;
  renderManualHistory();
}

function scheduleManualLiveEvaluation(trigger = "Manual edit") {
  if (!currentFitSupportsBaseManualEvaluation()) {
    $("manualLiveStatus").textContent = currentManualCapabilityMessage();
    return;
  }
  syncHiddenManualInputs();
  updateManualParamDeltas();
  $("manualLiveStatus").textContent = "Updating fit...";
  if (state.manualHistoryTimer) clearTimeout(state.manualHistoryTimer);
  state.manualHistoryTimer = setTimeout(async () => {
    state.manualHistoryTimer = null;
    try {
      if ($("manualPage").classList.contains("hidden")) return;
      const applied = await evaluateManualParams({ live: true, target: "manual" });
      if (!applied || $("manualPage").classList.contains("hidden")) return;
      $("manualLiveStatus").textContent = `${summarizeManualFit(state.manualDraftResult)} | not saved`;
      $("manualSummary").textContent = "Manual fit updated. Add a checkpoint when this state is worth keeping.";
    } catch (error) {
      $("manualLiveStatus").textContent = error.message || String(error);
    }
  }, 220);
}
