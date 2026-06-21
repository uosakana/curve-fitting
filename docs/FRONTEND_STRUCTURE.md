# Frontend Structure

The runtime frontend is the static HTML/CSS/JS app served by FastAPI.

## Runtime Files

- `app/static/index.html` owns the page sections, stable DOM ids, and script/style includes.
- `app/static/app.js` is the JavaScript manifest/legacy tooling path.
- `app/static/js/` owns runtime state, API calls, workflow transitions, chart drawing, manual tuning, import/export, and event binding, split in execution order.
- `app/static/styles.css` is the stylesheet manifest. It imports ordered CSS parts from `app/static/styles/`.
- `app/static/styles/` owns the visual system and page layouts, split in cascade order.

## Runtime Result State

`app.js` uses four result slots with separate meanings:

- `autoFitResult`: the latest automatic backend result.
- `displayResult`: the result currently shown in charts and diagnostics.
- `manualDraftResult`: an unaccepted manual live-evaluation draft.
- `acceptedResult`: the result selected for save/export.

Do not collapse these into one generic result variable. Manual live evaluation should stay gated by `manual_capability.can_evaluate === true`.

## Product Fit Modes

The main product flow exposes only two modes:

- `fast_fit`: quick baseline fit for preview and data-window checks.
- `diagnostic_fit`: full diagnostic pipeline that runs robust strategy search, effective n/m profile search, baseline-family comparison, and post-fit diagnostics.

Individual algorithm toggles can exist as internal/debug controls, but they should not be the primary product choice. Backend requests should include `product_fit_mode`, and result payloads should include ranked `candidates` for review.

## `app.js` Sections

`app/static/app.js` should remain a small manifest comment. Runtime JavaScript lives in `app/static/js/` and is loaded from `index.html` as ordered classic scripts. Keep the numeric filename prefixes and script tags in the same order.

- App state and contract defaults
- Fit result state and shared DOM helpers
- Parameter control metadata
- Status, element helpers, and API contract bootstrap
- Home page visual effects
- Formatting, navigation, and input parsing
- Parameter payload and manual capability helpers
- Backend request builders
- Fit series, snapshots, and training record payloads
- Records, exports, and fitpack persistence
- TXT import workflow
- Excel preview and range picker workflow
- Fit execution and manual live evaluation
- Result rendering and manual draft history
- Save page and device metadata editing
- Fit diagnostics and assistant rendering
- Charts and active view redraw
- Event binding and application bootstrap

## `styles.css` Sections

`app/static/styles.css` should contain only ordered `@import` statements plus a short manifest comment. Keep the imported files in cascade order:

- Theme tokens and base elements
- Home and model entry pages
- Home visual layer and motion
- Workbench shell and shared controls
- Data picker and spreadsheet range selection
- TXT import workflow
- Review, manual, and save flows
- Workbench results, charts, and diagnostics
- Records, exports, assistant, and evidence forms
- Responsive layout breakpoints
- Imported TXT, Select Data, Run, and early Review refreshes
- Unified flow, Home mega menu, Run console, Review tabs, and Save dialog passes
- Later Home, Select Data, TXT, Run, Review, Manual, Save, and Accept passes
- Shared UI infrastructure
- Final ownership layers for shared TXT/Home controls, Save, Manual, and Review

## CSS Maintenance Rules

The current visual system was built through several page-level passes. Preserve the rendered UI first, then reduce layering gradually.

- Do not add another broad `UI pass` override block when a page already has a scoped final rule. Edit the final scoped rule instead.
- Exact duplicate rules may be removed when a later identical rule remains. Prefer deleting the earlier copy so the final cascade stays intact.
- Repeated selectors with different declarations are not safe to delete mechanically; inspect the cascade and current page rendering first.
- Avoid new `!important` unless the rule is intentionally overriding a legacy layer that cannot be removed in the same change.
- For shared controls such as motion tabs, round nav buttons, key action buttons, glass panels, and chart surfaces, update the shared class before adding page-specific overrides.
- Files `10-17` are cascade-preserving cleanup chunks extracted from former late override passes. Files `18-21` are scoped final ownership layers for shared TXT/Home controls, Save, Manual, and Review. Edit the latest relevant scoped layer first; do not reorder these imports without a visual check.

