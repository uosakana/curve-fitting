# ML Records And Training

This document describes the current, implemented ML data flow. It replaces the
old planning notes with commands and contracts that match the repository.

## Data Flow

```text
Web app fit result
  -> labeled fit_record_*.json in app_data/records/
  -> flattened dataset CSV + manifest in app_data/datasets/
  -> optional offline zip package in app_data/packages/
  -> optional Random Forest model artifacts in app_data/models/
  -> optional release model bundle in app_data/models/bundles/
  -> local ML endpoints for similar records and pre/post-fit recommendations
```

Runtime data under `app_data/` is local output and is not committed by default.

## Record Contract

Saved records use `ml.record_schema.normalize_record_payload()` and currently
write:

- `schema_version`
- `record_type`
- `data_selection`
- `sample_context`
- `analysis_settings`
- `manual_parameters`
- `manual_history`
- `fit_delta`
- `training_summary`
- `component_series`
- `labels`
- `human_labels`
- `selected_result`
- `candidate_context`
- `result`

The fitting result may contain component series in either `result.series` or
`result.fit.series`. Normalization accepts both and fills both positions in the
saved record.

Schema v3 keeps the legacy `result` payload as the full selected fit while adding
smaller ML-facing summaries:

- `analysis_settings.product_fit_mode`: `fast_fit`, `diagnostic_fit`, or `legacy`.
- `selected_result`: the final result being saved, including display mode,
  candidate source/rank, evaluator kind, n/m, stats, and point count.
- `candidate_context`: ranked candidate summaries without duplicating full
  series arrays; this is diagnostic context, not a training label by itself.
- `human_labels`: normalized copy of the final save-form labels. Existing code
  can continue reading `labels`.

Important result fields for downstream analysis:

- `result.evaluator_kind`
- `result.model_context`
- `result.parameter_schema`
- `result.manual_capability`
- `result.fit.n`
- `result.fit.m`
- `result.fit.params`
- `result.fit.stats`
- `result.fit.diagnostics`

## Labels

Core label fields:

- `accepted`
- `quality`: `good`, `acceptable`, `poor`, `reject`
- `confidence`: `high`, `medium`, `low`
- `hypothesis`
- `external_evidence`
- `accept_reasons`
- `main_issue`
- `next_actions`
- `notes`

The default dataset builder keeps records where:

```text
accepted = true OR quality in {good, acceptable}
```

Use `--include-rejected` when building risk or rejection-oriented datasets.

## Build A Dataset

Build a candidate dataset from local records:

```powershell
python -m ml.build_dataset
```

Include rejected/poor records:

```powershell
python -m ml.build_dataset --include-rejected
```

Outputs:

```text
app_data/datasets/fit_dataset_<timestamp>.csv
app_data/datasets/fit_dataset_<timestamp>_manifest.json
```

The manifest records feature columns, label columns, context columns, filtering
rules, and deterministic group-hash split counts.

## Export Offline Package

Build a zip package for collecting records from an offline machine:

```powershell
python -m ml.export_package
```

Include rejected/poor records:

```powershell
python -m ml.export_package --include-rejected
```

Outputs go to:

```text
app_data/packages/
```

The package contains raw JSON records, the flattened dataset CSV, the dataset
manifest, and a package manifest.

## Train Baselines

Train one Random Forest baseline from records:

```powershell
python -m ml.train_baseline --task strategy
```

Train all implemented tasks:

```powershell
python -m ml.train_baseline --task all
```

Train from an existing dataset CSV:

```powershell
python -m ml.train_baseline --dataset app_data/datasets/fit_dataset_<timestamp>.csv --task quality
```

Include rejected/poor records while building the dataset before training:

```powershell
python -m ml.train_baseline --task quality --include-rejected
```

Outputs:

```text
app_data/models/<task>_random_forest_<timestamp>.pkl
app_data/models/<task>_random_forest_<timestamp>_metrics.json
```

## Implemented Tasks

Current tasks are defined in `ml.training_tasks.TASK_DEFS`:

- `strategy`: predict whether Fast Fit or Diagnostic Fit is likely useful from
  curve shape and sample context.
- `quality`: predict fit quality or risk after a fit has been evaluated.
- `scan_m`: predict whether exponent scanning is likely useful.
- `hypothesis`: assist hypothesis selection from diagnostics and sample context.

`strategy` and `scan_m` use mostly pre-fit curve features. `quality` and
`hypothesis` use post-fit diagnostics and should be treated as post-fit review
helpers.

## Runtime Framework

The ML code is split into layers:

- `ml.training_tasks`: task definitions, feature groups, and prefit/postfit phase metadata.
- `ml.record_schema`: saved-record normalization and v3 summaries.
- `ml.record_features`: flatten records into CSV/inference rows.
- `ml.similar_records`: sklearn-free nearest historical record retrieval.
- `ml.model_registry`: local model artifact discovery and metrics summaries.
- `ml.model_bundle`: bundle latest local artifacts with a release manifest.
- `ml.model_inference`: load latest local artifacts and run predictions.
- `ml.baseline_training`: train Random Forest baseline artifacts.

FastAPI exposes these framework endpoints:

- `GET /api/ml/tasks?phase=prefit|postfit`
- `GET /api/ml/models?phase=prefit|postfit`
- `GET /api/ml/bundles`
- `POST /api/ml/similar?phase=prefit|postfit`
- `POST /api/ml/prefit`
- `POST /api/ml/postfit`

`/api/ml/prefit` combines pre-fit similar records with any available pre-fit
model artifacts (`strategy`, `scan_m`). `/api/ml/postfit` combines post-fit
similar records with post-fit artifacts (`quality`, `hypothesis`). Missing model
artifacts return `status: "no_models"` rather than failing the workflow.

## ML Fit Assist

ML assist is a fit scheduler, not a replacement for deterministic physical
fitting. The web app can send `ml_assist_enabled=true` and an
`ml_assist_mode`:

- `advisory`: report suggestions only; no fit settings are changed.
- `auto_fit_mode`: apply a confident `fast_fit`/`diagnostic_fit` recommendation.
- `efficiency`: only apply a confident `fast_fit` recommendation.
- `quality`: only apply a confident `diagnostic_fit` recommendation.

The backend writes an `ml_assist` audit block into the result and saved record.
It includes requested settings, suggested overrides, applied overrides, local
model status, similar-record status, and policy messages. This keeps later
backtesting possible: records can distinguish fits that merely saw an ML
suggestion from fits where ML actually changed the requested fit mode.

## Cautions

- Do not treat model output as a physical conclusion.
- Keep train/val/test split grouped by `comparison_group`, `sample_batch`, or
  `sample_id` to reduce leakage.
- Check the metrics JSON before using a model in the web app.
- Small datasets are expected; rule-based advice and similar-record retrieval
  remain the primary fallback.
