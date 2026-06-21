/* ==========================================================================
   Charts and active view redraw
   ========================================================================== */

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[ch]));
}

function finiteNumbers(values) {
  return values.filter((value) => Number.isFinite(value));
}

const chartFontFamily = 'Inter, "TASA Orbiter", "Microsoft YaHei", "PingFang SC", Arial, sans-serif';

function chartFont(size, weight = 430) {
  return `${weight} ${size}px ${chartFontFamily}`;
}

function chartBounds(xs, ys) {
  const validX = finiteNumbers(xs);
  const validY = finiteNumbers(ys);
  let minX = Math.min(...validX);
  let maxX = Math.max(...validX);
  let minY = Math.min(...validY);
  let maxY = Math.max(...validY);
  if (minX === maxX) {
    minX -= 0.5;
    maxX += 0.5;
  }
  if (minY === maxY) {
    minY -= Math.abs(minY || 1) * 0.05;
    maxY += Math.abs(maxY || 1) * 0.05;
  }
  return { minX, maxX, minY, maxY };
}

function prepareCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return null;
  canvas.width = Math.floor(rect.width * dpr);
  canvas.height = Math.floor(rect.height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  return { ctx, width: rect.width, height: rect.height };
}

function drawAxes(ctx, box, labels) {
  const yOffset = labels.yOffset ?? 48;
  ctx.strokeStyle = colors.grid;
  ctx.lineWidth = 1;
  ctx.strokeRect(box.left, box.top, box.width, box.height);
  ctx.fillStyle = colors.text;
  ctx.font = chartFont(13, 520);
  ctx.textAlign = "center";
  if (labels.title) {
    ctx.fillText(labels.title, box.left + box.width / 2, box.top - 10);
  }
  ctx.fillStyle = colors.muted;
  ctx.font = chartFont(12, 430);
  ctx.fillText(labels.x, box.left + box.width / 2, box.top + box.height + 38);
  if (labels.y) {
    ctx.save();
    ctx.translate(box.left - yOffset, box.top + box.height / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(labels.y, 0, 0);
    ctx.restore();
  }
  ctx.textAlign = "left";
}

function drawXTicks(ctx, box, minX, maxX, count = 4) {
  ctx.strokeStyle = colors.fineGrid;
  ctx.fillStyle = colors.muted;
  ctx.font = chartFont(11.5, 430);
  ctx.textAlign = "center";
  for (let i = 0; i <= count; i += 1) {
    const value = minX + ((maxX - minX) * i) / count;
    const x = box.left + (i / count) * box.width;
    ctx.beginPath();
    ctx.moveTo(x, box.top);
    ctx.lineTo(x, box.top + box.height);
    ctx.stroke();
    ctx.fillText(value.toFixed(2), x, box.top + box.height + 16);
  }
  ctx.textAlign = "left";
}

function drawLogTicks(ctx, box, minLog, maxLog) {
  ctx.fillStyle = colors.muted;
  ctx.strokeStyle = colors.fineGrid;
  ctx.font = chartFont(11.5, 430);
  ctx.textAlign = "right";
  const step = Math.max(1, Math.ceil((maxLog - minLog) / 8));
  for (let p = minLog; p <= maxLog; p += step) {
    const y = box.top + (1 - ((p - minLog) / (maxLog - minLog))) * box.height;
    ctx.beginPath();
    ctx.moveTo(box.left, y);
    ctx.lineTo(box.left + box.width, y);
    ctx.stroke();
    ctx.fillText(`1e${p}`, box.left - 8, y + 4);
  }
  ctx.textAlign = "left";
}

function drawLinearYTicks(ctx, box, minY, maxY, count = 5, formatter = (value) => value.toPrecision(2)) {
  ctx.fillStyle = colors.muted;
  ctx.strokeStyle = colors.fineGrid;
  ctx.font = chartFont(11.5, 430);
  ctx.textAlign = "right";
  for (let i = 0; i <= count; i += 1) {
    const value = minY + ((maxY - minY) * i) / count;
    const y = box.top + (1 - ((value - minY) / (maxY - minY))) * box.height;
    ctx.beginPath();
    ctx.moveTo(box.left, y);
    ctx.lineTo(box.left + box.width, y);
    ctx.stroke();
    ctx.fillText(formatter(value), box.left - 8, y + 4);
  }
  ctx.textAlign = "left";
}

function withClip(ctx, box, draw) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(box.left, box.top, box.width, box.height);
  ctx.clip();
  draw();
  ctx.restore();
}

