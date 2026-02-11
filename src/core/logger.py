import logging
from logging.handlers import RotatingFileHandler
import sys
import json
from datetime import datetime
from src.core.config import settings

class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored log output in development"""
    grey = "\x1b[38;20m"
    blue = "\x1b[34;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    
    # Format: Time - LoggerName - Level - Message (File:Line)
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: blue + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging in production"""
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "file": record.filename,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        # Add extra fields from record if any
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
            
        return json.dumps(log_entry)

def setup_logging():
    """Configure the root logger based on settings"""
    logger = logging.getLogger()
    
    # Set log level from config
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    if logger.handlers:
        logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    
    # Set formatter based on environment
    if settings.LOG_JSON_FORMAT:
        formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    else:
        formatter = ColoredFormatter()
        
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Create file handler if configured
    if settings.LOG_FILE:
        file_handler = RotatingFileHandler(
            settings.LOG_FILE,
            maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT
        )
        # Always use JSON formatter for file logs for easier parsing
        file_handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(file_handler)
    
    # Set levels for third-party libraries to reduce noise
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    
    return logger

def get_logger(name: str):
    """Get a logger instance with the given name"""
    return logging.getLogger(name)

# Initialize logging configuration when module is imported
# This ensures logging is set up correctly the first time it's used
# However, usually setup_logging() is called in main/server startup
# We expose a default logger for convenience
logger = get_logger("app")
