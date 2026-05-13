#!/usr/bin/env python3
"""playwright-postfail-extract.py — H13 (v4.12.0)

After /vg:test 5e_regression runs `npx playwright test`, the human can watch
the list-reporter stream BUT the AI sees only PASS/FAIL counts. Browser
console messages, network failures, and per-test error stacks are buried in
test-results/<test>/trace.zip (binary) and playwright-results.json.

This script:
1. Reads playwright-results.json (JSON reporter output).
2. For each failed test, extracts:
   - test title, file:line
   - error.message + error.stack (first 30 lines)
   - attempt timing
   - paths to trace.zip / video.webm / screenshot
3. (Optional) Extracts console messages from trace.zip if present (Playwright
   trace = zip with trace.network + trace.stacks + trace.json frames — we read
   trace.network for console + request events).
4. Writes `${PHASE_DIR}/TEST-FAILURE-REPORT.md` — AI-readable summary.

Usage:
  python3 playwright-postfail-extract.py \\
    --phase-dir <path> \\
    --results-json <path/to/playwright-results.json> \\
    [--test-results-dir <path>] \\
    [--max-failures 20]
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any


def _short(text: str, max_lines: int = 30) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines truncated)"


def _walk_failures(results: dict) -> list[dict]:
    """Walk Playwright JSON reporter output, yield each failed test entry.

    Schema: suites[] -> specs[] -> tests[] -> results[].
    A test is "failed" when any result has status=failed or timedOut.
    """
    failures: list[dict] = []

    def walk_suites(suites: list[dict], breadcrumb: list[str]) -> None:
        for suite in suites or []:
            title = suite.get("title", "")
            new_crumb = breadcrumb + ([title] if title else [])
            for spec in suite.get("specs", []) or []:
                spec_title = spec.get("title", "")
                spec_file = spec.get("file", "")
                spec_line = spec.get("line", 0)
                for test in spec.get("tests", []) or []:
                    for result in test.get("results", []) or []:
                        status = result.get("status")
                        if status in ("failed", "timedOut"):
                            failures.append({
                                "suite": " > ".join(new_crumb + [spec_title]),
                                "file": spec_file,
                                "line": spec_line,
                                "title": spec_title,
                                "status": status,
                                "duration_ms": result.get("duration"),
                                "error_message": (result.get("error") or {}).get("message", ""),
                                "error_stack": (result.get("error") or {}).get("stack", ""),
                                "attachments": result.get("attachments") or [],
                                "stdout": result.get("stdout") or [],
                                "stderr": result.get("stderr") or [],
                            })
            walk_suites(suite.get("suites") or [], new_crumb)

    walk_suites(results.get("suites") or [], [])
    return failures


def _trace_console_messages(trace_zip: Path, max_lines: int = 50) -> list[str]:
    """Extract console messages from a Playwright trace.zip."""
    if not trace_zip.is_file():
        return []
    messages: list[str] = []
    try:
        with zipfile.ZipFile(trace_zip, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".trace") and not name.endswith(".network"):
                    continue
                with zf.open(name) as f:
                    for raw in f:
                        try:
                            line = raw.decode("utf-8", errors="replace").strip()
                        except Exception:
                            continue
                        if not line:
                            continue
                        try:
                            evt = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        evt_type = evt.get("type") or evt.get("event")
                        if evt_type in ("console", "log", "pageerror"):
                            text = evt.get("text") or evt.get("message") or json.dumps(evt)
                            messages.append(f"[{evt_type}] {text}")
                if len(messages) >= max_lines:
                    break
    except (zipfile.BadZipFile, OSError):
        return [f"(trace.zip unreadable: {trace_zip})"]
    return messages[:max_lines]


def _format_failure(idx: int, fail: dict, test_results_dir: Path | None) -> str:
    out: list[str] = []
    out.append(f"## Failure #{idx + 1}: {fail['title']}")
    out.append("")
    out.append(f"- **Status:** `{fail['status']}`")
    out.append(f"- **File:** `{fail['file']}:{fail['line']}`")
    out.append(f"- **Suite:** {fail['suite']}")
    if fail.get("duration_ms") is not None:
        out.append(f"- **Duration:** {fail['duration_ms']} ms")
    out.append("")
    if fail.get("error_message"):
        out.append("### Error message")
        out.append("```")
        out.append(_short(fail["error_message"], max_lines=10))
        out.append("```")
        out.append("")
    if fail.get("error_stack"):
        out.append("### Stack (first 30 lines)")
        out.append("```")
        out.append(_short(fail["error_stack"], max_lines=30))
        out.append("```")
        out.append("")
    if fail.get("attachments"):
        out.append("### Attachments")
        for att in fail["attachments"]:
            name = att.get("name", "?")
            path = att.get("path", "")
            out.append(f"- `{name}` → `{path}`")
        out.append("")
        # Try to extract console from any trace.zip attachment
        for att in fail["attachments"]:
            path = att.get("path") or ""
            if path.endswith("trace.zip") and Path(path).is_file():
                msgs = _trace_console_messages(Path(path))
                if msgs:
                    out.append("### Console messages (from trace.zip)")
                    out.append("```")
                    out.extend(msgs[:30])
                    out.append("```")
                    out.append("")
                break
    if fail.get("stdout"):
        joined = "\n".join(str(s.get("text") or s) for s in fail["stdout"][:5])
        if joined.strip():
            out.append("### Test stdout (first 5)")
            out.append("```")
            out.append(_short(joined))
            out.append("```")
            out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase-dir", required=True, type=Path)
    ap.add_argument("--results-json", required=True, type=Path)
    ap.add_argument("--test-results-dir", type=Path, default=None,
                    help="Playwright test-results/ dir (for trace.zip lookup)")
    ap.add_argument("--max-failures", type=int, default=20)
    ap.add_argument("--out", type=Path, default=None,
                    help="Output path (default: PHASE_DIR/TEST-FAILURE-REPORT.md)")
    args = ap.parse_args()

    if not args.results_json.is_file():
        print(f"⚠ H13 extractor: results JSON missing at {args.results_json}")
        return 0  # advisory — non-fatal

    try:
        results = json.loads(args.results_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"⚠ H13 extractor: results JSON malformed — {e}")
        return 0

    failures = _walk_failures(results)
    out_path = args.out or (args.phase_dir / "TEST-FAILURE-REPORT.md")
    args.phase_dir.mkdir(parents=True, exist_ok=True)

    stats = results.get("stats") or {}
    lines = [
        f"# Test Failure Report — phase {args.phase_dir.name}",
        "",
        f"- **Total tests:** {stats.get('expected', 0) + stats.get('unexpected', 0) + stats.get('skipped', 0)}",
        f"- **Failed/timedOut:** {len(failures)}",
        f"- **Duration:** {stats.get('duration', 0)} ms",
        "",
    ]
    if not failures:
        lines.append("All tests passed. No failures to report.")
    else:
        if len(failures) > args.max_failures:
            lines.append(f"> Showing first {args.max_failures} of {len(failures)} failures.\n")
        for i, fail in enumerate(failures[:args.max_failures]):
            lines.append(_format_failure(i, fail, args.test_results_dir))

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ H13 extractor: wrote {out_path} ({len(failures)} failures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