function drawLogLine(ctx, xs, ys, scale, color, options = {}) {
  const lineWidth = options.lineWidth ?? 2;
  const points = options.points || false;
  const pointRadius = options.pointRadius ?? 2.5;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.setLineDash(options.dash || []);
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < xs.length; i += 1) {
    const x = xs[i];
    const y = Math.abs(ys[i]);
    if (!Number.isFinite(x) || !Number.isFinite(y) || y <= 0) continue;
    const px = scale.x(x);
    const py = scale.y(y);
    if (!started) {
      ctx.moveTo(px, py);
      started = true;
    } else {
      ctx.lineTo(px, py);
    }
  }
  if (lineWidth > 0) ctx.stroke();
  ctx.setLineDash([]);
  if (points) {
    for (let i = 0; i < xs.length; i += 1) {
      const x = xs[i];
      const y = Math.abs(ys[i]);
      if (!Number.isFinite(x) || !Number.isFinite(y) || y <= 0) continue;
      ctx.beginPath();
      ctx.arc(scale.x(x), scale.y(y), pointRadius, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

function hideChartTooltip() {
  const tooltip = $("chartTooltip");
  if (tooltip) tooltip.classList.add("hidden");
}

function showChartTooltip(canvas, event) {
  const tooltip = $("chartTooltip");
  const meta = state.chartMeta[canvas.id];
  if (!tooltip || !meta) return;
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  const { box, series, scale } = meta;
  if (x < box.left || x > box.left + box.width || y < box.top || y > box.top + box.height) {
    hideChartTooltip();
    return;
  }
  const voltage = series.voltage || [];
  if (!voltage.length) return;
  let bestIndex = 0;
  let bestDistance = Infinity;
  for (let i = 0; i < voltage.length; i += 1) {
    const vx = Number(voltage[i]);
    if (!Number.isFinite(vx)) continue;
    const distance = Math.abs(scale.x(vx) - x);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = i;
    }
  }
  const measured = series.measured?.[bestIndex];
  const fitted = series.fitted?.[bestIndex];
  const error = series.relative_error?.[bestIndex];
  tooltip.innerHTML = `
    <strong>${Number(voltage[bestIndex]).toFixed(4)} V</strong>
    <span>Measured ${formatSci(measured)}</span>
    <span>Fitted ${formatSci(fitted)}</span>
    <span>Error ${formatPct(error)}</span>
  `;
  tooltip.style.left = `${event.clientX + 14}px`;
  tooltip.style.top = `${event.clientY + 14}px`;
  tooltip.classList.remove("hidden");
}

function drawLinearLine(ctx, xs, ys, scale, color, options = {}) {
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = options.lineWidth ?? 1.8;
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < xs.length; i += 1) {
    const x = xs[i];
    const y = ys[i];
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    const px = scale.x(x);
    const py = scale.y(y);
    if (!started) {
      ctx.moveTo(px, py);
      started = true;
    } else {
      ctx.lineTo(px, py);
    }
  }
  ctx.stroke();
}

function drawFitChart(series, canvasId = "fitCanvas", options = {}) {
  const prepared = prepareCanvas($(canvasId));
  if (!prepared) return;
  const { ctx, width, height } = prepared;
  const darkCanvas = canvasId === "reviewFitCanvas" || canvasId === "manualFitCanvas";
  const previousChartColors = {
    grid: colors.grid,
    fineGrid: colors.fineGrid,
    text: colors.text,
    muted: colors.muted,
  };
  if (darkCanvas) {
    Object.assign(colors, {
      grid: "rgba(148, 163, 184, 0.16)",
      fineGrid: "rgba(148, 163, 184, 0.055)",
      text: "#f2fbff",
      muted: "rgba(217, 231, 241, 0.62)",
    });
  }
  try {
  const overlays = Array.isArray(options.overlays) ? options.overlays : [];
  const displaySeries = displaySeriesForComponents(series || {});
  const v = displaySeries.voltage || [];
  const measured = displaySeries.measured || [];
  const fitted = displaySeries.fitted || [];
  const diode = displaySeries.diode || [];
  const ohmic = displaySeries.ohmic || [];
  const nonohmic = displaySeries.nonohmic || [];
  const extraCurrent = displaySeries.extra_current || [];
  const recombination = displaySeries.recombination || [];
  const diffusion = displaySeries.diffusion || [];
  const hasM4Components = hasCompleteSeries(displaySeries, "recombination") && hasCompleteSeries(displaySeries, "diffusion");
  const hasExtendedBranch = componentHasVisibleSignal(displaySeries, "extra_current");
  const componentSeries = hasM4Components
    ? [recombination, diffusion, ohmic]
    : [diode, ohmic, nonohmic, ...(hasExtendedBranch ? [extraCurrent] : [])];
  const overlayY = overlays.flatMap((item) => item?.series?.fitted || []);
  const allY = [measured, fitted, ...componentSeries, overlayY]
    .flat()
    .map((y) => Math.abs(y))
    .filter((y) => Number.isFinite(y) && y > 0);
  if (!v.length || !allY.length) return;

  const measuredY = measured.map((y) => Math.abs(y)).filter((y) => Number.isFinite(y) && y > 0);
  const measuredBounds = chartBounds(v, measuredY.length ? measuredY : allY);
  const stable = state.plotScale || {};
  const bounds = {
    minX: Number.isFinite(stable.minX) ? stable.minX : measuredBounds.minX,
    maxX: Number.isFinite(stable.maxX) ? stable.maxX : measuredBounds.maxX,
  };
  const box = { left: 72, top: 34, width: width - 104, height: height - 106 };
  const dynamicMin = Math.floor(Math.log10(Math.max(measuredBounds.minY, 1e-20)));
  const dynamicMax = Math.ceil(Math.log10(measuredBounds.maxY));
  const minLog = Number.isFinite(stable.minLog) ? stable.minLog : Math.min(-11, dynamicMin);
  const maxLog = Math.max(
    Number.isFinite(stable.maxLog) ? stable.maxLog : Math.max(-3, dynamicMax),
    minLog + 1
  );
  const scale = {
    x: (x) => box.left + ((x - bounds.minX) / (bounds.maxX - bounds.minX)) * box.width,
    y: (y) => box.top + (1 - ((Math.log10(y) - minLog) / (maxLog - minLog))) * box.height,
  };
  state.chartMeta[canvasId] = { box, bounds, minLog, maxLog, scale, series: displaySeries };

  drawAxes(ctx, box, {
    x: "Voltage (V)",
    y: "Current density (A)",
    title: hasM4Components ? "M4 recombination/diffusion fit and components" : "Diode I-V fit and current components",
  });
  drawLogTicks(ctx, box, minLog, maxLog);
  drawXTicks(ctx, box, bounds.minX, bounds.maxX);
  withClip(ctx, box, () => {
    drawLogLine(ctx, v, measured, scale, colors.measured, { lineWidth: 0, points: true, pointRadius: 2.7 });
    drawLogLine(ctx, v, fitted, scale, colors.fitted, { lineWidth: 0, points: true, pointRadius: 2.7 });
    if (hasM4Components) {
      drawLogLine(ctx, v, recombination, scale, colors.recombination, { lineWidth: 1.5, dash: [6, 4] });
      drawLogLine(ctx, v, diffusion, scale, colors.diffusion, { lineWidth: 1.5, dash: [6, 4] });
      drawLogLine(ctx, v, ohmic, scale, colors.ohmic, { lineWidth: 1.5, dash: [6, 4] });
    } else {
      drawLogLine(ctx, v, diode, scale, colors.diode, { lineWidth: 1.5, dash: [6, 4] });
      drawLogLine(ctx, v, ohmic, scale, colors.ohmic, { lineWidth: 1.5, dash: [6, 4] });
      drawLogLine(ctx, v, nonohmic, scale, colors.nonohmic, { lineWidth: 1.5, dash: [6, 4] });
      if (hasExtendedBranch) {
        drawLogLine(ctx, v, extraCurrent, scale, colors.extraCurrent, { lineWidth: 1.5, dash: [3, 5] });
      }
    }
    overlays.forEach((item) => {
      const overlaySeries = item.series || {};
      drawLogLine(
        ctx,
        overlaySeries.voltage || v,
        overlaySeries.fitted || [],
        scale,
        item.color || "#9ff7ef",
        { lineWidth: 2.1, dash: [2, 3] }
      );
    });
  });
  } finally {
    if (darkCanvas) Object.assign(colors, previousChartColors);
  }
}

function drawErrorChart(series) {
  const prepared = prepareCanvas($("errorCanvas"));
  if (!prepared) return;
  const { ctx, width, height } = prepared;
  const v = series.voltage || [];
  const err = series.relative_error || [];
  const measured = series.measured || [];
  const fitted = series.fitted || [];
  if (!v.length || !err.length) return;

  let indices = v
    .map((x, i) => i)
    .filter((i) =>
      Number.isFinite(v[i]) &&
      Number.isFinite(err[i]) &&
      Math.abs(v[i]) > 1e-12 &&
      Math.abs(measured[i]) >= 1e-11
    );
  if (!indices.length) {
    indices = v.map((x, i) => i).filter((i) => Number.isFinite(v[i]) && Number.isFinite(err[i]));
  }
  if (!indices.length) return;

  const measuredFinite = measured.filter((y) => Number.isFinite(y));
  const measuredBounds = chartBounds(v, measuredFinite.length ? measuredFinite : fitted);
  const stable = state.plotScale || {};
  const allBounds = {
    minX: Number.isFinite(stable.minX) ? stable.minX : measuredBounds.minX,
    maxX: Number.isFinite(stable.maxX) ? stable.maxX : measuredBounds.maxX,
    minY: Number.isFinite(stable.linearMinY) ? stable.linearMinY : measuredBounds.minY,
    maxY: Number.isFinite(stable.linearMaxY) ? stable.linearMaxY : measuredBounds.maxY,
  };
  const topBox = { left: 72, top: 34, width: width - 104, height: Math.max(150, height * 0.38) };
  const bottomBox = {
    left: 72,
    top: topBox.top + topBox.height + 78,
    width: width - 104,
    height: Math.max(120, height - topBox.height - 142),
  };

  const maxErr = Math.max(5, Math.ceil(Math.max(...indices.map((i) => err[i])) / 5) * 5);
  const barScale = {
    x: (x) => topBox.left + ((x - allBounds.minX) / (allBounds.maxX - allBounds.minX)) * topBox.width,
    y: (y) => topBox.top + (1 - y / maxErr) * topBox.height,
  };
  drawAxes(ctx, topBox, {
    x: "Voltage (V)",
    y: "Relative error (%)",
    title: "Relative error",
  });
  drawLinearYTicks(ctx, topBox, 0, maxErr, 5, (value) => value.toFixed(0));
  drawXTicks(ctx, topBox, allBounds.minX, allBounds.maxX);
  const barWidth = Math.max(2, topBox.width / Math.max(v.length, 1) * 0.6);
  withClip(ctx, topBox, () => {
    ctx.fillStyle = colors.measured;
    for (const i of indices) {
      const x = barScale.x(v[i]) - barWidth / 2;
      const y = barScale.y(Math.max(0, err[i]));
      ctx.fillRect(x, y, barWidth, topBox.top + topBox.height - y);
    }
  });

  const yPad = (allBounds.maxY - allBounds.minY) * 0.08 || Math.abs(allBounds.maxY || 1) * 0.08;
  const minY = allBounds.minY - yPad;
  const maxY = allBounds.maxY + yPad;
  const lineScale = {
    x: (x) => bottomBox.left + ((x - allBounds.minX) / (allBounds.maxX - allBounds.minX)) * bottomBox.width,
    y: (y) => bottomBox.top + (1 - ((y - minY) / (maxY - minY))) * bottomBox.height,
  };
  drawAxes(ctx, bottomBox, {
    x: "Voltage (V)",
    y: "Current density (A)",
    title: "I-V curve (linear scale)",
  });
  drawLinearYTicks(ctx, bottomBox, minY, maxY, 4);
  drawXTicks(ctx, bottomBox, allBounds.minX, allBounds.maxX);
  withClip(ctx, bottomBox, () => {
    drawLinearLine(ctx, v, measured, lineScale, colors.measured, { lineWidth: 1.5 });
    drawLinearLine(ctx, v, fitted, lineScale, colors.fitted, { lineWidth: 1.5 });
  });
}

function activeView() {
  return document.querySelector(".tab.active")?.dataset.view || "fit";
}

function redrawActiveView() {
  if (!$("txtImportPage").classList.contains("hidden")) {
    drawTxtPreview();
    return;
  }
  const result = currentDisplayResult();
  if (!result || !result.fit) return;
  if (!$("resultPage").classList.contains("hidden")) {
    renderReviewSeries(result);
    return;
  }
  if (!$("manualPage").classList.contains("hidden")) {
    const manualResult = state.manualDraftResult || result;
    if (manualResult?.fit?.series) drawFitChart(manualResult.fit.series, "manualFitCanvas");
    return;
  }
  const view = activeView();
  if (view === "fit") drawFitChart(result.fit.series);
  if (view === "error") drawErrorChart(result.fit.series);
}

function setView(view) {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((el) => {
    el.classList.toggle("active", el.id === `view-${view}`);
  });
  requestAnimationFrame(redrawActiveView);
}
