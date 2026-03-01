"""Step context manager — represents one decision unit in a trace."""
from __future__ import annotations

import time
import traceback
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from ai_trace.tracer import Tracer


class Step:
    """
    A single decision step inside a Tracer.

    Use as a context manager:
        with tracer.step("analyze", symbol="BTC") as step:
            step.log(signal=0.87, action="BUY")

    Or manually:
        step = tracer.step("analyze")
        step.start()
        step.log(action="BUY")
        step.finish()
    """

    def __init__(
        self,
        tracer: "Tracer",
        name: str,
        **context: Any,
    ):
        self._tracer = tracer
        self.name = name
        self.context: Dict[str, Any] = dict(context)
        self.logs: list[Dict[str, Any]] = []
        self.outcome: Optional[str] = None
        self.error: Optional[str] = None
        self._started_at: Optional[float] = None
        self._finished_at: Optional[float] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> "Step":
        self._started_at = time.time()
        return self

    def finish(self, outcome: str = "ok") -> "Step":
        self._finished_at = time.time()
        self.outcome = outcome
        self._tracer._record(self)
        return self

    def fail(self, reason: str) -> "Step":
        self._finished_at = time.time()
        self.outcome = "error"
        self.error = reason
        self._tracer._record(self)
        return self

    # ── Logging ──────────────────────────────────────────────────────────────

    def log(self, **kwargs: Any) -> "Step":
        """Append a structured log entry to this step."""
        entry = {"_t": time.time()}
        entry.update(kwargs)
        self.logs.append(entry)
        return self

    # ── Context manager ──────────────────────────────────────────────────────

    def __enter__(self) -> "Step":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            self.error = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            self.fail(reason=str(exc_val))
            return False  # re-raise
        self.finish()
        return False

    # ── Serialisation ────────────────────────────────────────────────────────

    @property
    def duration_ms(self) -> Optional[float]:
        if self._started_at and self._finished_at:
            return round((self._finished_at - self._started_at) * 1000, 2)
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "context": self.context,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "duration_ms": self.duration_ms,
            "outcome": self.outcome,
            "error": self.error,
            "logs": self.logs,
        }
