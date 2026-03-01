"""TraceWriter — handles serialisation of steps to JSON and Markdown."""
from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ai_trace.step import Step


def _ts(epoch: Optional[float]) -> str:
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"


class TraceWriter:
    """Writes trace data to disk. Uses atomic writes to avoid partial files."""

    def __init__(self, trace_dir: Path, agent: str, session_id: str):
        self._dir = trace_dir
        self._agent = agent
        self._session_id = session_id
        self._jsonl_path: Optional[Path] = None

    # ── Streaming JSONL (one line per step) ──────────────────────────────────

    def append_step(self, step: "Step") -> None:
        """Append one step to the running JSONL file. Called after each step."""
        path = self._ensure_jsonl()
        line = json.dumps(step.to_dict(), default=str) + "\n"
        # Atomic-ish: write to temp, then append (JSONL append is safe)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    def _ensure_jsonl(self) -> Path:
        if self._jsonl_path is None:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._jsonl_path = (
                self._dir / f"{self._agent}_{self._session_id}.jsonl"
            )
        return self._jsonl_path

    # ── Full JSON snapshot ────────────────────────────────────────────────────

    def write_full(
        self,
        steps: list["Step"],
        meta: Dict[str, Any],
        agent: str,
    ) -> Path:
        """Write a single JSON file with all steps. Atomic via temp file."""
        self._dir.mkdir(parents=True, exist_ok=True)
        out_path = self._dir / f"{agent}_{self._session_id}.json"

        payload = {
            "agent": agent,
            "session_id": self._session_id,
            "saved_at": datetime.utcnow().isoformat() + "Z",
            "meta": meta,
            "steps": [s.to_dict() for s in steps],
        }

        # Atomic write: write to temp then rename
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
            os.replace(tmp, out_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        return out_path

    # ── Markdown summary ──────────────────────────────────────────────────────

    def write_markdown(
        self,
        steps: list["Step"],
        meta: Dict[str, Any],
        agent: str,
    ) -> Path:
        """Write a human-readable Markdown summary."""
        self._dir.mkdir(parents=True, exist_ok=True)
        out_path = self._dir / f"{agent}_{self._session_id}.md"

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        ok = sum(1 for s in steps if s.outcome == "ok")
        err = sum(1 for s in steps if s.outcome == "error")
        durations = [s.duration_ms for s in steps if s.duration_ms is not None]
        avg_dur = round(sum(durations) / len(durations), 1) if durations else "—"

        lines = [
            f"# Trace: {agent} — {self._session_id}",
            f"*Generated: {now}*",
            "",
            "## Summary",
            f"| Steps | OK | Errors | Avg duration |",
            f"|---|---|---|---|",
            f"| {len(steps)} | {ok} | {err} | {avg_dur} ms |",
        ]

        if meta:
            lines += ["", "## Metadata"]
            for k, v in meta.items():
                lines.append(f"- **{k}**: {v}")

        lines += ["", "## Steps"]

        for i, s in enumerate(steps, 1):
            icon = "✅" if s.outcome == "ok" else "❌" if s.outcome == "error" else "⏳"
            dur = f"{s.duration_ms} ms" if s.duration_ms is not None else "—"
            lines.append(f"\n### {i}. {icon} `{s.name}` ({dur})")

            if s.context:
                lines.append("**Context:**")
                for k, v in s.context.items():
                    lines.append(f"- `{k}`: {v!r}")

            if s.logs:
                lines.append("\n**Logs:**")
                for entry in s.logs:
                    t = _ts(entry.pop("_t", None))
                    kv = ", ".join(f"`{k}={v!r}`" for k, v in entry.items())
                    lines.append(f"- `{t}` — {kv}")
                    entry["_t"] = None  # don't mutate original

            if s.error:
                lines.append(f"\n**Error:** `{s.error[:200]}`")

        content = "\n".join(lines) + "\n"

        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp, out_path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        return out_path
