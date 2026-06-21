/* ==========================================================================
   Event binding and application bootstrap
   ========================================================================== */

function bindHomeEvents() {
  const megaRoot = document.querySelector("[data-home-mega-root]");
  let megaResizeFrame = 0;
  let megaCloseTimer = 0;
  const cancelMegaClose = () => {
    window.clearTimeout(megaCloseTimer);
    megaCloseTimer = 0;
  };
  const scheduleMegaClose = () => {
    window.clearTimeout(megaCloseTimer);
    megaCloseTimer = window.setTimeout(closeHomeMegaPanel, 180);
  };
  document.querySelectorAll("[data-home-mega]").forEach((button) => {
    button.addEventListener("pointerenter", () => {
      cancelMegaClose();
      setHomeMegaPanel(button.dataset.homeMega, true);
    });
    button.addEventListener("focus", () => {
      cancelMegaClose();
      setHomeMegaPanel(button.dataset.homeMega, true);
    });
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      cancelMegaClose();
      const isOpen = !$("homeMegaPanel")?.classList.contains("hidden");
      const active = $("homeMegaPanel")?.dataset.activePanel;
      setHomeMegaPanel(button.dataset.homeMega, !(isOpen && active === button.dataset.homeMega));
    });
  });
  document.querySelectorAll("[data-workflow-detail]").forEach((step) => {
    step.addEventListener("pointerenter", () => {
      document.querySelectorAll("[data-workflow-detail]").forEach((item) => item.classList.toggle("is-active", item === step));
      setHomeWorkflowDetail(step);
    });
    step.addEventListener("focus", () => {
      document.querySelectorAll("[data-workflow-detail]").forEach((item) => item.classList.toggle("is-active", item === step));
      setHomeWorkflowDetail(step);
    });
    step.addEventListener("pointerleave", () => {
      step.classList.remove("is-active");
      setHomeWorkflowDetail(null);
    });
    step.addEventListener("blur", () => {
      step.classList.remove("is-active");
      setHomeWorkflowDetail(null);
    });
  });
  document.querySelectorAll("[data-model-title]").forEach((card) => {
    card.addEventListener("pointerenter", () => {
      document.querySelectorAll("[data-model-title]").forEach((item) => item.classList.toggle("is-active", item === card));
      setHomeModelDetail(card);
    });
    card.addEventListener("focus", () => {
      document.querySelectorAll("[data-model-title]").forEach((item) => item.classList.toggle("is-active", item === card));
      setHomeModelDetail(card);
    });
    card.addEventListener("pointerleave", () => {
      card.classList.remove("is-active");
      setHomeModelDetail(null);
    });
    card.addEventListener("blur", () => {
      card.classList.remove("is-active");
      setHomeModelDetail(null);
    });
  });
  if (megaRoot) {
    megaRoot.addEventListener("pointerenter", cancelMegaClose);
    megaRoot.addEventListener("pointerleave", scheduleMegaClose);
  }
  window.addEventListener("resize", () => {
    window.cancelAnimationFrame(megaResizeFrame);
    megaResizeFrame = window.requestAnimationFrame(() => {
      const panel = $("homeMegaPanel");
      if (!panel || panel.classList.contains("hidden")) return;
      const active = panel.dataset.activePanel || "workflow";
      updateHomeMegaIndicator(document.querySelector(`[data-home-mega="${active}"]`), true, false);
    });
  });
  onIfPresent("homeImportMenuBtn", "click", (event) => {
    event.stopPropagation();
    setHomeImportMenuOpen(!$("homeImportRadial")?.classList.contains("is-open"));
  });
  $("homeChooseFileBtn").addEventListener("click", () => {
    setHomeImportMenuOpen(false);
    triggerFilePicker("fileInput");
  });
  $("homeTxtImportBtn").addEventListener("click", () => {
    setHomeImportMenuOpen(false);
    triggerFilePicker("txtInput");
  });
  $("homeImportFitpackBtn").addEventListener("click", () => {
    setHomeImportMenuOpen(false);
    triggerFilePicker("fitpackInput");
  });
  $("sidebarChooseFileBtn").addEventListener("click", () => triggerFilePicker("fileInput"));
  $("changeFileBtn").addEventListener("click", () => triggerFilePicker("fileInput"));
  document.addEventListener("click", (event) => {
    const radial = $("homeImportRadial");
    if (radial && !radial.contains(event.target)) setHomeImportMenuOpen(false);
    if (megaRoot && !megaRoot.contains(event.target)) closeHomeMegaPanel();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setHomeImportMenuOpen(false);
      closeHomeMegaPanel();
      setRunProtocolDialogVisible(false);
    }
  });
}

