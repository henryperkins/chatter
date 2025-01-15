import json
import logging
import os
from flask import request, g


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record),
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
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            log_record["stack_trace"] = self.formatStack(record.stack_info)

        # Add request context if available
        try:
            if request:
                log_record.update({
                    "request_id": request.headers.get("X-Request-ID"),
                    "url": request.url,
                    "method": request.method,
                    "remote_addr": request.remote_addr,
                    "user_agent": request.headers.get("User-Agent"),
                    "referrer": request.referrer,
                    "user_id": getattr(g, "user_id", None),
                    "content_length": request.content_length,
                    "content_type": request.content_type,
                    "correlation_id": getattr(g, "correlation_id", None),
                })
        except Exception:
            pass

        # Redact sensitive information
        if "api_key" in log_record.get("message", ""):
            log_record["message"] = log_record["message"].replace(
                log_record["message"].split("api_key=")[1].split("&")[0],
                "***REDACTED***",
            )

        return json.dumps(log_record)


# Common log formats
DETAILED_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d:%(funcName)s] - %(message)s"
SIMPLE_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"