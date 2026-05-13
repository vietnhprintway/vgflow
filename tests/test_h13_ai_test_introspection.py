"""Regression test for H13 — AI test introspection (v4.12.0).

User feedback (2026-05-13): /vg:test 5e_regression invokes `npx playwright test`
CLI which streams only PASS/FAIL counts via the list reporter. The AI sees no
browser console messages, no network failures, no per-test error stacks. After
a failed run, the AI has no way to diagnose WHY a test failed without manually
opening trace.zip (binary) or replaying via Playwright MCP.

Fix:
- Generated Playwright config emits JSON reporter ALWAYS (both interactive +
  CI), so playwright-results.json is always present.
- New `scripts/playwright-postfail-extract.py` reads the JSON output, walks
  each failed test, extracts error message/stack + attempts to pull console
  messages from trace.zip, writes ${PHASE_DIR}/TEST-FAILURE-REPORT.md.
- regression-security.md 5e_regression invokes the extractor automatically
  after `npx playwright test` so the AI-readable report is always present
  on failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "templates" / "vg" / "playwright.config.generated.template.ts"
EXTRACTOR = REPO_ROOT / "scripts" / "playwright-postfail-extract.py"
REGSEC = REPO_ROOT / "commands" / "vg" / "_shared" / "test" / "regression-security.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_template_emits_json_reporter_in_both_modes():
    body = _read(TEMPLATE)
    # JSON reporter must appear in BOTH the isCi branch and the interactive branch
    isci_branch = body[body.index("isCi"):]
    # The reporter array literal should mention 'json' at least twice (CI + interactive)
    json_occurrences = body.count("'json'") + body.count('"json"')
    assert json_occurrences >= 2, (
        f"H13: playwright config template must emit 'json' reporter in BOTH "
        f"CI and interactive modes so AI can always parse per-test detail. "
        f"Got {json_occurrences} 'json' references."
    )
    # Output file path must be consistent
    assert "playwright-results.json" in body


def test_extractor_script_exists():
    assert EXTRACTOR.is_file(), "H13: scripts/playwright-postfail-extract.py must ship"


def test_extractor_handles_no_failures(tmp_path):
    """Extractor must run cleanly when 0 failures — writes report with summary."""
    results_path = tmp_path / "playwright-results.json"
    results_path.write_text(json.dumps({
        "stats": {"expected": 5, "unexpected": 0, "skipped": 0, "duration": 1234},
        "suites": [{"title": "all", "specs": [
            {"file": "a.spec.ts", "line": 1, "title": "passing test", "tests": [
                {"results": [{"status": "passed", "duration": 100}]}
            ]}
        ]}]
    }), encoding="utf-8")
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    r = subprocess.run(
        [sys.executable, str(EXTRACTOR),
         "--phase-dir", str(phase_dir),
         "--results-json", str(results_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    out = phase_dir / "TEST-FAILURE-REPORT.md"
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "0" in body  # 0 failures
    assert "All tests passed" in body or "0 failures" in body


def test_extractor_walks_failure_tree(tmp_path):
    """Extractor must surface error message + stack + suite from failed entries."""
    results_path = tmp_path / "playwright-results.json"
    results_path.write_text(json.dumps({
        "stats": {"expected": 2, "unexpected": 1, "skipped": 0, "duration": 5000},
        "suites": [{
            "title": "phase-99",
            "specs": [{
                "file": "G-08.spec.ts",
                "line": 42,
                "title": "creates project successfully",
                "tests": [{
                    "results": [{
                        "status": "failed",
                        "duration": 3000,
                        "error": {
                            "message": "expect(locator).toBeVisible()\\nLocator: locator('button[type=submit]')\\nExpected: visible\\nReceived: <element(s) not found>",
                            "stack": "Error: expect(...)\\n  at G-08.spec.ts:42:18\\n  at Promise.then"
                        },
                        "attachments": [
                            {"name": "trace", "path": "/tmp/test-results/G-08/trace.zip"},
                            {"name": "video", "path": "/tmp/test-results/G-08/video.webm"},
                        ],
                    }]
                }]
            }]
        }]
    }), encoding="utf-8")
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    r = subprocess.run(
        [sys.executable, str(EXTRACTOR),
         "--phase-dir", str(phase_dir),
         "--results-json", str(results_path)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    body = (phase_dir / "TEST-FAILURE-REPORT.md").read_text(encoding="utf-8")
    # AI-readable detail must be present
    assert "creates project successfully" in body
    assert "G-08.spec.ts" in body
    assert "toBeVisible" in body or "Locator" in body
    assert "trace" in body and "trace.zip" in body


def test_extractor_handles_missing_results_json(tmp_path):
    """Extractor must be advisory — missing JSON does not fail the step."""
    phase_dir = tmp_path / ".vg" / "phases" / "99-test"
    phase_dir.mkdir(parents=True)
    r = subprocess.run(
        [sys.executable, str(EXTRACTOR),
         "--phase-dir", str(phase_dir),
         "--results-json", str(tmp_path / "missing.json")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, (
        "H13: extractor must be advisory — missing results JSON must not fail "
        "the regression step"
    )


def test_regression_security_invokes_extractor():
    body = _read(REGSEC)
    assert "playwright-postfail-extract.py" in body, (
        "H13: regression-security.md 5e_regression must invoke the H13 "
        "post-fail extractor after the playwright test run completes"
    )
    assert "TEST-FAILURE-REPORT" in body, (
        "H13: regression-security.md must reference TEST-FAILURE-REPORT.md "
        "so users + AI know where to find per-failure detail"
    )
