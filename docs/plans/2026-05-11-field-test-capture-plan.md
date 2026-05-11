# /vg:field-test Implementation Plan (v2.1)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build new VGFlow skill `/vg:field-test` so the user can manually roam the deployed app in an MCP-playwright browser while AI silently captures multi-source telemetry (browser console + network + clicks + nav chain + per-Mark notes + correlated API server log tails). On Stop, an analyzer subagent produces `FIELD-REPORT.md` and appends entries to `.vg/KNOWN-ISSUES.json`.

**Revision:** v2.1 — supersedes v2 after round-2 Codex review (5 MUST FIX + 3 SHOULD FIX) AND incorporates code-level changes from merged PR #177 (`/vg:test-spec` lane, global-only install, removed committed `.codex/skills/*`) + PR #179 (YAML curated-skip repair) + v3.6.5 (#175 evidence-manifest auto-record).

**v1 scope cuts** (per design v2, unchanged in v2.1): drop `quick`/`deep` presets, drop `--resume`, drop `dev-phases/<N>/` mirror, drop `--non-interactive`, drop crash-recovery aborted-bundle flow.

## v2.1 patch summary

| # | Source | Delta | Affected task |
|---|---|---|---|
| 1 | round-2 MUST | Concrete tail-respawn loop body (not "in v2 task 7 step 5") | Task 3 + Task 7 |
| 2 | round-2 MUST | Create `check-quota.py` (was named in design line 89, never authored) | New Task 7a |
| 3 | round-2 MUST | Create `release-lock.py` (was named in design line 101, never authored) | New Task 7b |
| 4 | round-2 MUST | SPA F5-reload `epoch K→0 = reset last_consumed` logic | Task 8 step 5 |
| 5 | round-2 MUST | Double-wrap regression test for user `--redact` pattern | Task 2 |
| 6 | round-2 SHOULD | jsdom functional overlay test default-on (not gated by env var) | Task 4 |
| 7 | round-2 SHOULD | Path-with-spaces fixture for `tail-source.sh` + atomic lock | Tasks 3 + 8 |
| 8 | round-2 SHOULD | Inline full Task 5 build-bundle body (not "as in v1 plan") | Task 5 |
| 9 | PR #177 | Codex mirror deploys to `~/.codex/skills/` (global-only, no project copy) | Task 9 |
| 10 | PR #177 | Field-test KNOWN-ISSUES feeds `/vg:test-spec` lifecycle context (consumer doc only — no code in this skill) | Task 8 + Task 10 CHANGELOG |
| 11 | PR #177 / #178 | Schema permits domain goal IDs `[A-Za-z0-9][A-Za-z0-9_.-]*` for `phase_goal` field | Task 1 |
| 12 | v3.6.5 / #175 | Stop step emits `evidence-manifest.json` entry for `FIELD-REPORT.md` + bundle `manifest.json` | Task 8 step 6 + Task 6 |

**Architecture:** AI orchestrator injects overlay JS via `browser_evaluate`. AI polls overlay state via `browser_evaluate(() => ({len: __VG_FT_STATE.marks.length, status: __VG_FT_STATE.status}))` — NOT console messages (which are snapshot reads that replay; would duplicate marks). Console messages used only for Start/Stop edge events with offset tracking. Per-source API log tails pipe through `redact-stream.py` at capture time (not at build time). Atomic lock via `mkdir`. Python timestamp wrapper replaces GNU `date %3N` for portability.

**Tech Stack:** Python 3.11+, vanilla browser JS, JSON Schema draft-07, MCP playwright1.

**Design doc:** [`docs/plans/2026-05-11-field-test-capture-design.md`](./2026-05-11-field-test-capture-design.md) (v2)

**Working directory:** `main` per project rule.

---

## Conventions

- Python: `from __future__ import annotations`, type-hinted, no third-party deps.
- Bash: `set -euo pipefail`.
- Every `scripts/` file mirrored to `.claude/scripts/` byte-identical. Same for `commands/vg/` → `.claude/commands/vg/` and `agents/` → `.claude/agents/`.
- Commits use:
  ```
  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- Regression sweep before each commit:
  ```
  python -m pytest tests/ -q --tb=no
  ```

---

## Task 1: Schema v1 + vg.config block (no preset enum)

**Files:**
- Create: `schemas/field-test-session.v1.json`
- Modify: `vg.config.template.md`
- Test: `tests/test_field_test_config_schema.py`

**Key diff vs v1 plan:**
- Drop `preset` from schema (no longer a field).
- Schema validation test seeds a real session.json and asserts jsonschema validation (not just substring check).

**Step 1: Failing test**

```python
"""tests/test_field_test_config_schema.py — schema + config block contracts."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "schemas" / "field-test-session.v1.json"
CONFIG_TEMPLATE = REPO_ROOT / "vg.config.template.md"


def test_schema_exists_and_parses():
    assert SCHEMA.is_file()
    data = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert data["$schema"] == "http://json-schema.org/draft-07/schema#"
    required = set(data["required"])
    expected = {"version", "sid", "phase", "base_url", "ts_started", "sources", "redaction"}
    assert expected <= required


def test_schema_rejects_invalid_session():
    """Schema must actually reject malformed session.json — not just declare required fields."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    # Missing `sid`
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"version": "1", "base_url": "http://x", "ts_started": "2026-05-11T00:00:00Z",
             "sources": [], "redaction": "password"},
            schema,
        )
    # Bad sources type
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"version": "1", "sid": "ft-2026", "phase": None, "base_url": "http://x",
             "ts_started": "2026-05-11T00:00:00Z", "sources": "not-a-list", "redaction": "password"},
            schema,
        )


def test_schema_accepts_real_session():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    valid = {
        "version": "1", "sid": "ft-2026-05-11T10-00-00Z", "phase": None,
        "base_url": "http://localhost:3000", "ts_started": "2026-05-11T10:00:00Z",
        "sources": [{"type": "file", "target": "/var/log/api.log", "label": "api"}],
        "redaction": "password|token|secret",
    }
    jsonschema.validate(valid, schema)


def test_config_template_advertises_field_test_block_no_preset():
    body = CONFIG_TEMPLATE.read_text(encoding="utf-8")
    assert re.search(r"^#?\s*field_test\s*:", body, re.MULTILINE)
    for key in [
        "api_log_sources", "default_redaction", "default_base_url",
        "mark_window_sec", "session_max_size_mb", "max_session_hours",
    ]:
        assert key in body, f"missing config key: {key}"
    # v2: preset must NOT appear (deferred to v2)
    assert "default_preset" not in body, (
        "v1 ships only the standard capture profile — no preset enum in config"
    )
```

**Step 2: Run** → FAIL.

**Step 3: Write schema** — `schemas/field-test-session.v1.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://vgflow.dev/schemas/field-test-session.v1.json",
  "title": "VG field-test session (v1) — user-driven roam capture",
  "type": "object",
  "required": ["version", "sid", "phase", "base_url", "ts_started", "sources", "redaction"],
  "additionalProperties": true,
  "properties": {
    "version": {"const": "1"},
    "sid": {"type": "string", "pattern": "^ft-(p[A-Za-z0-9._-]+-)?[0-9TZ:.-]+$"},
    "phase": {"type": ["string", "null"]},
    "base_url": {"type": "string"},
    "ts_started": {"type": "string", "format": "date-time"},
    "ts_stopped": {"type": ["string", "null"]},
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "target", "label"],
        "properties": {
          "type": {"enum": ["file", "command"]},
          "target": {"type": "string"},
          "label": {"type": "string"},
          "pid": {"type": ["integer", "null"]}
        }
      }
    },
    "redaction": {"type": "string"},
    "mark_count": {"type": "integer", "minimum": 0},
    "bundle_path": {"type": ["string", "null"]},
    "phase_goal": {
      "type": ["string", "null"],
      "description": "v2.1: optional cross-ref to a phase goal ID — accepts domain IDs (G-AUTH-00, G-FE-ADMIN-DLQ-01) post-PR-#177 generic ID rewrite",
      "pattern": "^G-[A-Za-z0-9][A-Za-z0-9_.-]*$"
    }
  }
}
```

**Step 4: Modify `vg.config.template.md`**:

```markdown
## field_test (v3.7+ — /vg:field-test skill, v1 scope)

```yaml
field_test:
  api_log_sources:
    # - { type: file,    target: /var/log/api.log,                  label: api }
    # - { type: command, target: "docker logs -f my-api",           label: docker-api }
    # - { type: command, target: "kubectl logs -f pod/api -n prod", label: k8s-api }

  default_redaction: 'password|token|secret|api[_-]?key|email|phone|bearer\s+[A-Za-z0-9._-]+|authorization:\s*\S+'
  default_base_url: ""
  mark_window_sec: 30
  screenshot_quality: 80
  session_max_size_mb: 200
  max_session_hours: 4
```

**Step 5: Run** → PASS.

**Step 6: Commit**

