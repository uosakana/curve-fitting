# Current Functional Boundary

This document freezes the current application capability surface before the
desktop-product refactor. The goal is to keep behavior stable while moving
business logic out of FastAPI endpoints and into reusable Python services.

## In Scope

- Import Excel, XLS, CSV, TXT, and CV-style source files.
- Inspect workbook sheets and grid windows before selecting a current series.
- Activate parsed TXT blocks as generated CSV uploads for the same fitting flow.
- Run Fast Fit for quick baseline previews.
- Run Diagnostic Fit for strategy sweep, effective n/m profiling, baseline-family
  comparison, ranked candidates, and post-fit diagnostics.
- Evaluate manual `J0/Rs/Rsh/k` parameters only when the result contract says
  `manual_capability.can_evaluate` is true.
- Save accepted/manual/candidate fit records using the normalized v3-compatible
  record shape.
- Export component series as CSV/XLSX, fitpack JSON, record datasets, and offline
  record packages.
- List local ML tasks, local model artifacts, model bundles, similar records, and
  prefit/postfit ML recommendation payloads.
- Answer local assistant questions from the current fit result without cloud calls.

## Out Of Scope For Service Extraction

- pywebview or PySide6 desktop bridge.
- New project file format.
- New physical model behavior.
- New ML model training semantics.
- Removing FastAPI or changing existing `/api/...` routes.

## Service Boundary

`app_services/` is the reusable application layer. It may call `data_io/`,
`fit/`, `ml/`, `result/`, and payload helpers, but it should not depend on
FastAPI request or response classes.

`app/fastapi_server.py` is now an adapter layer. It should own HTTP-only details:

- route declarations;
- `Form`, `Body`, `File`, and `UploadFile` parsing;
- upload-id lookup;
- `FileResponse` and `Response` construction;
- HTTP status conversion.

Future desktop code should call `app_services/` directly instead of routing
through HTTP.
