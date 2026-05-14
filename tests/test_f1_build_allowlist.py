"""tests/test_f1_build_allowlist.py — F1 build preflight allowlist."""
from __future__ import annotations
import re
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
PRE = REPO / "commands" / "vg" / "_shared" / "build" / "preflight.md"


def _read(p): return p.read_text(encoding="utf-8")


def test_allowlist_includes_skip_pre_test():
    body = _read(PRE)
    # Find VALID_FLAGS_PATTERN line
    m = re.search(r"VALID_FLAGS_PATTERN='[^']+'", body)
    assert m, "F1: VALID_FLAGS_PATTERN line missing"
    pattern = m.group(0)
    assert "skip-pre-test" in pattern, (
        "F1: --skip-pre-test documented in build.md:4 but missing from "
        "preflight VALID_FLAGS_PATTERN → preflight rejects as unknown flag"
    )


def test_allowlist_includes_skip_contract_runtime():
    body = _read(PRE)
    m = re.search(r"VALID_FLAGS_PATTERN='[^']+'", body)
    pattern = m.group(0)
    assert "skip-contract-runtime" in pattern, (
        "F1: --skip-contract-runtime documented in build.md:4 but missing from "
        "preflight VALID_FLAGS_PATTERN"
    )


def test_help_text_mentions_new_flags():
    body = _read(PRE)
    # Help block must mention new flags so user sees them when typo error fires
    assert "--skip-pre-test" in body and "--skip-contract-runtime" in body, (
        "F1: help text must list --skip-pre-test + --skip-contract-runtime"
    )