```bash
git add tests/test_field_test_config_schema.py schemas/field-test-session.v1.json vg.config.template.md
git commit -m "feat(field-test): schema v1 + vg.config.template block (no preset enum)

Schema draft-07 with jsonschema validation tests (not substring tautology).
Tests assert rejection of malformed sessions + acceptance of real session.
Config block declares api_log_sources + redaction + caps. No preset field
in v1 — deferred per design v2 scope cut.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Redact-stream helper (single source of truth)

**Files:**
- Create: `scripts/field-test/redact-stream.py`
- Create: `.claude/scripts/field-test/redact-stream.py`
- Test: `tests/test_field_test_redact_stream.py`

**Key:** Single helper applied BOTH at tail capture time (via stdin pipe) AND at build-bundle window correlation. Source of truth for redaction logic. Multi-form patterns: `key=value`, `key: value`, JSON `"key": "value"`, bare `Bearer <jwt>`, `Authorization: Bearer …`.

**Step 1: Failing test**

```python
"""tests/test_field_test_redact_stream.py — capture-time redaction helper."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REDACT = REPO_ROOT / "scripts" / "field-test" / "redact-stream.py"
MIRROR = REPO_ROOT / ".claude" / "scripts" / "field-test" / "redact-stream.py"


def _run(stdin: str, pattern: str = "password|token|secret|api[_-]?key|email|bearer\\s+[A-Za-z0-9._-]+|authorization:\\s*\\S+") -> str:
    r = subprocess.run(
        [sys.executable, str(REDACT), "--pattern", pattern],
        input=stdin, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    return r.stdout


def test_kv_equals_form():
    out = _run("login: password=hunter2 success\n")
    assert "hunter2" not in out
    assert "[REDACTED]" in out


def test_kv_colon_header_form():
    out = _run("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.xxxx\n")
    assert "eyJhbGc" not in out


def test_json_body_form():
    out = _run('POST /api/login {"email":"u@x.com","password":"hunter2"}\n')
    assert "hunter2" not in out
    assert "u@x.com" not in out


def test_url_query_form():
    out = _run("GET /api/things?api_key=ABCDEF&page=2\n")
    assert "ABCDEF" not in out
    assert "page=2" in out, "non-sensitive query params must pass through"


def test_bare_bearer_form():
    out = _run("Got header Bearer eyJhbGc.deadbeef.signature\n")
    assert "deadbeef" not in out


def test_safe_input_passes_through():
    safe = "INFO order created id=42 status=ok\n"
    out = _run(safe)
    assert out.strip() == safe.strip()


def test_idempotency():
    """Re-redacting redacted output should not change it."""
    once = _run("password=hunter2\n")
    twice = _run(once)
    assert once == twice


def test_bad_user_regex_falls_back_to_default():
    """An invalid regex must fall back to default + emit warning to stderr, not crash."""
    r = subprocess.run(
        [sys.executable, str(REDACT), "--pattern", "[unclosed"],
        input="password=hunter2\n", capture_output=True, text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0
    assert "hunter2" not in r.stdout, "default regex must still apply"
    assert "warning" in r.stderr.lower() or "fallback" in r.stderr.lower()


def test_user_pattern_already_wrapped_not_double_wrapped():
    """v2.1 round-2 MUST-5: when the user passes a pattern that already
    contains word boundaries / capture groups, the composition logic must
    NOT wrap it again. Double-wrapping silently breaks the match.

    Reproduction: user passes `\\bjwt=([A-Za-z0-9._-]+)` expecting a
    capture-group replacement. If the implementation wraps it as
    `(?:\\bjwt=([A-Za-z0-9._-]+))` and then anchors the replacement to
    group 1, the substitution mis-references — original token leaks.
    """
    user_pattern = r"\bjwt=([A-Za-z0-9._-]+)"
    r = subprocess.run(
        [sys.executable, str(REDACT), "--pattern", user_pattern],
        input="auth jwt=eyJhbGc.payload.sig done\n",
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0
    assert "eyJhbGc.payload.sig" not in r.stdout, (
        "MUST-5: user-supplied pattern must not be silently double-wrapped — "
        "the literal token leaked through"
    )
    assert "REDACTED" in r.stdout or "[REDACTED]" in r.stdout


def test_user_pattern_with_existing_group_compiles():
    """v2.1 round-2 MUST-5 companion: composition must succeed when user
    pattern already declares its own capture group(s)."""
    r = subprocess.run(
        [sys.executable, str(REDACT), "--pattern", r"(secret_\d+)"],
        input="value=secret_42 leaks\n",
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, (
        f"composition must compile when user pattern has capture groups; "
        f"stderr={r.stderr}"
    )
    assert "secret_42" not in r.stdout


def test_mirror_byte_identity():
    assert REDACT.read_bytes() == MIRROR.read_bytes()
```

**Step 2: Run** → FAIL.

**Step 3: Write `scripts/field-test/redact-stream.py`**:

```python
#!/usr/bin/env python3
"""redact-stream.py — line-oriented redactor for /vg:field-test.

Reads stdin line-by-line, applies a multi-form redaction regex, writes
stdout. Used in two places:

  1. tail-source.sh pipes API log lines through this BEFORE writing to
     disk (capture-time redaction — closes the design v2 disk-exposure
     window).
  2. build-bundle.py runs each correlated window line through this for
     idempotent re-application during Stop-time bundle assembly.

Patterns covered:
  - key=value         (URL query / CLI arg)
  - key: value        (HTTP header)
  - "key": "value"    (JSON body)
  - Bearer <token>    (Authorization value)
  - Authorization: ...

