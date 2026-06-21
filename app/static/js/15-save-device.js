/* ==========================================================================
   Save page and device metadata editing
   ========================================================================== */

const saveHypothesisAliases = new Map([
  ["none", "none"],
  ["leakage reduced", "leakage_reduced"],
  ["leakage increased", "leakage_increased"],
  ["recombination changed", "recombination_changed"],
  ["series resistance changed", "series_resistance_changed"],
  ["interface passivation", "interface_passivation"],
  ["other", "other"],
]);

const allowedSaveMemberNames = new Set(["lky", "lyy", "zyx", "thd", "cym", "ff", "hhj", "rl", "cw"]);
const saveCustomSelectIds = ["saveQuality", "saveLeakageSituation", "saveModelSituation", "saveModelFeedback"];

function saveHypothesisAliasKey(value) {
  return String(value || "").trim().toLowerCase().replace(/[-_]+/g, " ").replace(/\s+/g, " ");
}

function saveSelectLabel(select) {
  return select?.selectedOptions?.[0]?.textContent?.trim() || select?.value || "";
}

function closeSaveCustomSelects(except = null) {
  document.querySelectorAll(".save-custom-select.is-open").forEach((control) => {
    if (control === except) return;
    control.classList.remove("is-open");
    control.querySelector(".save-custom-select-button")?.setAttribute("aria-expanded", "false");
  });
  if (except !== $("saveHypothesis")?.closest(".field")?.querySelector(".save-custom-suggest")) {
    closeSaveHypothesisMenu();
  }
}

function syncSaveCustomSelect(selectOrId) {
  const select = typeof selectOrId === "string" ? $(selectOrId) : selectOrId;
  if (!select) return;
  const control = select.closest(".field")?.querySelector(".save-custom-select");
  const button = control?.querySelector(".save-custom-select-button");
  if (!control || !button) return;
  button.textContent = saveSelectLabel(select);
  control.querySelectorAll("[data-save-option]").forEach((optionButton) => {
    const active = optionButton.dataset.saveOption === select.value;
    optionButton.classList.toggle("active", active);
    optionButton.setAttribute("aria-selected", active ? "true" : "false");
  });
}

function syncSaveCustomSelects() {
  saveCustomSelectIds.forEach(syncSaveCustomSelect);
}

function setupSaveCustomSelects() {
  saveCustomSelectIds.forEach((id) => {
    const select = $(id);
    const field = select?.closest(".field");
    if (!select || !field || select.dataset.customSelectReady === "true") return;
    select.dataset.customSelectReady = "true";
    select.classList.add("save-native-select");
    const control = document.createElement("div");
    control.className = "save-custom-select";
    control.innerHTML = `
      <button class="save-custom-select-button" type="button" aria-haspopup="listbox" aria-expanded="false"></button>
      <div class="save-custom-select-menu" role="listbox">
        ${Array.from(select.options).map((option) => `
          <button
            type="button"
            role="option"
            data-save-option="${escapeHtml(option.value)}"
          >${escapeHtml(option.textContent || option.value)}</button>
        `).join("")}
      </div>
    `;
    field.appendChild(control);
    const button = control.querySelector(".save-custom-select-button");
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = !control.classList.contains("is-open");
      closeSaveCustomSelects(control);
      control.classList.toggle("is-open", open);
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
    control.querySelectorAll("[data-save-option]").forEach((optionButton) => {
      optionButton.addEventListener("click", (event) => {
        event.stopPropagation();
        select.value = optionButton.dataset.saveOption || "";
        select.dispatchEvent(new Event("change", { bubbles: true }));
        syncSaveCustomSelect(select);
        closeSaveCustomSelects();
      });
    });
    select.addEventListener("change", () => syncSaveCustomSelect(select));
    syncSaveCustomSelect(select);
  });
  if (!setupSaveCustomSelects.boundClose) {
    document.addEventListener("click", () => closeSaveCustomSelects());
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeSaveCustomSelects();
    });
    setupSaveCustomSelects.boundClose = true;
  }
  setupSaveHypothesisMenu();
}

function closeSaveHypothesisMenu() {
  const menu = $("saveHypothesis")?.closest(".field")?.querySelector(".save-custom-suggest");
  menu?.classList.remove("is-open");
}

