"""Tier-2 element classifier tests (v2.41 closes v2.40 backlog #2).

Tier-2 detection rules (per design doc + v2.41 code-review concerns):

  redirect_url_param   URL param matches \\b(redirect_uri|return_to|next|continue)\\b
  url_fetch_param      URL param matches \\b(url|link|webhook|callback|fetch_from)\\b
  path_param           URL param matches \\b(file|path|template|name)\\b AND value contains '/'
  auth_endpoint        Endpoint path matches ^/(api/auth/.+|login|logout|oauth/) — PATH ONLY
  payment_or_workflow  business_flow.has_state_machine: true OR resource category in
                       {payment, refund, credit, quota}
  error_response       status >= 500 OR stack-trace marker in response body

Important: ONE entry per (element_class, distinct path/param key) — dedupe to
prevent overflow when 100 mutation buttons all show the same error.

Stack trace markers tested individually per language (Python/Java/Node/PHP/Ruby/
Go/Rust/.NET).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "identify_interesting_clickables.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "tier2-detection"


def _run(*scan_files: Path) -> list[dict]:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--scan-files",
         *(str(p) for p in scan_files), "--json"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"
    return json.loads(r.stdout)["clickables"]


def _filter(clickables: list[dict], element_class: str) -> list[dict]:
    return [c for c in clickables if c["element_class"] == element_class]


# ---------------------------------------------------------------------------
# redirect_url_param
# ---------------------------------------------------------------------------
def test_redirect_url_param_detected_in_query_string() -> None:
    """return_to + next params → 2 redirect_url_param entries (deduped)."""
    out = _run(FIXTURES / "scan-redirect.json")
    redirects = _filter(out, "redirect_url_param")
    param_names = {c["metadata"]["param_name"] for c in redirects}
    assert "return_to" in param_names
    assert "next" in param_names


def test_redirect_url_param_case_insensitive() -> None:
    """Param name matching must be case-insensitive (Return_To still flags)."""
    import scripts.identify_interesting_clickables as mod  # type: ignore
    # Direct API call avoids re-parsing JSON when we want to test pure regex.
    scan = {
        "view": "/x",
        "results": [{"selector": "a", "network": [
            {"method": "GET", "url": "https://x.com/?Return_To=/foo&CONTINUE=/bar"}
        ]}],
    }
    rows = mod._tier2_url_param_classes(scan, "/x")
    classes = [r["element_class"] for r in rows]
    assert "redirect_url_param" in classes
    # Both "Return_To" and "CONTINUE" should match (different keys, both kept).
    assert len([r for r in rows if r["element_class"] == "redirect_url_param"]) == 2


# ---------------------------------------------------------------------------
# url_fetch_param
# ---------------------------------------------------------------------------
def test_url_fetch_param_detected_in_query_string() -> None:
    out = _run(FIXTURES / "scan-url-fetch.json")
    fetches = _filter(out, "url_fetch_param")
    param_names = {c["metadata"]["param_name"] for c in fetches}
    # "url", "webhook", "callback" all appear → 3 entries.
    assert {"url", "webhook", "callback"} <= param_names


# ---------------------------------------------------------------------------
# path_param
# ---------------------------------------------------------------------------
def test_path_param_requires_slash_in_value() -> None:
    """?file=/etc/passwd flags; ?name=Alice does NOT (no slash in value)."""
    out = _run(FIXTURES / "scan-path-param.json")
    paths = _filter(out, "path_param")
    param_names = {c["metadata"]["param_name"] for c in paths}
    # 'file' has '/etc/passwd' → flagged
    assert "file" in param_names
    # 'name' has 'Alice' → NOT flagged (despite matching the regex)
    assert "name" not in param_names


# ---------------------------------------------------------------------------
# auth_endpoint
# ---------------------------------------------------------------------------
def test_auth_endpoint_detected_by_path_pattern() -> None:
    """/login, /logout, /oauth/token → 3 auth_endpoint entries."""
    out = _run(FIXTURES / "scan-auth-endpoint.json")
    auths = _filter(out, "auth_endpoint")
    paths = {c["metadata"]["path"] for c in auths}
    assert "/login" in paths
    assert "/logout" in paths
    assert "/oauth/token" in paths


def test_auth_endpoint_NOT_detected_by_authorization_header() -> None:
    """Regression guard: a /api/users/me call carrying Authorization header
    must NOT classify as auth_endpoint (that pattern over-spawns lens-auth-jwt
    + lens-csrf for every API call in a modern app — code-review concern).
    """
    out = _run(FIXTURES / "scan-auth-endpoint.json")
    auths = _filter(out, "auth_endpoint")
    paths = {c["metadata"]["path"] for c in auths}
    assert "/api/users/me" not in paths, (
        "Authorization-header heuristic regressed — auth_endpoint must be "
        "PATH-only per v2.41 code-review concern."
    )


# ---------------------------------------------------------------------------
# payment_or_workflow
# ---------------------------------------------------------------------------
def test_payment_or_workflow_from_crud_surfaces_category() -> None:
    """resource with category=refund OR business_flow.has_state_machine=true
    → payment_or_workflow entry.
    """
    out = _run(FIXTURES / "scan-payment-workflow.json")
    workflow = _filter(out, "payment_or_workflow")
    # Two triggers in this fixture:
    #   1. business_flow.has_state_machine=true → 1 entry keyed by view
    #   2. crud_resources[refunds].category=refund → 1 entry keyed by resource
    # crud_resources[audit_logs].category=audit must NOT trigger.
    assert len(workflow) == 2, f"expected 2, got {len(workflow)}: {workflow}"
    reasons = {c["metadata"]["reason"] for c in workflow}
    assert "has_state_machine" in reasons
    assert any("category=refund" in r for r in reasons)


def test_payment_or_workflow_skips_non_money_categories() -> None:
    """category=audit must NOT trigger payment_or_workflow."""
    out = _run(FIXTURES / "scan-payment-workflow.json")
    resources_in_metadata = [
        c["resource"] for c in _filter(out, "payment_or_workflow")
    ]
    assert "audit_logs" not in resources_in_metadata


# ---------------------------------------------------------------------------
# error_response
# ---------------------------------------------------------------------------
def test_error_response_status_500() -> None:
    """status>=500 → error_response entry."""
    out = _run(FIXTURES / "scan-error-500.json")
    errors = _filter(out, "error_response")
    assert len(errors) == 1
    assert errors[0]["metadata"]["status"] == 500
    assert errors[0]["metadata"]["reason"] == "status_500"


def test_error_response_stack_trace_node_js() -> None:
    """Node.js stack trace marker (at <anonymous>) → error_response even on 200."""
    out = _run(FIXTURES / "scan-stack-trace-node.json")
    errors = _filter(out, "error_response")
    assert len(errors) == 1
    assert errors[0]["metadata"]["reason"] == "stack_trace"


# ---------------------------------------------------------------------------
# Stack trace markers — tested individually per language
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("body,language", [
    ("Traceback (most recent call last):\n  File \"x.py\"", "Python"),
    ("Exception in thread \"main\" java.lang.NullPointerException\n\tat com.foo.Bar.baz", "Java"),
    ("TypeError: x is undefined\n    at <anonymous>:1:1", "Node.js"),
    ("PHP Fatal error: Uncaught Exception\nStack trace:\n#0 /var/www/foo.php(42)", "PHP"),
    ("NoMethodError\n in <main>'\n\tfrom /app/bar.rb:12", "Ruby"),
    ("panic: runtime error: invalid memory\ngoroutine 1 [running]", "Go"),
    ("thread 'main' panicked at 'something failed'", "Rust"),
    ("System.Exception: Object reference not set\n   at Foo.Bar()", ".NET"),
])
def test_stack_trace_marker_per_language(body: str, language: str) -> None:
    """Each of the 8 supported languages must trigger _has_stack_trace."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import identify_interesting_clickables as mod  # type: ignore
    assert mod._has_stack_trace(body), f"{language} marker not detected in: {body!r}"


