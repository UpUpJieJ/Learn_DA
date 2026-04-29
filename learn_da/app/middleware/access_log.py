"""
该模块提供 HTTP 请求访问日志记录功能，自动记录：
- 访问者 IP 地址
- 完整 URL 路径
- 请求处理结果（成功/失败状态）
- 响应时间
- 请求唯一 ID（X-Request-ID），用于跨日志关联同一请求
"""

import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.utils import log
from app.utils.logger import request_id_var

access_log = log.bind(access_only=True)


class AccessLogMiddleware(BaseHTTPMiddleware):
    EXCLUDED_PATHS = {
        "/health",
        "/favicon.ico",
        "/docs",
    }

    SUCCESS_STATUS_RANGE = range(200, 300)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # 优先使用客户端传入的 X-Request-ID，否则自动生成
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(request_id)

        start_time = time.perf_counter()
        client_ip = self._get_client_ip(request)
        method = request.method
        url_path = str(request.url)
        query_params = dict(request.query_params)

        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        process_time = time.perf_counter() - start_time
        process_time_ms = round(process_time * 1000, 2)
        status_code = response.status_code
        is_success = status_code in self.SUCCESS_STATUS_RANGE
        result_status = "SUCCESS" if is_success else "FAILED"

        log_data = {
            "request_id": request_id,
            "ip": client_ip,
            "method": method,
            "path": url_path,
            "status_code": status_code,
            "result": result_status,
            "process_time_ms": process_time_ms,
        }

        if query_params:
            log_data["query"] = query_params

        if status_code >= 500:
            access_log.error(f"[ACCESS] {log_data}")
        elif status_code >= 400:
            access_log.warning(f"[ACCESS] {log_data}")
        else:
            access_log.info(f"[ACCESS] {log_data}")

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time_ms}ms"

        return response

    def _get_client_ip(self, request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        if request.client:
            return request.client.host

        return "unknown"


def setup_access_log_middleware(app: FastAPI):
    app.add_middleware(AccessLogMiddleware)