function bindTxtImportEvents() {
  $("txtBackHomeBtn").addEventListener("click", showHomePage);
  onIfPresent("txtHomeBtn", "click", showHomePage);
  $("txtUseSelectedBtn").addEventListener("click", () => activateSelectedTxtBlock().catch(showError));
  $("txtClearSelectionBtn").addEventListener("click", () => {
    state.txtSelectedBlockIds = new Set();
    syncTxtFitRangeToSelection({ force: true });
    renderTxtBlockList();
    renderTxtDiagnostics();
    drawTxtPreview();
  });
  $("txtBlockList").addEventListener("change", (event) => {
    if (event.target.matches("[data-txt-block]")) updateTxtSelectionFromInputs();
  });
  document.querySelectorAll("[data-txt-scale]").forEach((button) => {
    button.addEventListener("click", () => {
      state.txtScale = button.dataset.txtScale || "linear";
      syncTxtScaleButtons();
      drawTxtPreview();
    });
    button.addEventListener("mouseenter", () => syncTxtScaleTabIndicator(button, { hover: true }));
    button.addEventListener("focus", () => syncTxtScaleTabIndicator(button, { hover: true }));
  });
  document.querySelector(".txt-import-page .segmented-control")?.addEventListener("mouseleave", clearTxtScaleTabHover);
  document.querySelector(".txt-import-page .segmented-control")?.addEventListener("focusout", clearTxtScaleTabHover);
  ["txtFitVoltageMin", "txtFitVoltageMax"].forEach((id) => {
    onIfPresent(id, "input", () => {
      state.txtFitRangeTouched = true;
      setTxtFitRangePresetActive("");
      drawTxtPreview();
    });
  });
  onIfPresent("txtFitCoreRangeBtn", "click", () => {
    const blocks = selectedTxtBlocks();
    if (blocks.length === 1) {
      setTxtFitRangeInputs(blocks[0]);
      state.txtFitRangeBlockId = blocks[0].id;
      state.txtFitRangeTouched = true;
      setTxtFitRangePresetActive("core");
      pulseControl("txtFitCoreRangeBtn");
      drawTxtPreview();
    }
  });
  onIfPresent("txtFitFullRangeBtn", "click", () => {
    const blocks = selectedTxtBlocks();
    if (blocks.length === 1) {
      setTxtFitRangeInputs(blocks[0], { full: true });
      state.txtFitRangeBlockId = blocks[0].id;
      state.txtFitRangeTouched = true;
      setTxtFitRangePresetActive("full");
      pulseControl("txtFitFullRangeBtn");
      drawTxtPreview();
    }
  });
  document.querySelectorAll("#txtFitCoreRangeBtn, #txtFitFullRangeBtn").forEach((button) => {
    button.addEventListener("mouseenter", () => syncRangeTabIndicator(".txt-preview-actions", button, { hover: true }));
    button.addEventListener("focus", () => syncRangeTabIndicator(".txt-preview-actions", button, { hover: true }));
  });
  document.querySelector(".txt-preview-actions")?.addEventListener("mouseleave", () => clearRangeTabHover(".txt-preview-actions"));
  document.querySelector(".txt-preview-actions")?.addEventListener("focusout", () => clearRangeTabHover(".txt-preview-actions"));
  $("txtInput").addEventListener("change", async () => {
    const file = $("txtInput").files[0];
    try {
      await importTxtFile(file);
    } catch (error) {
      showError(error);
    } finally {
      $("txtInput").value = "";
    }
  });
}

function bindFitpackEvents() {
  $("fitpackInput").addEventListener("change", async () => {
    try {
      await importFitpackFile($("fitpackInput").files[0]);
    } catch (error) {
      showError(error);
    } finally {
      $("fitpackInput").value = "";
    }
  });
}

