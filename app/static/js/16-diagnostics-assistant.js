/* ==========================================================================
   Fit diagnostics and assistant rendering
   ========================================================================== */

function formatRegionStat(row) {
  if (!row || row.mean === null || row.mean === undefined) return "--";
  return `${Number(row.mean).toFixed(2)}% / ${Number(row.max).toFixed(2)}%`;
}

function renderRegionStats(stats) {
  $("regionReverse").textContent = formatRegionStat(stats?.reverse);
  $("regionNearZero").textContent = formatRegionStat(stats?.near_zero);
  $("regionForward").textContent = formatRegionStat(stats?.forward);
  $("regionHighForward").textContent = formatRegionStat(stats?.high_forward);
}

function initializationDiagnosticView(init = {}) {
  const initLabel = init.selected || "--";
  const requested = init.requested_method;
  const candidateScores = (init.candidates || [])
    .map((item) => `${item.name}: ${item.score == null ? "--" : Number(item.score).toFixed(2)}`)
    .join(" | ");
  const initDetail = requested
    ? `requested ${requested}${candidateScores ? ` | ${candidateScores}` : ""}`
    : "No initialization diagnostics.";
  return { initLabel, initDetail };
}

function renderInitializationDiagnostics(init = {}) {
  const { initLabel, initDetail } = initializationDiagnosticView(init);
  $("diagInitialization").textContent = initLabel;
  $("diagInitializationDetail").textContent = initDetail;
  $("coreInit").textContent = initLabel;
  $("coreInitDetail").textContent = initDetail;
}

function fallbackDiagnosticView(deInfo = {}) {
  let fallbackLabel = "Not used";
  let fallbackDetail = "Differential Evolution fallback was not triggered.";
  if (deInfo.attempted && deInfo.used) {
    fallbackLabel = "Selected";
    fallbackDetail = "Differential Evolution fallback improved the fit.";
  } else if (deInfo.attempted) {
    fallbackLabel = "Tried";
    fallbackDetail = "Differential Evolution ran but did not beat the current fit.";
  }
  return { fallbackLabel, fallbackDetail };
}

function renderFallbackDiagnostics(deInfo = {}) {
  const { fallbackLabel, fallbackDetail } = fallbackDiagnosticView(deInfo);
  $("diagFallback").textContent = fallbackLabel;
  $("diagFallbackDetail").textContent = fallbackDetail;
  $("coreFallback").textContent = fallbackLabel;
}

function renderIdentifiabilityDiagnostics(ident = {}) {
  const weakParameters = ident.weak_parameters || [];
  const strongParameters = ident.strong_parameters || [];
  const weakLabel = weakParameters.length ? weakParameters.join(", ") : "No weak params";
  const strongDetail = strongParameters.length ? `strong: ${strongParameters.join(", ")}` : "No strongly constrained parameter flagged.";
  $("diagIdentifiability").textContent = weakLabel;
  $("diagIdentifiabilityDetail").textContent = strongDetail;
  $("coreWeakParams").textContent = weakLabel;
}

function renderBoundaryDiagnostics(boundaryHits = []) {
  const boundaryText = boundaryHits.length ? boundaryHits.map((item) => `${item.parameter} ${item.side}`).join(", ") : "None";
  $("diagBoundaries").textContent = String(boundaryHits.length);
  $("diagBoundariesDetail").textContent = boundaryText;
  $("coreBoundaryHits").textContent = boundaryText;
}

function renderDiagnosticWarnings(warnings = []) {
  $("diagnosticWarnings").innerHTML = warnings.length
    ? warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : "<li>No warnings.</li>";
}

function renderCoreDiagnostics(diagnostics = {}) {
  renderInitializationDiagnostics(diagnostics.initialization || {});
  renderFallbackDiagnostics(diagnostics.de_fallback || {});
  renderIdentifiabilityDiagnostics(diagnostics.identifiability || {});
  renderBoundaryDiagnostics(diagnostics.boundary_hits || []);
  renderDiagnosticWarnings(diagnostics.warnings || []);
}

