# Security Policy

## What this library protects against

`ai-decision-tracer` was built for production autonomous AI systems where
understanding agent behavior is critical for security and compliance.

### 1. Crash-safe trace persistence
All steps are auto-saved to JSONL as they complete. If your agent crashes
mid-execution, you still have a full trace up to the failure point.
Uses atomic writes (temp file + rename) to prevent partial/corrupt output.

### 2. No data exfiltration
All trace data stays local. No network calls. No telemetry. No cloud sync.
Your agent decisions, inputs, and outputs never leave your machine.

### 3. Safe error capture
Stack traces from exceptions are captured in the trace file for postmortems,
but the library never logs raw prompts or full model responses unless you
explicitly pass them to `step.log()`. You control what gets recorded.

### 4. No runtime dependencies
Zero third-party dependencies — nothing to supply-chain attack.
Pure Python stdlib only.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

Please report security vulnerabilities via GitHub Issues (mark as "security").
Do NOT include sensitive data (API keys, prompts) in public issues.

Expected response time: 48 hours.
