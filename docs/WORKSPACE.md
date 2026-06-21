# Workspace Organization

This repository is organized around the dark-current JV/I-V fitting workflow. Keep code changes grouped by topic so fitting behavior, web API behavior, frontend state flow, data import, post-fit model work, ML records, docs, and tests can be reviewed independently.

## Source Areas

- `main.py`: non-interactive batch CLI entry point.
- `desktop_app.py`: local desktop launcher for the web app.
- `app/`: FastAPI HTTP adapter, local assistant, static frontend assets.
- `app_services/`: reusable application services shared by HTTP and future desktop bridges.
- `contracts/`: stable runtime contract payloads shared by HTTP, the static frontend, and future desktop bridges.
- `data_io/`: Excel, CSV, TXT, and CV import helpers.
- `fit/`: fitting configuration, core optimizer, model selection, post-fit models, workflow orchestration.
- `ml/`: record schema, feature extraction, recommendation, dataset export, baseline training.
- `result/`: plotting and result persistence helpers.
- `tests/`: unittest coverage for importers, contracts, model selection, workflow display decisions, exports.
- `docs/`: project notes, model assumptions, metadata templates, and workspace guidance.

## Runtime Data

The following are runtime or experiment outputs and should stay out of normal source commits:

- `app_data/uploads/`
- `app_data/records/`
- `app_data/datasets/`
- `app_data/packages/`
- `app_data/models/`
- `outputs/`
- local raw Excel/TXT measurement files
- `__pycache__/`

If curated training examples are ever versioned, put only reviewed and de-identified examples under a dedicated versioned directory such as `datasets/curated/`.

`app_data/uploads/` is a temporary import cache. The FastAPI app clears it on
normal shutdown; use the cleanup tool below for stale files left by forced exits
or interrupted development servers.

Preview ignored runtime cleanup before deleting upload or generated record data:

```powershell
python tools/cleanup_runtime_data.py --target uploads --older-than-days 7
```

After checking the dry-run output, apply cleanup explicitly:

```powershell
python tools/cleanup_runtime_data.py --target uploads --older-than-days 7 --apply --remove-empty-dirs
```

## Pending Change Groups

Use these groups when staging or reviewing the current uncommitted work. Do not mix groups unless the change is intentionally cross-cutting.

Review a group with:

```powershell
git diff -- <paths>
```

Stage a group with:

```powershell
git add -- <paths>
```

Use the exact path lists below as the review boundary for each topic.

### workspace-entry

- `.gitignore`
- `README.md`
- `main.py`
- `desktop_app.py`
- `tools/cleanup_runtime_data.py`

### web-api

- `app/fastapi_server.py`
- `app/api_utils.py`
- `app/local_assistant.py`

### app-services

- `app_services/__init__.py`
- `app_services/assistant_service.py`
- `app_services/data_service.py`
- `app_services/export_service.py`
- `app_services/fit_service.py`
- `app_services/ml_service.py`
- `app_services/product_modes.py`
- `app_services/record_service.py`

### contracts

- `contracts/__init__.py`
- `contracts/app_contract.py`

### frontend-flow

- `app/static/fonts/`
- `app/static/app.js`
- `app/static/js/`
- `app/static/index.html`
- `app/static/styles.css`
- `app/static/styles/`

Keep local concept pages and screenshots out of this group unless they are intentionally promoted into the product.

### data-import

- `data_io/__init__.py`
- `data_io/data_source.py`
- `data_io/cv_import.py`
- `data_io/txt_import.py`

### fit-core

- `config.py`
- `fit/__init__.py`
- `fit/advice.py`
- `fit/core.py`
- `fit/initialize_parameters.py`
- `fit/optimization.py`
- `fit/parameter_schema.py`
- `fit/region_stats.py`
- `fit/strategy.py`
- `fit/workflow.py`

### post-fit-models

- `fit/post_fit.py`
- `fit/cqd_heterointerface.py`

### ml-records

- `ml/baseline_training.py`
- `ml/dataset_builder.py`
- `ml/fit_assist.py`
- `ml/model_bundle.py`
- `ml/model_inference.py`
- `ml/model_registry.py`
- `ml/record_schema.py`
- `ml/record_features.py`
- `ml/recommender.py`
- `ml/similar_records.py`
- `ml/training_tasks.py`

### docs

- `docs/WORKSPACE.md`: workspace boundaries and staging groups.
- `docs/FRONTEND_STRUCTURE.md`: frontend file boundaries, cascade ownership, and editing rules.
- `docs/UI_BASELINE.md`: accepted frontend baseline, page-level cleanup rules, and low-token handoff prompt.
- `docs/FUNCTIONAL_BOUNDARY.md`: fixed current capability surface and service boundary.
- `docs/CONTRACTS.md`: runtime contract boundary for Python services, HTTP, the static frontend, and future desktop bridge.
- `docs/ML_RECORDS_AND_TRAINING.md`: current ML record, dataset, package, and baseline training flow.
- `docs/MODEL_SELECTION.md`: current model-selection roadmap.
- `docs/PHYSICS_PARAMETER_REQUIREMENTS.md`: metadata needed for advanced physical models.
- `docs/DEVICE_METADATA_TEMPLATE.md`: reusable metadata template.
- `docs/LITERATURE_PRIORS_PBS_CQD_NORMAL_PD.md`: retained literature-prior summary.
- Removed early encoded/stale planning notes and raw extraction drafts.

### tests

- `tests/*`

## Suggested Review Order