function setupSaveHypothesisMenu() {
  const input = $("saveHypothesis");
  const field = input?.closest(".field");
  const datalist = $("saveHypothesisOptions");
  if (!input || !field || !datalist || input.dataset.customSuggestReady === "true") return;
  input.dataset.customSuggestReady = "true";
  input.removeAttribute("list");
  const menu = document.createElement("div");
  menu.className = "save-custom-suggest";
  menu.setAttribute("role", "listbox");
  field.appendChild(menu);

  function renderSuggestions() {
    const query = saveHypothesisAliasKey(input.value);
    const options = Array.from(datalist.options)
      .map((option) => option.value || option.textContent || "")
      .filter(Boolean)
      .filter((value) => !query || saveHypothesisAliasKey(value).includes(query));
    menu.innerHTML = options.map((value) => `
      <button type="button" role="option" data-save-suggestion="${escapeHtml(value)}">${escapeHtml(value)}</button>
    `).join("");
    menu.querySelectorAll("[data-save-suggestion]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        input.value = button.dataset.saveSuggestion || "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        closeSaveHypothesisMenu();
      });
    });
  }

  function openSuggestions(event) {
    event?.stopPropagation?.();
    renderSuggestions();
    closeSaveCustomSelects(menu);
    menu.classList.add("is-open");
  }

  input.addEventListener("focus", openSuggestions);
  input.addEventListener("click", openSuggestions);
  input.addEventListener("input", () => {
    renderSuggestions();
    menu.classList.add("is-open");
  });
}

function normalizeSaveHypothesisInput(value) {
  const key = saveHypothesisAliasKey(value);
  if (!key) return "";
  return saveHypothesisAliases.get(key) || "other";
}

function saveHypothesisCustomNote() {
  const input = $("saveHypothesis");
  if (!input) return "";
  const value = String(input.value || "").trim();
  const key = saveHypothesisAliasKey(value);
  return value && normalizeSaveHypothesisInput(value) === "other" && !saveHypothesisAliases.has(key) ? value : "";
}

function normalizedSaveMemberName() {
  return String($("saveMemberName")?.value || "").trim().toLowerCase();
}

function setDeviceStructureChecked(checked) {
  const input = $("saveDeviceChecked");
  if (input) input.checked = Boolean(checked);
}

function markDeviceStructureDirty() {
  setDeviceStructureChecked(false);
}

function syncSaveFieldsToRecordForm() {
  const member = normalizedSaveMemberName();
  const leakage = $("saveLeakageSituation")?.value || "";
  const trainingContext = typeof currentTrainingContextPayload === "function" ? currentTrainingContextPayload() : {};
  const batchTag = trainingContext.batch_tag || "accepted-fit";
  if ($("saveSampleId")) $("saveSampleId").value = member;
  if ($("saveBatch")) $("saveBatch").value = batchTag;
  $("sampleId").value = member;
  $("sampleBatch").value = batchTag;
  $("comparisonGroup").value = leakage;
  $("labelQuality").value = $("saveQuality").value;
  $("labelHypothesis").value = normalizeSaveHypothesisInput($("saveHypothesis").value) || "none";
  $("labelMainIssue").value = leakage && leakage !== "normal" ? "other" : "none";
  $("labelAccepted").checked = true;
  $("labelManualAdjusted").checked = state.manualHistory.length > 0;
  const reason = document.querySelector('[data-accept-reason="visual_fit_ok"]');
  if (reason) reason.checked = true;
}

function cloneDevicePreset(orientation = state.deviceOrientation) {
  const preset = deviceLayerPresets[orientation] || deviceLayerPresets.normal;
  return preset.map((layer) => ({ ...layer }));
}

