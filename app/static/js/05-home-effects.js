/* ==========================================================================
   Home page visual effects
   ========================================================================== */

function initHomeGlowRandomWalk() {
  const home = $("homePage");
  if (!home) return;
  const reducedQuery = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : { matches: false };
  let timer = null;

  function randomBetween(min, max) {
    return min + Math.random() * (max - min);
  }

  function setGlowTarget(prefix, xRange, yRange, durationRange) {
    const duration = randomBetween(durationRange[0], durationRange[1]);
    home.style.setProperty(`--home-${prefix}-left`, `${randomBetween(xRange[0], xRange[1]).toFixed(1)}%`);
    home.style.setProperty(`--home-${prefix}-top`, `${randomBetween(yRange[0], yRange[1]).toFixed(1)}%`);
    home.style.setProperty(`--home-${prefix}-path-duration`, `${duration.toFixed(1)}s`);
  }

  function schedule(delay = randomBetween(12000, 19000)) {
    if (timer !== null) clearTimeout(timer);
    timer = window.setTimeout(tick, delay);
  }

  function tick() {
    if (reducedQuery.matches) return;
    if (home.classList.contains("hidden") || home.classList.contains("menu-open")) {
      schedule(1800);
      return;
    }
    setGlowTarget("teal", [18, 82], [18, 74], [18, 30]);
    setGlowTarget("green", [14, 76], [24, 82], [22, 34]);
    schedule();
  }

  if (reducedQuery.addEventListener) {
    reducedQuery.addEventListener("change", () => {
      if (!reducedQuery.matches) schedule(1200);
    });
  } else if (reducedQuery.addListener) {
    reducedQuery.addListener(() => {
      if (!reducedQuery.matches) schedule(1200);
    });
  }
  schedule(2800);
}