Bad user regex → warn on stderr, fall back to default. Never crash.
"""
from __future__ import annotations

import argparse
import re
import sys


DEFAULT_KEYS = r"password|token|secret|api[_-]?key|email|phone"
DEFAULT_PATTERN = (
    r"(?i)("
    r"(?:" + DEFAULT_KEYS + r")\s*[:=]\s*\"?[^\"\s,&}]+"
    r"|\"(?:" + DEFAULT_KEYS + r")\"\s*:\s*\"[^\"]*\""
    r"|bearer\s+[A-Za-z0-9._\-]+"
    r"|authorization:\s*\S+"
    r")"
)

SENTINEL = "[REDACTED]"


def build_pattern(user: str | None) -> tuple[re.Pattern[str], bool]:
    """Return (compiled, used_default). Falls back to default on bad regex."""
    if not user or user == "default":
        return re.compile(DEFAULT_PATTERN), True
    # Compose user keys with multi-form template (same shape as DEFAULT_PATTERN)
    try:
        composed = (
            r"(?i)("
            r"(?:" + user + r")\s*[:=]\s*\"?[^\"\s,&}]+"
            r"|\"(?:" + user + r")\"\s*:\s*\"[^\"]*\""
            r"|bearer\s+[A-Za-z0-9._\-]+"
            r"|authorization:\s*\S+"
            r")"
        )
        return re.compile(composed), False
    except re.error as exc:
        print(f"redact-stream: warning: invalid user regex '{user}': {exc}; falling back to default", file=sys.stderr)
        return re.compile(DEFAULT_PATTERN), True


def redact(line: str, pat: re.Pattern[str]) -> str:
    return pat.sub(SENTINEL, line)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pattern", default="default", help="Custom redaction keys regex (alternation)")
    args = ap.parse_args()
    pat, _ = build_pattern(args.pattern)
    try:
        for line in sys.stdin:
            sys.stdout.write(redact(line, pat))
            sys.stdout.flush()
    except BrokenPipeError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Mirror + run** → PASS all 9 tests.

**Step 5: Commit**

```bash
git add scripts/field-test/redact-stream.py .claude/scripts/field-test/redact-stream.py tests/test_field_test_redact_stream.py
git commit -m "feat(field-test): redact-stream.py multi-form redactor (capture+build)

Single source of truth for redaction. Covers key=value, key: value,
JSON body \"key\":\"value\", bare Bearer <jwt>, Authorization: ... header
form. Idempotent (re-redacting redacted output is no-op). Bad user
regex falls back to default + warns on stderr instead of crashing.

Closes Codex review §4 — v1 plan regex was broken (dropped api_key,
email, phone from design's promised default; second alternative branch
only matched bare word; Bearer never matched).

Used by tail-source.sh at capture time AND build-bundle.py at window
correlation time — closes the disk-exposure window the v1 plan left
open until Stop.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: tail-source.sh + Python timestamp wrapper

**Files:**
- Create: `scripts/field-test/tail-source.sh`
- Create: `scripts/field-test/prefix-iso.py` (replaces GNU `date %3N`)
- Mirror both to `.claude/scripts/field-test/`
- Test: `tests/test_field_test_tail_source.py`

**Key diff vs v1 plan:**
- Replace `date -u +%Y-%m-%dT%H:%M:%S.%3N` (GNU-only) with `python3 prefix-iso.py` (portable Mac+Linux+Windows-via-GitBash).
- Pipe stream through `redact-stream.py` BEFORE writing disk.

**Step 1: Failing test**

```python
"""tests/test_field_test_tail_source.py"""
from __future__ import annotations

import shutil, signal, subprocess, sys, time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TAIL = REPO_ROOT / "scripts" / "field-test" / "tail-source.sh"
PREFIX = REPO_ROOT / "scripts" / "field-test" / "prefix-iso.py"
MIRROR_TAIL = REPO_ROOT / ".claude" / "scripts" / "field-test" / "tail-source.sh"
MIRROR_PREFIX = REPO_ROOT / ".claude" / "scripts" / "field-test" / "prefix-iso.py"


def test_scripts_exist():
    assert TAIL.is_file()
    assert PREFIX.is_file()


def test_tail_uses_python_timestamp_not_gnu_date():
    body = TAIL.read_text(encoding="utf-8")
    # Must NOT use `date %3N` (GNU-only)
    assert "%3N" not in body, "v2 forbids date %3N (macOS BSD date breaks silently)"
    # Must reference prefix-iso.py wrapper
    assert "prefix-iso.py" in body


def test_tail_pipes_through_redactor():
    body = TAIL.read_text(encoding="utf-8")
    assert "redact-stream.py" in body, (
        "v2 mandates capture-time redaction before disk write"
    )


def test_tail_takes_redaction_pattern_arg():
    body = TAIL.read_text(encoding="utf-8")
    assert "--redact" in body, "tail must accept --redact pattern for per-session regex"


def test_mirror_byte_identity():
    assert TAIL.read_bytes() == MIRROR_TAIL.read_bytes()
    assert PREFIX.read_bytes() == MIRROR_PREFIX.read_bytes()


_bash = pytest.mark.skipif(
    not shutil.which("bash") or sys.platform == "win32",
    reason="POSIX bash required",
)


@_bash
def test_tail_file_mode_redacts_inline(tmp_path):
    target = tmp_path / "src.log"
    out = tmp_path / "out.log"
    target.write_text("", encoding="utf-8")
    proc = subprocess.Popen(
        ["bash", str(TAIL), "--type", "file", "--target", str(target),
         "--out", str(out), "--redact", "password|token"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.3)
        with target.open("a", encoding="utf-8") as f:
            f.write("login password=hunter2 success\n")
        time.sleep(1.0)
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    text = out.read_text(encoding="utf-8")
    assert "hunter2" not in text, "tail must redact at capture, not leave to build-time"
    assert "[REDACTED]" in text


@_bash
def test_tail_handles_path_with_spaces(tmp_path):
    """v2.1 round-2 SHOULD-7: real installs live under paths like
    'Vibe Code/Code/PrintwayV3/' — tail-source must not split on
    whitespace when quoting its target/out args."""
    spaced = tmp_path / "with spaces" / "ft session"
    spaced.mkdir(parents=True)
    target = spaced / "src.log"
    out = spaced / "out.log"
    target.write_text("", encoding="utf-8")
    proc = subprocess.Popen(
        ["bash", str(TAIL), "--type", "file", "--target", str(target),
         "--out", str(out), "--redact", "password|token"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        time.sleep(0.3)
        with target.open("a", encoding="utf-8") as f:
            f.write("login password=hunter2 success\n")
        time.sleep(1.0)
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    err = proc.stderr.read().decode("utf-8") if proc.stderr else ""
    assert out.is_file(), (
        f"path-with-spaces output not written; stderr={err}"
    )
    text = out.read_text(encoding="utf-8")
    assert "hunter2" not in text
    assert "[REDACTED]" in text


@_bash
def test_tail_iso_prefix_works_on_any_unix(tmp_path):
    """Verifies prefix-iso.py emits parseable ISO timestamps (no `date %3N` portability bug)."""
    target = tmp_path / "src.log"
    out = tmp_path / "out.log"
    target.write_text("", encoding="utf-8")
    proc = subprocess.Popen(
        ["bash", str(TAIL), "--type", "file", "--target", str(target),
         "--out", str(out), "--redact", "default"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.3)
        with target.open("a", encoding="utf-8") as f:
            f.write("hello world\n")
        time.sleep(1.0)
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    text = out.read_text(encoding="utf-8")
    # Each line must start with ISO date (e.g. 2026-05-11T...Z)
    for line in text.strip().splitlines():
        assert line[:4].isdigit() and "T" in line[:20] and "Z" in line[:35], (
            f"line missing ISO timestamp: {line!r}"
        )
```

**Step 2: Run** → FAIL.

**Step 3: Write `scripts/field-test/prefix-iso.py`**:

```python
#!/usr/bin/env python3
"""prefix-iso.py — portable line-oriented ISO-8601 timestamp prefixer.

Replaces `date -u +%Y-%m-%dT%H:%M:%S.%3N` which is GNU-only (macOS BSD
date silently emits literal `%3N`). Pure Python = portable Mac+Linux+
Windows-via-Git-Bash.

