"""Theory of Python logging — stub handler + capture + fidelity.

The adorned library is :mod:`logging`.  The stub intercepts every
``logging.Logger`` call during a scenario and records it as a
structured ``LogEmit`` in the trace, so contracts can assert on
log content (level counts, message patterns, extra-field
constraints) with the same ``extends_by_one`` machinery they use
for domain events.

Unlike the SQL theory, there is no transaction model and no
string-to-action translation — every ``logger.info(...)`` is
already a typed Python call, so the stub handler is the sole
interception point.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class LogTheoryError(Exception):
    """All logging-theory discipline errors."""


class LogCaptureError(LogTheoryError):
    """A capture was used after the context exited."""


# ---------------------------------------------------------------------------
# Action model (what the adorned library does)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LogEmit:
    """One emission — typed, comparable, contract-checkable."""
    level: int           # logging.DEBUG / INFO / WARNING / ERROR / CRITICAL
    logger: str          # dotted name, e.g. "invitations.email"
    msg: str             # format string, e.g. "InvitationSent"
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Event model (what appears in the trace)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Emit:
    """A single log event in the trace."""
    record: LogEmit


Event = Emit   # union — only one kind of event so far


# ---------------------------------------------------------------------------
# State model
# ---------------------------------------------------------------------------


@dataclass
class LogStore:
    """Accumulates all captured emissions."""
    emits: list[LogEmit] = field(default_factory=list)

    def copy(self) -> LogStore:
        return LogStore(emits=list(self.emits))

    @property
    def by_level(self) -> dict[int, list[LogEmit]]:
        out: dict[int, list[LogEmit]] = {}
        for e in self.emits:
            out.setdefault(e.level, []).append(e)
        return out

    @property
    def by_logger(self) -> dict[str, list[LogEmit]]:
        out: dict[str, list[LogEmit]] = {}
        for e in self.emits:
            out.setdefault(e.logger, []).append(e)
        return out


# ---------------------------------------------------------------------------
# StubHandler — intercepts logging, records trace + store
# ---------------------------------------------------------------------------


class LogStubHandler(logging.Handler):
    """A logging handler that captures every record for verification.

    Installed via :func:`make_log_capture`; stays active for the
    duration of a scenario.  The captured ``_store`` is compared
    against the real logging module's output in fidelity tests.
    """

    def __init__(self, store: LogStore | None = None) -> None:
        super().__init__()
        self._store = store or LogStore()
        self._trace: list[Event] = []
        self._active = True

    def emit(self, record: logging.LogRecord) -> None:
        if not self._active:
            return
        extra = {
            k: v for k, v in record.__dict__.items()
            if k not in {
                "name", "msg", "args", "levelname", "levelno",
                "pathname", "filename", "module", "exc_info",
                "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread",
                "threadName", "processName", "process",
                "message", "asctime", "taskName",
            }
        }
        le = LogEmit(
            level=record.levelno,
            logger=record.name,
            msg=record.msg or "",
            extra=extra,
        )
        self._store.emits.append(le)
        self._trace.append(Emit(record=le))

    @property
    def store(self) -> LogStore:
        return self._store

    @property
    def trace(self) -> tuple[Event, ...]:
        return tuple(self._trace)

    @property
    def active(self) -> bool:
        return self._active

    def flush(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Capture context manager — installs the stub, yields the store
# ---------------------------------------------------------------------------


@contextmanager
def make_log_capture(
    logger_name: str = "",
    level: int = logging.DEBUG,
) -> Iterator[LogStubHandler]:
    """Install a stub handler, run the body, return the captured store.

    Sets the root (or named) logger level to *level* so that every
    emission within the captured block is visible — the default
    root level is ``WARNING``, which would silently drop ``INFO``.

    Usage::

        with make_log_capture("inventory") as h:
            service.reserve(engine, ...)
        assert len(h.store.emits) == 2
    """
    root = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    old_level = root.level
    handler = LogStubHandler()
    handler.setLevel(level)
    root.setLevel(level)
    root.addHandler(handler)
    try:
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
        handler._active = False


# ---------------------------------------------------------------------------
# Adornment registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CallRule:
    name: str
    emits: str
    reads: tuple[str, ...]
    writes: tuple[str, ...]
    note: str = ""


LOGTHEORY: tuple[CallRule, ...] = (
    CallRule(
        name="logging.Logger.log",
        emits="Emit",
        reads=(),
        writes=("log_store.emits",),
        note="every log call appends one emission",
    ),
)
