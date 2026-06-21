# UI Baseline

This file records the current frontend baseline so future UI edits can start from a smaller context window without rediscovering the design decisions.

## Current Principle

Preserve the rendered UI first. The frontend has gone through many visual passes, so repeated selectors and late overrides are expected. Do not mechanically remove repeated selectors unless the rule body is exactly duplicated or the page has been visually confirmed after the change.

Use this loop for each page:

1. Confirm the current rendered page is acceptable or list the exact design change.
2. Change only that page or shared component.
3. Run syntax/tests.
4. Re-check the page visually.
5. Only then reduce old CSS overrides for that page.

## Page Status

### Home

Status: visually closest to final.

Keep:

- Dark, high-contrast hero with small moving glow.
- Top mega menu sliding interaction and residual/follow feel.
- Get Start interaction and import radial style unless explicitly redesigning imports.
- Current typography stack using local TASA Orbiter and Inter.

Avoid:

- Broad color restyling.
- Rebuilding the hero from scratch.
- Adding new card containers around the hero.

Allowed cleanup:

- Dead JS/CSS that references removed home canvas experiments.
- Exact duplicate CSS rules.
- Minor mega menu content/spacing fixes after visual confirmation.

### Select Data

Status: mostly acceptable, but table polish may still be improved.

Keep:

- Core/Full and Use Selection should follow the shared motion-tab/key-action visual language.
- Preview curve below the selection controls.
- Workbook can stay compact rather than full-page stretched.

Known concerns:

- Spreadsheet robustness is more important than aggressive auto-detection because user workbooks are irregular.
- Avoid making range selection less explicit.

Allowed cleanup:

- Consolidate data-picker-only CSS after checking `dataPickerOverlay`.
- Keep selected-cell and header layering intact.

### TXT Data

Status: mostly acceptable.

Keep:

- Default `log_abs` display.
- Core/Full should match Select Data.
- Use Block should match Use Selection.

Known concerns:

- CV-like TXT should not pretend to be compatible with the device-export TXT parser.
- Avoid overly strong card glow/selection marks.

Allowed cleanup:

- Consolidate `txt-import-page` selectors after checking dark/light block selection.
- Preserve parser diagnostics behavior.

### Run Fit

Status: acceptable direction, may still need interaction polish.

Keep:

- Fast/Super or Fast/Diagnostic mode as a shared motion-tab style.
- Single key Start button.
- Loading page should use the flow/glow language, not a noisy fixed circle.

Known concerns:

- Loading glow should not look like low-quality noise.
- Super/diagnostic mode should have a clear blue-purple state without dirty purple.

Allowed cleanup:

- Consolidate run-mode tab CSS only after checking both modes.
- Keep loading color switch tied to diagnostic mode.

### Review

Status: functionally important and visually near final.

Keep:

- Candidate stack/card interaction.
- Current selected candidate clearly connected to the chart.
- Candidate model name on the chart.
- M4 physical / diagnostic / total-only semantics.

Known concerns:

- Candidate stack animation should stay light; avoid janky reflow.
- Analysis text is still a product/design question, not a CSS-only cleanup.

Allowed cleanup:

- Consolidate review candidate selectors after checking candidate wheel/click behavior.
- Do not change post-fit candidate series semantics while cleaning UI.

### Manual / Adjust Parameters

Status: mostly acceptable, should stay aligned with Review.

Keep:

- Chart alignment with Review.
- Manual history cards.
- Star/favorite checkpoint behavior.
- Accept as the key action, with a short fixed-width button.

Known concerns:

- Avoid making Manual darker than Review.
- Add/checkpoint should stay secondary to Accept.

Allowed cleanup:

- Consolidate manual history and parameter panel CSS after checking Review-to-Manual alignment.

### Save / Accept

Status: not final. Do not do preservation-only cleanup first.

Design goals still open:

- Frosted glass modal that blurs the underlying page.
- Remove stale blue `Accepted fit` style.
- Normal/Reverse orientation as shared motion tabs with residual/follow feel.
- Device structure should feel compact and jelly/press responsive, not long and weak.
- Reverse stack: ITO / NiOx / EDT / Ink / C60 / PCBM / BCP / Ag, with ITO visually at the bottom.
- Aging/test days should live on the right side.
- Record block should not stretch too wide.
- Final label and interpretation/self-label fields need a better unified style.
- Save should require the form; missing fields should shake.
- ML backtest collection should be saved by default without asking the user.
- Output should be user-facing XLSX plus restorable replay pack. The user does not need to see internal ML package wording.
- Save success should use confetti.

Cleanup rule:

- Tune Save/Accept first. Only consolidate `.save-page` CSS after the design is accepted.

## Shared Components To Preserve

- Motion tabs / segmented controls: used in Home mega, TXT scales, Core/Full, Run mode, Review side tabs, Save orientation.
- Round navigation buttons: Back and Home should stay visually consistent across flow pages.
- Key action buttons: Get Start, Use Selection, Use Block, Run/Start, Accept, Save + Export should share hierarchy but not all be identical sizes.
- Glass panels: use sparingly; avoid nested card-in-card framing.
- Chart surfaces: keep Review and Manual aligned before tuning local chart size.

## Safe Cleanup Rules

- Safe: keep `app/static/app.js` as a JavaScript manifest/legacy path and edit ordered chunks in `app/static/js/`.
- Safe: keep `app/static/styles.css` as an import manifest and edit the ordered files in `app/static/styles/`.
- Safe: remove exact duplicate CSS rules when a later identical rule remains.
- Safe: remove JS functions that are never called and reference DOM ids that no longer exist.
- Safe: update docs, contract enumerations, and tests to match real payloads.
- Risky: merging repeated selectors with different declarations.
- Risky: removing `!important` without visual checking.
- Risky: changing shared classes used by multiple pages without checking every page.

## Minimum Checks

Run these after cleanup or UI refactors:

```powershell
python -m unittest discover -s tests -p "test_frontend_static_integrity.py"
python -m unittest discover -s tests
python main.py --demo-data
.\.codex_tmp\node_runtime\extract\node-v24.16.0-win-x64\node.exe --check app/static/app.js
git diff --check
```

`git diff --check` may emit LF/CRLF warnings on Windows. Treat real whitespace errors separately from those warnings.

## Low-Token Handoff Prompt

Use this when continuing in a new window:

```text
Read docs/UI_BASELINE.md and docs/FRONTEND_STRUCTURE.md first.
Preserve the accepted UI. Work page-by-page.
Do not mechanically delete repeated CSS selectors unless rule bodies are exactly duplicated.
Save/Accept is not final: tune design first, clean CSS after approval.
Run unittest, demo-data, JS syntax check, and git diff --check after changes.
```