1. `fit-core`: establishes the shared parameter schema, default grids, model selection, optimizer behavior, and workflow result semantics.
2. `app-services`: keeps fitting, import, export, records, ML, and assistant behavior reusable outside FastAPI.
3. `contracts`: freezes the UI/service payload boundary before replacing any frontend runtime.
4. `web-api`: serializes the fit contract and exposes `/api/fit-contract`; should stay an HTTP adapter over services.
5. `frontend-flow`: consumes `manual_capability`, keeps auto/display/manual/accepted results separate, and gates live manual evaluation.
6. `ml-records`: normalizes saved records produced by the new payload shape and keeps older records readable.
7. `data-import` and `post-fit-models`: review independently after the main contract boundary is clear.
8. `workspace-entry`, `docs`, and `tests`: review last so entry-point docs and coverage match the final boundaries.

## Pressure Test Checklist

Run this checklist before staging a broad UI, payload, or fitting change:

- Excel generated-voltage import: choose a current column, run Core `-0.5..0.3 V`, and verify preview, Fast Fit, Diagnostic Fit, Review, Manual, Accept, and Save.
- Excel irregular workbook import: scroll after selecting a range, confirm headers and selected cells remain readable, then run the same flow.
- TXT device import: parse a normal device-export TXT, select dark and light blocks, confirm default `log_abs`, Core/Full switching, and `Use Block`.
- Invalid TXT/CV import: verify unsupported CV-like text is rejected or left unactivated with a clear error.
- Candidate review: confirm M4 physical, legacy double-diode, reverse diagnostic, and total-only candidates display with correct View/Summary behavior.
- Save/reopen: save a completed record, export the replay pack, reopen it from Home, and confirm the curve and accepted metadata restore.
- Regression commands: run `python -m unittest discover -s tests`, `python main.py --demo-data`, and `git diff --check`.

## Current Staging Paths

Use these commands only when the corresponding topic has been reviewed. They are intentionally separated so commits can stay narrow.

```powershell
git add -- .gitignore README.md main.py desktop_app.py
git add -- tools/cleanup_runtime_data.py
git add -- app/fastapi_server.py app/api_utils.py app/local_assistant.py
git add -- app_services
git add -- contracts
git add -- app/static/fonts app/static/app.js app/static/js app/static/index.html app/static/styles.css app/static/styles
git add -- data_io/__init__.py data_io/data_source.py data_io/cv_import.py data_io/txt_import.py
git add -- config.py fit/__init__.py fit/advice.py fit/core.py fit/initialize_parameters.py fit/optimization.py fit/parameter_schema.py fit/region_stats.py fit/strategy.py fit/workflow.py
git add -- fit/post_fit.py fit/cqd_heterointerface.py
git add -- ml/baseline_training.py ml/dataset_builder.py ml/fit_assist.py ml/model_bundle.py ml/model_inference.py ml/model_registry.py ml/record_features.py ml/record_schema.py ml/recommender.py ml/similar_records.py ml/training_tasks.py
git add -- docs/WORKSPACE.md docs/FRONTEND_STRUCTURE.md docs/UI_BASELINE.md docs/CONTRACTS.md docs/FUNCTIONAL_BOUNDARY.md docs/ML_RECORDS_AND_TRAINING.md docs/MODEL_SELECTION.md docs/PHYSICS_PARAMETER_REQUIREMENTS.md docs/DEVICE_METADATA_TEMPLATE.md docs/LITERATURE_PRIORS_PBS_CQD_NORMAL_PD.md
git add -- tests
```

## Contract Boundary

`app_services/` is the reusable business boundary for the current product. Service modules may call `data_io/`, `fit/`, `ml/`, `result/`, and payload helpers, but should not depend on FastAPI request/response classes. `app/fastapi_server.py` should remain an adapter for route declarations, upload-id lookup, form/body parsing, file responses, and HTTP error conversion.

Backend result payloads should expose these top-level fields consistently:

- `dataset`
- `fit`
- `series`
- `diagnostics`
- `model_context`
- `parameter_schema`
- `manual_capability`
- `evaluator_kind`
- `candidates`

The frontend should treat `manual_capability.can_evaluate` as the authority for manual live evaluation. ML record code should accept both `result.series` and `result.fit.series`, then normalize saved records so both positions are populated.

Frontend result handling should also normalize `result.series` and `result.fit.series` before rendering, exporting, or saving. This keeps reopened fitpacks and direct API responses on the same shape.

Saved ML records use a v3-compatible shape: `result` remains the full selected fit, `selected_result` stores a compact summary of the final saved display/manual/candidate result, and `candidate_context` stores ranked diagnostic candidates as context rather than direct labels. Save-form labels stay available as both `labels` and `human_labels`.

`parameter_schema.parameters` may include `lower`, `upper`, and `scale` only when the bounds belong to the same parameter names. Base `J0/Rs/Rsh/k` fits expose the shared bounds from `fit/parameter_schema.py`; post-fit or custom displays should omit bounds unless their own parameter metadata names match the displayed parameter names.

Product fit modes should stay simple:

- Fast Fit runs a quick baseline for preview and data-window checks.
- Diagnostic Fit runs the full diagnostic pipeline and returns ranked candidates.

Diagnostic internals should stay separate inside the payload and review diagnostics:

- Strategy search controls robust strategy sweep.
- Effective `n/m` profile controls bounded exponent profiling.
- Baseline-family comparison controls M0-M3/M4 ranking and rescue.
- Post-fit diagnostics run slower physical candidates and core-window checks after the baseline result.