function syncDeviceOrientationUi() {
  document.querySelectorAll("[data-device-orientation]").forEach((button) => {
    const active = button.dataset.deviceOrientation === state.deviceOrientation;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  const tabs = document.querySelector(".device-orientation-tabs");
  if (tabs) tabs.dataset.orientation = state.deviceOrientation;
  const stack = $("deviceStack");
  if (stack) stack.dataset.orientation = state.deviceOrientation;
  requestAnimationFrame(() => syncDeviceOrientationIndicator(state.deviceOrientation));
}

function setDeviceOrientation(orientation) {
  if (!deviceLayerPresets[orientation]) return;
  state.deviceOrientation = orientation;
  state.selectedDeviceLayerId = null;
  state.deviceLayers = cloneDevicePreset(orientation);
  $("deviceStack")?.classList.remove("is-expanded", "is-editing");
  markDeviceStructureDirty();
  syncDeviceOrientationUi();
  renderDeviceStack();
  animateDeviceStackSwitch();
  renderDeviceLayerEditor();
}

function syncDeviceOrientationIndicator(buttonOrOrientation, options = {}) {
  const tabs = document.querySelector(".device-orientation-tabs");
  if (!tabs) return;
  const button = typeof buttonOrOrientation === "string"
    ? tabs.querySelector(`[data-device-orientation="${buttonOrOrientation}"]`)
    : buttonOrOrientation;
  if (!button) return;
  const tabsRect = tabs.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const next = {
    x: buttonRect.left - tabsRect.left,
    y: buttonRect.top - tabsRect.top,
    w: buttonRect.width,
    h: buttonRect.height,
  };
  const previousX = parseFloat(tabs.style.getPropertyValue("--save-tab-x"));
  const previousW = parseFloat(tabs.style.getPropertyValue("--save-tab-w"));
  const prefix = options.hover ? "--save-hover" : "--save-tab";
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
    tabs.style.setProperty("--save-trail-x", `${trailX}px`);
    tabs.style.setProperty("--save-trail-y", `${next.y}px`);
    tabs.style.setProperty("--save-trail-w", `${trailRight - trailX}px`);
    tabs.style.setProperty("--save-trail-h", `${next.h}px`);
    tabs.classList.remove("is-moving");
    requestAnimationFrame(() => {
      tabs.classList.add("is-moving");
      clearTimeout(syncDeviceOrientationIndicator.timer);
      syncDeviceOrientationIndicator.timer = setTimeout(() => tabs.classList.remove("is-moving"), 320);
    });
  }
}

function clearDeviceOrientationHover() {
  document.querySelector(".device-orientation-tabs")?.classList.remove("is-hovering");
}

function animateDeviceStackSwitch() {
  const stack = $("deviceStack");
  if (!stack) return;
  stack.classList.remove("is-switching");
  void stack.offsetWidth;
  stack.classList.add("is-switching");
  window.setTimeout(() => stack.classList.remove("is-switching"), 560);
}

function renderDeviceStack() {
  const stack = $("deviceStack");
  if (!stack) return;
  stack.dataset.orientation = state.deviceOrientation;
  stack.innerHTML = state.deviceLayers.map((layer, index) => {
    const layerName = String(layer.name || "").trim();
    const isPrimary = layer.role === "absorber" || /(^|[-\s/])ink($|[-\s/])/i.test(layerName) || /pbs-?ink/i.test(layerName);
    const thickness = String(layer.thickness_nm || "").trim();
    const caption = thickness ? `${layer.role || "layer"} | ${thickness} nm` : (layer.role || "layer");
    const rowClass = [
      "device-layer-row",
      isPrimary ? "is-primary-layer" : "",
      layer.role === "modifier" ? "is-modifier-layer" : "",
    ].filter(Boolean).join(" ");
    const displayName = isPrimary ? "Ink" : (layerName || "Layer");
    return `
    <div class="${rowClass}" style="--layer-index:${index}">
      <button class="device-layer ${escapeHtml(layer.role || "modifier")} ${layer.id === state.selectedDeviceLayerId ? "active" : ""}" type="button" data-device-layer="${escapeHtml(layer.id)}">
        <span>${escapeHtml(displayName)}</span>
        <small>${escapeHtml(caption)}</small>
      </button>
      ${index < state.deviceLayers.length - 1 ? `<button class="add-modifier-btn" type="button" data-insert-after="${index}">+ modifier</button>` : ""}
    </div>
  `;
  }).join("");
  syncDeviceOrientationUi();
}

function syncDeviceStackLabels() {
  renderDeviceStack();
}

function selectedDeviceLayer() {
  return state.deviceLayers.find((layer) => layer.id === state.selectedDeviceLayerId) || state.deviceLayers[0];
}

function renderDeviceLayerEditor() {
  const editor = $("deviceLayerEditor");
  const layer = selectedDeviceLayer();
  if (!editor) return;
  if (!state.selectedDeviceLayerId || !layer) {
    editor.classList.remove("is-open");
    editor.classList.add("hidden");
    return;
  }
  editor.classList.remove("hidden");
  editor.classList.add("is-open");
  setTextIfPresent("deviceEditorTitle", layer.name || "Layer");
  setTextIfPresent("deviceEditorRole", layer.role || "modifier");
  $("deviceEditName").value = layer.name || "";
  $("deviceEditThickness").value = layer.thickness_nm || "";
  $("deviceEditAbsorption").value = layer.absorption_peak_nm || "";
}

function selectDeviceLayer(id) {
  if (!state.deviceLayers.some((layer) => layer.id === id)) return;
  state.selectedDeviceLayerId = id;
  $("deviceStack")?.classList.add("is-editing");
  renderDeviceStack();
  renderDeviceLayerEditor();
}

function closeDeviceLayerEditor() {
  state.selectedDeviceLayerId = null;
  $("deviceStack")?.classList.remove("is-editing");
  renderDeviceStack();
  renderDeviceLayerEditor();
}

function updateSelectedDeviceLayer(field, value) {
  const layer = selectedDeviceLayer();
  if (!layer) return;
  layer[field] = value;
  markDeviceStructureDirty();
  if (field === "name") {
    setTextIfPresent("deviceEditorTitle", value || "Layer");
    const button = Array.from(document.querySelectorAll("[data-device-layer]"))
      .find((item) => item.dataset.deviceLayer === layer.id)
      ?.querySelector("span");
    if (button) button.textContent = value || "Layer";
  }
}

function addModifierLayer(afterIndex) {
  const index = Number(afterIndex);
  if (!Number.isInteger(index)) return;
  state.deviceLayers.splice(index + 1, 0, {
    id: `modifier_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    role: "modifier",
    name: "Modifier",
    thickness_nm: "",
    absorption_peak_nm: "",
  });
  state.selectedDeviceLayerId = state.deviceLayers[index + 1].id;
  $("deviceStack")?.classList.add("is-editing");
  markDeviceStructureDirty();
  renderDeviceStack();
  renderDeviceLayerEditor();
}

function adjustAgingDaysByWheel(event) {
  event.preventDefault();
  const input = $("saveAgingDays");
  const current = agingDaysValue();
  const step = event.shiftKey ? 7 : 1;
  const next = event.deltaY < 0 ? current + step : Math.max(0, current - step);
  input.value = String(next);
}

function suggestedQualityFromFit(fit) {
  if (!fit) return { value: "acceptable", detail: "No fit loaded." };
  const mean = Number(fit.stats?.mean);
  const max = Number(fit.stats?.max);
  const warnings = fit.diagnostics?.warnings || [];
  const boundaryHits = fit.diagnostics?.boundary_hits || [];
  let value = "acceptable";
  if (Number.isFinite(mean) && Number.isFinite(max)) {
    if (mean <= 5 && max <= 20 && boundaryHits.length === 0) value = "good";
    else if (mean > 25 || max > 120 || warnings.length >= 5) value = "poor";
  }
  return {
    value,
    detail: `mean ${formatPct(mean)}, max ${formatPct(max)}, warnings ${warnings.length}, boundaries ${boundaryHits.length}`,
  };
}

function updateSaveSystemQuality() {
  const suggestion = suggestedQualityFromFit(currentAcceptedResult()?.fit);
  if ($("saveQuality")) $("saveQuality").value = suggestion.value;
  syncSaveCustomSelect("saveQuality");
}

function markSaveFieldInvalid(element) {
  if (!element) return;
  const field = element.closest(".field") || element;
  field.classList.remove("is-invalid-shake");
  void field.offsetWidth;
  field.classList.add("is-invalid-shake");
  window.setTimeout(() => field.classList.remove("is-invalid-shake"), 640);
}



function validateSavePageInputs() {
  const missing = [];
  const memberInput = $("saveMemberName");
  const agingInput = $("saveAgingDays");
  const qualityInput = $("saveQuality");
  const hypothesisInput = $("saveHypothesis");
  const leakageInput = $("saveLeakageSituation");
  const deviceCheckInput = $("saveDeviceChecked");
  const member = normalizedSaveMemberName();
  const deviceLayersComplete = state.deviceLayers.length > 0
    && state.deviceLayers.every((layer) => String(layer.name || "").trim());
  if (!member || !allowedSaveMemberNames.has(member)) {
    missing.push("Member name");
    markSaveFieldInvalid(memberInput);
  }
  if (!agingInput?.value.trim() || !Number.isFinite(Number(agingInput.value)) || Number(agingInput.value) < 0) {
    missing.push("Aging / test days");
    markSaveFieldInvalid(agingInput);
  }
  if (!qualityInput?.value.trim()) {
    missing.push("Label");
    markSaveFieldInvalid(qualityInput);
  }
  if (!hypothesisInput?.value.trim()) {
    missing.push("Self label");
    markSaveFieldInvalid(hypothesisInput);
  }
  if (!leakageInput?.value.trim()) {
    missing.push("Leakage situation");
    markSaveFieldInvalid(leakageInput);
  }
  if (!deviceStackPayload().length || !deviceLayersComplete) {
    missing.push("Device stack");
    markSaveFieldInvalid($("deviceStack"));
  }
  if (!deviceCheckInput?.checked) {
    missing.push("Structure checked");
    $("deviceStack")?.classList.add("is-expanded");
    markSaveFieldInvalid(deviceCheckInput || $("deviceStack"));
  }
  if (missing.length) {
    const firstInvalid = [
      memberInput,
      agingInput,
      qualityInput,
      hypothesisInput,
      leakageInput,
      deviceCheckInput,
    ].find((input) => input && input.closest(".field")?.classList.contains("is-invalid-shake"));
    firstInvalid?.focus?.();
    throw new Error("Save required fields need attention.");
  }
}

async function saveAcceptedFromPage() {
  const button = $("saveAcceptedRecordBtn");
  button?.classList.add("is-saving");
  try {
    validateSavePageInputs();
    syncSaveFieldsToRecordForm();
    $("savePageStatus").textContent = "Saving accepted record...";
    await saveCurrentRecord();
    $("savePageStatus").textContent = `Saved: ${$("recordStatus").textContent}. Exporting XLSX and replay pack...`;
    await exportComponentsXlsx();
    exportFitpack();
    $("savePageStatus").textContent = "Saved locally. Copy-friendly XLSX and replay pack export started.";
    showSaveSuccessAndReturnHome();
  } finally {
    window.setTimeout(() => button?.classList.remove("is-saving"), 520);
  }
}

function launchSaveConfetti() {
  const origin = { x: 0.5, y: 0.52 };
  if (typeof window.confetti === "function") {
    window.confetti({ particleCount: 90, spread: 62, origin });
    return;
  }

  const canvas = document.createElement("canvas");
  canvas.className = "save-confetti-canvas";
  const context = canvas.getContext("2d");
  if (!context) return;
  const colors = ["#78f2e5", "#7fd6ff", "#d8c4ff", "#f5d28e", "#9ff7c8"];
  const particles = Array.from({ length: 110 }, () => ({
    x: window.innerWidth * origin.x + (Math.random() - 0.5) * 130,
    y: window.innerHeight * origin.y + (Math.random() - 0.5) * 40,
    vx: (Math.random() - 0.5) * 9,
    vy: -Math.random() * 9 - 4,
    size: Math.random() * 5 + 3,
    rotation: Math.random() * Math.PI,
    vr: (Math.random() - 0.5) * 0.26,
    color: colors[Math.floor(Math.random() * colors.length)],
    life: Math.random() * 26 + 54,
  }));

  function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  function frame() {
    context.clearRect(0, 0, canvas.width, canvas.height);
    let alive = 0;
    for (const particle of particles) {
      if (particle.life <= 0) continue;
      alive += 1;
      particle.life -= 1;
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.vy += 0.22;
      particle.vx *= 0.985;
      particle.rotation += particle.vr;
      context.save();
      context.translate(particle.x, particle.y);
      context.rotate(particle.rotation);
      context.globalAlpha = Math.max(0, Math.min(1, particle.life / 50));
      context.fillStyle = particle.color;
      context.fillRect(-particle.size / 2, -particle.size / 2, particle.size, particle.size * 0.64);
      context.restore();
    }
    if (alive) requestAnimationFrame(frame);
    else canvas.remove();
  }

  resize();
  document.body.appendChild(canvas);
  requestAnimationFrame(frame);
}

function showSaveSuccessAndReturnHome() {
  setHidden("saveSuccessOverlay", false);
  launchSaveConfetti();
  window.setTimeout(() => {
    setHidden("saveSuccessOverlay", true);
    closeSavePage();
    showHomePage();
    setStatus("Record saved.");
  }, 1100);
}
