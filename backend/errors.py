"""Consistent, request-correlated API error responses."""

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "requestId": _request_id(request),
    }
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error})


def _status_code(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "AUTH_REQUIRED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, f"HTTP_{status_code}")


async def http_exception_handler(
    request: Request,
    exception: HTTPException,
) -> JSONResponse:
    detail = exception.detail
    custom_code: str | None = None
    if isinstance(detail, dict):
        message = str(detail.get("message", "Request failed."))
        if detail.get("code"):
            custom_code = str(detail["code"])
        details = {
            key: value
            for key, value in detail.items()
            if key not in {"message", "code"}
        }
        details = details or None
    else:
        message = str(detail)
        details = None
    return _error_response(
        request,
        status_code=exception.status_code,
        code=custom_code or _status_code(exception.status_code),
        message=message,
        details=details,
    )


async def validation_exception_handler(
    request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    details = [
        {key: value for key, value in error.items() if key != "ctx"}
        for error in exception.errors()
    ]
    return _error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        details=details,
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
