"""FastAPI wrapper for one-step UAV/USV algorithm adapters."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api_models import RunOnceRequest


app = FastAPI(title="UAV/USV Algorithm Service", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    try:
        errors = exc.errors(include_input=False)
    except TypeError:
        errors = [
            {key: error[key] for key in ("loc", "msg", "type") if key in error}
            for error in exc.errors()
        ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/algorithms/run-once")
def run_once(request: RunOnceRequest) -> JSONResponse:
    adapter_request = request.to_adapter_request()
    if adapter_request.algorithmType == "CAPTURE":
        from adapters.capture_adapter import run_capture_once

        result = run_capture_once(adapter_request)
    else:
        from adapters.escort_adapter import run_escort_once

        result = run_escort_once(adapter_request)

    payload = _serialize(result)
    if result.status == "INVALID_REQUEST":
        return JSONResponse(status_code=400, content=payload)
    if result.status == "UNSUPPORTED_CONFIGURATION":
        return JSONResponse(status_code=422, content=payload)
    return JSONResponse(status_code=200, content=payload)


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    return jsonable_encoder(value)
