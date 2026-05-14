"""tests/test_f6_blocking_gate_enforced.py — F6 blocking gate enforced resolve."""
from __future__ import annotations
import re
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "scripts" / "lib" / "blocking-gate-prompt.sh"
CLOSE = REPO / "commands" / "vg" / "_shared" / "review" / "close.md"


def test_emit_no_longer_returns_zero_on_critical():
    body = LIB.read_text(encoding="utf-8")
    # Find blocking_gate_prompt_emit function body
    fn_idx = body.find("blocking_gate_prompt_emit()")
    assert fn_idx > 0
    # Find the closing of the function (next function or EOF)
    next_fn = body.find("\nblocking_gate_prompt_resolve()", fn_idx)
    fn_body = body[fn_idx:next_fn if next_fn > 0 else len(body)]
    # On critical/error severity, must return non-zero so caller branches
    assert ("return 1" in fn_body or "return 2" in fn_body) and "critical" in fn_body, (
        "F6: blocking_gate_prompt_emit must return non-zero for critical/error "
        "severity by default, so callers cannot ignore the prompt and fall "
        "through to run-complete"
    )


def test_callers_handle_emit_return_code():
    body = CLOSE.read_text(encoding="utf-8")
    # Each blocking_gate_prompt_emit call must be guarded by a conditional
    # or follow with exit/abort logic. Spot-check 3 known critical callers.
    critical_callers = ["rcrurd_post_state", "evidence_provenance", "mutation_submit"]
    for caller in critical_callers:
        idx = body.find(f'blocking_gate_prompt_emit "{caller}"')
        assert idx > 0, f"caller '{caller}' not found"
        # Within next 800 chars, must reference EMIT_RC assignment OR explicit
        # exit 1 outside of comment lines (lines starting with #).
        after_lines = body[idx:idx + 800].split("\n")
        non_comment_lines = [l for l in after_lines if l.strip() and not l.strip().startswith("#")]
        non_comment_text = "\n".join(non_comment_lines)
        assert ("EMIT_RC" in non_comment_text or "exit 1" in non_comment_text), (
            f"F6: caller '{caller}' must handle emit return code via EMIT_RC=$? "
            f"capture or explicit exit 1 in non-comment code, not just in comments"
        )
