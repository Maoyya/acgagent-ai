"""请求日志中间件。记录每个请求的方法、路径、响应状态码和耗时。"""
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("acgagent-ai")


class LoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件：按 INFO 级别记录每个请求的方法、路径、状态码与耗时。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        """放行请求，并在响应返回后记录耗时与状态码。"""
        start = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
