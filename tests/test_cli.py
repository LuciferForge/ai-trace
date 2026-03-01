"""Tests for ai-trace CLI."""
import json
from pathlib import Path

import pytest

from ai_trace import Tracer
from ai_trace.cli import main


def _run(args: list, capsys):
    import sys
    old = sys.argv
    sys.argv = ["ai-trace"] + args
    try:
        main()
    except SystemExit:
        pass
    finally:
        sys.argv = old
    return capsys.readouterr()


def _make_trace(tmp_path, steps=3):
    tracer = Tracer("cli_agent", trace_dir=tmp_path, auto_save=True)
    for i in range(steps):
        with tracer.step(f"step_{i}", idx=i) as s:
            s.log(result=i * 10)
    return tracer


# ── list ──────────────────────────────────────────────────────────────────────

def test_list_empty(tmp_path, capsys):
    out, _ = _run(["--dir", str(tmp_path), "list"], capsys)
    assert "No trace" in out


def test_list_shows_files(tmp_path, capsys):
    _make_trace(tmp_path)
    out, _ = _run(["--dir", str(tmp_path), "list"], capsys)
    assert "cli_agent" in out


# ── view ──────────────────────────────────────────────────────────────────────

def test_view_jsonl(tmp_path, capsys):
    _make_trace(tmp_path)
    files = list(tmp_path.glob("*.jsonl"))
    out, _ = _run(["--dir", str(tmp_path), "view", str(files[0])], capsys)
    assert "step_0" in out
    assert "step_1" in out
    assert "step_2" in out


def test_view_json(tmp_path, capsys):
    tracer = Tracer("j_agent", trace_dir=tmp_path, auto_save=False)
    with tracer.step("alpha") as s:
        s.log(x=99)
    path = tracer.save()
    out, _ = _run(["--dir", str(tmp_path), "view", str(path)], capsys)
    assert "alpha" in out
    assert "99" in out


# ── stats ─────────────────────────────────────────────────────────────────────

def test_stats(tmp_path, capsys):
    _make_trace(tmp_path, steps=5)
    out, _ = _run(["--dir", str(tmp_path), "stats"], capsys)
    assert "Steps" in out
    assert "5" in out


def test_stats_empty(tmp_path, capsys):
    out, _ = _run(["--dir", str(tmp_path), "stats"], capsys)
    assert "No trace" in out or "Sessions" in out
