# Current Diff Review

Date: 2026-06-17

This document freezes the current dirty-worktree review boundary after the confirmed UI baseline. It is intended to guide narrow staging and commits. Do not treat this as a commit log; it is a checklist for what to review before staging.

## Verified Baseline

Commands that passed before this document was written:

```powershell
python -m unittest discover -s tests -p test_frontend_static_integrity.py
python -m unittest discover -s tests
python main.py --demo-data
git diff --check
```

Manual UI notes:

- Home, Select Data, TXT Data, Run Fit, Review, Manual, and Save have been visually tuned.
- Save page is confirmed to depend on several restored legacy/final cascade layers. Do not large-delete `app/static/styles/19-save-page-final.css`; only add scoped final ownership rules or migrate one small section at a time after visual confirmation.
- `app/static/styles/05-data-picker.css` currently appears as modified in `git status`, but `git diff -- app/static/styles/05-data-picker.css` shows no content diff. Treat it as line-ending/stat noise unless a real diff appears.

## Group 1: Workspace Entry

Files:

- `.gitignore`

Intent:

- Ignore root-level CSV and fitpack pressure-test files so local imported samples do not pollute `git status`.

Review risk: low.

Stage:

```powershell
git add -- .gitignore
```

## Group 2: Frontend Flow And UI Baseline

Files:

- `app/static/index.html`
- `app/static/js/01-state-contract.js`
- `app/static/js/02-result-state.js`
- `app/static/js/06-format-navigation.js`
- `app/static/js/09-fit-series-record-payload.js`
- `app/static/js/11-txt-import.js`
- `app/static/js/12-data-picker.js`
- `app/static/js/14-result-rendering.js`
- `app/static/js/15-save-device.js`
- `app/static/js/17-charts-redraw.js`
- `app/static/js/18-events-bootstrap.js`
- `app/static/styles.css`
- `app/static/styles/16-txt-manual-save-loading.css` removed
- `app/static/styles/18-accept-review-final-overrides.css` removed
- `app/static/styles/16-txt-manual-review-loading.css` added
- `app/static/styles/18-txt-home-shared-final.css` added
- `app/static/styles/19-save-page-final.css` added
- `app/static/styles/20-manual-page-final.css` added
- `app/static/styles/21-review-page-final.css` added

Intent:

- Freeze the confirmed frontend baseline.
- Split the old late override CSS into scoped ownership layers.
- Keep Save page working with restored cascade ownership plus final direct-device-stack rules.
- Add Save custom select/suggestion controls.
- Keep candidate display, extended component rendering, TXT/XLSX Core-Full tabs, and current page navigation behavior.

Review risk: high visually, medium behaviorally.

Human confirmation checklist:

- Save page: direct device stack is visible, no old click-to-open square, Structure checked is the small green status, normal/reverse tab animates, Save stays anchored.
- Review: candidate stack scroll/wheel, selected candidate chart, current model label.
- Manual: star, checkpoint add, accept button, chart alignment.
- XLSX/TXT: Core-Full tabs, Use Selection/Use Block, preview chart grid.

Stage:

```powershell
git add -- app/static/index.html app/static/js app/static/styles.css app/static/styles
```

Note: verify `git diff -- app/static/styles/05-data-picker.css` before staging if it still appears as modified with no content diff.

## Group 3: Web API And App Services

Files:

- `app/api_utils.py`
- `app/fastapi_server.py`
- `app_services/data_service.py`

Intent:

- Include extended post-fit component arrays in API fit series.
- Increase grid endpoint/service defaults to support large irregular workbooks.

Review risk: medium.

Stage:

```powershell
git add -- app/api_utils.py app/fastapi_server.py app_services/data_service.py
```

## Group 4: Data Import

Files:

- `data_io/data_source.py`

Intent:

- Add CSV encoding fallback for equipment-exported CSV files.
- Support larger grid windows with explicit max caps.
- Keep Excel sheet inspection scoped with context-managed `ExcelFile`.

Review risk: medium.

Stage:

```powershell
git add -- data_io/data_source.py
```

## Group 5: Post-Fit And Workflow Components

Files:

- `fit/post_fit.py`
- `fit/workflow.py`

Intent:

- Separate empirical non-ohmic current from extra post-fit branch current.
- Expose `extra_current`, `extended_nonohmic_total`, and `v_drop` in post-fit selected candidates.
- Make reconstructed workflow currents sum with extra branch current when available.

Review risk: medium-high because it affects candidate component interpretation.

Stage:

```powershell
git add -- fit/post_fit.py fit/workflow.py
```

## Group 6: ML Record Schema

Files:

- `ml/record_schema.py`

Intent:

- Preserve extended branch current columns in saved/exported records.

Review risk: low-medium.

Stage:

```powershell
git add -- ml/record_schema.py
```

## Group 7: Tests

Files:

- `tests/test_post_fit_series.py`
- `tests/test_csv_import.py`

Intent:

- Cover separated extended non-ohmic branches.
- Cover GB18030 CSV import, deep CSV headers, and wide XLSX grid loading.

Review risk: low.

Stage:

```powershell
git add -- tests/test_post_fit_series.py tests/test_csv_import.py
```

## Group 8: Docs

Files:

- `docs/WORKSPACE.md`
- `docs/FRONTEND_STRUCTURE.md`
- `docs/MODEL_SELECTION.md`
- `docs/CURRENT_DIFF_REVIEW.md`

Intent:

- Record final CSS ownership layers and staging boundaries.
- Add model-selection literature context.
- Provide this current review checklist.

Review risk: low.

Stage:

```powershell
git add -- docs/WORKSPACE.md docs/FRONTEND_STRUCTURE.md docs/MODEL_SELECTION.md docs/CURRENT_DIFF_REVIEW.md
```

## Suggested Commit Order

1. Workspace ignore rules.
2. Data import plus web API/app service grid changes.
3. Post-fit/workflow/ML record schema plus tests.
4. Frontend UI baseline.
5. Docs.

Before the frontend commit, rerun:

```powershell
python -m unittest discover -s tests -p test_frontend_static_integrity.py
python -m unittest discover -s tests
git diff --check
```
