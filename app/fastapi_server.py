from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import quote

import uvicorn
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api_utils import (
    STATIC_DIR,
    UPLOADS,
    cleanup_uploads,
    fit_contract_payload,
    save_upload,
    json_compatible,
)
from app_services.assistant_service import assistant_chat_response
from app_services.data_service import activate_txt_block, inspect_data_file, parse_txt_upload, read_data_grid
from app_services.export_service import components_xlsx_export
from app_services.fit_service import analyze_file, evaluate_file, normalize_product_fit_mode
from app_services.ml_service import (
    find_similar,
    list_ml_bundles,
    list_ml_models,
    list_ml_tasks,
    ml_postfit_response,
    ml_prefit_response,
    ml_recommend_response,
)
from app_services.record_service import (
    export_training_records_dataset,
    export_training_records_package,
    list_training_records,
    recommend_from_training_records,
    save_training_record,
)
from contracts import app_contract_payload


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    try:
        yield
    finally:
        cleanup_uploads(all_files=True)


app = FastAPI(title="Dark Current Fitting Workbench", version="0.1.0", lifespan=app_lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_cache_static_assets(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/")
def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/api/fit-contract")
def fit_contract_endpoint():
    return {"ok": True, "contract": json_compatible(fit_contract_payload())}


@app.get("/api/app-contract")
def app_contract_endpoint():
    return {"ok": True, "contract": json_compatible(app_contract_payload())}


@app.post("/api/inspect")
async def inspect_endpoint(
    file: UploadFile | None = File(default=None),
    upload_id: str = Form(default=""),
    sheet_name: str = Form(default=""),
):
    try:
        if file is not None and file.filename:
            content = await file.read()
            upload_id, file_path = save_upload(file.filename, content)
        elif upload_id:
            file_path = UPLOADS.get(upload_id)
            if file_path is None:
                raise ValueError("Unknown upload id. Upload the file again.")
        else:
            raise ValueError("Upload a file before inspecting data.")

        return {"ok": True, "upload_id": upload_id, "file": inspect_data_file(file_path, sheet_name=sheet_name)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/analyze")
async def analyze_endpoint(
    upload_id: str = Form(...),
    sheet_name: str = Form(default=""),
    cell_range: str = Form(default=""),
    voltage_range: str = Form(default=""),
    current_range: str = Form(default=""),
    voltage_start: float = Form(default=-1.0),
    voltage_end: float = Form(default=1.0),
    voltage_step: float = Form(default=0.01),
    product_fit_mode: str = Form(default=""),
    mode: str = Form(default="fit"),
    fit_strategy: str = Form(default="quick_global"),
    sweep_strategies: bool = Form(default=False),
    reverse_weight: float = Form(default=1.5),
    near_zero_weight: float = Form(default=0.5),
    forward_weight: float = Form(default=1.0),
    high_forward_weight: float = Form(default=1.5),
    scan_m: bool = Form(default=False),
    scan_n: bool = Form(default=False),
    use_best_m_after_scan: bool = Form(default=True),
    compare_models: bool = Form(default=False),
    post_fit_models: bool = Form(default=False),
    m_values: str = Form(default=""),
    n_values: str = Form(default=""),
    use_initial_params: bool = Form(default=False),
    param_j0: str = Form(default=""),
    param_rs: str = Form(default=""),
    param_rsh: str = Form(default=""),
    param_k: str = Form(default=""),
    param_m: str = Form(default=""),
    ml_assist_enabled: bool = Form(default=False),
    ml_assist_mode: str = Form(default="advisory"),
):
    try:
        file_path = UPLOADS.get(upload_id)
        if file_path is None:
            raise ValueError("Upload and inspect a file before running analysis.")
        result = analyze_file(
            file_path,
            {
                "sheet_name": sheet_name,
                "cell_range": cell_range,
                "voltage_range": voltage_range,
                "current_range": current_range,
                "voltage_start": voltage_start,
                "voltage_end": voltage_end,
                "voltage_step": voltage_step,
                "product_fit_mode": product_fit_mode,
                "mode": mode,
                "fit_strategy": fit_strategy,
                "sweep_strategies": sweep_strategies,
                "reverse_weight": reverse_weight,
                "near_zero_weight": near_zero_weight,
                "forward_weight": forward_weight,
                "high_forward_weight": high_forward_weight,
                "scan_m": scan_m,
                "scan_n": scan_n,
                "use_best_m_after_scan": use_best_m_after_scan,
                "compare_models": compare_models,
                "post_fit_models": post_fit_models,
                "m_values": m_values,
                "n_values": n_values,
                "use_initial_params": use_initial_params,
                "param_j0": param_j0,
                "param_rs": param_rs,
                "param_rsh": param_rsh,
                "param_k": param_k,
                "param_m": param_m,
                "ml_assist_enabled": ml_assist_enabled,
                "ml_assist_mode": ml_assist_mode,
            },
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/grid")
async def grid_endpoint(
    upload_id: str,
    sheet_name: str = "",
    row_offset: int = 0,
    col_offset: int = 0,
    row_count: int = 2000,
    col_count: int = 2000,
):
    try:
        file_path = UPLOADS.get(upload_id)
        if file_path is None:
            raise ValueError("Upload and inspect a file before opening the data grid.")
        grid = read_data_grid(
            file_path,
            sheet_name=sheet_name,
            row_offset=row_offset,
            col_offset=col_offset,
            row_count=row_count,
            col_count=col_count,
        )
        return {"ok": True, "grid": grid}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/txt-import/parse")
async def txt_import_parse_endpoint(file: UploadFile = File(...)):
    try:
        content = await file.read()
        if not content:
            raise ValueError("Upload a non-empty txt file.")
        upload_id, file_path = save_upload(file.filename or "import.txt", content)
        return {"ok": True, "upload_id": upload_id, "txt": parse_txt_upload(file_path)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/txt-import/activate")
async def txt_import_activate_endpoint(payload: dict = Body(...)):
    try:
        upload_id = str(payload.get("upload_id") or "").strip()
        block_id = str(payload.get("block_id") or "").strip()
        if not upload_id or not block_id:
            raise ValueError("TXT upload_id and block_id are required.")
        file_path = UPLOADS.get(upload_id)
        if file_path is None:
            raise ValueError("Unknown TXT upload id. Upload the txt file again.")

        return {"ok": True, **activate_txt_block(file_path, payload, save_upload)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/evaluate")
async def evaluate_endpoint(
    upload_id: str = Form(...),
    sheet_name: str = Form(default=""),
    cell_range: str = Form(default=""),
    voltage_range: str = Form(default=""),
    current_range: str = Form(default=""),
    voltage_start: float = Form(default=-1.0),
    voltage_end: float = Form(default=1.0),
    voltage_step: float = Form(default=0.01),
    param_j0: str = Form(...),
    param_rs: str = Form(...),
    param_rsh: str = Form(...),
    param_k: str = Form(...),
    param_n: str = Form(default=""),
    param_m: str = Form(default=""),
):
    try:
        file_path = UPLOADS.get(upload_id)
        if file_path is None:
            raise ValueError("Upload and inspect a file before evaluating parameters.")

        result = evaluate_file(
            file_path,
            {
                "sheet_name": sheet_name,
                "cell_range": cell_range,
                "voltage_range": voltage_range,
                "current_range": current_range,
                "voltage_start": voltage_start,
                "voltage_end": voltage_end,
                "voltage_step": voltage_step,
                "param_j0": param_j0,
                "param_rs": param_rs,
                "param_rsh": param_rsh,
                "param_k": param_k,
                "param_n": param_n,
                "param_m": param_m,
            },
        )
        return {"ok": True, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/export/components-xlsx")
async def export_components_xlsx_endpoint(payload: dict = Body(...)):
    try:
        content, utf8_filename, ascii_filename = components_xlsx_export(payload)
        disposition = f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{quote(utf8_filename)}'
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": disposition},
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/records")
async def save_record_endpoint(payload: dict = Body(...)):
    try:
        path = save_training_record(payload)
        return {"ok": True, "record_path": str(path)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/records")
async def list_records_endpoint():
    try:
        return {"ok": True, "records": list_training_records()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/records/export")
async def export_records_endpoint():
    try:
        path, count = export_training_records_dataset()
        return {"ok": True, "dataset_path": str(path), "record_count": count}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/records/package")
async def export_records_package_endpoint(include_rejected: bool = False):
    try:
        path, _manifest = export_training_records_package(include_rejected=include_rejected, app_version=app.version)
        return FileResponse(
            path,
            media_type="application/zip",
            filename=path.name,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/recommend")
async def recommend_endpoint(payload: dict = Body(...)):
    try:
        return recommend_from_training_records(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ml/tasks")
async def list_ml_tasks_endpoint(phase: str = ""):
    try:
        return {"ok": True, "tasks": list_ml_tasks(phase)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ml/models")
async def list_ml_models_endpoint(phase: str = ""):
    try:
        return {"ok": True, "models": list_ml_models(phase)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ml/bundles")
async def list_ml_bundles_endpoint():
    try:
        return {"ok": True, "bundles": list_ml_bundles()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ml/similar")
async def ml_similar_endpoint(payload: dict = Body(...), phase: str = "postfit", limit: int = 5, include_rejected: bool = False):
    try:
        return find_similar(payload, phase=phase, limit=limit, include_rejected=include_rejected)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ml/prefit")
async def ml_prefit_endpoint(payload: dict = Body(...)):
    try:
        return ml_prefit_response(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ml/postfit")
async def ml_postfit_endpoint(payload: dict = Body(...)):
    try:
        return ml_postfit_response(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ml/recommend")
async def ml_recommend_endpoint(payload: dict = Body(...)):
    try:
        return ml_recommend_response(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/assistant/chat")
async def assistant_chat_endpoint(payload: dict = Body(...)):
    try:
        return assistant_chat_response(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def main() -> None:
    uvicorn.run("app.fastapi_server:app", host="127.0.0.1", port=8011, reload=False)


if __name__ == "__main__":
    main()