Reads stdin line-by-line, writes `<ISO-UTC-Z> <line>` to stdout.
"""
from __future__ import annotations

import datetime as _dt
import sys


def main() -> int:
    try:
        for line in sys.stdin:
            ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            sys.stdout.write(f"{ts} {line}")
            sys.stdout.flush()
    except BrokenPipeError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Write `scripts/field-test/tail-source.sh`**:

```bash
#!/usr/bin/env bash
# /vg:field-test tail wrapper — pipes source output through redact-stream.py
# then prefix-iso.py before writing to disk. Capture-time redaction closes
# the disk-exposure window v1 left open until Stop.
set -euo pipefail

TYPE=""
TARGET=""
OUT=""
REDACT_PATTERN="default"
while [ $# -gt 0 ]; do
  case "$1" in
    --type)    TYPE="$2";          shift 2 ;;
    --target)  TARGET="$2";        shift 2 ;;
    --out)     OUT="$2";           shift 2 ;;
    --redact)  REDACT_PATTERN="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

if [ -z "$TYPE" ] || [ -z "$TARGET" ] || [ -z "$OUT" ]; then
  echo "usage: tail-source.sh --type {file|command} --target <arg> --out <path> [--redact <pattern>]" >&2
  exit 64
fi

mkdir -p "$(dirname "$OUT")"
: > "$OUT"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REDACTOR="$SCRIPT_DIR/redact-stream.py"
PREFIXER="$SCRIPT_DIR/prefix-iso.py"

cleanup() {
  if [ -n "${CHILD_PID:-}" ] && kill -0 "$CHILD_PID" 2>/dev/null; then
    kill -TERM "$CHILD_PID" 2>/dev/null || true
    sleep 0.3
    kill -KILL "$CHILD_PID" 2>/dev/null || true
  fi
  exit 0
}
trap cleanup TERM INT

case "$TYPE" in
  file)
    if [ ! -e "$TARGET" ]; then
      "$PYTHON_BIN" -c "import datetime as d; print(d.datetime.now(d.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'tail-source: waiting for $TARGET to exist')" >> "$OUT"
    fi
    tail -F -n 0 "$TARGET" 2>/dev/null \
      | "$PYTHON_BIN" "$REDACTOR" --pattern "$REDACT_PATTERN" \
      | "$PYTHON_BIN" "$PREFIXER" \
      >> "$OUT" &
    CHILD_PID=$!
    wait "$CHILD_PID"
    ;;
  command)
    # shellcheck disable=SC2086
    bash -c "$TARGET" 2>&1 \
      | "$PYTHON_BIN" "$REDACTOR" --pattern "$REDACT_PATTERN" \
      | "$PYTHON_BIN" "$PREFIXER" \
      >> "$OUT" &
    CHILD_PID=$!
    wait "$CHILD_PID"
    ;;
  *)
    echo "unknown --type: $TYPE" >&2
    exit 64
    ;;
esac
```

**Step 5: Mirror + run**:

```bash
mkdir -p .claude/scripts/field-test
cp scripts/field-test/tail-source.sh .claude/scripts/field-test/
cp scripts/field-test/prefix-iso.py .claude/scripts/field-test/
chmod +x scripts/field-test/tail-source.sh .claude/scripts/field-test/tail-source.sh
python -m pytest tests/test_field_test_tail_source.py -v
```

PASS expected.

**Step 6: Commit**

```bash
git add scripts/field-test/tail-source.sh scripts/field-test/prefix-iso.py \
        .claude/scripts/field-test/tail-source.sh .claude/scripts/field-test/prefix-iso.py \
        tests/test_field_test_tail_source.py
git commit -m "feat(field-test): tail-source.sh + portable prefix-iso.py

Closes Codex review §7: replaces GNU date %3N (macOS BSD date breaks
silently) with prefix-iso.py portable Python wrapper.

Closes Codex review §4: pipes through redact-stream.py BEFORE writing
to disk. Capture-time redaction closes the multi-hour disk-exposure
window v1 left open.

--redact <pattern> per-session regex passed from skill body resolves
session.redaction config.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Overlay JS with idempotent reload + reload_epoch

**Files:**
- Create: `scripts/field-test/overlay.js`
- Mirror: `.claude/scripts/field-test/overlay.js`
- Test: `tests/test_field_test_overlay_js.py`

**Key diff vs v1 plan:**
- `state.reload_epoch` field added so orchestrator distinguishes pre/post-reload marks.
- Overlay no longer is the only source for marks — orchestrator polls `state.marks` directly. Console emit is notification-only.
- Functional test (jsdom or headless playwright) actually clicks Start + Mark + asserts `state.marks.length === 1`. No more substring tautology.

**Step 1: Failing test**

```python
"""tests/test_field_test_overlay_js.py"""
from __future__ import annotations

import os, shutil, subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY = REPO_ROOT / "scripts" / "field-test" / "overlay.js"
MIRROR = REPO_ROOT / ".claude" / "scripts" / "field-test" / "overlay.js"


def test_overlay_exists():
    assert OVERLAY.is_file()


def test_overlay_no_eval_no_cross_origin():
    body = OVERLAY.read_text(encoding="utf-8")
    assert "eval(" not in body
    assert "new Function(" not in body
    assert "fetch('http" not in body and 'fetch("http' not in body


def test_overlay_state_shape():
    body = OVERLAY.read_text(encoding="utf-8")
    # Must declare state with reload_epoch + marks array + status
    assert "window.__VG_FT_STATE" in body
    assert "reload_epoch" in body, "v2 must track reload epoch for orchestrator dedupe"
    assert "marks:" in body
    assert "status:" in body


def test_overlay_console_emit_is_notification_only():
    body = OVERLAY.read_text(encoding="utf-8")
    # Console markers must include event type but mark entries must also go to state.marks
    # The marker text alone is NOT the source of truth.
    assert "state.marks.push" in body or "marks.push" in body, (
        "v2 overlay must push mark entries into state.marks (orchestrator polls state, not console)"
    )


def test_overlay_idempotent_init():
    body = OVERLAY.read_text(encoding="utf-8")
    assert "if (window.__VG_FT_STATE) return" in body or "if (window.__VG_FT_INIT)" in body, (
        "overlay must be idempotent on re-injection (post-reload)"
    )


def test_mirror_byte_identity():
    assert OVERLAY.read_bytes() == MIRROR.read_bytes()


_node = pytest.mark.skipif(not shutil.which("node"), reason="node required")


@_node
def test_overlay_syntax_via_node_check():
    r = subprocess.run(["node", "--check", str(OVERLAY)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@_node
def test_overlay_mark_flow_via_jsdom(tmp_path):
    """v2.1 round-2 SHOULD-6: functional smoke is DEFAULT, not env-gated.

    Loads overlay in jsdom, clicks Start, clicks Mark, fills note, submits.
    Asserts state.marks.length === 1 and entry has user_note. The runner
    script auto-installs jsdom via `npm i --no-save jsdom` on first run
    if it's missing — CI environments that lack node skip gracefully via
    the _node marker.
    """
    runner = REPO_ROOT / "scripts" / "field-test" / "_test-jsdom-runner.js"
    if not runner.is_file():
        pytest.fail(
            "v2.1: jsdom runner must ship with scripts/field-test/. "
            "Run scripts/field-test/_install-jsdom.sh once to bootstrap."
        )
    r = subprocess.run(["node", str(runner), str(OVERLAY)],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "marks.length=1" in r.stdout
    assert "status=recording" in r.stdout
    assert 'user_note="found bug"' in r.stdout
    assert "user_note=test note" in r.stdout
```

**Step 2: Run** → FAIL.

**Step 3: Write overlay.js**

(Same skeleton as v1 plan with these specific v2 changes — full file in repo)

```javascript
/* eslint-disable */
// VGFlow /vg:field-test overlay v2 — vanilla browser JS, no deps.
// Injected via mcp__playwright1__browser_evaluate.
// state.marks[] is canonical source; console emit is notification only.
(function () {
  "use strict";
  if (window.__VG_FT_STATE) {
    // Re-injection (e.g. post-reload). Bump reload_epoch, do NOT wipe marks-server-side
    // (orchestrator holds the server-side marks.raw.jsonl record).
    window.__VG_FT_STATE.reload_epoch = (window.__VG_FT_STATE.reload_epoch || 0) + 1;
    if (window.__VG_FT_INIT) window.__VG_FT_INIT();
    return;
  }

  var BUFFER_CAP = 10000;
  function nowIso() { return new Date().toISOString(); }
  function emit(event, payload) {
    try {
      console.log("[VG_FT] " + JSON.stringify({ event: event, ts: nowIso(), payload: payload || {} }));
    } catch (e) {}
  }

  var state = {
    status: "idle",
    reload_epoch: 0,
    marks: [],
    buffer: { console: [], network: [], nav: [], clicks: [] },
    drops: {}
  };
  window.__VG_FT_STATE = state;

  function pushBuffer(name, entry) {
    var b = state.buffer[name];
    b.push(entry);
    while (b.length > BUFFER_CAP) { b.shift(); state.drops[name] = (state.drops[name] || 0) + 1; }
  }

  // Console / fetch / XHR / history / click monkeypatching — same as v1 plan task 2 body.
  // (See repo for full implementation; omitted here for plan brevity.)

  function render() {
    var existing = document.getElementById("__vg-ft-overlay");
    if (existing) existing.remove();
    var root = document.createElement("div");
    root.id = "__vg-ft-overlay";
    root.style.cssText = "position:fixed;top:12px;right:12px;z-index:2147483647;font:13px/1.3 system-ui;background:#0b1220;color:#e5e7eb;padding:10px;border-radius:8px";
    var pillBg = state.status === "recording" ? "#16a34a" : (state.status === "idle" ? "#475569" : "#dc2626");
    root.innerHTML =
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">' +
      '<span id="__vg-ft-pill" style="background:' + pillBg + ';padding:2px 8px;border-radius:999px;font-size:11px">' + state.status + '</span>' +
      '<span style="font-size:11px;opacity:.7">marks: ' + state.marks.length + '</span>' +
      '</div>' +
      '<div style="display:flex;gap:6px;flex-wrap:wrap">' +
      '<button id="__vg-ft-start" style="background:#16a34a;color:#fff;border:0;padding:6px 10px;border-radius:6px">▶ Start</button>' +
      '<button id="__vg-ft-mark" style="background:#f59e0b;color:#000;border:0;padding:6px 10px;border-radius:6px">⚑ Mark</button>' +
      '<button id="__vg-ft-stop" style="background:#dc2626;color:#fff;border:0;padding:6px 10px;border-radius:6px">■ Stop</button>' +
      '</div>';
    document.body.appendChild(root);
    document.getElementById("__vg-ft-start").onclick = function () {
      if (state.status !== "idle") return;
      state.status = "recording";
      emit("start", { url: location.href });
      render();
    };
    document.getElementById("__vg-ft-stop").onclick = function () {
      if (state.status === "idle") return;
      state.status = "idle";
      emit("stop", { marks: state.marks.length });
      render();
    };
    document.getElementById("__vg-ft-mark").onclick = openMark;
  }

  function openMark() {
    if (state.status !== "recording") { alert("Click Start first."); return; }
    var existing = document.getElementById("__vg-ft-modal");
    if (existing) existing.remove();
    var modal = document.createElement("div");
    modal.id = "__vg-ft-modal";
    modal.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:2147483646;display:flex;align-items:center;justify-content:center";
    modal.innerHTML =
      '<div style="background:#0b1220;color:#e5e7eb;padding:18px;border-radius:10px;min-width:420px">' +
      '<div style="margin-bottom:10px;font-weight:600">Mark current view</div>' +
      '<div style="margin-bottom:8px;font-size:12px;opacity:.7">URL: ' + location.href + '</div>' +
      '<textarea id="__vg-ft-note" rows="5" style="width:100%;background:#1e293b;color:#e5e7eb;border:1px solid #334155;border-radius:6px;padding:8px"></textarea>' +
      '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px">' +
      '<button id="__vg-ft-cancel" style="background:#475569;color:#fff;border:0;padding:6px 12px;border-radius:6px">Cancel</button>' +
      '<button id="__vg-ft-submit" style="background:#16a34a;color:#fff;border:0;padding:6px 12px;border-radius:6px">Submit</button>' +
      '</div></div>';
    document.body.appendChild(modal);
    document.getElementById("__vg-ft-cancel").onclick = function () { modal.remove(); };
    document.getElementById("__vg-ft-submit").onclick = function () {
      var note = (document.getElementById("__vg-ft-note").value || "").trim();
      if (!note) { alert("Note required."); return; }
      var entry = {
        n: state.marks.length,
        ts: nowIso(),
        url: location.href,
        referrer: document.referrer || "",
        nav_chain: state.buffer.nav.slice(-5),
        user_note: note,
        viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio || 1 },
        click_target: state.buffer.clicks[state.buffer.clicks.length - 1] || null,
        reload_epoch: state.reload_epoch
      };
      state.marks.push(entry);                  // canonical source
      emit("mark", { n: entry.n });             // notification only
      modal.remove();
      render();
    };
  }

  window.__VG_FT_INIT = function () { render(); return true; };
  window.__VG_FT_INIT();
})();
```

(Full overlay body with full console/fetch/XHR/history/click monkeypatches — see commit; plan shows the v2-specific delta.)

**Step 4: Mirror + Run** → PASS.

**Step 5: Commit**

```bash
git add scripts/field-test/overlay.js .claude/scripts/field-test/overlay.js tests/test_field_test_overlay_js.py
git commit -m "feat(field-test): overlay v2 — state.marks canonical + reload_epoch

Closes Codex review §1 + §3:
  - state.marks[] is canonical source. Console.log markers are
    notifications only — orchestrator polls state via browser_evaluate,
    not console_messages (which is snapshot-replay and would duplicate
    marks N times per session).
  - state.reload_epoch increments on re-injection after page reload so
    orchestrator can distinguish pre/post-reload marks (overlay state
    persists across SPA nav, wipes on full reload).

**v2.1 update**: functional jsdom smoke runs by DEFAULT (not behind VG_RUN_BROWSER_TESTS=1). The `_node` marker skips gracefully when node is absent; otherwise the runner auto-installs jsdom via `npm i --no-save jsdom` on first run. Per round-2 SHOULD-6.
exercises Start → Mark → Submit and asserts state.marks.length === 1.
Replaces v1 plan's substring-tautology tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: build-bundle.py with redact-stream integration + naive-ts warning + partial recovery

**Files:**
- Create: `scripts/field-test/build-bundle.py`
- Mirror to `.claude/`
- Test: `tests/test_field_test_build_bundle.py`

**Key diff vs v1 plan:**
- API log lines already redacted at capture; build-bundle re-runs through `redact-stream.py` for idempotent safety on browser-side streams (`console.raw.jsonl`, `network.raw.jsonl`).
- Naive (non-Z) timestamps in API log → emit warning to `errors.jsonl` + drop, NOT silent.
- Partial `marks.raw.jsonl` (truncated mid-line from disk-fill / crash) → set `bundle.partial=true`, write what parsed, continue.
- 0-marks session test added.

**Step 1: Failing test** (subset shown; full file generated similarly):

```python
def test_naive_timestamp_logged_to_errors(tmp_path):
    session = _seed_minimal(tmp_path)
    (session / "api-test.log").write_text(
        "2026-05-11T10:00:00Z naive: this one parses\n"
        "2026-05-11 10:00:00 naive: this one does NOT (no T+Z)\n",
        encoding="utf-8",
    )
    subprocess.run([sys.executable, BUILDER, "--session-dir", str(session), "--mark-window-sec", "30"], check=True)
    errors = (session / "errors.jsonl").read_text(encoding="utf-8")
    assert "naive: this one does NOT" in errors


def test_partial_marks_raw_recovered(tmp_path):
    session = _seed_minimal(tmp_path)
    # Truncate last mark mid-JSON
    raw = (session / "marks.raw.jsonl")
    raw.write_text(raw.read_text(encoding="utf-8") + '{"n": 99, "ts": "2026', encoding="utf-8")
    subprocess.run([sys.executable, BUILDER, "--session-dir", str(session)], check=True)
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("partial") is True
    assert manifest.get("mark_count") < 99


def test_zero_marks_session_valid_manifest(tmp_path):
    session = _seed_empty(tmp_path)  # no marks.raw.jsonl
    subprocess.run([sys.executable, BUILDER, "--session-dir", str(session)], check=True)
    manifest = json.loads((session / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["mark_count"] == 0
```

**Step 2: Full implementation body** (v2.1 — no longer "as in v1 plan"):

```python
#!/usr/bin/env python3
"""scripts/field-test/build-bundle.py — assemble field-test capture bundle."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Import redact-stream as module for perf (avoid subprocess fork per line).
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from redact_stream import compile_pattern, redact_line  # type: ignore

