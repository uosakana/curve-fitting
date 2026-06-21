# JV/I-V Dark Current Fitting Workbench

Local tools for fitting dark-current JV/I-V curves, reviewing model diagnostics,
manual parameter tuning, and saving labeled records for later ML-assisted
recommendations.

## Entry Points

Install dependencies:

```powershell
pip install -r requirements.txt
```

Start the local web app:

```powershell
python desktop_app.py
```


To create a Windows preview package for another PC, run this on the build
computer:

```text
build_preview_package.bat
```

It creates `dist/DarkCurrentWorkbenchPreview.zip`. The recipient only needs to
extract the zip and double-click `Start Preview.bat`.

Or start FastAPI directly:

```powershell
python -m uvicorn app.fastapi_server:app --host 127.0.0.1 --port 8011
```

Then open:

```text
http://127.0.0.1:8011/
```

Run the non-interactive CLI on the built-in sample:

```powershell
python main.py --demo-data
```

Run the CLI on a data file:

```powershell
python main.py --data path\to\data.xlsx --current-range B2:B82 --voltage-start -0.5 --voltage-end 0.3 --voltage-step 0.01
```

Use the web app for manual tuning. `main.py` is intentionally batch-only.

## Capabilities

- Import Excel, CSV, TXT, and CV-style data through `data_io/`.
- Fit the base `J0/Rs/Rsh/k` dark-current model with configurable `n` and `m`.
- Run Fast Fit for quick baseline previews or Diagnostic Fit for ranked candidates.
- Diagnostic Fit runs strategy sweeps, exponent profiles, model comparison, and post-fit diagnostics.
- Keep fitted/displayed/manual/accepted results separate in the frontend state.
- Save labeled records with component series for ML dataset building.
- Export offline record packages and train local baseline recommenders.

## API Contract

Backend fitting responses expose a stable result payload with:

- `dataset`
- `fit`
- `series`
- `diagnostics`
- `model_context`
- `parameter_schema`
- `manual_capability`
- `evaluator_kind`
- `candidates`

Manual live evaluation is allowed only when
`manual_capability.can_evaluate === true`. The `/api/evaluate` endpoint is the
base `J0/Rs/Rsh/k` evaluator; promoted post-fit or custom model displays should
not be live-evaluated through it.

The web app exposes two product modes:

- Fast Fit runs a quick baseline for preview and data-window checks.
- Diagnostic Fit ranks robust strategy, effective `n/m`, baseline-family, and post-fit candidates.

The individual strategy, exponent-profile, M-model, and post-fit diagnostics remain visible in the payload and review diagnostics, but they are not separate top-level product modes.

The static fit contract is available at:

```text
GET /api/fit-contract
```

## Repository Layout

```text
app/           FastAPI adapter, local assistant, static frontend.
app_services/   Reusable service layer for HTTP and future desktop bridges.
contracts/      Stable runtime contract payloads.
data_io/        Excel, CSV, TXT, and CV import helpers.
fit/            Core model, optimization, workflow, model selection, post-fit models.
ml/             Record schema, feature extraction, package export, recommendation, training.
result/         Plotting and result persistence helpers.
docs/           Workspace, model-selection, physics metadata, and prior notes.
tests/          unittest coverage for contracts, importers, workflow, exports.
app_data/       Runtime uploads, records, datasets, packages, and models. Not committed.
outputs/        CLI output artifacts. Not committed.
```

## Useful Checks

```powershell
python -m unittest discover -s tests
python main.py --demo-data
git diff --check
```

`git diff --check` may report LF/CRLF warnings on Windows; those are not
whitespace errors.

## Runtime Cleanup

The web app automatically clears `app_data/uploads/` when the local FastAPI
process shuts down normally. These files are temporary import caches, not saved
records.

Preview ignored upload cleanup without deleting files:

```powershell
python tools/cleanup_runtime_data.py --target uploads --older-than-days 7
```

Delete only after reviewing the dry-run output:

```powershell
python tools/cleanup_runtime_data.py --target uploads --older-than-days 7 --apply --remove-empty-dirs
```

## Documentation

- `docs/WORKSPACE.md`: workspace boundaries and suggested change groups.
- `docs/UI_BASELINE.md`: accepted frontend baseline, page status, cleanup rules, and low-token handoff prompt.
- `docs/CONTRACTS.md`: runtime contract boundary and frontend type guidance.
- `docs/FUNCTIONAL_BOUNDARY.md`: current capability surface and service boundary.
- `docs/ML_RECORDS_AND_TRAINING.md`: current ML record, dataset, package, and baseline training flow.
- `docs/MODEL_SELECTION.md`: model-selection roadmap.
- `docs/PHYSICS_PARAMETER_REQUIREMENTS.md`: metadata needed for advanced physical models.
- `docs/DEVICE_METADATA_TEMPLATE.md`: reusable device metadata template.
- `docs/LITERATURE_PRIORS_PBS_CQD_NORMAL_PD.md`: retained literature-prior summary.
