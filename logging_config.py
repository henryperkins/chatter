"""Logging configuration module."""

import logging
import os
import json
import platform
import sys
from logging.handlers import RotatingFileHandler
from concurrent_log_handler import ConcurrentRotatingFileHandler
from datetime import datetime
from typing import Dict, Any

# Constants
LOG_DIRS = {
    "base": "logs",
    "api": "logs/api",
    "http": "logs/http",
    "user": "logs/user",
    "error": "logs/error",
}

LOG_FORMATS = {
    "standard": "%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s",
    "user": "%(asctime)s - %(levelname)s - %(name)s - [%(filename)s:%(lineno)d] - %(message)s",
    "json": {
        "timestamp": "%(asctime)s",
        "level": "%(levelname)s",
        "logger": "%(name)s",
        "file": "%(filename)s",
        "line": "%(lineno)d",
        "message": "%(message)s",
        "request_id": "%(request_id)s",
        "user_id": "%(user_id)s",
    },
}

HANDLER_CONFIG = {
    "app": {
        "dir": LOG_DIRS["base"],
        "level": logging.INFO,
        "maxBytes": 20 * 1024 * 1024,
        "backupCount": 10,
    },
    "token_usage": {
        "dir": LOG_DIRS["base"],
        "level": logging.DEBUG,
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
    },
    "chat_api": {
        "dir": LOG_DIRS["api"],
        "level": logging.INFO,
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
    },
    "httpx": {
        "dir": LOG_DIRS["http"],
        "level": logging.WARNING,
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
    },
    "httpcore": {
        "dir": LOG_DIRS["http"],
        "level": logging.WARNING,
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
    },
    "user_actions": {
        "dir": LOG_DIRS["user"],
        "level": logging.INFO,
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
    },
    "errors": {
        "dir": LOG_DIRS["error"],
        "level": logging.ERROR,
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
    },
    "openai": {
        "dir": LOG_DIRS["api"],
        "level": logging.WARNING,
        "maxBytes": 10 * 1024 * 1024,
        "backupCount": 5,
    },
}


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        for key in ["user_id", "request_id"]:
            if not hasattr(record, key):
                setattr(record, key, "none")

        log_record = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "logger": record.name,
            "level": record.levelname,
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
            "message": record.getMessage(),
            "thread": record.threadName,
            "process": record.processName,
            "environment": os.getenv("FLASK_ENV", "development"),
            "application": "chat_app",
            "pid": os.getpid(),
            "host": platform.node(),
            "request_id": getattr(record, "request_id", "none"),
            "user_id": getattr(record, "user_id", "none"),
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_record["stack_trace"] = self.formatStack(record.stack_info)

        return json.dumps(log_record)


class HttpClientFilter(logging.Filter):
    """Filter for HTTP client logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.WARNING


def create_rotating_handler(
    log_dir: str,
    name: str,
    max_bytes: int,
    backup_count: int,
    use_concurrent: bool = True,
) -> logging.Handler:
    """Create a rotating file handler."""
    os.makedirs(log_dir, exist_ok=True)
    filename = os.path.join(
        log_dir, f"{name}_{datetime.now().strftime('%Y-%m-%d')}.log"
    )

    handler_class = (
        ConcurrentRotatingFileHandler if use_concurrent else RotatingFileHandler
    )
    return handler_class(
        filename=filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )


def configure_logger(
    name: str,
    config: Dict[str, Any],
    formatter: logging.Formatter,
    add_filter: bool = False,
) -> logging.Logger:
    """Configure a logger with specified settings."""
    logger = logging.getLogger(name)
    logger.setLevel(config["level"])
    logger.propagate = False

    handler = create_rotating_handler(
        config["dir"], name, config["maxBytes"], config["backupCount"]
    )
    handler.setFormatter(formatter)

    if add_filter:
        handler.addFilter(HttpClientFilter())

    logger.addHandler(handler)
    return logger


def configure_logging() -> None:
    """Configure all logging for the application."""
    if hasattr(configure_logging, "_configured"):
        return

    for directory in LOG_DIRS.values():
        os.makedirs(directory, exist_ok=True)

    is_production = os.getenv("FLASK_ENV") == "production"
    formatter = (
        JsonFormatter() if is_production else logging.Formatter(LOG_FORMATS["standard"])
    )
    user_formatter = logging.Formatter(LOG_FORMATS["user"])

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    for name, config in HANDLER_CONFIG.items():
        log_formatter = user_formatter if name == "user_actions" else formatter
        add_filter = name in ["httpx", "httpcore"]
        configure_logger(name, config, log_formatter, add_filter)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    if not is_production and not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    configure_logging._configured = True


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger by name."""
    if not hasattr(configure_logging, "_configured"):
        configure_logging()
    return logging.getLogger(name)


configure_logging()
