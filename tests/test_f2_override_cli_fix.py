"""tests/test_f2_override_cli_fix.py — F2 override CLI fix."""
from __future__ import annotations
import re
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]


def test_no_override_use_callers_remain():
    """vg-orchestrator CLI registers 'override' subcommand. 'override-use' is
    not registered — any caller silently fails."""
    matches = []
    for p in REPO.rglob("*.md"):
        if "node_modules" in str(p) or ".git" in str(p):
            continue
        try:
            body = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for line in body.splitlines():
            if "override-use" in line and "vg-orchestrator" in line:
                # Skip historical changelog / audit references
                if ("CHANGELOG" in str(p) or "audit" in str(p).lower()
                        or "/plans/" in str(p) or "\\plans\\" in str(p)
                        or str(p).startswith(str(REPO / "docs"))):
                    continue
                matches.append(f"{p.relative_to(REPO)}: {line.strip()[:120]}")
    assert not matches, (
        "F2: vg-orchestrator subcommand is 'override' not 'override-use'. "
        "Callers still using override-use will silently fail:\n  " + "\n  ".join(matches)
    )


def test_pre_test_gate_parses_override_reason_from_arg():
    body = (REPO / "commands/vg/_shared/build/pre-test-gate.md").read_text(encoding="utf-8")
    # Find the bash block where --skip-pre-test is checked (not the HARD-GATE comment).
    # Look for the if [[ "$ARGUMENTS" =~ --skip-pre-test ]] pattern in bash code
    import re
    m = re.search(r'if \[\[.*\$ARGUMENTS.*--skip-pre-test', body)
    assert m, "F2: cannot find bash --skip-pre-test branch in pre-test-gate.md"
    idx = m.start()
    block = body[idx:idx + 1500]
    # Must extract --override-reason=<text> from $ARGUMENTS, not rely on
    # undefined $OVERRIDE_REASON env var
    assert ("OVERRIDE_REASON=" in block and ("sed" in block or "grep" in block or "awk" in block or "${ARGUMENTS" in block)), (
        "F2: pre-test-gate.md --skip-pre-test branch must parse --override-reason=<text> "
        "from ARGUMENTS before calling vg-orchestrator override"
    )