function bindDataPickerEvents() {
  $("openDataPickerBtn").addEventListener("click", async () => {
    try {
      if (!state.uploadId) await inspectSelectedFile();
      if (!state.dataGrid) await loadDataGrid();
      openDataPicker();
    } catch (error) {
      showError(error);
    }
  });
  $("dataPickerCloseBtn").addEventListener("click", () => {
    const returnStep = state.flowReturnStep;
    state.flowReturnStep = null;
    if (returnStep === "fit" && flowStepAvailable("fit")) showModelPage();
    else showHomePage();
  });
  onIfPresent("dataPickerHomeBtn", "click", showHomePage);
  $("applyDataSelectionBtn").addEventListener("click", () => {
    try {
      applyDataPickerSelection();
    } catch (error) {
      showError(error);
    }
  });
  onIfPresent("dataCoreRangeBtn", "click", setDataPickerCoreRange);
  onIfPresent("dataFullRangeBtn", "click", setDataPickerFullRange);
  document.querySelectorAll("#dataCoreRangeBtn, #dataFullRangeBtn").forEach((button) => {
    button.addEventListener("mouseenter", () => syncRangeTabIndicator("#dataPickerOverlay .data-range-tabs", button, { hover: true }));
    button.addEventListener("focus", () => syncRangeTabIndicator("#dataPickerOverlay .data-range-tabs", button, { hover: true }));
  });
  document.querySelector("#dataPickerOverlay .data-range-tabs")?.addEventListener("mouseleave", () => clearRangeTabHover("#dataPickerOverlay .data-range-tabs"));
  document.querySelector("#dataPickerOverlay .data-range-tabs")?.addEventListener("focusout", () => clearRangeTabHover("#dataPickerOverlay .data-range-tabs"));
  $("clearDataSelectionBtn").addEventListener("click", clearCurrentSelection);
  $("dataGrid").addEventListener("pointerdown", startGridSelection);
  $("dataGrid").addEventListener("pointerover", extendGridSelection);
  $("dataGrid").addEventListener("pointermove", extendGridSelection);
  $("dataGrid").addEventListener("click", clickGridSelection);
  window.addEventListener("pointerup", finishGridSelection);
  $("fileInput").addEventListener("change", handleDataFileSelection);
  $("sheetSelect").addEventListener("change", () => {
    if (state.uploadId) inspectSelectedFile().catch(showError);
  });
  $("currentColumn").addEventListener("input", updateColumnSuggestions);
  $("voltageColumn").addEventListener("input", updateColumnSuggestions);
  $("pickerVoltageStart").addEventListener("input", () => {
    state.userVoltageOverride = true;
    setDataPickerPresetActive("");
    $("voltageStart").value = $("pickerVoltageStart").value;
    syncGeneratedVoltageEnd();
    drawDataPickerPreview();
  });
  $("pickerVoltageStep").addEventListener("input", () => {
    state.userVoltageOverride = true;
    setDataPickerPresetActive("");
    $("voltageStep").value = $("pickerVoltageStep").value;
    syncGeneratedVoltageEnd();
    drawDataPickerPreview();
  });
  [
    "currentColumn",
    "currentStartRow",
    "currentEndRow",
    "voltageStart",
    "voltageEnd",
    "voltageStep",
    "voltageColumn",
    "voltageStartRow",
    "voltageEndRow",
  ].forEach((id) => {
    $(id).addEventListener("input", () => handleDataRangeInput(id));
  });
}

function bindFitControlEvents() {
  $("runBtn").addEventListener("click", () => runAnalysis().catch(showError));
  $("useFitParamsBtn").addEventListener("click", () => {
    const result = currentDisplayResult();
    if (!result || !result.fit) {
      showError(new Error("Run or evaluate a fit before using fitted parameters."));
      return;
    }
    syncParamInputs(result.fit.params, result.fit.m, result.fit.diagnostics || {});
    setStatus("Manual inputs reset to the latest auto-fit result.");
  });
  $("optimizeFromParamsBtn").addEventListener("click", () => runAnalysis({ useInitialParams: true }).catch(showError));
  $("fitMode").addEventListener("change", () => handleFitModeChange("fitMode"));
  onIfPresent("modelFitMode", "change", () => handleFitModeChange("modelFitMode"));
  onIfPresent("mlAssistToggle", "change", refreshFitModeUi);
  $("scanMToggle").addEventListener("change", refreshFitModeUi);
  $("voltageMode").addEventListener("change", () => {
    state.userVoltageOverride = true;
    refreshVoltageModeUi();
    state.fixedMeasured = null;
    state.plotScale = null;
  });
  for (const control of paramControls) {
    $(control.input).addEventListener("input", scheduleLiveEvaluation);
    $(control.input).addEventListener("wheel", (event) => adjustParameterByWheel(event, control.input), {
      passive: false,
    });
  }
}

