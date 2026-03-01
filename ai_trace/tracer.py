"""Core Tracer — session-level decision journal for an AI agent."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_trace.step import Step
from ai_trace.writer import TraceWriter


class Tracer:
    """
    Root object for one agent's trace session.

    Parameters
    ----------
    agent : str
        Human-readable agent name (e.g. "trading_bot", "classifier").
    trace_dir : str or Path, optional
        Directory to write trace files. Defaults to ``./traces``.
    auto_save : bool
        If True (default) automatically saves after each step finishes.
    meta : dict
        Arbitrary metadata stored in trace header (model name, version, etc).

    Example
    -------
    >>> tracer = Tracer("my_agent", meta={"model": "claude-haiku-4-5"})
    >>> with tracer.step("classify", input="hello") as step:
    ...     step.log(label="greeting", confidence=0.99)
    >>> tracer.save()
    """

    def __init__(
        self,
        agent: str,
        trace_dir: str | Path = "traces",
        auto_save: bool = True,
        meta: Optional[Dict[str, Any]] = None,
    ):
        self.agent = agent
        self.trace_dir = Path(trace_dir)
        self.auto_save = auto_save
        self.meta: Dict[str, Any] = meta or {}

        self._session_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self._steps: List[Step] = []
        self._writer = TraceWriter(self.trace_dir, self.agent, self._session_id)

    # ── Step factory ─────────────────────────────────────────────────────────

    def step(self, name: str, **context: Any) -> Step:
        """
        Create a new Step. Use as a context manager or call .start()/.finish() manually.

        Parameters
        ----------
        name : str
            Step name — a short label for this decision (e.g. "market_scan").
        **context : Any
            Key/value pairs describing the input state (symbol, model, prompt, etc).
        """
        return Step(tracer=self, name=name, **context)

    # ── Internal record hook (called by Step.finish / Step.fail) ─────────────

    def _record(self, s: Step) -> None:
        self._steps.append(s)
        if self.auto_save:
            self._writer.append_step(s)

    # ── Manual save ──────────────────────────────────────────────────────────

    def save(self) -> Path:
        """Force-save the full trace. Returns path to JSON file."""
        return self._writer.write_full(self._steps, self.meta, self.agent)

    def save_markdown(self) -> Path:
        """Write a human-readable Markdown summary of the trace."""
        return self._writer.write_markdown(self._steps, self.meta, self.agent)

    # ── Summary ──────────────────────────────────────────────────────────────

    def summary(self) -> Dict[str, Any]:
        """Return a dict summarising the session so far."""
        ok = sum(1 for s in self._steps if s.outcome == "ok")
        err = sum(1 for s in self._steps if s.outcome == "error")
        durations = [s.duration_ms for s in self._steps if s.duration_ms is not None]
        return {
            "agent": self.agent,
            "session_id": self._session_id,
            "steps": len(self._steps),
            "ok": ok,
            "errors": err,
            "avg_duration_ms": round(sum(durations) / len(durations), 2) if durations else None,
        }

    def __repr__(self) -> str:
        s = self.summary()
        return (
            f"<Tracer agent={self.agent!r} steps={s['steps']} "
            f"ok={s['ok']} errors={s['errors']}>"
        )
