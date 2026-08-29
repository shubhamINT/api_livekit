import contextvars
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from multiprocessing import current_process

from src.core.config import settings

# Two-layer room context.
#
# The module-level global is what the agent subprocess uses: it handles exactly one call, and
# a ContextVar alone was unreliable there because the livekit TTS plugin spawns its own asyncio
# tasks that don't inherit the caller's context, so the ContextVar read back None inside them.
#
# The ContextVar exists for the SIP dispatcher process, which interleaves many calls on one
# event loop. Writing the global from there attributed log lines to whichever call happened to
# set it last, which made load-test logs actively misleading. Callers in that process pass
# global_fallback=False so they only touch the ContextVar, which asyncio scopes per task.
#
# A record resolves the ContextVar first and falls back to the global, so both work unchanged.
_current_room: str | None = None
_room_context: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "call_room", default=None
)

# LiveKit names agent worker subprocesses with this value.
# See: livekit-agents ipc/job_proc_executor.py _create_process()
_LIVEKIT_JOB_PROC_NAME = "job_proc"


def set_room_context(room_name: str, *, global_fallback: bool = True) -> None:
    """Tag subsequent log records with room_name.

    global_fallback=False confines the tag to the current asyncio task, for processes that
    handle more than one call at a time.
    """
    global _current_room
    _room_context.set(room_name)
    if global_fallback:
        _current_room = room_name


def clear_room_context(*, global_fallback: bool = True) -> None:
    global _current_room
    _room_context.set(None)
    if global_fallback:
        _current_room = None


_orig_record_factory = None


def _make_log_record(*args, **kwargs) -> logging.LogRecord:
    # Stamp call_room at record creation so it survives livekit's IPC pickle
    # before any handler (including LogQueueHandler) serializes the record.
    # A root-logger filter doesn't work here: Python's callHandlers walks up
    # to parent handlers without running parent-logger filters.
    record = _orig_record_factory(*args, **kwargs)
    record.call_room = _room_context.get() or _current_room
    return record


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


_STANDARD_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging in production.

    Anything passed via `extra={...}` lands as plain attributes on the record, not under
    a literal `.extra` — so callers like the Sarvam STT plugin (extra={"session_id":,
    "chunks_sent":, "connection_state":, ...}) need every non-standard attribute promoted
    into the JSON, not just the ones under a key that never actually exists. That structured
    context is what makes a call traceable: filter by call_room + session_id and every
    DEBUG line for one STT connection lines up, chunk counts included.
    """
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "file": record.filename,
            "line": record.lineno,
            "call_room": getattr(record, "call_room", None),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS and key not in log_entry:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


_logging_configured = False


def setup_logging() -> None:
    """Configure the root logger based on settings."""
    global _logging_configured, _orig_record_factory
    if _logging_configured:
        return

    root_logger = logging.getLogger()
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    root_logger.setLevel(level)

    _orig_record_factory = logging.getLogRecordFactory()
    logging.setLogRecordFactory(_make_log_record)
    _logging_configured = True

    # Before the job_proc early-return below — the agent worker IS the job_proc, and that
    # is the only process where the Sarvam STT plugin runs.
    _enable_sarvam_stt_debug()

    # LiveKit agent subprocesses are named "job_proc". Every log record they
    # emit is forwarded to the parent via LogQueueHandler and re-emitted there.
    # Adding our own StreamHandler/FileHandler here would cause every line to
    # appear twice. Skip handlers in subprocesses; parent process owns output.
    if current_process().name == _LIVEKIT_JOB_PROC_NAME:
        return

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_JSON_FORMAT:
        handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
    else:
        handler.setFormatter(ColoredFormatter())
    root_logger.addHandler(handler)

    if settings.LOG_FILE:
        file_handler = RotatingFileHandler(
            settings.LOG_FILE,
            maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT,
        )
        file_handler.setFormatter(JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
        root_logger.addHandler(file_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("pymongo").setLevel(logging.WARNING)


def _enable_sarvam_stt_debug() -> None:
    """Keep the Sarvam STT plugin at DEBUG in every environment.

    The plugin already logs the three lines that diagnose a dead socket, and only at
    DEBUG: "Starting audio processing" (the send loop ran), "Sent N audio chunks" every
    ~5s (audio is still going *into* the socket), and "Received empty transcript"
    (the server answered, just with nothing). Without them, a Sarvam session that stops
    answering is indistinguishable from a caller who went quiet — see the stall watchdog
    in src/core/agents/dynamic_assistant.py.

    Costs roughly one line per 5s per call. Deliberate: one silent-death incident costs
    far more than the log volume.
    """
    logging.getLogger("livekit.plugins.sarvam").setLevel(logging.DEBUG)


def get_logger(name: str):
    """Get a logger instance with the given name"""
    return logging.getLogger(name)

logger = get_logger("app")
