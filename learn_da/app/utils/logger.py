import sys
from contextvars import ContextVar
from loguru import logger

# 每个请求的唯一追踪 ID，通过 contextvars 在异步上下文中传递
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return request_id_var.get()


logger.remove()


def _console_filter(record):
    record["extra"].setdefault("request_id", request_id_var.get())
    return not record["extra"].get("access_only", False)


def _app_file_filter(record):
    record["extra"].setdefault("request_id", request_id_var.get())
    return not record["extra"].get("access_only", False)


def _access_file_filter(record):
    record["extra"].setdefault("request_id", request_id_var.get())
    return record["extra"].get("access_only", False)


_fmt_app = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level} | "
    "{extra[request_id]} | {name}:{function}:{line} - {message}"
)
_fmt_access = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level} | "
    "{extra[request_id]} | {message}"
)

logger.add(
    sys.stderr,
    format=_fmt_app,
    level="INFO",
    filter=_console_filter,
    enqueue=True,
)

logger.add(
    "logs/app_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="7 days",
    format=_fmt_app,
    level="DEBUG",
    filter=_app_file_filter,
    encoding="utf-8",
    enqueue=True,
)

logger.add(
    "logs/access_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="7 days",
    format=_fmt_access,
    level="INFO",
    filter=_access_file_filter,
    encoding="utf-8",
    enqueue=True,
)


log = logger