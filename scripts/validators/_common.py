"""
Shared helpers for validator scripts. Every validator outputs
vg.validator-output schema (see .claude/schemas/validator-output.json).
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Evidence:
    type: str
    message: str
    file: str | None = None
    line: int | None = None
    expected: Any = None
    actual: Any = None
    fix_hint: str | None = None


@dataclass
class Output:
    validator: str
    verdict: str = "PASS"  # PASS | BLOCK | WARN
    evidence: list[Evidence] = field(default_factory=list)
    duration_ms: int = 0
    cache_key: str | None = None

    def add(self, evidence: Evidence, escalate: bool = True) -> None:
        self.evidence.append(evidence)
        if escalate and self.verdict == "PASS":
            self.verdict = "BLOCK"

    def warn(self, evidence: Evidence) -> None:
        self.evidence.append(evidence)
        if self.verdict == "PASS":
            self.verdict = "WARN"

    def to_json(self) -> str:
        return json.dumps({
            "validator": self.validator,
            "verdict": self.verdict,
            "evidence": [
                {k: v for k, v in e.__dict__.items() if v is not None}
                for e in self.evidence
            ],
            "duration_ms": self.duration_ms,
            "cache_key": self.cache_key,
        })


class timer:
    """Context manager that records ms into Output.duration_ms."""
    def __init__(self, output: Output):
        self.output = output

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.output.duration_ms = int((time.time() - self.start) * 1000)


def emit_and_exit(output: Output) -> None:
    """Print JSON + exit 0 (PASS/WARN) or 1 (BLOCK). Orchestrator reads both."""
    print(output.to_json())
    if output.verdict == "BLOCK":
        sys.exit(1)
    sys.exit(0)
