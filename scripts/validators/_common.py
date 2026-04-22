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


def find_phase_dir(phase: str):
    """Resolve phase input to on-disk directory.

    Mirrors orchestrator contracts.resolve_phase_dir + bash phase-resolver.sh
    (OHOK v2 follow-up fix 2026-04-22). Handles zero-padding of decimal phases
    (`7.13` → `07.13-*`), bare dirs (legacy GSD `07/`), three-level decimals
    (`07.0.1`), and exact-beats-prefix (`07.12` not matching `07.12.1-*`).

    Previously every validator had inline `PHASES_DIR.glob(f"{phase}-*")` +
    buggy `zfill(2)` fallback that never zero-padded decimals correctly.
    Centralized here so fixes land once.

    Args:
      phase: user-provided phase string (e.g. "7.13", "14", "07.0.1")

    Returns:
      Path to phase dir if found, else None.
    """
    import os
    from pathlib import Path as _Path
    repo = _Path(os.environ.get("VG_REPO_ROOT") or os.getcwd()).resolve()
    phases_dir = repo / ".vg" / "phases"
    if not phase or not phases_dir.exists():
        return None

    # Step 1: exact dash-suffix match (prevents 07.12 matching 07.12.1-*)
    candidates = list(phases_dir.glob(f"{phase}-*"))
    if candidates:
        return candidates[0]

    # Step 1b: exact bare-dir match
    bare = phases_dir / phase
    if bare.is_dir():
        return bare

    # Step 2: zero-pad major part of decimal phase
    if "." in phase:
        major, _, rest = phase.partition(".")
    else:
        major, rest = phase, ""
    if major.isdigit() and len(major) < 2:
        normalized = f"{major.zfill(2)}.{rest}" if rest else major.zfill(2)
        if normalized != phase:
            candidates = list(phases_dir.glob(f"{normalized}-*"))
            if candidates:
                return candidates[0]
            bare_norm = phases_dir / normalized
            if bare_norm.is_dir():
                return bare_norm

    return None
