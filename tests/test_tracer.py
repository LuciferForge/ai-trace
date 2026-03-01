"""Tests for ai-trace core functionality."""
import json
import time
from pathlib import Path

import pytest

from ai_trace import Tracer, Step


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_tracer(tmp_path):
    return Tracer("test_agent", trace_dir=tmp_path, auto_save=True)


# ── Tracer basics ─────────────────────────────────────────────────────────────

def test_tracer_creates_step(tmp_tracer):
    step = tmp_tracer.step("decide", symbol="BTC")
    assert isinstance(step, Step)
    assert step.name == "decide"
    assert step.context["symbol"] == "BTC"


def test_step_context_manager_ok(tmp_tracer):
    with tmp_tracer.step("scan", model="haiku") as step:
        step.log(signal=0.9, action="BUY")

    assert len(tmp_tracer._steps) == 1
    s = tmp_tracer._steps[0]
    assert s.outcome == "ok"
    assert s.duration_ms is not None
    assert s.duration_ms >= 0
    assert len(s.logs) == 1
    assert s.logs[0]["signal"] == 0.9


def test_step_context_manager_exception(tmp_tracer):
    with pytest.raises(ValueError):
        with tmp_tracer.step("bad") as step:
            raise ValueError("boom")

    assert tmp_tracer._steps[0].outcome == "error"
    assert "boom" in tmp_tracer._steps[0].error


def test_step_manual_lifecycle(tmp_tracer):
    step = tmp_tracer.step("manual")
    step.start()
    step.log(x=1)
    step.finish(outcome="ok")

    assert len(tmp_tracer._steps) == 1
    assert tmp_tracer._steps[0].outcome == "ok"


def test_step_fail(tmp_tracer):
    step = tmp_tracer.step("failing")
    step.start()
    step.fail(reason="network timeout")

    s = tmp_tracer._steps[0]
    assert s.outcome == "error"
    assert s.error == "network timeout"


def test_multiple_steps(tmp_tracer):
    for name in ["scan", "filter", "decide", "execute"]:
        with tmp_tracer.step(name):
            pass

    assert len(tmp_tracer._steps) == 4
    assert [s.name for s in tmp_tracer._steps] == ["scan", "filter", "decide", "execute"]


# ── Summary ───────────────────────────────────────────────────────────────────

def test_summary(tmp_tracer):
    with tmp_tracer.step("a"):
        pass
    with pytest.raises(RuntimeError):
        with tmp_tracer.step("b"):
            raise RuntimeError("x")

    s = tmp_tracer.summary()
    assert s["steps"] == 2
    assert s["ok"] == 1
    assert s["errors"] == 1
    assert s["agent"] == "test_agent"


def test_repr(tmp_tracer):
    r = repr(tmp_tracer)
    assert "test_agent" in r
    assert "steps=0" in r


# ── File output ───────────────────────────────────────────────────────────────

def test_auto_save_creates_jsonl(tmp_path):
    tracer = Tracer("agent", trace_dir=tmp_path, auto_save=True)
    with tracer.step("step1"):
        pass

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["name"] == "step1"
    assert data["outcome"] == "ok"


def test_save_json(tmp_path):
    tracer = Tracer("agent2", trace_dir=tmp_path, auto_save=False, meta={"version": "1.0"})
    with tracer.step("s1", x=1) as s:
        s.log(result="ok")

    path = tracer.save()
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["agent"] == "agent2"
    assert data["meta"]["version"] == "1.0"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["context"]["x"] == 1


def test_save_markdown(tmp_path):
    tracer = Tracer("md_agent", trace_dir=tmp_path, auto_save=False)
    with tracer.step("think") as s:
        s.log(thought="market is bullish")

    path = tracer.save_markdown()
    assert path.suffix == ".md"
    content = path.read_text()
    assert "md_agent" in content
    assert "think" in content
    assert "bullish" in content


def test_no_auto_save(tmp_path):
    tracer = Tracer("agent", trace_dir=tmp_path, auto_save=False)
    with tracer.step("x"):
        pass

    files = list(tmp_path.glob("*.jsonl")) + list(tmp_path.glob("*.json"))
    assert files == []


def test_atomic_write_no_partial(tmp_path):
    """JSON output should never be partially written."""
    tracer = Tracer("atom", trace_dir=tmp_path, auto_save=False)
    for _ in range(50):
        with tracer.step("work"):
            pass

    path = tracer.save()
    # Should parse without error
    data = json.loads(path.read_text())
    assert len(data["steps"]) == 50


# ── Step serialisation ────────────────────────────────────────────────────────

def test_step_to_dict(tmp_tracer):
    with tmp_tracer.step("s", k="v") as s:
        s.log(a=1, b="two")

    d = tmp_tracer._steps[0].to_dict()
    assert d["name"] == "s"
    assert d["context"] == {"k": "v"}
    assert d["outcome"] == "ok"
    assert len(d["logs"]) == 1
    assert d["logs"][0]["a"] == 1
    assert "_t" in d["logs"][0]
    assert d["duration_ms"] >= 0


def test_duration_ms_none_before_finish():
    # No tracer needed — just test Step directly
    # We need a mock tracer
    class FakeTracer:
        def _record(self, s):
            pass

    s = Step(FakeTracer(), "x")
    assert s.duration_ms is None
    s.start()
    assert s.duration_ms is None  # not finished yet


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_context(tmp_tracer):
    with tmp_tracer.step("bare"):
        pass
    assert tmp_tracer._steps[0].context == {}


def test_empty_logs(tmp_tracer):
    with tmp_tracer.step("silent"):
        pass
    assert tmp_tracer._steps[0].logs == []


def test_meta_in_summary(tmp_path):
    tracer = Tracer("x", trace_dir=tmp_path, meta={"model": "claude-haiku"})
    with tracer.step("s"):
        pass
    path = tracer.save()
    data = json.loads(path.read_text())
    assert data["meta"]["model"] == "claude-haiku"
