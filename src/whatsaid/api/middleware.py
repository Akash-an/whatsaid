import time
import uuid
from typing import Callable
from fastapi import Request, Response
from ..logging import request_id_ctx, get_logger

logger = get_logger(__name__)

async def request_logging_middleware(request: Request, call_next: Callable) -> Response:
    """Middleware to inject request ID and log requests/responses."""
    req_id = str(uuid.uuid4())[:8]
    token = request_id_ctx.set(req_id)
    
    start_time = time.time()
    logger.info("Request received", extra={"method": request.method, "path": request.url.path})
    
    try:
        response = await call_next(request)
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info("Response sent", extra={"status_code": response.status_code, "duration_ms": duration_ms})
        return response
    except Exception as exc:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Request failed", extra={"exc": str(exc), "duration_ms": duration_ms})
        raise
    finally:
        request_id_ctx.reset(token)
