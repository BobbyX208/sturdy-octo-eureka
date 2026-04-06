import logging
import sys
import json
from datetime import datetime, timezone
from typing import Dict, Any
import traceback


class JSONFormatter(logging.Formatter):
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id
        
        if hasattr(record, "guild_id"):
            log_entry["guild_id"] = record.guild_id
        
        if hasattr(record, "command"):
            log_entry["command"] = record.command
        
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_entry)


class PlainFormatter(logging.Formatter):
    
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        
        location = f"{record.module}:{record.lineno}"
        
        return f"[{timestamp}] [{record.levelname}] [{record.name}] {location} - {record.getMessage()}"


def setup_logger(name: str, level: str = "INFO", log_format: str = "plain") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    if logger.handlers:
        return logger
    
    handler = logging.StreamHandler(sys.stdout)
    
    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(PlainFormatter())
    
    logger.addHandler(handler)
    
    return logger


class LoggerAdapter(logging.LoggerAdapter):
    
    def __init__(self, logger: logging.Logger, extra: Dict[str, Any] = None):
        super().__init__(logger, extra or {})
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        return msg, kwargs
    
    def with_context(self, **kwargs) -> "LoggerAdapter":
        new_extra = self.extra.copy() if self.extra else {}
        new_extra.update(kwargs)
        return LoggerAdapter(self.logger, new_extra)


def get_logger(name: str, **context) -> LoggerAdapter:
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(PlainFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return LoggerAdapter(logger, context)