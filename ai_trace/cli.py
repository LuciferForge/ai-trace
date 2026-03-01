"""
ai-trace CLI — view and tail trace files from the terminal.

Commands:
    ai-trace list  [--dir traces]          List all trace sessions
    ai-trace view  <session>               Pretty-print a trace session
    ai-trace tail  [--dir traces] [-n 20]  Live tail of the latest JSONL trace
    ai-trace stats [--dir traces]          Summary stats across all sessions
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts(epoch: float | None) -> str:
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"


def _color(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


OK   = lambda t: _color(t, "32")   # green
ERR  = lambda t: _color(t, "31")   # red
DIM  = lambda t: _color(t, "2")    # dim
BOLD = lambda t: _color(t, "1")    # bold
CYAN = lambda t: _color(t, "36")


# ── Subcommands ───────────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> None:
    d = Path(args.dir)
    if not d.exists():
        print(f"No trace directory found at {d}")
        return

    files = sorted(d.glob("*.jsonl")) + sorted(d.glob("*.json"))
    if not files:
        print("No trace files found.")
        return

    print(BOLD(f"{'File':<50} {'Size':>8}"))
    print("─" * 60)
    for f in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
        size = f.stat().st_size
        human = f"{size/1024:.1f} KB" if size > 1024 else f"{size} B"
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{f.name:<50} {human:>8}  {DIM(mtime)}")


def cmd_view(args: argparse.Namespace) -> None:
    target = Path(args.session)
    if not target.exists():
        # Try locating in default dir
        d = Path(args.dir)
        candidates = list(d.glob(f"*{args.session}*"))
        if not candidates:
            print(ERR(f"Session not found: {args.session}"))
            sys.exit(1)
        target = sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]

    if target.suffix == ".jsonl":
        _view_jsonl(target)
    else:
        _view_json(target)


def _view_jsonl(path: Path) -> None:
    print(BOLD(f"\n=== {path.name} ===\n"))
    with open(path, encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                step = json.loads(line)
            except json.JSONDecodeError:
                continue
            _print_step(i, step)


def _view_json(path: Path) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    agent = data.get("agent", "unknown")
    sid = data.get("session_id", "")
    print(BOLD(f"\n=== {agent} / {sid} ==="))
    if data.get("meta"):
        for k, v in data["meta"].items():
            print(DIM(f"  {k}: {v}"))
    print()

    for i, step in enumerate(data.get("steps", []), 1):
        _print_step(i, step)


def _print_step(i: int, step: dict) -> None:
    outcome = step.get("outcome", "?")
    icon = OK("✔") if outcome == "ok" else ERR("✘") if outcome == "error" else "·"
    name = BOLD(step.get("name", "?"))
    dur = f"{step.get('duration_ms', '?')} ms"

    print(f"  {icon} {i:>3}. {name} {DIM(dur)}")

    ctx = step.get("context", {})
    if ctx:
        parts = "  ".join(f"{k}={v!r}" for k, v in ctx.items())
        print(f"       {DIM('ctx: ' + parts)}")

    for entry in step.get("logs", []):
        entry = dict(entry)
        t = _ts(entry.pop("_t", None))
        kv = "  ".join(f"{k}={v!r}" for k, v in entry.items())
        print(f"       {CYAN(t)}  {kv}")

    if step.get("error"):
        print(f"       {ERR('err: ' + step['error'][:120])}")

    print()


def cmd_tail(args: argparse.Namespace) -> None:
    d = Path(args.dir)
    if not d.exists():
        print(f"No trace directory found at {d}")
        return

    # Find latest JSONL
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        print("No JSONL trace files found.")
        return

    path = files[-1]
    print(BOLD(f"Tailing {path.name} — Ctrl+C to stop\n"))

    with open(path, encoding="utf-8", errors="replace") as f:
        # Skip to end minus last N lines
        lines_buf: list[str] = []
        for line in f:
            lines_buf.append(line)
            if len(lines_buf) > args.n:
                lines_buf.pop(0)

        # Print last N
        for i, line in enumerate(lines_buf):
            line = line.strip()
            if not line:
                continue
            try:
                step = json.loads(line)
                _print_step(i + 1, step)
            except json.JSONDecodeError:
                pass

        # Live follow
        try:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    step = json.loads(line)
                    _print_step("?", step)
                except json.JSONDecodeError:
                    pass
        except KeyboardInterrupt:
            pass


def cmd_stats(args: argparse.Namespace) -> None:
    d = Path(args.dir)
    if not d.exists():
        print(f"No trace directory found at {d}")
        return

    total_steps = 0
    total_ok = 0
    total_err = 0
    step_names: dict[str, int] = {}
    sessions = 0

    for path in d.glob("*.jsonl"):
        sessions += 1
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    step = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total_steps += 1
                if step.get("outcome") == "ok":
                    total_ok += 1
                elif step.get("outcome") == "error":
                    total_err += 1
                name = step.get("name", "unknown")
                step_names[name] = step_names.get(name, 0) + 1

    print(BOLD("\n=== Trace Stats ===\n"))
    print(f"  Sessions : {sessions}")
    print(f"  Steps    : {total_steps}")
    print(f"  OK       : {OK(str(total_ok))}")
    print(f"  Errors   : {ERR(str(total_err)) if total_err else '0'}")

    if step_names:
        print(f"\n  {BOLD('Top step names:')}")
        for name, count in sorted(step_names.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"    {name:<30} {count}")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ai-trace",
        description="View and tail AI agent decision traces.",
    )
    parser.add_argument("--dir", default="traces", help="Trace directory (default: traces)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all trace sessions")

    p_view = sub.add_parser("view", help="View a trace session")
    p_view.add_argument("session", help="Session ID, filename, or path")

    p_tail = sub.add_parser("tail", help="Live tail the latest trace")
    p_tail.add_argument("-n", type=int, default=20, help="Lines to show before following")

    sub.add_parser("stats", help="Summary stats across all sessions")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "view":
        cmd_view(args)
    elif args.command == "tail":
        cmd_tail(args)
    elif args.command == "stats":
        cmd_stats(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
