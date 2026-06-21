/* ==========================================================================
   Status, element helpers, and API contract bootstrap
   ========================================================================== */

function setStatus(text) {
  setTextIfPresent("statusText", text);
}

function setLoading(visible, title = "Running fit...", hint = "The plot will update after the current fitting task finishes.", options = {}) {
  const overlay = $("loadingOverlay");
  setHidden("loadingOverlay", !visible);
  if (overlay) overlay.classList.toggle("diagnostic-loading", Boolean(visible && options.diagnostic));
  const loadingTitle = $("loadingTitle");
  loadingTitle.textContent = title;
  loadingTitle.setAttribute("data-loading-text", title);
  $("loadingHint").textContent = hint;
}

function setDisabledIfPresent(id, disabled) {
  const element = $(id);
  if (element) element.disabled = disabled;
}

function setHtmlIfPresent(id, html) {
  const element = $(id);
  if (element) element.innerHTML = html;
}

function setTextIfPresent(id, text) {
  const element = $(id);
  if (element) element.textContent = text;
}

function pulseControl(id) {
  const element = $(id);
  if (!element) return;
  element.classList.remove("is-pulsing");
  void element.offsetWidth;
  element.classList.add("is-pulsing");
}

function triggerFilePicker(inputId) {
  const input = $(inputId);
  input.value = "";
  input.click();
}

function setHomeImportMenuOpen(open) {
  const radial = $("homeImportRadial");
  const trigger = $("homeImportMenuBtn");
  const homePage = $("homePage");
  if (!radial || !trigger) return;
  radial.classList.toggle("is-open", Boolean(open));
  if (homePage) homePage.classList.toggle("menu-open", Boolean(open));
  trigger.setAttribute("aria-expanded", open ? "true" : "false");
}

function updateHomeMegaIndicator(button, open = true, animateTrail = true) {
  const tabs = button?.closest(".home-mega-tabs") || document.querySelector(".home-mega-tabs");
  if (!tabs) return;
  if (!open || !button) {
    tabs.classList.remove("is-open", "is-moving");
    delete tabs.dataset.hasMegaIndicator;
    return;
  }

  const tabsRect = tabs.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const next = {
    x: buttonRect.left - tabsRect.left,
    y: buttonRect.top - tabsRect.top,
    w: buttonRect.width,
    h: buttonRect.height,
  };
  const current = {
    x: tabs.style.getPropertyValue("--mega-x") || `${next.x}px`,
    y: tabs.style.getPropertyValue("--mega-y") || `${next.y}px`,
    w: tabs.style.getPropertyValue("--mega-w") || `${next.w}px`,
    h: tabs.style.getPropertyValue("--mega-h") || `${next.h}px`,
  };
  const hasPrevious = tabs.dataset.hasMegaIndicator === "true";
  const previous = {
    x: parseFloat(current.x),
    y: parseFloat(current.y),
    w: parseFloat(current.w),
    h: parseFloat(current.h),
  };
  const moved =
    Math.abs(previous.x - next.x) > 0.5 ||
    Math.abs(previous.y - next.y) > 0.5 ||
    Math.abs(previous.w - next.w) > 0.5 ||
    Math.abs(previous.h - next.h) > 0.5;

  if (Math.abs(previous.y - next.y) <= 2) {
    const trailX = Math.min(previous.x, next.x);
    const trailRight = Math.max(previous.x + previous.w, next.x + next.w);
    tabs.style.setProperty("--mega-trail-x", `${trailX}px`);
    tabs.style.setProperty("--mega-trail-y", `${next.y}px`);
    tabs.style.setProperty("--mega-trail-w", `${trailRight - trailX}px`);
    tabs.style.setProperty("--mega-trail-h", `${next.h}px`);
  } else {
    tabs.style.setProperty("--mega-trail-x", current.x);
    tabs.style.setProperty("--mega-trail-y", current.y);
    tabs.style.setProperty("--mega-trail-w", current.w);
    tabs.style.setProperty("--mega-trail-h", current.h);
  }
  tabs.style.setProperty("--mega-x", `${next.x}px`);
  tabs.style.setProperty("--mega-y", `${next.y}px`);
  tabs.style.setProperty("--mega-w", `${next.w}px`);
  tabs.style.setProperty("--mega-h", `${next.h}px`);
  tabs.dataset.hasMegaIndicator = "true";
  tabs.classList.add("is-open");

  if (hasPrevious && moved && animateTrail) {
    tabs.classList.remove("is-moving");
    window.requestAnimationFrame(() => {
      tabs.classList.add("is-moving");
      window.clearTimeout(updateHomeMegaIndicator.trailTimer);
      updateHomeMegaIndicator.trailTimer = window.setTimeout(() => {
        tabs.classList.remove("is-moving");
      }, 260);
    });
  }
}