function strategyName(row) {
  return row?.preset || row?.strategy || "--";
}

function selectedStrategySummary(rows = []) {
  const selected = rows[0];
  const quick = rows.find((row) => strategyName(row) === "quick_global") || rows.find((row) => row.strategy === "quick_global");
  const selectedName = strategyName(selected);
  const quickMean = quick?.stats?.mean;
  const selectedMean = selected?.stats?.mean;
  const improvement = Number.isFinite(Number(quickMean)) && Number.isFinite(Number(selectedMean))
    ? Number(quickMean) - Number(selectedMean)
    : null;
  const changedStrategy = quick && selected !== quick;
  return { selected, selectedName, improvement, changedStrategy };
}

function renderStrategyGainSummary(rows = []) {
  const { selected, selectedName, improvement, changedStrategy } = selectedStrategySummary(rows);
  $("deepSummaryTitle").textContent = changedStrategy
    ? `Improved by ${formatPct(improvement)}`
    : "No strategy gain";
  $("deepSummaryDetail").textContent = changedStrategy
    ? `Compared ${rows.length} strategies against Fast Fit.`
    : `Compared ${rows.length} strategies; Fast Fit remained competitive.`;
  $("deepSummarySelected").textContent = selectedName;
  $("deepSummaryImprovement").textContent = `mean ${formatPct(selected?.stats?.mean)}, max ${formatPct(selected?.stats?.max)}, score ${selected?.score == null ? "--" : Number(selected.score).toFixed(2)}`;
}

function renderExponentProfileSummary(result, mProfile = {}) {
  const scanRows = result?.m_scan || [];
  const bestM = scanRows[0];
  if (!bestM) {
    $("deepSummaryM").textContent = "Not run";
    $("deepSummaryMDetail").textContent = "n/m were kept fixed.";
    return;
  }
  const status = mProfile.status === "used_for_display" ? "used" : "diagnostic";
  const meanGain = mProfile.mean_improvement;
  $("deepSummaryM").textContent = `${formatExponentPair(bestM)} ${status}`;
  $("deepSummaryMDetail").textContent = Number.isFinite(Number(meanGain))
    ? `best n/m mean ${formatPct(bestM.stats?.mean)} (${Number(meanGain) >= 0 ? "+" : ""}${Number(meanGain).toFixed(2)}% vs selected strategy)`
    : `best n/m mean ${formatPct(bestM.stats?.mean)}, max ${formatPct(bestM.stats?.max)}`;
}

function renderDeepStrategySummary(result) {
  const rows = result?.strategy_sweep || [];
  const fit = result?.fit || {};
  const mProfile = fit.diagnostics?.m_profile || {};
  setHidden("deepStrategySummary", rows.length === 0);
  if (!rows.length) return;

  renderStrategyGainSummary(rows);
  renderExponentProfileSummary(result, mProfile);
}

function updateDiagnosticVisibility(result) {
  const scanRows = result.m_scan || [];
  const strategyRows = result.strategy_sweep || [];
  const modelRows = [...(result.model_comparison || []), ...(result.post_fit_models || [])];

  setHidden("scanTab", scanRows.length === 0);
  setHidden("deepStrategySummary", strategyRows.length === 0);
  setHidden("strategySection", strategyRows.length === 0);
  setHidden("modelSection", modelRows.length === 0);

  if (scanRows.length === 0 && activeView() === "scan") {
    setView("fit");
  }
}

function assistantListItems(notes = [], advice = []) {
  const noteItems = Array.from(new Set((notes || []).map((item) => String(item).trim()).filter(Boolean)));
  const adviceItems = (advice || [])
    .map((item) => [item.title || "Next step", [item.detail, item.action].filter(Boolean).join(" ").trim()])
    .filter(([, detail]) => detail);
  return { noteItems, adviceItems };
}

function compactReviewText(text, maxLength = 118) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  return value.length > maxLength ? `${value.slice(0, maxLength - 1).trim()}...` : value;
}