function bindRecordAndExportEvents() {
  $("openRecordFormBtn").addEventListener("click", () => {
    if (!currentDisplayResult()?.fit) {
      showError(new Error("Run or evaluate a fit before preparing a record."));
      return;
    }
    toggleRecordForm(true);
    setStatus("Complete the record form and save the accepted fit.");
  });
  $("cancelRecordFormBtn").addEventListener("click", () => {
    toggleRecordForm(false);
    setStatus("Record form closed.");
  });
  $("saveRecordBtn").addEventListener("click", () => saveCurrentRecord().catch(showError));
  $("exportPackageBtn").addEventListener("click", exportDataPackageFromMenu);
  onIfPresent("exportComponentsCsvBtn", "click", exportComponentsCsvFromMenu);
  onIfPresent("exportComponentsXlsxBtn", "click", exportComponentsXlsxFromMenu);
  $("exportFitpackBtn").addEventListener("click", exportFitpackFromMenu);
}

function bindFlowNavigationEvents() {
  $("modelBackToDataBtn").addEventListener("click", () => {
    if (state.txtImport) showTxtImportPage();
    else if (state.dataGrid) {
      state.flowReturnStep = "fit";
      openDataPicker();
    }
    else showHomePage();
  });
  onIfPresent("modelHomeBtn", "click", showHomePage);
  onIfPresent("modelProtocolBtn", "click", () => setRunProtocolDialogVisible(true));
  onIfPresent("modelProtocolCloseBtn", "click", () => setRunProtocolDialogVisible(false));
  onIfPresent("modelProtocolDoneBtn", "click", () => setRunProtocolDialogVisible(false));
  onIfPresent("runProtocolDialog", "click", (event) => {
    if (event.target === $("runProtocolDialog")) setRunProtocolDialogVisible(false);
  });
  document.querySelectorAll("[data-run-mode]").forEach((button) => {
    button.addEventListener("click", () => setRunFitMode(button.dataset.runMode));
    button.addEventListener("mouseenter", () => syncRunModeTabIndicator(button, { hover: true }));
    button.addEventListener("focus", () => syncRunModeTabIndicator(button, { hover: true }));
  });
  document.querySelector(".run-mode-tabs")?.addEventListener("mouseleave", clearRunModeTabHover);
  document.querySelector(".run-mode-tabs")?.addEventListener("focusout", clearRunModeTabHover);
  const runText = document.querySelector("#modelRunFitBtn [data-scramble-text]");
  onIfPresent("modelRunFitBtn", "pointerenter", () => setScrambleLoop(runText, true));
  onIfPresent("modelRunFitBtn", "pointerleave", () => setScrambleLoop(runText, false));
  onIfPresent("modelRunFitBtn", "focus", () => setScrambleLoop(runText, true));
  onIfPresent("modelRunFitBtn", "blur", () => setScrambleLoop(runText, false));
  $("modelRunFitBtn").addEventListener("click", () => {
    setScrambleLoop(runText, false);
    scrambleTextElement(runText, runText?.dataset.scrambleText, { duration: 1000, interval: 50 });
    syncFitControlsFromModelControls();
    setRunProtocolDialogVisible(false);
    runAnalysis().catch(showError);
  });
  $("reviewBackModelBtn").addEventListener("click", showModelPage);
  onIfPresent("reviewHomeBtn", "click", showHomePage);
  $("reviewManualFitBtn").addEventListener("click", showManualPage);
  $("reviewAcceptFitBtn").addEventListener("click", showSavePage);
  $("reviewCandidateList").addEventListener("click", (event) => {
    clearTimeout(event.currentTarget._candidateHoverTimer);
    const action = event.target.closest("[data-candidate-action]");
    const item = event.target.closest("[data-candidate-index]");
    if (!item) return;
    const index = Number(item.dataset.candidateIndex);
    if (!Number.isInteger(index)) return;
    if (action?.dataset.candidateAction === "view") {
      viewCandidate(index);
      return;
    }
    const result = currentDisplayResult();
    const focused = currentReviewCandidateFocusIndex() === index;
    if (!focused) {
      animateReviewCandidateToIndex(index);
      return;
    }
    const expanded = state.selectedCandidateIndex === index;
    if (!expanded) {
      state.reviewCandidatePreviewIndex = index;
      state.selectedCandidateIndex = index;
      renderReviewCandidates(result);
      return;
    }
    state.reviewCandidatePreviewIndex = index;
    state.selectedCandidateIndex = -1;
    renderReviewCandidates(result);
  });
  $("reviewCandidateList").addEventListener("pointerover", (event) => {
    const item = event.target.closest("[data-candidate-index]");
    if (!item || item.contains(event.relatedTarget)) return;
    const index = Number(item.dataset.candidateIndex);
    if (Number.isInteger(index)) scheduleReviewCandidateHoverFocus(index);
  });
  $("reviewCandidateList").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const item = event.target.closest("[data-candidate-index]");
    if (!item) return;
    event.preventDefault();
    item.click();
  });
  $("reviewCandidateList").addEventListener("wheel", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const list = event.currentTarget;
    const delta = normalizedWheelDelta(event);
    if (!Number.isFinite(delta) || Math.abs(delta) < 1) return;
    list._candidateWheelDelta = (list._candidateWheelDelta || 0) + delta;
    const threshold = 42;
    if (Math.abs(list._candidateWheelDelta) < threshold) return;
    const now = performance.now();
    if (now - (list._candidateWheelAt || 0) < 300) return;
    const direction = list._candidateWheelDelta > 0 ? 1 : -1;
    list._candidateWheelDelta = 0;
    list._candidateWheelAt = now;
    flipReviewCandidateByWheel(direction);
  }, { passive: false });
  onIfPresent("reviewOverlayToggleBtn", "click", () => {
    state.reviewOverlayEnabled = !state.reviewOverlayEnabled;
    renderReviewResult(currentDisplayResult());
  });
  document.querySelectorAll("[data-review-panel]").forEach((button) => {
    button.addEventListener("click", () => setReviewSidePanel(button.dataset.reviewPanel));
    button.addEventListener("mouseenter", () => syncReviewSideTabIndicator(button, { hover: true }));
    button.addEventListener("focus", () => syncReviewSideTabIndicator(button, { hover: true }));
  });
  document.querySelector(".review-side-tabs")?.addEventListener("mouseleave", clearReviewSideTabHover);
  document.querySelector(".review-side-tabs")?.addEventListener("focusout", clearReviewSideTabHover);
  $("acceptFitBtn").addEventListener("click", () => {
    showSavePage();
  });
  $("manualFitBtn").addEventListener("click", () => {
    showManualPage();
  });
}