## Event Binding Groups

`bindEvents()` is only the bootstrap dispatcher. Add new event listeners to the narrowest matching group:

- `bindHomeEvents()`: home entry buttons and file picker triggers.
- `bindTxtImportEvents()`: TXT parser page controls and selected-block activation.
- `bindFitpackEvents()`: saved fitpack import.
- `bindDataPickerEvents()`: spreadsheet picker, grid selection, uploaded file inspection, and data range inputs.
- `bindFitControlEvents()`: run fit, model mode controls, and sidebar parameter editor events.
- `bindRecordAndExportEvents()`: legacy workbench record form and workbench export buttons.
- `bindFlowNavigationEvents()`: model/review/manual/save page transitions.
- `bindManualEvents()`: manual page actions, history, and manual parameter wheel/input events.
- `bindSavePageEvents()`: save page exports and device stack metadata editing.
- `bindAssistantEvents()`: assistant compose/clear/send shortcuts.
- `bindChartEvents()`: chart hover tooltips.
- `bindViewEvents()`: diagnostic tabs and resize redraw.

## Result Rendering Helpers

Keep `renderResult()` as the top-level workbench result renderer. Put details in the narrow helpers:

- `renderWorkbenchMetrics()`: top metric strip.
- `syncResultParameterEditor()`: sidebar parameter editor sync.
- `renderResultDiagnostics()`: assistant, regions, core diagnostics, strategy/profile/model tables.
- `renderReviewResult()`: result review page renderer.
- `renderReviewMetrics()`, `renderReviewNotes()`, `renderReviewSeries()`: review page subregions.
- `renderManualDraftResult()` and `renderManualHistory()`: manual draft and checkpoint UI.

## Diagnostics Helpers

- `renderCoreDiagnostics()` delegates initialization, DE fallback, identifiability, boundary hits, and warnings to focused helpers.
- `renderDeepStrategySummary()` delegates strategy gain summary and n/m profile summary separately.
- `renderModelTable()` delegates row normalization, recommended baseline labeling, and decision labeling to focused helpers.
- Product wording for Fast Fit, Diagnostic Fit, n/m profile, M-model, and post-fit diagnostics should be changed in these helpers and in `index.html`, not inside backend request code.

## Data Picker Helpers

- `resetDataFileSession()` clears result, manual, assistant, TXT, and grid state for a newly selected spreadsheet/CSV file.
- `handleDataFileSelection()` is the file input handler and owns the inspect-on-select flow.
- `handleDataRangeInput()` owns current/voltage range input side effects.

## Editing Rules

- Before changing an HTML id, search `app/static/app.js` for every reference and update all bindings together.
- Before changing an HTML id, search `app/static/js/` for every reference and update all bindings together.
- Keep visual-only CSS changes inside the relevant CSS section first. Move shared styling only when two or more sections genuinely need the same rule.
- Keep API shape assumptions near the request/render code that consumes them, and keep `FitResultPayload` contract changes mirrored in backend tests.
- Prefer small page-level UI changes over global restyling. The workbench has multiple flows that share buttons, fields, and panels.
- Keep `tests/test_frontend_static_integrity.py` green after frontend cleanup. It checks duplicate HTML ids, direct JS id references across loaded chunks, static asset paths, script/style cache versions, JS chunk order, CSS brace balance, and exact duplicate CSS rules.

## Useful Prompt Shape

For a precise UI change, provide:

- Page: for example `manualPage`, `resultPage`, `txtImportPage`, or `homePage`.
- Target: id/class or visible text, for example `manualHistoryList`, `review-analysis-grid`, or "Post-fit diagnostics toggle".
- Desired change: size, position, visibility, animation, spacing, color, or interaction.
- Viewport: desktop, laptop, or mobile; include approximate width if relevant.
- Constraint: what must not change, for example "do not change API calls" or "keep manual live evaluate disabled when capability is false".

Example:

```text
Page: manualPage
Target: right parameter panel and manual history strip
Change: make the history strip shorter and keep the parameter inputs visible without scrolling on a 1366x768 laptop
Constraint: do not change manual evaluate/refit behavior
```