function reviewAssistantSummaryHtml(noteItems, adviceItems) {
  if (!noteItems.length && !adviceItems.length) {
    return `
      <div class="assistant-item">
        <strong>No analysis yet.</strong>
        <span>Run a fit to generate structured interpretation.</span>
      </div>
    `;
  }
  const primaryNote = noteItems[0] ? compactReviewText(noteItems[0]) : "";
  const secondaryNote = noteItems[1] ? compactReviewText(noteItems[1], 96) : "";
  const primaryAdvice = adviceItems[0]
    ? compactReviewText(`${adviceItems[0][0]}: ${adviceItems[0][1]}`, 108)
    : "";
  return [
    primaryNote
      ? `<div class="assistant-item"><strong>Fit signal</strong><span>${escapeHtml(primaryNote)}</span></div>`
      : "",
    secondaryNote
      ? `<div class="assistant-item"><strong>Check</strong><span>${escapeHtml(secondaryNote)}</span></div>`
      : "",
    primaryAdvice
      ? `<div class="assistant-item"><strong>Next</strong><span>${escapeHtml(primaryAdvice)}</span></div>`
      : "",
  ].filter(Boolean).join("");
}

function renderAssistant(notes, advice) {
  const list = $("assistantList");
  const { noteItems, adviceItems } = assistantListItems(notes, advice);

  if (!noteItems.length && !adviceItems.length) {
    list.innerHTML = `
      <div class="assistant-item">
        <strong>No analysis yet.</strong>
        <span>Run a fit to generate structured interpretation and next-step suggestions.</span>
      </div>
    `;
    setHtmlIfPresent("reviewAssistantList", reviewAssistantSummaryHtml(noteItems, adviceItems));
    return;
  }

  const cards = [];
  if (noteItems.length) {
    cards.push(`
      <div class="assistant-item">
        <strong>What the fit says</strong>
        <span>${noteItems.map((item) => `- ${escapeHtml(item)}`).join("<br />")}</span>
      </div>
    `);
  }
  if (adviceItems.length) {
    cards.push(`
      <div class="assistant-item">
        <strong>What to try next</strong>
        <span>${adviceItems.map(([title, detail]) => `- ${escapeHtml(title)}: ${escapeHtml(detail)}`).join("<br />")}</span>
      </div>
    `);
  }
  list.innerHTML = cards.join("").replaceAll(String.fromCharCode(37413, 63), "- ");
  setHtmlIfPresent("reviewAssistantList", reviewAssistantSummaryHtml(noteItems, adviceItems));
}

function renderScanTable(rows) {
  const body = $("scanRows");
  if (!rows || rows.length === 0) {
    body.innerHTML = '<tr><td colspan="9">No exponent diagnostic was run.</td></tr>';
    return;
  }
  body.innerHTML = rows.map((row, idx) => `
    <tr>
      <td>${idx + 1}</td>
      <td>${Number(row.n ?? 1.4).toFixed(3)}</td>
      <td>${Number(row.m).toFixed(3)}</td>
      <td>${formatPct(row.stats.mean)}</td>
      <td>${formatPct(row.stats.max)}</td>
      <td>${formatSci(row.params[0])}</td>
      <td>${formatSci(row.params[1])}</td>
      <td>${formatSci(row.params[2])}</td>
      <td>${formatSci(row.params[3])}</td>
    </tr>
  `).join("");
}

function renderStrategyTable(rows) {
  const body = $("strategyRows");
  if (!rows || rows.length === 0) {
    body.innerHTML = '<tr><td colspan="8">No strategy sweep was run.</td></tr>';
    return;
  }
  body.innerHTML = rows.map((row, idx) => {
    const worst = row.region_stats?.worst_region || "--";
    return `
      <tr>
        <td>${idx + 1}</td>
        <td>${escapeHtml(row.preset || row.strategy || "--")}</td>
        <td>${row.score == null ? "--" : Number(row.score).toFixed(2)}</td>
        <td>${formatPct(row.stats?.mean)}</td>
        <td>${formatPct(row.stats?.max)}</td>
        <td>${escapeHtml(worst)}</td>
        <td>${row.boundary_hit_count ?? 0}</td>
        <td>${row.warning_count ?? 0}</td>
      </tr>
    `;
  }).join("");
}