function bindFlowStepperEvents() {
  updateFlowSteppers();
}

function bindManualEvents() {
  $("manualBackReviewBtn").addEventListener("click", () => {
    cancelPendingManualEvaluation();
    showResultPage();
  });
  onIfPresent("manualHomeBtn", "click", () => {
    cancelPendingManualEvaluation();
    showHomePage();
  });
  $("manualAcceptBtn").addEventListener("click", acceptManualDraft);
  $("manualHistoryList").addEventListener("click", (event) => {
    const star = event.target.closest("[data-history-star]");
    if (star) {
      event.preventDefault();
      event.stopPropagation();
      toggleManualHistoryStar(star.dataset.historyStar);
      return;
    }
    const item = event.target.closest("[data-history-id]");
    if (item) restoreManualHistory(item.dataset.historyId);
  });
  $("manualHistoryList").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const star = event.target.closest("[data-history-star]");
    if (star) {
      event.preventDefault();
      toggleManualHistoryStar(star.dataset.historyStar);
      return;
    }
    const item = event.target.closest("[data-history-id]");
    if (item) {
      event.preventDefault();
      restoreManualHistory(item.dataset.historyId);
    }
  });
  $("manualClearHistoryBtn").addEventListener("click", clearManualHistory);
  $("manualAddCheckpointBtn").addEventListener("click", () => addManualCheckpointFromCurrent().catch(showError));
  $("saveBackReviewBtn").addEventListener("click", closeSavePage);
  onIfPresent("saveHomeBtn", "click", showHomePage);
  onIfPresent("saveGlass", "click", closeSavePage);
  for (const control of manualParamControls) {
    $(control.input).addEventListener("input", () => scheduleManualLiveEvaluation(`Edit ${control.name}`));
    $(control.input).addEventListener("wheel", (event) => adjustManualParameterByWheel(event, control.input), {
      passive: false,
    });
  }
}

