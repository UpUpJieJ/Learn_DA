import traceback

from fastapi import Request, FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions.base_exceptions import AppException
from app.utils.base_response import StdResp
from app.utils.logger import log, get_request_id


def setup_exception_handlers(app: FastAPI):
    # Clear default exception handlers to avoid conflicts
    app.exception_handlers.clear()

    def _safe_message(value):
        if value is None:
            return ""
        try:
            return str(value)
        except Exception:
            return ""

    def _request_context(request: Request):
        return {
            "request_id": get_request_id(),
            "method": request.method,
            "path": request.url.path,
            "query": dict(request.query_params),
            "client": request.client.host if request.client else None,
            "userAgent": request.headers.get("user-agent"),
        }

    def _normalize_ctx(ctx):
        if not ctx:
            return None
        normalized = {}
        for key, value in ctx.items():
            if isinstance(value, Exception):
                normalized[key] = str(value)
            else:
                normalized[key] = value
        return normalized

    def _format_validation_errors(raw_errors):
        formatted = []
        for error in raw_errors:
            loc = error.get("loc") or []
            loc_list = list(loc)
            source = str(loc_list[0]) if loc_list else ""
            field = ".".join(str(item) for item in loc_list[1:]) if len(loc_list) > 1 else (
                str(loc_list[0]) if loc_list else ""
            )
            formatted.append(
                {
                    "loc": loc_list,
                    "source": source,
                    "field": field,
                    "msg": error.get("msg"),
                    "type": error.get("type"),
                    "ctx": _normalize_ctx(error.get("ctx")),
                }
            )
        return formatted

    def _log_exception(tag, request: Request, exc, message, extra=None):
        context = _request_context(request)
        if extra:
            log.error(
                f"{tag} | context={context} | extra={extra} | exception={exc.__class__.__name__} | message={message}"
            )
        else:
            log.error(
                f"{tag} | context={context} | exception={exc.__class__.__name__} | message={message}"
            )
        log.error(traceback.format_exc())

    async def app_exception_handler(request: Request, exc: AppException):
        message = _safe_message(exc.message) or _safe_message(exc)
        _log_exception("AppException", request, exc, message, extra=exc.extra)
        response = StdResp.error(msg=message, code=exc.status_code)
        http_response = response.to_response()
        http_response.headers["X-Request-ID"] = get_request_id()
        return http_response

    app.add_exception_handler(AppException, app_exception_handler)

    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        detail_message = _safe_message(detail) or _safe_message(exc)
        _log_exception("HTTPException", request, exc, detail_message)
        msg = detail_message or ("用户未认证" if exc.status_code == status.HTTP_401_UNAUTHORIZED else detail_message)
        response = StdResp.error(msg=msg, code=exc.status_code)
        http_response = response.to_response()
        http_response.headers["X-Request-ID"] = get_request_id()
        return http_response

    app.add_exception_handler(HTTPException, http_exception_handler)

    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = _format_validation_errors(exc.errors())
        key_info = ""
        if errors:
            first = errors[0]
            field = first.get("field") or first.get("source")
            msg = first.get("msg") or ""
            if field and msg:
                key_info = f"{field} {msg}"
            elif msg:
                key_info = msg
        message = _safe_message(exc) or "参数校验失败"
        _log_exception("RequestValidationError", request, exc, message, extra={"errors": errors})
        response = StdResp.error(
            msg=key_info or "参数校验失败",
            code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            data={
                "exceptionType": exc.__class__.__name__,
                "message": message,
                "keyInfo": key_info,
                "errors": errors,
            },
        )
        http_response = response.to_response()
        http_response.headers["X-Request-ID"] = get_request_id()
        return http_response

    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    async def database_exception_handler(request: Request, exc: SQLAlchemyError):
        message = _safe_message(exc) or "Database operation failed"
        _log_exception("DatabaseError", request, exc, message)
        response = StdResp.error(
            msg="Database operation failed",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        http_response = response.to_response()
        http_response.headers["X-Request-ID"] = get_request_id()
        return http_response

    app.add_exception_handler(SQLAlchemyError, database_exception_handler)

    async def general_exception_handler(request: Request, exc: Exception):
        message = _safe_message(exc) or "Internal server error"
        _log_exception("UnhandledException", request, exc, message)
        response = StdResp.error(
            msg="Internal server error",
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
        http_response = response.to_response()
        http_response.headers["X-Request-ID"] = get_request_id()
        return http_response

    app.add_exception_handler(Exception, general_exception_handler)