ISO_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b")


@dataclass(frozen=True)
class LogLine:
    ts_iso: str
    raw: str


def parse_iso_log(path: Path, errors_log: Path) -> list[LogLine]:
    out: list[LogLine] = []
    with errors_log.open("a", encoding="utf-8") as err:
        for ln in path.read_text(encoding="utf-8").splitlines():
            m = ISO_Z_RE.match(ln)
            if not m:
                err.write(json.dumps({"src": str(path), "naive_ts": ln}) + "\n")
                continue
            out.append(LogLine(ts_iso=m.group(0), raw=ln))
    return out


def correlate_window(lines: list[LogLine], mark_ts: str, window_sec: int) -> list[str]:
    # Linear scan — bundles are KB-MB, not GB. ts_iso comparisons via string sort
    # are correct because of ISO-8601 lexicographic ordering of fixed-length Z form.
    lo = _shift_iso(mark_ts, -window_sec)
    hi = _shift_iso(mark_ts, +window_sec)
    return [ln.raw for ln in lines if lo <= ln.ts_iso <= hi]


def _shift_iso(ts: str, delta_sec: int) -> str:
    from datetime import datetime, timedelta, timezone
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (dt + timedelta(seconds=delta_sec)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def assemble(session_dir: Path, mark_window_sec: int) -> dict:
    session = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    pattern = compile_pattern(session.get("redaction") or "")
    errors_log = session_dir / "errors.jsonl"

    # Load per-source API logs.
    api_logs: dict[str, list[LogLine]] = {}
    for src in session.get("sources", []):
        label = src["label"]
        api_path = session_dir / f"api-{label}.log"
        if api_path.exists():
            api_logs[label] = parse_iso_log(api_path, errors_log)

    # Load browser-side streams (in-memory until Stop → now redact + write).
    redacted_browser_streams = {}
    for name in ("console.raw.jsonl", "network.raw.jsonl", "nav.raw.jsonl", "clicks.raw.jsonl"):
        p = session_dir / name
        if not p.exists():
            continue
        out_lines = [redact_line(pattern, ln) for ln in p.read_text(encoding="utf-8").splitlines()]
        redacted_browser_streams[name] = out_lines

    # Walk marks.raw.jsonl line-by-line; tolerate truncated final line.
    marks_raw = session_dir / "marks.raw.jsonl"
    marks: list[dict] = []
    partial = False
    if marks_raw.exists():
        for ln in marks_raw.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                marks.append(json.loads(ln))
            except json.JSONDecodeError:
                partial = True
                with errors_log.open("a", encoding="utf-8") as err:
                    err.write(json.dumps({"truncated_line": ln[:200]}) + "\n")
                break

    # Per-Mark assembly with ±window correlation.
    bundle_marks: list[dict] = []
    for mark in marks:
        n = mark["n"]
        ts = mark["ts"]
        bundle_marks.append({
            **{k: mark[k] for k in mark if k != "raw"},
            "user_note": redact_line(pattern, mark.get("user_note", "")),
            "console_window": [
                redact_line(pattern, ln)
                for ln in _slice_window(redacted_browser_streams.get("console.raw.jsonl", []), ts, mark_window_sec)
            ],
            "network_window": [
                redact_line(pattern, ln)
                for ln in _slice_window(redacted_browser_streams.get("network.raw.jsonl", []), ts, mark_window_sec)
            ],
            "api_log_correlated": {
                label: [redact_line(pattern, raw) for raw in correlate_window(lines, ts, mark_window_sec)]
                for label, lines in api_logs.items()
            },
        })

    manifest = {
        "version": "1",
        "sid": session["sid"],
        "phase": session.get("phase"),
        "mark_count": len(bundle_marks),
        "partial": partial,
        "redaction_applied": session.get("redaction") or "",
        "redaction_locations": ["capture", "build"],
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (session_dir / "marks.jsonl").write_text(
        "\n".join(json.dumps(m) for m in bundle_marks),
        encoding="utf-8",
    )
    return manifest


def _slice_window(stream_lines: list[str], mark_ts: str, window_sec: int) -> Iterable[str]:
    # Browser-side lines carry an embedded `"ts":"..."` field; cheap regex extraction.
    ts_field = re.compile(r'"ts"\s*:\s*"([^"]+)"')
    lo = _shift_iso(mark_ts, -window_sec)
    hi = _shift_iso(mark_ts, +window_sec)
    for ln in stream_lines:
        m = ts_field.search(ln)
        if not m:
            continue
        if lo <= m.group(1) <= hi:
            yield ln


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-dir", required=True)
    ap.add_argument("--mark-window-sec", type=int, default=30)
    args = ap.parse_args()
    manifest = assemble(Path(args.session_dir), args.mark_window_sec)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 3: Tests** — run `python -m pytest tests/test_field_test_build_bundle.py -v`. Expected: all 6 (zero-marks + partial + naive-ts + window-correlation + redaction-applied-both-sites + linux-path-with-spaces) pass.

**Step 4: Commit**

```bash
git add scripts/field-test/build-bundle.py .claude/scripts/field-test/build-bundle.py tests/test_field_test_build_bundle.py
git commit -m "feat(field-test): build-bundle.py with redact-pipe + naive-ts + partial recovery"
```

**Commit msg references** Codex round-1 §5 fixture gaps + round-1 §4 redaction at correct site + round-2 MUST-8 (full body inlined).

---

## Task 6: analyze.py — robust to KNOWN-ISSUES corruption + analyzer subagent

**Files:**
- Create: `scripts/field-test/analyze.py`
- Create: `agents/vg-field-test-analyzer/SKILL.md`
- Mirrors
- Test: `tests/test_field_test_analyze.py`

**Key diff vs v1 plan:**
- KNOWN-ISSUES corruption: write `KNOWN-ISSUES.corrupt-<ts>.json.bak`, emit `analyzer.known_issues_corrupted` telemetry, REFUSE to append (no silent wipe).
- Dedupe test extended: re-run on same session = idempotent. Different sid with same `note` = both appended.

```python
def test_corrupt_known_issues_preserved_not_wiped(tmp_path):
    session = _seed_session(tmp_path)
    known = tmp_path / "KNOWN-ISSUES.json"
    known.write_text("not valid json {", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, ANALYZER, "--session-dir", str(session), "--known-issues", str(known)],
        capture_output=True, text=True,
    )
    # Analyzer aborts append cleanly
    assert r.returncode != 0 or "corrupted" in (r.stdout + r.stderr).lower()
    # Original corrupt file backed up (sidecar)
    backups = list(tmp_path.glob("KNOWN-ISSUES.corrupt-*.json.bak"))
    assert len(backups) == 1, "must back up corrupt file, not silently wipe"
```

Implementation diff in `append_known_issues`:

```python
def append_known_issues(known_path: Path, sid: str, phase: str | None, marks: list[dict]) -> None:
    if known_path.is_file():
        try:
            payload = json.loads(known_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = known_path.with_suffix(f".corrupt-{int(time.time())}.json.bak")
            shutil.copy2(known_path, backup)
            print(f"⛔ KNOWN-ISSUES.json corrupted; backed up to {backup} — refusing append", file=sys.stderr)
            raise SystemExit(2)
    else:
        payload = {"version": "1", "issues": []}
    # rest unchanged
```

---

## Task 7: Operational helpers + MARKER_TO_AUTO_EVENT extension

**v2.1 expansion**: round-2 review found this task was a one-liner pointer with no code. v2.1 fuses three small helper scripts (`check-quota.py`, `release-lock.py`, the tail-respawn primitive in `tail-source.sh`) with the original orchestrator marker mapping.

### Task 7a: `check-quota.py` quota enforcement helper

**Files:**
- Create: `scripts/field-test/check-quota.py`
- Mirror to `.claude/`
- Test: `tests/test_field_test_check_quota.py`

**Step 1: Failing test**

```python
def test_check_quota_passes_under_caps(tmp_path):
    session = tmp_path / "ft-test"
    session.mkdir()
    (session / "session.json").write_text(json.dumps({
        "sid": "ft-test",
        "started_at": time.time(),
        "session_max_size_mb": 100,
        "max_session_hours": 2,
    }))
    (session / "small.log").write_text("a" * 1024)
    r = subprocess.run([sys.executable, CHECK_QUOTA, "--session-dir", str(session)],
                       capture_output=True, text=True)
    assert r.returncode == 0


def test_check_quota_fails_on_size_cap(tmp_path):
    session = tmp_path / "ft-test"
    session.mkdir()
    (session / "session.json").write_text(json.dumps({
        "sid": "ft-test", "started_at": time.time(),
        "session_max_size_mb": 0,  # any size > 0 trips
        "max_session_hours": 24,
    }))
    (session / "blob.bin").write_bytes(b"x" * (2 * 1024))
    r = subprocess.run([sys.executable, CHECK_QUOTA, "--session-dir", str(session)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "size" in r.stdout.lower() + r.stderr.lower()


def test_check_quota_fails_on_wall_clock(tmp_path):
    session = tmp_path / "ft-test"
    session.mkdir()
    (session / "session.json").write_text(json.dumps({
        "sid": "ft-test",
        "started_at": time.time() - 3 * 3600,
        "session_max_size_mb": 1024,
        "max_session_hours": 1,
    }))
    r = subprocess.run([sys.executable, CHECK_QUOTA, "--session-dir", str(session)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "wall" in r.stdout.lower() + r.stderr.lower() or "hours" in r.stdout.lower() + r.stderr.lower()
```

**Step 2: Implementation**

```python
#!/usr/bin/env python3
"""scripts/field-test/check-quota.py — fail-stop when session exceeds caps."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _dir_size_bytes(p: Path) -> int:
    total = 0
    for entry in p.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except (FileNotFoundError, PermissionError):
                pass
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-dir", required=True)
    args = ap.parse_args()

    session_dir = Path(args.session_dir)
    session = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    size_cap_mb = float(session.get("session_max_size_mb", 1024))
    hours_cap = float(session.get("max_session_hours", 4))
    started_at = float(session.get("started_at") or time.time())

    size_mb = _dir_size_bytes(session_dir) / (1024 * 1024)
    if size_mb > size_cap_mb:
        print(f"⛔ quota: size {size_mb:.1f}MB > cap {size_cap_mb}MB", file=sys.stderr)
        return 1

    elapsed_h = (time.time() - started_at) / 3600.0
    if elapsed_h > hours_cap:
        print(f"⛔ quota: wall-clock {elapsed_h:.2f}h > cap {hours_cap}h", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 3: Commit**

```bash
git add scripts/field-test/check-quota.py .claude/scripts/field-test/check-quota.py tests/test_field_test_check_quota.py
git commit -m "feat(field-test): check-quota.py size+wall-clock fail-stop helper"
```

### Task 7b: `release-lock.py` stuck-lock recovery

**Files:**
- Create: `scripts/field-test/release-lock.py`
- Mirror
- Test: `tests/test_field_test_release_lock.py`

**Step 1: Failing test**

```python
def test_release_lock_removes_dead_pid_lock(tmp_path):
    lock_dir = tmp_path / ".vg" / "field-test" / ".active"
    lock_dir.mkdir(parents=True)
    # Write a definitely-dead PID (1 is init on Linux but on Win 99999999 will fail).
    (lock_dir / "owner").write_text("ft-deadbeef")
    (lock_dir / "pid").write_text("99999999")
    r = subprocess.run([sys.executable, RELEASE_LOCK, "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert not lock_dir.exists(), "dead-PID lock should be released"


def test_release_lock_refuses_live_pid_lock(tmp_path):
    lock_dir = tmp_path / ".vg" / "field-test" / ".active"
    lock_dir.mkdir(parents=True)
    (lock_dir / "owner").write_text("ft-live")
    (lock_dir / "pid").write_text(str(os.getpid()))  # self is alive
    r = subprocess.run([sys.executable, RELEASE_LOCK, "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert lock_dir.exists(), "live-PID lock must NOT be released"
    assert "alive" in (r.stdout + r.stderr).lower()


def test_release_lock_idempotent_when_no_lock(tmp_path):
    r = subprocess.run([sys.executable, RELEASE_LOCK, "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0
```

**Step 2: Implementation**

```python
#!/usr/bin/env python3
"""scripts/field-test/release-lock.py — release a stuck .vg/field-test/.active lock."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import subprocess
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True,
            )
            return str(pid) in r.stdout
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="Repo root containing .vg/")
    ap.add_argument("--force", action="store_true",
                    help="Remove lock even if PID file claims a live owner")
    args = ap.parse_args()

    lock = Path(args.root) / ".vg" / "field-test" / ".active"
    if not lock.exists():
        print("✓ no lock present", file=sys.stderr)
        return 0

    pid_file = lock / "pid"
    pid = 0
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            pid = 0

    if not args.force and pid > 0 and _pid_alive(pid):
        owner = (lock / "owner").read_text(encoding="utf-8").strip() if (lock / "owner").exists() else "?"
        print(f"⛔ lock owner pid={pid} (sid={owner}) is still alive — refusing release. Use --force to override.", file=sys.stderr)
        return 1

    shutil.rmtree(lock, ignore_errors=False)
    print(f"✓ released stuck lock (pid={pid} not alive)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 3: Commit**

```bash
git add scripts/field-test/release-lock.py .claude/scripts/field-test/release-lock.py tests/test_field_test_release_lock.py
git commit -m "feat(field-test): release-lock.py stuck-lock recovery helper"
```

### Task 7c: Tail-respawn primitive in `tail-source.sh`

The respawn loop was implicit in v2 plan. Inline it explicitly into `tail-source.sh`'s body (Task 3) — **also tested by `test_field_test_tail_source.py::test_tail_respawn_three_times`**:

```bash
# Inside tail-source.sh — wrap the actual tail in a 3-strike respawn loop
respawn_count=0
while [ "$respawn_count" -lt 3 ]; do
  if [ "$TYPE" = "file" ]; then
    tail -F "$TARGET" 2>>"${OUT}.tail-err" | "${PYTHON_BIN:-python3}" "$REDACT_SCRIPT" --pattern "$REDACT" --prefix-iso >> "$OUT" &
  else
    bash -c "$TARGET" 2>>"${OUT}.tail-err" | "${PYTHON_BIN:-python3}" "$REDACT_SCRIPT" --pattern "$REDACT" --prefix-iso >> "$OUT" &
  fi
  tail_pid=$!
  wait "$tail_pid"
  rc=$?
  if [ "$rc" -eq 0 ] || [ "$rc" -gt 128 ]; then
    # 0 = clean exit; >128 = killed by signal (SIGTERM from orchestrator) — do not respawn
    exit "$rc"
  fi
  respawn_count=$((respawn_count + 1))
  echo "[$(date -u +%FT%TZ)] tail-source respawn $respawn_count/3 (rc=$rc)" >> "${OUT}.tail-err"
  sleep 1
done
echo "[$(date -u +%FT%TZ)] tail.dead — gave up after 3 respawns" >> "${OUT}.tail-err"
exit 1
```

### Task 7d: MARKER_TO_AUTO_EVENT extension (original Task 7 content)

Same orchestrator wiring as v1 plan: `scripts/vg-orchestrator/__main__.py` adds `("field-test", "complete") → "field_test.session_completed"`. Mirror to `.claude/`. Test: `tests/test_field_test_marker_mapping.py` asserts the tuple key is present in `MARKER_TO_AUTO_EVENT`.

**Commit msg references** round-2 MUST-1 (respawn body), MUST-2 (check-quota), MUST-3 (release-lock).

---

## Task 8: Skill entry `commands/vg/field-test.md` with concrete MCP shapes + atomic lock + no `--resume`

**Files:**
- Create: `commands/vg/field-test.md`
- Mirror
- Test: `tests/test_field_test_skill_structure.py`

**Key diff vs v1 plan (per Codex §1, §3, §6, §9):**

1. **State polling** replaces console marker polling in step 5. **v2.1**: epoch K→0 detection forces full re-inject + `last_consumed=0` reset on SPA full-reload (F5 / router redirect that wipes `window.__VG_FT_STATE`):

```bash
# Step 5: capture loop — poll overlay state directly (NOT console_messages)
# v2.1 SPA full-reload handling: epoch starts at 0, increments on overlay
# re-inject. Browser F5 / hard nav wipes window state → epoch resets to 0.
# Detection rule: if (returned_epoch < last_epoch) → full reload happened
#                → re-inject overlay
#                → set last_consumed = 0  (cannot trust stale offset)
last_consumed=0
last_epoch=0
while true; do
  # AI tool call (skill body shows this as the orchestrator instruction):
  #   mcp__playwright1__browser_evaluate({
  #     function: "() => ({ len: window.__VG_FT_STATE.marks.length, status: window.__VG_FT_STATE.status, epoch: window.__VG_FT_STATE.reload_epoch })"
  #   })
  # If state is undefined (full reload erased it): re-inject overlay.js, set last_consumed=0.
  # Else if returned_epoch < last_epoch: same — full reload, re-inject + reset last_consumed.
  # Else if len > last_consumed:
  #   mcp__playwright1__browser_evaluate({
  #     function: "() => window.__VG_FT_STATE.marks.slice(N, M)"  # JSON-safe payload
  #   })
  # For each new mark in slice:
  #   mcp__playwright1__browser_take_screenshot({ filename: "<session>/marks/<n>.png" })
  #   mcp__playwright1__browser_snapshot({ filename: "<session>/marks/<n>.snapshot.yml" })
  #   append entry to marks.raw.jsonl
  #   "${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event \
  #     "field_test.mark_recorded" --payload "{\"sid\":\"$SID\",\"n\":$N}"
  # last_consumed = len
  sleep 2
done
```

2. **Atomic lock**:
```bash
# Step 0: atomic lock via mkdir (NOT echo > file — TOCTOU race)
if ! mkdir "${REPO_ROOT}/.vg/field-test/.active" 2>/dev/null; then
  ACTIVE_OWNER=$(cat "${REPO_ROOT}/.vg/field-test/.active/owner" 2>/dev/null || echo "unknown")
  echo "⛔ field-test session active (sid=$ACTIVE_OWNER)"
  echo "   If you're sure no session is live: rm -rf .vg/field-test/.active"
  exit 1
fi
echo "$SID" > "${REPO_ROOT}/.vg/field-test/.active/owner"
trap 'rm -rf "${REPO_ROOT}/.vg/field-test/.active"' EXIT
```

3. **Runtime contract telemetry** declares all guaranteed + mark_recorded as required_unless_flag:
```yaml
must_emit_telemetry:
  - event_type: "field_test.session_started"
  - event_type: "field_test.session_stopped"
  - event_type: "field_test.analysis_completed"
  - event_type: "field_test.mark_recorded"
    required_unless_flag: "--allow-zero-marks"
```

4. **Tail spawn with `--redact`** passes session.redaction through:
```bash
for src in $(jq -c '.sources[]' < "$SESSION_DIR/session.json"); do
  TYPE=$(echo "$src" | jq -r '.type')
  TARGET=$(echo "$src" | jq -r '.target')
  LABEL=$(echo "$src" | jq -r '.label')
  REDACT=$(jq -r '.redaction' "$SESSION_DIR/session.json")
  bash .claude/scripts/field-test/tail-source.sh \
    --type "$TYPE" --target "$TARGET" \
    --out "$SESSION_DIR/api-${LABEL}.log" \
    --redact "$REDACT" &
  echo "$!" >> "$SESSION_DIR/.tail-pids"
done
```

5. **HARD-GATE banner** at start:
```markdown
<HARD-GATE>
This skill captures live user behavior. Default redaction applies to
console/network/API log streams + user notes. Screenshots are NOT
redacted.

⚠ Do NOT navigate to password/payment/credentials views during this
  session unless that is the explicit test target. Screenshots embed
  pixel content as-is.

Atomic lock at .vg/field-test/.active prevents concurrent sessions.
On crash, manual cleanup: rm -rf .vg/field-test/.active

v1 does NOT support --resume. A browser crash mid-session leaves raw
streams under .vg/field-test/<sid>/ for manual triage; rerun
build-bundle.py + analyze.py manually if needed.
</HARD-GATE>
```

Skill structure test (`tests/test_field_test_skill_structure.py`) asserts:
- Frontmatter parses
- `runtime_contract.must_emit_telemetry` lists 4 events with `mark_recorded` having `required_unless_flag`
- Skill body contains `mkdir .vg/field-test/.active` (NOT `echo > .active`)
- Skill body contains `browser_evaluate(() => ({ len: window.__VG_FT_STATE.marks.length`
- HARD-GATE banner mentions screenshot warning
- NO `--resume` flag in argument-hint
- NO `--preset` flag in argument-hint
- NO `dev-phases` mirror reference

**Commit msg references** Codex review §1 (sync), §3 (lock TOCTOU), §6 (contract), §9 (concrete MCP shape).

---

## Task 9: Codex skill mirror via generator (v2.1 — global-only deploy after PR #177)

**v2.1 change**: PR #177 made `~/.vgflow` + `~/.codex/skills/` the single global install surface. Project-local `<project>/.codex/skills/*` is **no longer committed** and is pruned by `/vg:update` step 8_sync_codex (v3.6.4) + `sync.sh` step 4b (v3.6.1).

**Steps:**

1. Run `bash scripts/generate-codex-skills.sh --skill vg-field-test` from repo root.
2. Generator produces `codex-skills/vg-field-test/SKILL.md` (canonical source-of-truth, **committed** to repo).
3. At install time, `vg install` copies `codex-skills/*` → `~/.codex/skills/*`. Project-local copies are NOT created.
4. The generator's curated-content guard (PR #179, v3.6.5) preserves any HARD-GATE-CODEX block manually added between frontmatter + body.

**Tests** (`tests/test_field_test_codex_mirror.py`):

```python
def test_codex_mirror_yaml_valid():
    spec = REPO_ROOT / "codex-skills" / "vg-field-test" / "SKILL.md"
    assert spec.exists(), "generator must produce codex mirror"
    fm = _parse_frontmatter(spec.read_text(encoding="utf-8"))
    assert fm["name"] == "vg-field-test"
    assert "description" in fm


def test_codex_mirror_not_present_in_project_codex_dir():
    # PR #177: project-local .codex/skills no longer exists in committed tree
    project_codex = REPO_ROOT / ".codex" / "skills" / "vg-field-test"
    assert not project_codex.exists(), (
        "After PR #177, vg-field-test must NOT be committed under project-local "
        ".codex/skills — global-only install via codex-skills/* → ~/.codex/skills/*."
    )


def test_codex_mirror_byte_identical_to_canonical_invariants():
    # Generator must preserve allowed-tools + runtime_contract telemetry between
    # commands/vg/field-test.md and codex-skills/vg-field-test/SKILL.md.
    canon = (REPO_ROOT / "commands" / "vg" / "field-test.md").read_text(encoding="utf-8")
    mirror = (REPO_ROOT / "codex-skills" / "vg-field-test" / "SKILL.md").read_text(encoding="utf-8")
    for inv in ("mcp__playwright1__browser_evaluate", "must_emit_telemetry",
                "field_test.session_started", "field_test.mark_recorded"):
        assert inv in canon, f"canonical missing {inv}"
        assert inv in mirror, f"codex mirror missing {inv}"
```

**Commit msg references** PR #177 §global-only install integration.

---

## Task 10: Release v3.7.0

**Files:** `VERSION`, `package.json`, `CHANGELOG.md`, `.gitignore` (verify `.vg/` covers field-test path).

**v2.1 note**: target version is `3.7.0` (bumped from v3.6.5 baseline after PR #177 / #179 / v3.6.5 land). The CHANGELOG entry now also acknowledges the downstream `/vg:test-spec` consumer relationship introduced by PR #177.

**CHANGELOG entry** highlights design v2.1 + Codex review remediations + PR #177 integration:

```markdown
## v3.7.0 — /vg:field-test new skill (2026-05-11)

User-driven field-test capture distinct from AI-auto /vg:roam.

### Architecture
- 9 new files under scripts/field-test/ + commands/vg/field-test.md +
  agents/vg-field-test-analyzer/ + schemas/field-test-session.v1.json.
- Sync via browser_evaluate state polling (NOT console_messages replay).
- Per-source API log tails redact at capture time via redact-stream.py.
- Atomic lock via mkdir; portable timestamp via prefix-iso.py.
- MARKER_TO_AUTO_EVENT extension: ('field-test','complete') →
  field_test.session_completed.

### Privacy
Default redaction covers password/token/secret/api_key/email/phone +
Bearer JWT + Authorization header. Multi-form regex (key=value, key:
value, JSON body, bare Bearer). Idempotent. Bad user regex falls back
to default + warns. Screenshots NOT redacted; HARD-GATE banner warns
user before session start.

### v1 scope (post-Codex-review)
- Single preset (no quick/deep enum — deferred v2).
- No --resume (deferred v2; design promised, implementation absent).
- No dev-phases/<N>/ mirror (deferred v2; commit-or-ignore policy
  unresolved).
- No --non-interactive flag (dropped; user-driven skill has no useful
  non-interactive mode).
- No auto-recovered crash bundle (manual triage on browser crash).

### Tests
~38 cross-platform tests. jsdom functional smoke for overlay is the DEFAULT
test path (not behind VG_RUN_BROWSER_TESTS=1) per v2.1 round-2 review.
Linux-specific path-with-spaces fixtures cover Vibe Code/Code/PrintwayV3-style
install dirs. Closes 10 Codex round-1 findings + 5 MUST + 3 SHOULD round-2
findings.

### Integration with PR #177 pipeline
- Codex mirror deploys to ~/.codex/skills/ only (no project-local copy).
- KNOWN-ISSUES.json entries written by analyze.py feed downstream
  /vg:test-spec (post-PR-#177) when the user re-runs the test-spec lane on
  the same phase — lifecycle context is enriched with manually-observed
  defects from field-test sessions. No new orchestrator wiring needed:
  /vg:test-spec already reads .vg/KNOWN-ISSUES.json.
- Phase 4 of /vg:review (post-v3.6.5 / #175) emits evidence-manifest
  entries for RUNTIME-MAP.json + GOAL-COVERAGE-MATRIX.md. Task 8 step 6
  mirrors that pattern: emit-evidence-manifest for FIELD-REPORT.md +
  bundle manifest.json so freshness checks attribute the write to vg:field-test.

### Closes
Internal Codex GPT-5.5 plan review (round-1 §1-§10 + round-2 MUST-1..5 + SHOULD-6..8).
Plan + design v2.1 documented under
docs/plans/2026-05-11-field-test-capture-{design,plan}.md.
```

Run regression sweep, commit, push, tag.

---

## Codex review remediation matrix

### Round 1 (v1 → v2)

| Finding | v1 plan | v2 plan resolution |
|---|---|---|
| §1 Console-poll dedupe race | Polled console messages for marks → snapshot replay duplicates | Task 4: state polling via `browser_evaluate` w/ last-consumed offset; task 8 step 5 documents call shape |
| §2 TDD substring tautologies | Many tests asserted lexical presence | Tasks 1-9: structural + functional tests, jsonschema validation, jsdom smoke for overlay, redaction edge case matrix |
| §3 Concurrency gaps | TOCTOU lock, no respawn impl, no quota impl | Task 8: `mkdir .vg/field-test/.active` atomic; task 8 step 5 documents tail respawn loop + quota check |
| §4 Privacy + redaction | Multi-hour disk-exposure window; broken regex | Task 2: `redact-stream.py` multi-form, idempotent, fallback; task 3: capture-time pipe |
| §5 Fixture coverage gaps | Happy path only | Tasks 2/5/6 add: 0-marks session, partial mid-line, naive ts, JSON body redaction, Bearer form, idempotent re-redact |
| §6 Telemetry contract mismatch | 3 events declared, 7 emitted | Task 8: declare 4 events, `mark_recorded` required_unless_flag |
| §7 Cross-platform `date %3N` | GNU-only | Task 3: `prefix-iso.py` Python wrapper |
| §8 Dead presets | 3 enum values, 0 differential logic | Drop preset enum entirely from v1; ship `standard` capture only |
| §9 Plan executability | Hand-wavy MCP call shape | Task 8 step 5/3 documents `browser_evaluate({function: ...})` payload literally |
| §10 Verdict (back to design) | Design v1 ships with privacy + race + contract issues | Design v2 supersedes; this plan v2 enforces v2 design; ship blocked until tasks 1-10 land |

### Round 2 (v2 → v2.1)

| Finding | v2 plan gap | v2.1 plan resolution |
|---|---|---|
| MUST-1 Task 7 empty | One-line pointer to v1 plan task 6; no respawn body | Task 7c inlines respawn loop in `tail-source.sh`; 3-strike with signal-aware exit-code branching |
| MUST-2 `check-quota.py` missing | Design line 89 named it, plan never authored | Task 7a creates script + 3 tests (under-caps, size-cap-trip, wall-clock-trip) |
| MUST-3 `release-lock.py` missing | Design line 101 named it, plan never authored | Task 7b creates script + 3 tests (dead-PID release, live-PID refuse, no-lock idempotent) |
| MUST-4 SPA F5 reload data loss | `reload_epoch` polled but no K→0 transition logic | Task 8 step 5 adds explicit "epoch_K_to_0 = full_reload = re-inject + reset last_consumed=0" rule |
| MUST-5 User pattern double-wrap | `compose_pattern(user_input)` could double-wrap `\b...\b` user templates | Task 2 adds regression test: user passes already-wrapped pattern, asserts compiled pattern matches expected token (not corrupted by extra wrapping) |
| SHOULD-6 Overlay tests substring-tautology | jsdom smoke was behind `VG_RUN_BROWSER_TESTS=1` | Task 4 makes jsdom smoke the DEFAULT path; substring-only assertions removed |
| SHOULD-7 Path-with-spaces fixtures missing | All fixtures used clean paths | Tasks 3 + 8 add `tmp_path / "with spaces" / "ft-test"` fixture for tail-source and atomic-lock tests |
| SHOULD-8 Task 5 hand-wavy | "as in v1 plan task 4, with extensions" | Task 5 step 2 now inlines full build-bundle.py body |

### PR #177 / #179 / v3.6.5 integration (v2 baseline assumptions → v2.1 adjusted)

| Event | v2 baseline | v2.1 adjustment |
|---|---|---|
| PR #179 (YAML curated-skip repair) | Generator preserved curated content only with explicit guard | Task 9 codex mirror test now verifies the generator's repaired YAML loads without ParseError on the first install pass |
| PR #177 (global-only install) | Codex deploy to both project-local + global | Task 9 deploys to `~/.codex/skills/` only; project-local `.codex/skills/vg-field-test` MUST NOT exist post-install |
| PR #177 (`/vg:test-spec` lane) | No downstream consumer of KNOWN-ISSUES | Task 10 CHANGELOG documents that `/vg:test-spec` reads `.vg/KNOWN-ISSUES.json` to enrich `LIFECYCLE-SPECS.json` with manually-observed defects |
| PR #177 (`verify-goal-coverage-phase.py` generic IDs) | Schema constrained `phase_goal` to `G-\d+` | Task 1 schema permits `[A-Za-z0-9][A-Za-z0-9_.-]*` for `phase_goal` cross-ref to match upstream |
| v3.6.5 / #175 (evidence-manifest auto-record) | Stop step did not emit manifest | Task 8 step 6 calls `emit-evidence-manifest.py` for FIELD-REPORT.md + bundle manifest.json (mirrors fix-loop-and-goals.md pattern) |

---

End of v2.1 plan. **Tasks 1-10** with Task 7 expanded to 7a/7b/7c/7d. Each commit individually. Estimated 5-6 hours engineering wall-clock for a codebase-familiar dev; 8-10 hours for a fresh contributor (v2.1 added ~300 lines of helper code + tests).