function bindSavePageEvents() {
  onIfPresent("saveComponentsCsvBtn", "click", exportComponentsCsvFromMenu);
  onIfPresent("saveComponentsXlsxBtn", "click", exportComponentsXlsxFromMenu);
  onIfPresent("saveFitpackBtn", "click", exportFitpackFromMenu);
  $("saveAcceptedRecordBtn").addEventListener("click", () => saveAcceptedFromPage().catch(showError));
  document.querySelectorAll("[data-device-orientation]").forEach((button) => {
    button.addEventListener("click", () => setDeviceOrientation(button.dataset.deviceOrientation));
    button.addEventListener("mouseenter", () => syncDeviceOrientationIndicator(button, { hover: true }));
    button.addEventListener("focus", () => syncDeviceOrientationIndicator(button, { hover: true }));
  });
  document.querySelector(".device-orientation-tabs")?.addEventListener("mouseleave", clearDeviceOrientationHover);
  document.querySelector(".device-orientation-tabs")?.addEventListener("focusout", clearDeviceOrientationHover);
  onIfPresent("deviceStack", "click", (event) => {
    const stack = event.currentTarget;
    const button = event.target.closest("[data-insert-after]");
    if (button) {
      addModifierLayer(button.dataset.insertAfter);
      return;
    }
    const layer = event.target.closest("[data-device-layer]");
    if (layer) {
      selectDeviceLayer(layer.dataset.deviceLayer);
      return;
    }
  });
  setupSaveCustomSelects();
  onIfPresent("deviceEditName", "input", (event) => updateSelectedDeviceLayer("name", event.target.value));
  onIfPresent("deviceEditThickness", "input", (event) => updateSelectedDeviceLayer("thickness_nm", event.target.value));
  onIfPresent("deviceEditAbsorption", "input", (event) => updateSelectedDeviceLayer("absorption_peak_nm", event.target.value));
  onIfPresent("deviceEditorCloseBtn", "click", closeDeviceLayerEditor);
  if (!bindSavePageEvents.boundDeviceEditorOutsideClose) {
    document.addEventListener("click", (event) => {
      const savePage = $("savePage");
      if (!savePage || savePage.classList.contains("hidden") || !state.selectedDeviceLayerId) return;
      if (event.target.closest("#deviceLayerEditor") || event.target.closest("#deviceStack")) return;
      closeDeviceLayerEditor();
    });
    bindSavePageEvents.boundDeviceEditorOutsideClose = true;
  }
  onIfPresent("saveAgingDays", "wheel", adjustAgingDaysByWheel, { passive: false });
}

function bindAssistantEvents() {
  $("assistantClearBtn").addEventListener("click", resetAssistantConversation);
  $("assistantSendBtn").addEventListener("click", () => sendAssistantQuestion().catch(showError));
  $("assistantQuestion").addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      sendAssistantQuestion().catch(showError);
    }
  });
}

function bindChartEvents() {
  onIfPresent("reviewFitCanvas", "mousemove", (event) => showChartTooltip($("reviewFitCanvas"), event));
  onIfPresent("reviewFitCanvas", "mouseleave", hideChartTooltip);
  onIfPresent("manualFitCanvas", "mousemove", (event) => showChartTooltip($("manualFitCanvas"), event));
  onIfPresent("manualFitCanvas", "mouseleave", hideChartTooltip);
}

function bindViewEvents() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });
  window.addEventListener("resize", redrawActiveView);
}

function bindEvents() {
  bindHomeEvents();
  bindTxtImportEvents();
  bindFitpackEvents();
  bindDataPickerEvents();
  bindFitControlEvents();
  bindRecordAndExportEvents();
  bindFlowStepperEvents();
  bindFlowNavigationEvents();
  bindManualEvents();
  bindSavePageEvents();
  bindAssistantEvents();
  bindChartEvents();
  bindViewEvents();
}

function showError(error) {
  const message = error.message || String(error);
  setStatus(message);
  if (!$("savePage").classList.contains("hidden")) {
    const status = $("savePageStatus");
    if (status) status.textContent = message === "Save required fields need attention." ? "" : message;
  }
  if (!$("manualPage").classList.contains("hidden")) {
    $("manualLiveStatus").textContent = message;
  }
}

updateColumnSuggestions();
refreshVoltageModeUi();
refreshFitModeUi();
updateFileSelectionUi();
renderDeviceStack();
toggleRecordForm(false);
initHomeGlowRandomWalk();
bindEvents();
loadFitContract().catch(() => {
  fitContract = null;
});
refreshRecords().catch(() => {
  $("recordsSummary").textContent = "No records loaded.";
});
