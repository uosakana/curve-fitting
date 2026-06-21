from __future__ import annotations

from typing import Any

from fit.parameter_schema import (
    BASE_EVALUATOR_KIND,
    CUSTOM_EVALUATOR_KIND,
    POST_FIT_EVALUATOR_KIND,
    fit_contract_payload,
)
from ml.record_schema import SCHEMA_VERSION as RECORD_SCHEMA_VERSION


APP_CONTRACT_VERSION = 1

PRODUCT_FIT_MODES = (
    {
        "id": "fast_fit",
        "label": "Fast Fit",
        "description": "Quick baseline fit for preview, range checks, and fast iteration.",
    },
    {
        "id": "diagnostic_fit",
        "label": "Diagnostic Fit",
        "description": "Full diagnostic search with ranked candidates and post-fit checks.",
    },
)

FIT_RESULT_REQUIRED_TOP_LEVEL = (
    "dataset",
    "fit",
    "series",
    "diagnostics",
    "model_context",
    "parameter_schema",
    "manual_capability",
    "evaluator_kind",
    "candidates",
)

FIT_SERIES_REQUIRED_KEYS = (
    "voltage",
    "measured",
    "fitted",
    "diode",
    "ohmic",
    "nonohmic",
)

FIT_SERIES_OPTIONAL_KEYS = (
    "relative_error",
    "recombination",
    "diffusion",
)

CANDIDATE_CORE_KEYS = (
    "rank",
    "source",
    "label",
    "reason",
    "is_primary",
    "diagnostic_only",
    "promotable",
    "stats",
    "manual_capability",
    "evaluator_kind",
)

CANDIDATE_SOURCES = (
    "primary_fit",
    "strategy_fit",
    "strategy_sweep",
    "nm_profile",
    "baseline_family",
    "diagnostic_ablation",
    "post_fit_diagnostic",
    "manual_fit",
)

SERVICE_METHODS = (
    {
        "id": "inspect_data_file",
        "http": {"method": "POST", "path": "/api/inspect"},
        "desktop": "inspectDataFile",
        "summary": "Upload or re-inspect a data file and return sheet/preview metadata.",
    },
    {
        "id": "read_data_grid",
        "http": {"method": "GET", "path": "/api/grid"},
        "desktop": "readDataGrid",
        "summary": "Read a bounded spreadsheet preview window for range selection.",
    },
    {
        "id": "parse_txt",
        "http": {"method": "POST", "path": "/api/txt-import/parse"},
        "desktop": "parseTxt",
        "summary": "Parse TXT measurement blocks before activation.",
    },
    {
        "id": "activate_txt_block",
        "http": {"method": "POST", "path": "/api/txt-import/activate"},
        "desktop": "activateTxtBlock",
        "summary": "Convert one parsed TXT block into a generated CSV upload.",
    },
    {
        "id": "analyze_fit",
        "http": {"method": "POST", "path": "/api/analyze"},
        "desktop": "analyzeFit",
        "summary": "Run Fast Fit or Diagnostic Fit and return a FitResult payload.",
    },
    {
        "id": "evaluate_manual_params",
        "http": {"method": "POST", "path": "/api/evaluate"},
        "desktop": "evaluateManualParams",
        "summary": "Evaluate base J0/Rs/Rsh/k parameters without optimization.",
    },
    {
        "id": "save_record",
        "http": {"method": "POST", "path": "/api/records"},
        "desktop": "saveRecord",
        "summary": "Save an accepted fit record with normalized record schema.",
    },
    {
        "id": "ml_prefit",
        "http": {"method": "POST", "path": "/api/ml/prefit"},
        "desktop": "mlPrefit",
        "summary": "Return prefit similar-record and local-model advice.",
    },
    {
        "id": "ml_postfit",
        "http": {"method": "POST", "path": "/api/ml/postfit"},
        "desktop": "mlPostfit",
        "summary": "Return postfit similar-record and local-model advice.",
    },
    {
        "id": "assistant_chat",
        "http": {"method": "POST", "path": "/api/assistant/chat"},
        "desktop": "assistantChat",
        "summary": "Answer local fit-analysis questions from the active result.",
    },
)

WORKSPACE_AREAS = (
    {"id": "project", "label": "Project"},
    {"id": "data", "label": "Data"},
    {"id": "fit", "label": "Fit"},
    {"id": "review", "label": "Review"},
    {"id": "records", "label": "Records"},
    {"id": "models", "label": "Models"},
)


def app_contract_payload() -> dict[str, Any]:
    return {
        "schema_version": APP_CONTRACT_VERSION,
        "product_name": "Dark Current Studio",
        "runtime_targets": ["http", "desktop_bridge"],
        "workspace_areas": list(WORKSPACE_AREAS),
        "product_fit_modes": list(PRODUCT_FIT_MODES),
        "evaluator_kinds": {
            "base": BASE_EVALUATOR_KIND,
            "post_fit": POST_FIT_EVALUATOR_KIND,
            "custom": CUSTOM_EVALUATOR_KIND,
        },
        "fit_result": {
            "required_top_level": list(FIT_RESULT_REQUIRED_TOP_LEVEL),
            "series_required_keys": list(FIT_SERIES_REQUIRED_KEYS),
            "series_optional_keys": list(FIT_SERIES_OPTIONAL_KEYS),
            "candidate_core_keys": list(CANDIDATE_CORE_KEYS),
            "candidate_sources": list(CANDIDATE_SOURCES),
        },
        "manual_evaluate": {
            "allowed_evaluator_kind": BASE_EVALUATOR_KIND,
            "authority_field": "manual_capability.can_evaluate",
        },
        "record": {
            "schema_version": RECORD_SCHEMA_VERSION,
            "required_save_payload_keys": ["result"],
        },
        "services": list(SERVICE_METHODS),
        "fit_contract": fit_contract_payload(),
    }
