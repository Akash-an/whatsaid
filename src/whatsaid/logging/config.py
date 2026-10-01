import json
import logging
import logging.handlers
import os
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Context variable to hold the current request ID
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

class NDJSONFormatter(logging.Formatter):
    """Formats log records as NDJSON."""
    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "ts": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        req_id = request_id_ctx.get()
        if req_id:
            log_obj["request_id"] = req_id

        # Include any extra kwargs passed to the logger
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord(None, None, "", 0, "", (), None).__dict__ and key not in ("message", "asctime"):
                log_obj[key] = value

        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)

        return json.dumps(log_obj, default=str)

def configure_logging() -> None:
    """Configure the application's root logger and handlers."""
    log_level_str = os.environ.get("WHATSAID_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    log_dir_str = os.environ.get("WHATSAID_LOG_DIR", "logs")
    # Resolve relative to project root if not absolute
    project_root = Path(__file__).resolve().parents[3]
    if os.path.isabs(log_dir_str):
        log_dir = Path(log_dir_str)
    else:
        log_dir = project_root / log_dir_str

    log_dir.mkdir(parents=True, exist_ok=True)

    whatsaid_log_path = log_dir / "whatsaid.log"
    llm_log_path = log_dir / "llm.log"
    ui_log_path = log_dir / "ui.log" # For configuring a specific logger for UI if needed

    # Root logger
    root_logger = logging.getLogger("whatsaid")
    # Set root logger to lowest level so handlers can do their own filtering
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear() # Clear existing

    formatter = NDJSONFormatter()

    # whatsaid.log handler (Rotating, 10MB x 5)
    file_handler = logging.handlers.RotatingFileHandler(
        whatsaid_log_path, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level) # Apply the configured WHATSAID_LOG_LEVEL here
    root_logger.addHandler(file_handler)

    # stderr handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.WARNING) # Only WARN+ to stderr
    root_logger.addHandler(stream_handler)

    # llm.log handler (Rotating, 20MB x 5)
    class LLMFilter(logging.Filter):
        def filter(self, record):
            return getattr(record, "llm", False)
            
    llm_handler = logging.handlers.RotatingFileHandler(
        llm_log_path, maxBytes=20 * 1024 * 1024, backupCount=5
    )
    llm_handler.setFormatter(formatter)
    llm_handler.setLevel(logging.DEBUG) # Always capture LLM logs
    llm_handler.addFilter(LLMFilter())
    root_logger.addHandler(llm_handler)
    
    # UI Logger setup
    ui_logger = logging.getLogger("whatsaid_ui")
    ui_logger.setLevel(logging.WARNING)
    ui_logger.handlers.clear()
    ui_handler = logging.handlers.RotatingFileHandler(
        ui_log_path, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    ui_handler.setFormatter(formatter)
    ui_logger.addHandler(ui_handler)
    ui_logger.propagate = False # Don't send to root logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the given module."""
    if not name.startswith("whatsaid"):
        name = f"whatsaid.{name}"
    return logging.getLogger(name)