function setHomeMegaPanel(panelName, open = true) {
  const panel = $("homeMegaPanel");
  if (!panel) return;
  const wasOpen = !panel.classList.contains("hidden");
  const previousTarget = panel.dataset.activePanel || "workflow";
  const target = panelName || panel.dataset.activePanel || "workflow";
  const targetButton = document.querySelector(`[data-home-mega="${target}"]`);
  if (open && wasOpen && target !== previousTarget) {
    ghostHomeMegaContent(panel, panel.querySelector(`[data-home-mega-panel="${previousTarget}"]`));
  }
  panel.dataset.activePanel = target;
  setHidden("homeMegaPanel", !open);
  updateHomeMegaIndicator(targetButton, open);
  document.querySelectorAll("[data-home-mega]").forEach((button) => {
    const active = button.dataset.homeMega === target && open;
    button.classList.toggle("active", active);
    button.setAttribute("aria-expanded", active ? "true" : "false");
  });
  document.querySelectorAll("[data-home-mega-panel]").forEach((content) => {
    content.classList.toggle("hidden", content.dataset.homeMegaPanel !== target);
  });
  if (open) {
    panel.classList.remove("is-switching");
    window.requestAnimationFrame(() => panel.classList.add("is-switching"));
  } else {
    panel.classList.remove("is-switching");
  }
}

function ghostHomeMegaContent(panel, content) {
  if (!panel || !content) return;
  panel.querySelector(".home-mega-content-ghost")?.remove();
  const ghost = content.cloneNode(true);
  ghost.classList.remove("hidden");
  ghost.classList.add("home-mega-content-ghost");
  ghost.setAttribute("aria-hidden", "true");
  ghost.querySelectorAll("[id]").forEach((element) => element.removeAttribute("id"));
  ghost.querySelectorAll("[tabindex]").forEach((element) => element.removeAttribute("tabindex"));
  ghost.querySelectorAll("a, button, input, select, textarea").forEach((element) => {
    element.setAttribute("tabindex", "-1");
  });
  panel.appendChild(ghost);
  window.setTimeout(() => {
    if (ghost.parentElement) ghost.remove();
  }, 300);
}

function closeHomeMegaPanel() {
  const panel = $("homeMegaPanel");
  const active = panel?.dataset.activePanel || "workflow";
  setHomeMegaPanel(active, false);
  document.querySelectorAll("[data-workflow-detail]").forEach((step) => step.classList.remove("is-active"));
  setHomeWorkflowDetail(null);
  document.querySelectorAll("[data-model-title]").forEach((card) => card.classList.remove("is-active"));
  setHomeModelDetail(null);
  panel?.querySelector(".home-mega-content-ghost")?.remove();
}

function setHomeWorkflowDetail(step) {
  const detail = $("homeWorkflowDetail");
  if (!detail) return;
  const fallback = detail.dataset.defaultText || "";
  const nextText = step?.dataset.workflowDetail || fallback;
  if (detail.textContent.trim() === nextText) return;
  detail.textContent = nextText;
  detail.classList.remove("is-changing");
  void detail.offsetWidth;
  detail.classList.add("is-changing");
}

function setHomeModelDetail(card) {
  const detail = $("homeModelDetail");
  if (!detail) return;
  const defaults = {
    role: "Model role",
    title: "Hover a model.",
    formula: "J model = transport assumption + residual evidence",
    detail: "Each candidate is ranked by fit quality and physical plausibility before it becomes a final record.",
  };
  const next = {
    role: card?.dataset.modelRole || defaults.role,
    title: card?.dataset.modelTitle || defaults.title,
    formula: card?.dataset.modelFormula || defaults.formula,
    detail: card?.dataset.modelDetail || defaults.detail,
  };
  const role = detail.querySelector("[data-model-detail-role]");
  const title = detail.querySelector("[data-model-detail-title]");
  const formula = detail.querySelector("[data-model-detail-formula]");
  const text = detail.querySelector("[data-model-detail-text]");
  if (role) role.textContent = next.role;
  if (title) title.textContent = next.title;
  if (formula) formula.textContent = next.formula;
  if (text) text.textContent = next.detail;
  detail.classList.remove("is-changing");
  void detail.offsetWidth;
  detail.classList.add("is-changing");
}

function onIfPresent(id, eventName, handler, options) {
  const element = $(id);
  if (element) element.addEventListener(eventName, handler, options);
}

function profileValuesString(values, fallback) {
  if (!Array.isArray(values) || !values.length) return fallback;
  const numeric = values.map(Number).filter((value) => Number.isFinite(value) && value > 0);
  return numeric.length ? numeric.join(", ") : fallback;
}

function defaultParamNamesFromContract() {
  const params = fitContract?.parameter_schema?.parameters || [];
  const names = params.map((item) => String(item?.name || "").trim()).filter(Boolean);
  return names.length >= 4 ? names.slice(0, 4) : ["J0", "Rs", "Rsh", "k"];
}

async function loadFitContract() {
  const response = await fetch("/api/fit-contract");
  const payload = await response.json();
  if (!payload.ok) {
    throw new Error(payload.error || payload.detail || "Could not load fit contract.");
  }
  fitContract = payload.contract || null;
  const defaults = fitContract?.defaults || {};
  internalNProfileValues = profileValuesString(defaults.n_values, internalNProfileValues);
  internalMProfileValues = profileValuesString(defaults.m_values, internalMProfileValues);
}