def test_stack_trace_no_false_positive() -> None:
    """A clean 200 response with no stack-trace markers must not trigger."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import identify_interesting_clickables as mod  # type: ignore
    assert not mod._has_stack_trace('{"ok": true, "items": []}')
    assert not mod._has_stack_trace("")


# ---------------------------------------------------------------------------
# Dedupe contract — overflow guard
# ---------------------------------------------------------------------------
def test_tier2_dedupe_collapses_repeated_endpoints() -> None:
    """100 mutation buttons all returning 500 from /api/items/1 → ONE error_response.

    Without dedupe, this blows the worker cap (guard #1 violation).
    """
    out = _run(FIXTURES / "scan-dedupe-overflow.json")
    errors = _filter(out, "error_response")
    assert len(errors) == 1, (
        f"expected 1 deduped error_response, got {len(errors)}: {errors}"
    )
    assert errors[0]["metadata"]["path"] == "/api/items/1"


# ---------------------------------------------------------------------------
# Integration: Tier-2 + Tier-1 emit alongside each other
# ---------------------------------------------------------------------------
def test_tier1_and_tier2_emit_in_same_run() -> None:
    """Tier-2 detection does not displace Tier-1 — both fire on a mixed scan."""
    # The dedupe-overflow fixture has 5 mutation buttons (Tier-1) + 1 deduped
    # error_response (Tier-2). Both classes must be present.
    out = _run(FIXTURES / "scan-dedupe-overflow.json")
    classes = {c["element_class"] for c in out}
    assert "mutation_button" in classes
    assert "error_response" in classes
