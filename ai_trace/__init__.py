"""
ai-trace — Zero-dependency local AI agent decision tracer.

Records every decision an AI agent makes: what it saw, what it decided,
why it decided it, and what happened next. JSON + Markdown output. No network.

Usage:
    from ai_trace import Tracer

    tracer = Tracer("trading_agent")
    with tracer.step("market_scan", symbol="BTCUSDT") as step:
        signal = analyze(data)
        step.log(signal=signal, action="ENTER", reason="SuperTrend bullish")
"""
from ai_trace.tracer import Tracer
from ai_trace.step import Step
from ai_trace.exceptions import TraceError

__all__ = ["Tracer", "Step", "TraceError"]
__version__ = "0.1.0"