function normalizeModelTableRows(rows = [], postRows = [], diagnosticAblations = []) {
  const baselineRows = (rows || [])
    .filter((row) => row.category !== "diagnostic_ablation")
    .map((row) => ({ ...row, display_name: `${row.stage || "M?"}: ${row.name}`, source: "baseline" }));
  const ablationRows = (diagnosticAblations.length ? diagnosticAblations : (rows || []).filter((row) => row.category === "diagnostic_ablation"))
    .map((row) => ({ ...row, display_name: row.name, source: "ablation" }));
  const postFitRows = (postRows || []).map((row) => ({
    ...row,
    stage: row.diagnostics?.model_stage || row.name,
    display_name: row.status && row.status !== "ok" ? `${row.name} (${row.status})` : row.name,
    source: "post-fit",
  }));
  return { baselineRows, ablationRows, postFitRows };
}

function recommendedBaselineLabel(recommendedBaseline) {
  return recommendedBaseline
    ? `${recommendedBaseline.recommended_baseline_stage || recommendedBaseline.stage || "--"} (${recommendedBaseline.name || "--"})`
    : "not selected";
}

function modelDecisionLabel(row = {}) {
  if (row.diagnostics?.selected_for_replacement) return "Selected";
  if (row.is_recommended_baseline || row.diagnostics?.selected_for_baseline) {
    return `Baseline ${row.recommended_baseline_stage || row.diagnostics?.recommended_baseline_stage || row.stage || ""}`.trim();
  }
  if (row.diagnostics?.selected_for_nested_model) return "No-k option";
  if (row.category === "diagnostic_ablation" || row.source === "ablation") return "Ablation";
  return "Diagnostic";
}

function modelTableRowHtml(row, idx) {
  return `
    <tr>
      <td>${idx + 1}</td>
      <td>${escapeHtml(row.display_name || row.name || "--")}</td>
      <td>${formatFixed(row.bic)}</td>
      <td>${formatPct(row.stats?.mean)}</td>
      <td>${formatPct(row.stats?.max)}</td>
      <td>${row.free_parameter_count ?? "--"}</td>
      <td>${escapeHtml(row.diagnostics?.physical_confidence || row.diagnostics?.publication_confidence || "--")}</td>
      <td>${escapeHtml(modelDecisionLabel(row))}</td>
    </tr>
  `;
}

function renderModelTable(rows, postRows = [], recommendedBaseline = null, diagnosticAblations = []) {
  const body = $("modelRows");
  const { baselineRows, ablationRows, postFitRows } = normalizeModelTableRows(rows, postRows, diagnosticAblations);
  if (!baselineRows.length && !ablationRows.length && !postFitRows.length) {
    body.innerHTML = '<tr><td colspan="8">No model comparison was run.</td></tr>';
    return;
  }
  const sections = [];
  if (baselineRows.length) {
    sections.push(`<tr><td colspan="8"><strong>Recommended baseline:</strong> ${escapeHtml(recommendedBaselineLabel(recommendedBaseline))}</td></tr>`);
    sections.push(...baselineRows.map(modelTableRowHtml));
  }
  if (ablationRows.length) {
    sections.push('<tr><td colspan="8"><strong>Diagnostic ablation models</strong></td></tr>');
    sections.push(...ablationRows.map((row, idx) => modelTableRowHtml(row, baselineRows.length + idx)));
  }
  if (postFitRows.length) {
    sections.push('<tr><td colspan="8"><strong>Post-fit physical and diagnostic candidates</strong></td></tr>');
    sections.push(...postFitRows.map((row, idx) => modelTableRowHtml(row, baselineRows.length + ablationRows.length + idx)));
  }
  body.innerHTML = sections.join("");
}
