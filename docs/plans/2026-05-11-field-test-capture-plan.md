# /vg:field-test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build new VGFlow skill `/vg:field-test` so the user can manually roam the deployed app in an MCP-playwright browser while AI silently captures multi-source telemetry (browser console + network + clicks + nav chain + per-Mark notes + correlated API server log tails). On Stop, an analyzer subagent produces `FIELD-REPORT.md` and appends entries to `.vg/KNOWN-ISSUES.json`.

**Architecture:** 3-tier — AI orchestrator (skill body) injects a floating overlay JS via `mcp__playwright1__browser_evaluate`; overlay emits markers via `console.log('[VG_FT] ...')`; AI polls `browser_console_messages` every 2s. Per-source API log tails (config-driven file or command sources) run as background subprocesses for the session window. On Stop, `build-bundle.py` correlates streams ±N seconds per Mark, then `vg-field-test-analyzer` subagent writes the human report and KNOWN-ISSUES entries.

**Tech Stack:** Python 3.11+ (orchestrator scripts + analyzer logic), bash (tail wrapper), vanilla browser JS (overlay, no deps), JSON Schema draft-07, MCP playwright1 (already configured), VGFlow runtime_contract + telemetry hash chain (existing).

**Design doc:** [`docs/plans/2026-05-11-field-test-capture-design.md`](./2026-05-11-field-test-capture-design.md)

**Working directory:** stay on `main` per project rule (memory: `feedback_main_branch_only.md`). Commit + push direct.

---

## Conventions for every task below

- All Python = Python 3.11+, type-hinted, follows existing `scripts/` style (`from __future__ import annotations` header, no third-party deps unless already vendored).
- All bash = `set -euo pipefail` header.
- Every script written under `scripts/` MUST be mirrored to `.claude/scripts/` (byte-identical) per existing VGFlow convention. Same for `commands/vg/` → `.claude/commands/vg/`.
- Every test imports `from pathlib import Path` and `REPO_ROOT = Path(__file__).resolve().parents[1]` (or `.parents[2]` for tests/<sub>/).
- Commits use the existing project trailer:
  ```
  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```
- Run full regression sweep before each commit:
  ```
  python -m pytest tests/ -q --tb=no
  ```
  Document any newly green / newly red counts in the commit body.

---

## Task 1: Add `field_test` block to vg.config schema

**Files:**
- Create: `schemas/field-test-session.v1.json`
- Modify: `vg.config.template.md` (add commented `field_test:` block in same style as existing review/test sections)
- Test: `tests/test_field_test_config_schema.py`

**Step 1: Write the failing test**

```python
"""tests/test_field_test_config_schema.py — schema + config block contracts."""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "schemas" / "field-test-session.v1.json"
CONFIG_TEMPLATE = REPO_ROOT / "vg.config.template.md"


def test_schema_exists_and_parses():
    assert SCHEMA.is_file(), "schemas/field-test-session.v1.json must exist"
    data = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert data["$schema"] == "http://json-schema.org/draft-07/schema#"
    required = set(data["required"])
    expected = {
        "version", "sid", "phase", "preset", "base_url",
        "ts_started", "sources", "redaction",
    }
    missing = expected - required
    assert not missing, f"schema must require all v1 fields, missing: {missing}"


def test_config_template_advertises_field_test_block():
    body = CONFIG_TEMPLATE.read_text(encoding="utf-8")
    # Block must be present (commented or uncommented)
    assert re.search(r"^#?\s*field_test\s*:", body, re.MULTILINE), (
        "vg.config.template.md must include a field_test: block"
    )
    for key in [
        "api_log_sources", "default_preset", "default_redaction",
        "default_base_url", "mark_window_sec", "session_max_size_mb",
        "max_session_hours",
    ]:
        assert key in body, f"field_test block must document `{key}`"
```

**Step 2: Run test to verify it fails**

```
python -m pytest tests/test_field_test_config_schema.py -v
```
Expected: FAIL both tests (schema + template not yet present).

**Step 3: Write minimal implementation — create schema**

`schemas/field-test-session.v1.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://vgflow.dev/schemas/field-test-session.v1.json",
  "title": "VG field-test session (v1) — user-driven roam capture",
  "description": "Schema for .vg/field-test/<sid>/session.json — written at session start, mutated on stop. Validated by build-bundle.py + analyzer subagent.",
  "type": "object",
  "required": [
    "version", "sid", "phase", "preset", "base_url",
    "ts_started", "sources", "redaction"
  ],
  "additionalProperties": true,
  "properties": {
    "version": {"const": "1"},
    "sid": {
      "type": "string",
      "pattern": "^ft-(p[0-9A-Z._-]+-)?[0-9TZ:.-]+$",
      "description": "Session id. Phase-less: ft-<iso_ts>. Phase-bound: ft-p<N>-<iso_ts>."
    },
    "phase": {"type": ["string", "null"]},
    "preset": {"enum": ["quick", "standard", "deep"]},
    "base_url": {"type": "string"},
    "ts_started": {"type": "string", "format": "date-time"},
    "ts_stopped": {"type": ["string", "null"], "format": "date-time"},
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
    "redaction": {"type": "string", "description": "Compiled regex pattern actually applied"},
    "mark_count": {"type": "integer", "minimum": 0},
    "aborted": {"type": "boolean"},
    "abort_reason": {"type": ["string", "null"]},
    "bundle_path": {"type": ["string", "null"]}
  }
}
```

**Step 4: Modify `vg.config.template.md`** — append (or merge into existing config block):

```markdown
## field_test (v3.7+ — /vg:field-test skill)

```yaml
field_test:
  # API log sources to tail during a field-test session. Each source
  # produces one .vg/field-test/<sid>/api-<n>.log file.
  api_log_sources:
    # - { type: file,    target: /var/log/api.log,                    label: api-stdout }
    # - { type: command, target: "docker logs -f my-api-container",   label: docker-api }
    # - { type: command, target: "kubectl logs -f pod/api -n prod",   label: k8s-api }

  default_preset: standard       # quick | standard | deep
  default_redaction: 'password|token|secret|api[_-]?key|email|phone'
  default_base_url: ""           # fallback if ENV-CONTRACT.md target.base_url missing
  mark_window_sec: 30            # ±sec correlated window per Mark
  screenshot_quality: 80         # jpeg quality 0-100
  session_max_size_mb: 200       # hard cap before forced stop
  max_session_hours: 4           # absolute wall-clock cap
```

**Step 5: Re-run test**

```
python -m pytest tests/test_field_test_config_schema.py -v
```
Expected: PASS both.

**Step 6: Commit**

```bash
git add tests/test_field_test_config_schema.py schemas/field-test-session.v1.json vg.config.template.md
git commit -m "feat(field-test): schema v1 + vg.config.template block

scaffolds /vg:field-test from docs/plans/2026-05-11-field-test-capture-design.md.
Adds JSON schema draft-07 for session.json + documents config block users
need (api_log_sources, default_preset, default_redaction, base_url,
window/size/duration caps).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Browser overlay JS (vanilla, IIFE)

**Files:**
- Create: `scripts/field-test/overlay.js`
- Create: `.claude/scripts/field-test/overlay.js` (byte-identical mirror)
- Test: `tests/test_field_test_overlay_js.py`

**Step 1: Write the failing test**

```python
"""tests/test_field_test_overlay_js.py — overlay.js structural + syntactic checks."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY = REPO_ROOT / "scripts" / "field-test" / "overlay.js"
MIRROR = REPO_ROOT / ".claude" / "scripts" / "field-test" / "overlay.js"


def test_overlay_exists():
    assert OVERLAY.is_file()


def test_overlay_uses_namespaced_state():
    body = OVERLAY.read_text(encoding="utf-8")
    assert "window.__VG_FT_STATE" in body
    assert "[VG_FT]" in body, "must emit markers with [VG_FT] prefix for AI poller"


def test_overlay_exports_init():
    body = OVERLAY.read_text(encoding="utf-8")
    assert "window.__VG_FT_INIT" in body, (
        "overlay must expose __VG_FT_INIT so AI can verify injection"
    )


def test_overlay_namespace_does_not_collide():
    body = OVERLAY.read_text(encoding="utf-8")
    # No bare global identifiers (defensive). Crude but catches common mistakes.
    for forbidden in ["var FT_", "let FT_", "const FT_", "function FT_"]:
        assert forbidden not in body, f"overlay must namespace all identifiers under __VG_FT_*; found {forbidden}"


def test_overlay_no_eval():
    body = OVERLAY.read_text(encoding="utf-8")
    assert "eval(" not in body
    assert "new Function(" not in body


def test_overlay_no_cross_origin_fetch():
    body = OVERLAY.read_text(encoding="utf-8")
    # Overlay must never reach out to non-same-origin endpoints
    assert "fetch('http" not in body
    assert 'fetch("http' not in body


def test_mirror_byte_identity():
    assert OVERLAY.read_bytes() == MIRROR.read_bytes()


_node = pytest.mark.skipif(not shutil.which("node"), reason="node required for --check")


@_node
def test_overlay_node_check_passes():
    r = subprocess.run(
        ["node", "--check", str(OVERLAY)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"node --check failed:\n{r.stderr}"
```

**Step 2: Run test to verify it fails**

```
python -m pytest tests/test_field_test_overlay_js.py -v
```
Expected: FAIL (file missing).

**Step 3: Write overlay.js**

`scripts/field-test/overlay.js`:

```javascript
/* eslint-disable */
// VGFlow /vg:field-test overlay — vanilla browser JS, no deps.
// Injected via mcp__playwright1__browser_evaluate at session start.
// Emits markers via console.log('[VG_FT] <json>') for AI to poll.

(function () {
  "use strict";
  if (window.__VG_FT_STATE) return; // idempotent

  var BUFFER_CAP = 10000;
  var CLICK_CAP = 200;
  var NAV_CAP = 100;

  function nowIso() { return new Date().toISOString(); }
  function emit(event, payload) {
    try {
      console.log("[VG_FT] " + JSON.stringify({ event: event, ts: nowIso(), payload: payload || {} }));
    } catch (e) { /* swallow */ }
  }

  var state = {
    status: "idle",
    sid: null,
    start_ts: null,
    marks: [],
    buffer: {
      console: [],
      network: [],
      nav: [],
      clicks: []
    },
    drops: { console: 0, network: 0 }
  };
  window.__VG_FT_STATE = state;

  function pushBuffer(name, entry) {
    var b = state.buffer[name];
    b.push(entry);
    var cap = (name === "clicks") ? CLICK_CAP : (name === "nav" ? NAV_CAP : BUFFER_CAP);
    while (b.length > cap) { b.shift(); state.drops[name] = (state.drops[name] || 0) + 1; }
  }

  // ── console monkeypatch ─────────────────────────────────────────────
  ["log", "info", "warn", "error", "debug"].forEach(function (lvl) {
    var orig = console[lvl].bind(console);
    console[lvl] = function () {
      try {
        var args = Array.prototype.slice.call(arguments);
        var text = args.map(function (a) {
          if (typeof a === "string") return a;
          try { return JSON.stringify(a); } catch (_) { return String(a); }
        }).join(" ");
        if (text.indexOf("[VG_FT]") !== 0) {
          pushBuffer("console", { ts: nowIso(), level: lvl, text: text });
        }
      } catch (e) { /* swallow */ }
      return orig.apply(null, arguments);
    };
  });

  // ── fetch + XHR monkeypatch ─────────────────────────────────────────
  var _fetch = window.fetch;
  if (_fetch) {
    window.fetch = function (input, init) {
      var startTs = nowIso();
      var t0 = performance.now();
      var method = (init && init.method) || (input && input.method) || "GET";
      var url = (typeof input === "string") ? input : (input && input.url) || "";
      return _fetch.apply(this, arguments).then(function (resp) {
        pushBuffer("network", {
          ts: startTs, method: method, url: url, status: resp.status,
          duration_ms: Math.round(performance.now() - t0)
        });
        return resp;
      }).catch(function (err) {
        pushBuffer("network", {
          ts: startTs, method: method, url: url, status: 0,
          duration_ms: Math.round(performance.now() - t0),
          error: String(err && err.message || err)
        });
        throw err;
      });
    };
  }
  var _open = XMLHttpRequest.prototype.open;
  var _send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__vg_ft_method = method;
    this.__vg_ft_url = url;
    return _open.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    var xhr = this;
    var startTs = nowIso();
    var t0 = performance.now();
    xhr.addEventListener("loadend", function () {
      pushBuffer("network", {
        ts: startTs,
        method: xhr.__vg_ft_method,
        url: xhr.__vg_ft_url,
        status: xhr.status,
        duration_ms: Math.round(performance.now() - t0)
      });
    });
    return _send.apply(this, arguments);
  };

  // ── navigation tracking ─────────────────────────────────────────────
  function recordNav(reason) {
    pushBuffer("nav", { ts: nowIso(), url: location.href, reason: reason });
  }
  recordNav("init");
  var _push = history.pushState;
  var _replace = history.replaceState;
  history.pushState = function () { var r = _push.apply(this, arguments); recordNav("push"); return r; };
  history.replaceState = function () { var r = _replace.apply(this, arguments); recordNav("replace"); return r; };
  window.addEventListener("popstate", function () { recordNav("popstate"); });

  // ── click capture ───────────────────────────────────────────────────
  document.addEventListener("click", function (ev) {
    try {
      var el = ev.target;
      if (!el || !el.tagName) return;
      var sel = el.tagName.toLowerCase();
      if (el.id) sel += "#" + el.id;
      if (el.className && typeof el.className === "string") sel += "." + el.className.trim().split(/\s+/).slice(0, 3).join(".");
      var text = (el.innerText || el.value || "").slice(0, 80);
      pushBuffer("clicks", { ts: nowIso(), selector: sel, text: text });
    } catch (e) { /* swallow */ }
  }, true);

  // ── overlay UI ──────────────────────────────────────────────────────
  function render() {
    var existing = document.getElementById("__vg-ft-overlay");
    if (existing) existing.remove();
    var root = document.createElement("div");
    root.id = "__vg-ft-overlay";
    root.style.cssText = [
      "position:fixed", "top:12px", "right:12px",
      "z-index:2147483647", "font:13px/1.3 system-ui,sans-serif",
      "background:#0b1220", "color:#e5e7eb",
      "padding:10px 12px", "border-radius:8px",
      "box-shadow:0 4px 12px rgba(0,0,0,.4)", "min-width:220px"
    ].join(";");
    var pillBg = state.status === "recording" ? "#16a34a" : (state.status === "idle" ? "#475569" : "#dc2626");
    root.innerHTML =
      '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">' +
      '<span id="__vg-ft-pill" style="background:' + pillBg + ';padding:2px 8px;border-radius:999px;font-size:11px">' + state.status + '</span>' +
      '<span style="font-size:11px;opacity:.7">marks: ' + state.marks.length + '</span>' +
      '</div>' +
      '<div style="display:flex;gap:6px;flex-wrap:wrap">' +
      '<button id="__vg-ft-start" style="background:#16a34a;color:#fff;border:0;padding:6px 10px;border-radius:6px;cursor:pointer">▶ Start</button>' +
      '<button id="__vg-ft-mark" style="background:#f59e0b;color:#000;border:0;padding:6px 10px;border-radius:6px;cursor:pointer">⚑ Mark</button>' +
      '<button id="__vg-ft-stop" style="background:#dc2626;color:#fff;border:0;padding:6px 10px;border-radius:6px;cursor:pointer">■ Stop</button>' +
      '</div>';
    document.body.appendChild(root);
    document.getElementById("__vg-ft-start").onclick = startSession;
    document.getElementById("__vg-ft-stop").onclick = stopSession;
    document.getElementById("__vg-ft-mark").onclick = openMarkModal;
  }

  function startSession() {
    if (state.status !== "idle") return;
    state.status = "recording";
    state.start_ts = nowIso();
    emit("start", { url: location.href });
    render();
  }
  function stopSession() {
    if (state.status === "idle") return;
    state.status = "idle";
    emit("stop", { marks: state.marks.length });
    render();
  }

  function openMarkModal() {
    if (state.status !== "recording") {
      alert("Click Start first.");
      return;
    }
    var existing = document.getElementById("__vg-ft-modal");
    if (existing) existing.remove();
    var modal = document.createElement("div");
    modal.id = "__vg-ft-modal";
    modal.style.cssText = [
      "position:fixed", "inset:0", "background:rgba(0,0,0,.5)",
      "z-index:2147483646", "display:flex", "align-items:center", "justify-content:center",
      "font:14px/1.4 system-ui,sans-serif"
    ].join(";");
    modal.innerHTML =
      '<div style="background:#0b1220;color:#e5e7eb;padding:18px 22px;border-radius:10px;min-width:420px;max-width:80vw">' +
      '<div style="margin-bottom:10px;font-weight:600">Mark current view</div>' +
      '<div style="margin-bottom:8px;font-size:12px;opacity:.7">URL: ' + location.href + '</div>' +
      '<textarea id="__vg-ft-note" rows="5" style="width:100%;background:#1e293b;color:#e5e7eb;border:1px solid #334155;border-radius:6px;padding:8px;font:13px/1.4 system-ui,sans-serif" placeholder="Describe what you observed at this view (bug, missing feature, slow, etc.)"></textarea>' +
      '<div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px">' +
      '<button id="__vg-ft-cancel" style="background:#475569;color:#fff;border:0;padding:6px 12px;border-radius:6px;cursor:pointer">Cancel</button>' +
      '<button id="__vg-ft-submit" style="background:#16a34a;color:#fff;border:0;padding:6px 12px;border-radius:6px;cursor:pointer">Submit</button>' +
      '</div></div>';
    document.body.appendChild(modal);
    setTimeout(function () { var t = document.getElementById("__vg-ft-note"); if (t) t.focus(); }, 50);
    document.getElementById("__vg-ft-cancel").onclick = function () { modal.remove(); };
    document.getElementById("__vg-ft-submit").onclick = function () {
      var note = (document.getElementById("__vg-ft-note").value || "").trim();
      if (!note) { alert("Note required."); return; }
      var n = state.marks.length;
      var lastClick = state.buffer.clicks[state.buffer.clicks.length - 1] || null;
      var entry = {
        n: n,
        ts: nowIso(),
        url: location.href,
        referrer: document.referrer || "",
        nav_chain: state.buffer.nav.slice(-5),
        user_note: note,
        viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio || 1 },
        click_target: lastClick
      };
      state.marks.push(entry);
      emit("mark", entry);
      modal.remove();
      render();
    };
  }

  window.__VG_FT_INIT = function () { render(); return true; };
  window.__VG_FT_INIT();
})();
```

`.claude/scripts/field-test/overlay.js` is a byte-identical copy.

**Step 4: Sync mirror + re-run tests**

```bash
mkdir -p .claude/scripts/field-test
cp scripts/field-test/overlay.js .claude/scripts/field-test/overlay.js
python -m pytest tests/test_field_test_overlay_js.py -v
```
Expected: PASS all (node smoke skipped if no node).

**Step 5: Commit**

```bash
git add scripts/field-test/overlay.js .claude/scripts/field-test/overlay.js tests/test_field_test_overlay_js.py
git commit -m "feat(field-test): browser overlay JS (vanilla, IIFE, namespaced)

Floating overlay top-right with Start/Stop/Mark buttons + modal note.
Monkeypatches console + fetch + XHR + history + click for capture
buffers (capped). Emits markers via console.log('[VG_FT] <json>') so
AI orchestrator can poll browser_console_messages. State exposed at
window.__VG_FT_STATE; init exposed at window.__VG_FT_INIT.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: API log tail wrapper

**Files:**
- Create: `scripts/field-test/tail-source.sh`
- Create: `.claude/scripts/field-test/tail-source.sh`
- Test: `tests/test_field_test_tail_source.py`

**Step 1: Write the failing test**

```python
"""tests/test_field_test_tail_source.py — tail-source.sh wrapper."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TAIL = REPO_ROOT / "scripts" / "field-test" / "tail-source.sh"
MIRROR = REPO_ROOT / ".claude" / "scripts" / "field-test" / "tail-source.sh"


def test_tail_script_exists():
    assert TAIL.is_file()


def test_tail_script_starts_with_bash_strict():
    body = TAIL.read_text(encoding="utf-8")
    assert body.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in body


def test_tail_handles_both_modes_in_source():
    body = TAIL.read_text(encoding="utf-8")
    assert "--type" in body and "--target" in body and "--out" in body
    assert "file)" in body or '"file"' in body
    assert "command)" in body or '"command"' in body


def test_mirror_byte_identity():
    assert TAIL.read_bytes() == MIRROR.read_bytes()


_bash = pytest.mark.skipif(
    not shutil.which("bash") or sys.platform == "win32",
    reason="bash + POSIX semantics required (Windows skipped)",
)


@_bash
def test_tail_file_mode_writes_iso_prefixed_lines(tmp_path):
    target = tmp_path / "input.log"
    out = tmp_path / "output.log"
    target.write_text("first line\n", encoding="utf-8")
    proc = subprocess.Popen(
        ["bash", str(TAIL), "--type", "file", "--target", str(target), "--out", str(out)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.5)
        target.write_text("first line\nsecond line\n", encoding="utf-8")
        time.sleep(1.5)
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    text = out.read_text(encoding="utf-8")
    assert "second line" in text
    # Lines should be ISO-prefixed (YYYY-MM-DDT...Z)
    for line in text.strip().splitlines():
        assert line[:4].isdigit() and "T" in line[:20], f"line missing ISO prefix: {line!r}"


@_bash
def test_tail_command_mode_captures_command_output(tmp_path):
    out = tmp_path / "output.log"
    proc = subprocess.Popen(
        ["bash", str(TAIL), "--type", "command",
         "--target", "for i in 1 2 3 4 5; do echo line-$i; sleep 0.05; done",
         "--out", str(out)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    proc.wait(timeout=10)
    text = out.read_text(encoding="utf-8")
    for i in range(1, 6):
        assert f"line-{i}" in text
```

**Step 2: Run test to verify it fails**

```
python -m pytest tests/test_field_test_tail_source.py -v
```
Expected: FAIL (script missing).

**Step 3: Write `tail-source.sh`**

`scripts/field-test/tail-source.sh`:

```bash
#!/usr/bin/env bash
# VGFlow /vg:field-test tail wrapper.
# Modes:
#   --type file    --target <path>  --out <path>   → tail -F path
#   --type command --target "cmd..." --out <path>  → eval cmd
# Prepends ISO-8601 UTC timestamp to every emitted line.
# Traps SIGTERM/SIGINT → flushes + exits 0.
set -euo pipefail

TYPE=""
TARGET=""
OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --type)   TYPE="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --out)    OUT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 64 ;;
  esac
done

if [ -z "$TYPE" ] || [ -z "$TARGET" ] || [ -z "$OUT" ]; then
  echo "usage: tail-source.sh --type {file|command} --target <arg> --out <path>" >&2
  exit 64
fi

mkdir -p "$(dirname "$OUT")"
: > "$OUT"

prefix_iso() {
  while IFS= read -r line; do
    printf '%sZ %s\n' "$(date -u +%Y-%m-%dT%H:%M:%S.%3N)" "$line"
  done
}

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
      echo "Z $(date -u +%Y-%m-%dT%H:%M:%S.%3N) tail-source: target file does not yet exist: $TARGET" >> "$OUT"
    fi
    tail -F -n 0 "$TARGET" 2>/dev/null | prefix_iso >> "$OUT" &
    CHILD_PID=$!
    wait "$CHILD_PID"
    ;;
  command)
    # shellcheck disable=SC2086
    bash -c "$TARGET" 2>&1 | prefix_iso >> "$OUT" &
    CHILD_PID=$!
    wait "$CHILD_PID"
    ;;
  *)
    echo "unknown --type: $TYPE" >&2
    exit 64
    ;;
esac
```

**Step 4: Mirror + run tests**

```bash
cp scripts/field-test/tail-source.sh .claude/scripts/field-test/tail-source.sh
chmod +x scripts/field-test/tail-source.sh .claude/scripts/field-test/tail-source.sh
python -m pytest tests/test_field_test_tail_source.py -v
```
Expected: 4 content tests PASS on Windows; 2 functional PASS on Linux/Mac (skipped on Windows).

**Step 5: Commit**

```bash
git add scripts/field-test/tail-source.sh .claude/scripts/field-test/tail-source.sh tests/test_field_test_tail_source.py
git commit -m "feat(field-test): tail-source.sh wrapper for API logs

Supports --type file (tail -F path) and --type command (eval shell cmd).
Prepends ISO-8601 UTC timestamps to every line so build-bundle.py can
correlate Mark windows by wall-clock. Traps SIGTERM/SIGINT for clean
shutdown when /vg:field-test step 6 kills tails.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Bundle builder (Stop-time correlator)

**Files:**
- Create: `scripts/field-test/build-bundle.py`
- Create: `.claude/scripts/field-test/build-bundle.py`
- Test: `tests/test_field_test_build_bundle.py`

**Step 1: Write the failing test**

```python
"""tests/test_field_test_build_bundle.py — bundle assembler + correlator."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER = REPO_ROOT / "scripts" / "field-test" / "build-bundle.py"
MIRROR = REPO_ROOT / ".claude" / "scripts" / "field-test" / "build-bundle.py"


def test_builder_exists():
    assert BUILDER.is_file()


def test_mirror_byte_identity():
    assert BUILDER.read_bytes() == MIRROR.read_bytes()


def _seed(session_dir: Path) -> None:
    session_dir.mkdir(parents=True)
    (session_dir / "session.json").write_text(json.dumps({
        "version": "1", "sid": "ft-test", "phase": None, "preset": "standard",
        "base_url": "http://localhost:3000",
        "ts_started": "2026-05-11T10:00:00Z",
        "ts_stopped": "2026-05-11T10:05:00Z",
        "sources": [{"type": "file", "target": "/var/log/api.log", "label": "api", "pid": None}],
        "redaction": "password|token|secret"
    }), encoding="utf-8")
    (session_dir / "marks.raw.jsonl").write_text(
        json.dumps({
            "n": 0, "ts": "2026-05-11T10:02:00Z",
            "url": "http://localhost:3000/orders/42",
            "referrer": "http://localhost:3000/orders",
            "nav_chain": [],
            "user_note": "save button no response. token=abc123",
            "viewport": {"w": 1440, "h": 900, "dpr": 2},
            "click_target": {"selector": "button.save-btn", "text": "Save"}
        }) + "\n",
        encoding="utf-8",
    )
    (session_dir / "console.raw.jsonl").write_text(
        "\n".join([
            json.dumps({"ts": "2026-05-11T10:01:59Z", "level": "error", "text": "TypeError: cannot read undefined"}),
            json.dumps({"ts": "2026-05-11T10:02:01Z", "level": "warn", "text": "slow op (8s)"}),
            json.dumps({"ts": "2026-05-11T10:04:00Z", "level": "info", "text": "outside window"}),
        ]) + "\n",
        encoding="utf-8",
    )
    (session_dir / "network.raw.jsonl").write_text(
        json.dumps({
            "ts": "2026-05-11T10:02:00.412Z", "method": "POST",
            "url": "/api/orders/42", "status": 500, "duration_ms": 8420
        }) + "\n",
        encoding="utf-8",
    )
    (session_dir / "api-1.log").write_text(
        "2026-05-11T10:01:58.500Z api: incoming POST /orders/42\n"
        "2026-05-11T10:02:00.300Z api: ERROR upstream timeout (db) token=abc123\n"
        "2026-05-11T10:10:00.000Z api: unrelated later line\n",
        encoding="utf-8",
    )


def test_build_bundle_correlates_mark_window(tmp_path):
    session_dir = tmp_path / "ft-test"
    _seed(session_dir)
    r = subprocess.run(
        [sys.executable, str(BUILDER), "--session-dir", str(session_dir),
         "--mark-window-sec", "30"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, f"builder exited {r.returncode}\n{r.stdout}\n{r.stderr}"
    marks = (session_dir / "marks.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(marks) == 1
    bundle = json.loads(marks[0])
    # Console window: only entries within ±30s of ts=10:02:00
    levels = {e["level"] for e in bundle["console_window"]}
    assert "error" in levels and "warn" in levels
    assert all("outside window" not in e["text"] for e in bundle["console_window"])
    # Network window: 500 captured
    assert any(req["status"] == 500 for req in bundle["network_window"])
    # API log window: ERROR + incoming POST in, unrelated later out
    api = bundle["api_log_correlated"]["api"]
    assert any("ERROR upstream" in line for line in api)
    assert any("incoming POST" in line for line in api)
    assert all("unrelated later" not in line for line in api)


def test_redaction_applied_to_logs_and_note(tmp_path):
    session_dir = tmp_path / "ft-test"
    _seed(session_dir)
    subprocess.run(
        [sys.executable, str(BUILDER), "--session-dir", str(session_dir),
         "--mark-window-sec", "30"],
        check=True,
    )
    text = (session_dir / "marks.jsonl").read_text(encoding="utf-8")
    assert "abc123" not in text, "token value should have been redacted"
    assert "[REDACTED]" in text, "redaction sentinel should appear"


def test_manifest_written(tmp_path):
    session_dir = tmp_path / "ft-test"
    _seed(session_dir)
    subprocess.run(
        [sys.executable, str(BUILDER), "--session-dir", str(session_dir),
         "--mark-window-sec", "30"],
        check=True,
    )
    manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sid"] == "ft-test"
    assert manifest["mark_count"] == 1
    assert "redaction_applied" in manifest
    assert "ts_built" in manifest
```

**Step 2: Run test — expect FAIL** (script missing).

**Step 3: Write `scripts/field-test/build-bundle.py`**

```python
#!/usr/bin/env python3
"""build-bundle.py — Stop-time bundle assembler for /vg:field-test.

Reads .vg/field-test/<sid>/{session.json, marks.raw.jsonl, console.raw.jsonl,
network.raw.jsonl, clicks.raw.jsonl, nav.raw.jsonl, api-*.log}.

Per Mark: collect ±mark_window_sec windows from each stream, apply redaction
regex, write bundle to marks.jsonl + manifest.json.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path


def parse_ts(s: str) -> _dt.datetime | None:
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def parse_api_log_line(line: str) -> tuple[_dt.datetime | None, str]:
    # Lines emitted by tail-source.sh: "<ISO>Z <rest>"
    parts = line.split(" ", 1)
    if not parts:
        return None, line
    ts = parse_ts(parts[0])
    rest = parts[1] if len(parts) > 1 else ""
    return ts, rest


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def window(items: list[dict], center: _dt.datetime, sec: int, ts_key: str = "ts") -> list[dict]:
    lo = center - _dt.timedelta(seconds=sec)
    hi = center + _dt.timedelta(seconds=sec)
    out = []
    for it in items:
        t = parse_ts(it.get(ts_key, ""))
        if t and lo <= t <= hi:
            out.append(it)
    return out


def api_window(api_path: Path, center: _dt.datetime, sec: int) -> list[str]:
    if not api_path.is_file():
        return []
    lo = center - _dt.timedelta(seconds=sec)
    hi = center + _dt.timedelta(seconds=sec)
    out = []
    for line in api_path.read_text(encoding="utf-8", errors="replace").splitlines():
        ts, rest = parse_api_log_line(line)
        if ts and lo <= ts <= hi:
            out.append(line)
    return out


def redact(value: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub(lambda m: "[REDACTED]", value)


def redact_obj(obj, pattern: re.Pattern[str]):
    if isinstance(obj, str):
        return redact(obj, pattern)
    if isinstance(obj, list):
        return [redact_obj(x, pattern) for x in obj]
    if isinstance(obj, dict):
        return {k: redact_obj(v, pattern) for k, v in obj.items()}
    return obj


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session-dir", required=True)
    ap.add_argument("--mark-window-sec", type=int, default=30)
    args = ap.parse_args()

    session_dir = Path(args.session_dir).resolve()
    if not session_dir.is_dir():
        print(f"session dir not found: {session_dir}", file=sys.stderr)
        return 2

    session = json.loads((session_dir / "session.json").read_text(encoding="utf-8"))
    pattern_src = session.get("redaction") or "password|token|secret"
    try:
        # value-pair pattern: redact `<key>=<value>` style + bare key values
        pat = re.compile(
            r"(?i)(" + pattern_src + r")\s*[:=]\s*\S+|(" + pattern_src + r")(['\"]\s*:\s*['\"][^'\"]+['\"])?"
        )
    except re.error:
        pat = re.compile(r"(?i)password|token|secret")

    marks_raw = load_jsonl(session_dir / "marks.raw.jsonl")
    console = load_jsonl(session_dir / "console.raw.jsonl")
    network = load_jsonl(session_dir / "network.raw.jsonl")
    clicks = load_jsonl(session_dir / "clicks.raw.jsonl")
    nav = load_jsonl(session_dir / "nav.raw.jsonl")
    api_logs = sorted(session_dir.glob("api-*.log"))

    out_marks = session_dir / "marks.jsonl"
    with out_marks.open("w", encoding="utf-8") as fh:
        for mark in marks_raw:
            center = parse_ts(mark.get("ts", ""))
            if center is None:
                continue
            mark = redact_obj(mark, pat)
            mark["console_window"] = redact_obj(window(console, center, args.mark_window_sec), pat)
            mark["network_window"] = redact_obj(window(network, center, args.mark_window_sec), pat)
            mark["click_window"] = redact_obj(window(clicks, center, args.mark_window_sec), pat)
            mark["nav_window"] = redact_obj(window(nav, center, args.mark_window_sec), pat)
            api_corr: dict[str, list[str]] = {}
            for ap_path in api_logs:
                label = ap_path.stem.replace("api-", "", 1)
                lines = api_window(ap_path, center, args.mark_window_sec)
                api_corr[label] = [redact(l, pat) for l in lines]
            mark["api_log_correlated"] = api_corr
            fh.write(json.dumps(mark, ensure_ascii=False) + "\n")

    manifest = {
        "sid": session.get("sid"),
        "phase": session.get("phase"),
        "ts_started": session.get("ts_started"),
        "ts_stopped": session.get("ts_stopped"),
        "ts_built": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mark_count": len(marks_raw),
        "redaction_applied": pattern_src,
        "sources": session.get("sources"),
        "preset": session.get("preset"),
    }
    (session_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"✓ bundle built: {out_marks} ({len(marks_raw)} marks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Mirror + tests**

```bash
cp scripts/field-test/build-bundle.py .claude/scripts/field-test/build-bundle.py
python -m pytest tests/test_field_test_build_bundle.py -v
```
Expected: 5 PASS.

**Step 5: Commit**

```bash
git add scripts/field-test/build-bundle.py .claude/scripts/field-test/build-bundle.py tests/test_field_test_build_bundle.py
git commit -m "feat(field-test): build-bundle.py Stop-time correlator + redactor

Reads raw streams (marks.raw.jsonl, console.raw.jsonl, network.raw.jsonl,
clicks.raw.jsonl, nav.raw.jsonl, api-*.log), for each Mark collects
±mark_window_sec windows by wall-clock, applies redaction regex to all
string values, writes marks.jsonl + manifest.json.

Redaction sentinel '[REDACTED]' replaces matched key=value pairs across
console / network / api log / user_note / clicks. Pattern compiled from
session.redaction (default 'password|token|secret|api_key|email|phone'
defined in vg.config field_test.default_redaction).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Analyzer subagent + KNOWN-ISSUES integration (deterministic core)

**Files:**
- Create: `agents/vg-field-test-analyzer/SKILL.md`
- Create: `.claude/agents/vg-field-test-analyzer/SKILL.md` (mirror)
- Create: `scripts/field-test/analyze.py` (deterministic logic; subagent wraps it + LLM narrative)
- Create: `.claude/scripts/field-test/analyze.py`
- Test: `tests/test_field_test_analyze.py`

**Step 1: Write failing test**

```python
"""tests/test_field_test_analyze.py — deterministic analyzer logic."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYZER = REPO_ROOT / "scripts" / "field-test" / "analyze.py"
SUBAGENT = REPO_ROOT / "agents" / "vg-field-test-analyzer" / "SKILL.md"


def _seed_session(tmp_path: Path) -> Path:
    sid_dir = tmp_path / "ft-test"
    sid_dir.mkdir()
    (sid_dir / "manifest.json").write_text(json.dumps({
        "sid": "ft-test", "phase": None, "preset": "standard",
        "ts_started": "2026-05-11T10:00:00Z", "ts_stopped": "2026-05-11T10:05:00Z",
        "ts_built": "2026-05-11T10:05:30Z",
        "mark_count": 3, "redaction_applied": "password|token",
        "sources": [],
    }), encoding="utf-8")
    marks = [
        {  # HIGH — 500 in window + unhandled exception
            "n": 0, "ts": "2026-05-11T10:01:00Z", "url": "http://x/orders/42",
            "user_note": "save broke", "referrer": "", "nav_chain": [],
            "viewport": {"w": 1440, "h": 900, "dpr": 2}, "click_target": {"selector": "button.save", "text": "Save"},
            "console_window": [{"ts": "...", "level": "error", "text": "TypeError: undefined"}],
            "network_window": [{"ts": "...", "method": "POST", "url": "/api/orders/42", "status": 500, "duration_ms": 8000}],
            "api_log_correlated": {"api": ["2026-05-11T10:01:00Z api: ERROR db timeout"]},
        },
        {  # MEDIUM — 400 in window
            "n": 1, "ts": "2026-05-11T10:02:00Z", "url": "http://x/users", "user_note": "invalid form",
            "referrer": "", "nav_chain": [],
            "viewport": {"w": 1440, "h": 900, "dpr": 2}, "click_target": None,
            "console_window": [],
            "network_window": [{"ts": "...", "method": "POST", "url": "/api/users", "status": 400, "duration_ms": 200}],
            "api_log_correlated": {},
        },
        {  # LOW — visual only, no errors
            "n": 2, "ts": "2026-05-11T10:03:00Z", "url": "http://x/dashboard", "user_note": "header looks faded",
            "referrer": "", "nav_chain": [],
            "viewport": {"w": 1440, "h": 900, "dpr": 2}, "click_target": None,
            "console_window": [], "network_window": [], "api_log_correlated": {},
        },
    ]
    with (sid_dir / "marks.jsonl").open("w", encoding="utf-8") as fh:
        for m in marks:
            fh.write(json.dumps(m) + "\n")
    return sid_dir


def test_severity_heuristic(tmp_path):
    sid_dir = _seed_session(tmp_path)
    known = tmp_path / "KNOWN-ISSUES.json"
    r = subprocess.run(
        [sys.executable, str(ANALYZER), "--session-dir", str(sid_dir),
         "--known-issues", str(known)],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(known.read_text(encoding="utf-8"))
    assert "issues" in payload
    by_n = {i["mark_n"]: i for i in payload["issues"] if i["sid"] == "ft-test"}
    assert by_n[0]["severity"] == "HIGH"
    assert by_n[1]["severity"] == "MEDIUM"
    assert by_n[2]["severity"] == "LOW"


def test_field_report_written(tmp_path):
    sid_dir = _seed_session(tmp_path)
    known = tmp_path / "KNOWN-ISSUES.json"
    subprocess.run(
        [sys.executable, str(ANALYZER), "--session-dir", str(sid_dir),
         "--known-issues", str(known)],
        check=True,
    )
    report = sid_dir / "FIELD-REPORT.md"
    assert report.is_file()
    body = report.read_text(encoding="utf-8")
    assert "ft-test" in body
    assert "HIGH" in body
    assert "save broke" in body
    assert "/orders/42" in body


def test_known_issues_idempotent_append(tmp_path):
    """Re-running analyzer on the same session must not duplicate entries."""
    sid_dir = _seed_session(tmp_path)
    known = tmp_path / "KNOWN-ISSUES.json"
    subprocess.run(
        [sys.executable, str(ANALYZER), "--session-dir", str(sid_dir),
         "--known-issues", str(known)],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(ANALYZER), "--session-dir", str(sid_dir),
         "--known-issues", str(known)],
        check=True,
    )
    payload = json.loads(known.read_text(encoding="utf-8"))
    sids_seen = [i for i in payload["issues"] if i["sid"] == "ft-test"]
    assert len(sids_seen) == 3, f"expected 3 entries (not 6), got {len(sids_seen)}"


def test_subagent_md_exists():
    assert SUBAGENT.is_file()
    body = SUBAGENT.read_text(encoding="utf-8")
    assert "field-test" in body.lower()
    assert "FIELD-REPORT.md" in body
    assert "KNOWN-ISSUES.json" in body
```

**Step 2: Run — expect FAIL.**

**Step 3: Write `scripts/field-test/analyze.py`**

```python
#!/usr/bin/env python3
"""analyze.py — deterministic analyzer for /vg:field-test bundles.

Heuristics (severity per Mark):
  HIGH   = network 5xx in window OR console error containing 'TypeError'/'Uncaught'
  MEDIUM = network 4xx in window OR console error any other
  LOW    = no errors anywhere; user_note only

Appends to KNOWN-ISSUES.json with idempotent dedupe key (sid + mark_n).
Writes FIELD-REPORT.md to <session_dir>.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path


SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"


def classify(mark: dict) -> str:
    net = mark.get("network_window") or []
    for req in net:
        s = req.get("status", 0)
        try:
            s = int(s)
        except (TypeError, ValueError):
            s = 0
        if 500 <= s < 600:
            return SEVERITY_HIGH
    console = mark.get("console_window") or []
    for entry in console:
        text = entry.get("text", "")
        if entry.get("level") == "error" and re.search(r"Uncaught|TypeError|ReferenceError", text):
            return SEVERITY_HIGH
    for req in net:
        try:
            s = int(req.get("status", 0))
        except (TypeError, ValueError):
            s = 0
        if 400 <= s < 500:
            return SEVERITY_MEDIUM
    for entry in console:
        if entry.get("level") == "error":
            return SEVERITY_MEDIUM
    return SEVERITY_LOW


def render_report(sid: str, manifest: dict, marks: list[dict]) -> str:
    lines: list[str] = []
    lines.append(f"# Field Test Report — {sid}")
    lines.append("")
    lines.append(f"- Preset: {manifest.get('preset')}")
    lines.append(f"- Started: {manifest.get('ts_started')}")
    lines.append(f"- Stopped: {manifest.get('ts_stopped')}")
    lines.append(f"- Mark count: {manifest.get('mark_count')}")
    lines.append(f"- Redaction applied: {manifest.get('redaction_applied')}")
    if manifest.get("phase"):
        lines.append(f"- Phase: {manifest['phase']}")
    lines.append("")
    lines.append("## Marks")
    lines.append("")
    for m in marks:
        sev = classify(m)
        lines.append(f"### Mark {m.get('n')} — {sev}")
        lines.append("")
        lines.append(f"- ts: `{m.get('ts')}`")
        lines.append(f"- url: `{m.get('url')}`")
        lines.append(f"- note: {m.get('user_note', '').strip() or '(none)'}")
        net = m.get("network_window") or []
        if net:
            lines.append("- network:")
            for req in net[:5]:
                lines.append(
                    f"  - {req.get('method')} {req.get('url')} → "
                    f"{req.get('status')} ({req.get('duration_ms')}ms)"
                )
        console = m.get("console_window") or []
        if console:
            lines.append("- console:")
            for entry in console[:5]:
                lines.append(f"  - {entry.get('level')}: {entry.get('text', '')[:160]}")
        api = m.get("api_log_correlated") or {}
        if any(api.values()):
            lines.append("- api log excerpts:")
            for label, src_lines in api.items():
                for ln in src_lines[:3]:
                    lines.append(f"  - [{label}] {ln[:200]}")
        lines.append("")
    return "\n".join(lines) + "\n"


def load_manifest(session_dir: Path) -> dict:
    mp = session_dir / "manifest.json"
    if not mp.is_file():
        raise FileNotFoundError(f"manifest.json missing: {mp}")
    return json.loads(mp.read_text(encoding="utf-8"))


def load_marks(session_dir: Path) -> list[dict]:
    p = session_dir / "marks.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_known_issues(known_path: Path, sid: str, phase: str | None, marks: list[dict]) -> None:
    if known_path.is_file():
        try:
            payload = json.loads(known_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {"version": "1", "issues": []}
    else:
        payload = {"version": "1", "issues": []}
    payload.setdefault("issues", [])
    seen = {(i.get("sid"), i.get("mark_n")) for i in payload["issues"]}
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    added = 0
    for m in marks:
        key = (sid, m.get("n"))
        if key in seen:
            continue
        payload["issues"].append({
            "id": f"KI-{sid}-{m.get('n'):03d}",
            "ts": now,
            "sid": sid,
            "mark_n": m.get("n"),
            "phase": phase,
            "severity": classify(m),
            "url": m.get("url"),
            "note": m.get("user_note"),
            "evidence_paths": [
                f".vg/field-test/{sid}/marks.jsonl",
                f".vg/field-test/{sid}/FIELD-REPORT.md",
            ],
            "source": "vg:field-test",
        })
        added += 1
    known_path.parent.mkdir(parents=True, exist_ok=True)
    known_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"KNOWN-ISSUES: appended {added} (total {len(payload['issues'])})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session-dir", required=True)
    ap.add_argument("--known-issues", default=None,
                    help="Path to KNOWN-ISSUES.json (default <session-dir>/../KNOWN-ISSUES.json)")
    args = ap.parse_args()

    session_dir = Path(args.session_dir).resolve()
    if not session_dir.is_dir():
        print(f"session dir not found: {session_dir}", file=sys.stderr)
        return 2

    manifest = load_manifest(session_dir)
    sid = manifest.get("sid", session_dir.name)
    phase = manifest.get("phase")
    marks = load_marks(session_dir)

    report_md = render_report(sid, manifest, marks)
    (session_dir / "FIELD-REPORT.md").write_text(report_md, encoding="utf-8")

    known_path = Path(args.known_issues) if args.known_issues else (session_dir.parent.parent / "KNOWN-ISSUES.json")
    append_known_issues(known_path, sid, phase, marks)
    print(f"✓ FIELD-REPORT.md written ({len(marks)} marks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Write `agents/vg-field-test-analyzer/SKILL.md`**

```markdown
---
name: vg-field-test-analyzer
description: Analyzes a /vg:field-test session bundle. Runs deterministic severity heuristics via scripts/field-test/analyze.py, writes FIELD-REPORT.md + appends KNOWN-ISSUES.json. Optional LLM narrative on top of the deterministic skeleton.
model: sonnet
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
---

# vg-field-test-analyzer

## Inputs

You receive a `session_dir` path (e.g. `.vg/field-test/ft-2026-05-11T10:00:00Z/`).

## Process

1. Run the deterministic analyzer:
   ```
   python3 scripts/field-test/analyze.py --session-dir <session_dir>
   ```
   This writes `FIELD-REPORT.md` + appends `.vg/KNOWN-ISSUES.json`.

2. Read the resulting `FIELD-REPORT.md`. For each Mark with severity HIGH or MEDIUM, augment the markdown with a 1-2 sentence diagnosis under a `**Diagnosis:**` line. Suggest 1-2 suspect files (grep symbols from console errors + URL routes against the repo). Do not modify the LOW Mark sections.

3. Return: path to FIELD-REPORT.md, count of issues appended, severity breakdown.

## Hard rules

- Do NOT rewrite the deterministic severity classification. Only add narrative.
- Do NOT touch KNOWN-ISSUES.json directly (analyze.py is the sole writer).
- Do NOT speculate on root cause when console + network + API log are all empty in the window. Leave the Diagnosis line as `(no signals beyond user_note)`.
```

**Step 5: Mirror + tests**

```bash
mkdir -p .claude/agents/vg-field-test-analyzer
cp agents/vg-field-test-analyzer/SKILL.md .claude/agents/vg-field-test-analyzer/SKILL.md
cp scripts/field-test/analyze.py .claude/scripts/field-test/analyze.py
python -m pytest tests/test_field_test_analyze.py -v
```
Expected: 4 PASS.

**Step 6: Commit**

```bash
git add scripts/field-test/analyze.py .claude/scripts/field-test/analyze.py \
        agents/vg-field-test-analyzer/SKILL.md .claude/agents/vg-field-test-analyzer/SKILL.md \
        tests/test_field_test_analyze.py
git commit -m "feat(field-test): deterministic analyzer + analyzer subagent shell

scripts/field-test/analyze.py is the deterministic core: classify per Mark
(HIGH = 5xx | uncaught exception, MEDIUM = 4xx | other console error,
LOW = visual/note only), render FIELD-REPORT.md, idempotent-append to
KNOWN-ISSUES.json keyed by (sid, mark_n).

vg-field-test-analyzer subagent (agents/vg-field-test-analyzer/SKILL.md)
wraps the deterministic step then augments HIGH/MEDIUM Marks with 1-2
sentence diagnosis + suspect file grep — narrative only, never rewrites
severity or KNOWN-ISSUES.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: MARKER_TO_AUTO_EVENT extension

**Files:**
- Modify: `scripts/vg-orchestrator/__main__.py` (extend `MARKER_TO_AUTO_EVENT` dict added in v3.6.0)
- Modify: `.claude/scripts/vg-orchestrator/__main__.py` (mirror)
- Modify: `scripts/vg-orchestrator-telemetry-repair.py` (extend `MARKER_TO_EVENT` to match)
- Modify: `.claude/scripts/vg-orchestrator-telemetry-repair.py` (mirror)
- Test: `tests/test_field_test_marker_to_auto_event.py`

**Step 1: Write failing test**

```python
"""tests/test_field_test_marker_to_auto_event.py — auto-emit covers field-test."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ORCH = REPO_ROOT / "scripts" / "vg-orchestrator" / "__main__.py"
REPAIR = REPO_ROOT / "scripts" / "vg-orchestrator-telemetry-repair.py"


def test_marker_to_auto_event_field_test():
    body = ORCH.read_text(encoding="utf-8")
    assert '("field-test", "complete"): ("field_test.session_completed"' in body, (
        "MARKER_TO_AUTO_EVENT must include ('field-test','complete') → field_test.session_completed"
    )


def test_repair_script_field_test():
    body = REPAIR.read_text(encoding="utf-8")
    assert '("field-test", "complete"): "field_test.session_completed"' in body
```

**Step 2: Run — expect FAIL.**

**Step 3: Modify `scripts/vg-orchestrator/__main__.py`**

Find `MARKER_TO_AUTO_EVENT` dict (added in v3.6.0). Append entry:

```python
    # v3.7.0 (#new-feature) — /vg:field-test user-driven roam capture
    ("field-test", "complete"): ("field_test.session_completed", "INFO"),
```

**Step 4: Modify `scripts/vg-orchestrator-telemetry-repair.py`**

Find `MARKER_TO_EVENT` dict. Append:

```python
    ("field-test", "complete"): "field_test.session_completed",
```

**Step 5: Mirror + tests**

```bash
cp scripts/vg-orchestrator/__main__.py .claude/scripts/vg-orchestrator/__main__.py
cp scripts/vg-orchestrator-telemetry-repair.py .claude/scripts/vg-orchestrator-telemetry-repair.py
python -m pytest tests/test_field_test_marker_to_auto_event.py tests/test_v3_6_codex_telemetry_parity.py -v
```
Expected: PASS, no regression on existing telemetry parity tests.

**Step 6: Commit**

```bash
git add scripts/vg-orchestrator/__main__.py .claude/scripts/vg-orchestrator/__main__.py \
        scripts/vg-orchestrator-telemetry-repair.py .claude/scripts/vg-orchestrator-telemetry-repair.py \
        tests/test_field_test_marker_to_auto_event.py
git commit -m "feat(field-test): wire MARKER_TO_AUTO_EVENT for /vg:field-test

Adds ('field-test','complete') → 'field_test.session_completed' to the
v3.6.0 auto-emit mapping + repair script. Codex adapters get the
lifecycle event for free without needing to remember explicit
emit-event calls.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Skill entry `commands/vg/field-test.md`

**Files:**
- Create: `commands/vg/field-test.md`
- Create: `.claude/commands/vg/field-test.md` (mirror)
- Test: `tests/test_field_test_skill_structure.py`

**Step 1: Write failing test**

```python
"""tests/test_field_test_skill_structure.py — skill md frontmatter + sections."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_CANON = REPO_ROOT / "commands" / "vg" / "field-test.md"
SKILL_MIRROR = REPO_ROOT / ".claude" / "commands" / "vg" / "field-test.md"


def _frontmatter(p: Path) -> dict:
    yaml = pytest.importorskip("yaml")
    body = p.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", body, re.S)
    assert m, "frontmatter missing"
    return yaml.safe_load(m.group(1))


def test_skill_exists_and_parses():
    assert SKILL_CANON.is_file()
    fm = _frontmatter(SKILL_CANON)
    assert fm["name"] == "vg:field-test"
    assert "description" in fm


def test_allowed_tools_includes_playwright():
    fm = _frontmatter(SKILL_CANON)
    tools = fm.get("allowed-tools") or []
    for t in [
        "mcp__playwright1__browser_navigate",
        "mcp__playwright1__browser_evaluate",
        "mcp__playwright1__browser_console_messages",
        "mcp__playwright1__browser_take_screenshot",
        "mcp__playwright1__browser_snapshot",
    ]:
        assert t in tools, f"allowed-tools must include {t}"
    for t in ["Bash", "Read", "Write", "Edit", "Agent", "AskUserQuestion", "TodoWrite"]:
        assert t in tools


def test_runtime_contract_markers():
    fm = _frontmatter(SKILL_CANON)
    rc = fm.get("runtime_contract") or {}
    markers = [m if isinstance(m, str) else m["name"] for m in rc.get("must_touch_markers", [])]
    expected = [
        "0_preflight", "1_resolve_config", "2_launch_browser", "3_inject_overlay",
        "4_wait_start", "5_capture_loop", "6_stop_finalize", "7_analyze", "complete",
    ]
    for e in expected:
        assert e in markers, f"runtime_contract.must_touch_markers missing {e}"


def test_runtime_contract_telemetry():
    fm = _frontmatter(SKILL_CANON)
    rc = fm.get("runtime_contract") or {}
    events = [e["event_type"] for e in (rc.get("must_emit_telemetry") or [])]
    for ev in [
        "field_test.session_started",
        "field_test.session_stopped",
        "field_test.analysis_completed",
    ]:
        assert ev in events


def test_mirror_byte_identity():
    assert SKILL_CANON.read_bytes() == SKILL_MIRROR.read_bytes()


def test_skill_body_references_overlay_and_analyze():
    body = SKILL_CANON.read_text(encoding="utf-8")
    assert "scripts/field-test/overlay.js" in body
    assert "scripts/field-test/build-bundle.py" in body
    assert "scripts/field-test/analyze.py" in body
    assert "scripts/field-test/tail-source.sh" in body
```

**Step 2: Run — expect FAIL.**

**Step 3: Create `commands/vg/field-test.md`** (slim entry; refs into `_shared/field-test/*.md` would be the v2 split — for v1 keep inline)

```markdown
---
name: vg:field-test
description: User-driven field-test capture. Opens MCP playwright browser with floating Start/Stop/Mark overlay; user manually roams while AI passively captures browser console + network + clicks + nav chain + per-Mark notes + correlated API server log tails. On Stop, runs deterministic analyzer + LLM-augmented narrative subagent, writes FIELD-REPORT.md and appends KNOWN-ISSUES.json. Distinct from /vg:roam (which is AI-auto).
argument-hint: "[--phase=N] [--preset=quick|standard|deep] [--redact=<regex>] [--base-url=<url>] [--non-interactive] [--resume=<sid>]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
  - TodoWrite
  - mcp__playwright1__browser_navigate
  - mcp__playwright1__browser_evaluate
  - mcp__playwright1__browser_console_messages
  - mcp__playwright1__browser_network_requests
  - mcp__playwright1__browser_snapshot
  - mcp__playwright1__browser_take_screenshot
  - mcp__playwright1__browser_click
  - mcp__playwright1__browser_type
  - mcp__playwright1__browser_close
runtime_contract:
  must_write:
    - "${SESSION_DIR}/session.json"
    - "${SESSION_DIR}/marks.jsonl"
    - "${SESSION_DIR}/manifest.json"
    - "${SESSION_DIR}/FIELD-REPORT.md"
  must_touch_markers:
    - "0_preflight"
    - "1_resolve_config"
    - "2_launch_browser"
    - "3_inject_overlay"
    - "4_wait_start"
    - "5_capture_loop"
    - "6_stop_finalize"
    - "7_analyze"
    - "complete"
  must_emit_telemetry:
    - event_type: "field_test.session_started"
    - event_type: "field_test.session_stopped"
    - event_type: "field_test.analysis_completed"
  forbidden_without_override:
    - "--non-interactive"
---

<HARD-GATE>
This skill captures live user behavior. Default redaction regex MUST be applied
to all log streams + user_note + form values. Per-session redaction declared in
session.json `redaction` field; build-bundle.py is sole enforcer.

Default behaviour is interactive. `--non-interactive` requires
`--override-reason=<text>` per VGFlow convention.

Only ONE active session per project. `.vg/field-test/.active` lock file gates
concurrent invocations.
</HARD-GATE>

## Steps

### STEP 0 — preflight (`0_preflight`)

```bash
set -e
"${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator step-active 0_preflight >/dev/null 2>&1 || true

REPO_ROOT="${REPO_ROOT:-$(pwd)}"
LOCK="${REPO_ROOT}/.vg/field-test/.active"
if [ -f "$LOCK" ] && [[ ! "$ARGUMENTS" =~ --resume ]]; then
  echo "⛔ field-test session already active: $(cat "$LOCK")"
  echo "   Pass --resume=$(cat "$LOCK") to continue, or remove the lock manually."
  exit 1
fi

# Verify playwright1 MCP available (best-effort check via settings.json grep)
if ! grep -q '"playwright1"' .claude/settings.json 2>/dev/null && \
   ! grep -q '"playwright1"' ~/.claude/settings.json 2>/dev/null; then
  echo "⛔ MCP playwright1 not configured. Run:"
  echo "   python3 .claude/scripts/validators/verify-playwright-mcp-config.py --repair"
  exit 1
fi

"${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator mark-step field-test 0_preflight
```

### STEP 1 — resolve config (`1_resolve_config`)

Read `field_test` block from `vg.config.md`. If missing → AskUserQuestion to configure inline OR skip API tail.

Resolve `base_url` from (in order): `--base-url=<url>` flag → `ENV-CONTRACT.md target.base_url` → `field_test.default_base_url` → AskUserQuestion fallback.

Compute `SID`:
```bash
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ | tr ':' '-')
if [[ "$ARGUMENTS" =~ --phase=([A-Za-z0-9_.-]+) ]]; then
  PHASE="${BASH_REMATCH[1]}"
  SID="ft-p${PHASE}-${TS}"
else
  PHASE=""
  SID="ft-${TS}"
fi
SESSION_DIR="${REPO_ROOT}/.vg/field-test/${SID}"
mkdir -p "$SESSION_DIR"
echo "$SID" > "${REPO_ROOT}/.vg/field-test/.active"
```

Write `session.json` (validates against `schemas/field-test-session.v1.json`).
Mark step.

### STEP 2 — launch browser (`2_launch_browser`)

Invoke `mcp__playwright1__browser_navigate` with the resolved `base_url`.
Mark step.

### STEP 3 — inject overlay (`3_inject_overlay`)

```bash
OVERLAY_JS=$(cat .claude/scripts/field-test/overlay.js)
```

Invoke `mcp__playwright1__browser_evaluate({ function: <wrap OVERLAY_JS in arrow fn> })`.
Verify by `browser_evaluate(() => typeof window.__VG_FT_INIT === 'function')`.
Mark step.

### STEP 4 — wait for Start (`4_wait_start`)

Poll `mcp__playwright1__browser_console_messages` every 2s for `[VG_FT] start`. On hit:

```bash
# Spawn one tail-source process per session.sources[]
"${PYTHON_BIN:-python3}" - <<'PY'
import json, os, subprocess
from pathlib import Path
sess = json.loads(Path(os.environ['SESSION_DIR'] + '/session.json').read_text())
pids = []
for i, src in enumerate(sess.get('sources', []), start=1):
    out = Path(os.environ['SESSION_DIR']) / f"api-{src['label']}.log"
    proc = subprocess.Popen(
        ['bash', '.claude/scripts/field-test/tail-source.sh',
         '--type', src['type'], '--target', src['target'], '--out', str(out)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    src['pid'] = proc.pid
    pids.append(proc.pid)
Path(os.environ['SESSION_DIR'] + '/session.json').write_text(json.dumps(sess, indent=2))
PY

"${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event \
  "field_test.session_started" --payload "{\"sid\":\"$SID\",\"phase\":\"$PHASE\"}"
```
Mark step.

### STEP 5 — capture loop (`5_capture_loop`)

Polling loop (2s base, throttle to 5s if iteration >1.5s, hard cap `max_session_hours`):

For each `[VG_FT] mark <json>` console message:
1. Parse json from console message text.
2. `browser_evaluate(() => window.__VG_FT_STATE.marks[<n>])` to fetch full bundle (overlay state has more than console echo).
3. `browser_take_screenshot --filename marks/<n>.png` (save under `$SESSION_DIR`).
4. `browser_snapshot --filename marks/<n>.snapshot.yml`.
5. Append raw entry to `marks.raw.jsonl`.
6. Append recent `browser_console_messages` + `browser_network_requests` to `console.raw.jsonl` + `network.raw.jsonl`.
7. Emit `field_test.mark_recorded`.

For `[VG_FT] stop` → break.
For `[VG_FT] heartbeat` → ignore (overlay may emit every 30s).

Mark step.

### STEP 6 — stop + finalize (`6_stop_finalize`)

```bash
# Kill tail PIDs
"${PYTHON_BIN:-python3}" - <<'PY'
import json, os, signal
from pathlib import Path
sess = json.loads(Path(os.environ['SESSION_DIR'] + '/session.json').read_text())
for src in sess.get('sources', []):
    if src.get('pid'):
        try:
            os.kill(src['pid'], signal.SIGTERM)
        except ProcessLookupError:
            pass
PY

# Dump remaining buffers from overlay state (console/network/clicks/nav) to raw.jsonl
# via browser_evaluate to read window.__VG_FT_STATE.buffer.*

# Run bundle builder
"${PYTHON_BIN:-python3}" .claude/scripts/field-test/build-bundle.py \
  --session-dir "$SESSION_DIR" --mark-window-sec "${MARK_WINDOW_SEC:-30}"

# Update session.json ts_stopped
"${PYTHON_BIN:-python3}" -c "
import json, datetime
from pathlib import Path
p = Path('$SESSION_DIR/session.json')
d = json.loads(p.read_text())
d['ts_stopped'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
p.write_text(json.dumps(d, indent=2))"

"${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event \
  "field_test.session_stopped" --payload "{\"sid\":\"$SID\"}"
```
Mark step.

### STEP 7 — analyze (`7_analyze`)

Spawn `vg-field-test-analyzer` subagent (see agents/vg-field-test-analyzer/SKILL.md).

```bash
bash scripts/vg-narrate-spawn.sh vg-field-test-analyzer spawning "analyze field-test session $SID"
# Then: Agent(subagent_type="vg-field-test-analyzer", prompt={"session_dir": "$SESSION_DIR"})
```

After subagent returns, mirror bundle to `dev-phases/$PHASE/field-test/$SID/` if `$PHASE` set.

```bash
"${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator emit-event \
  "field_test.analysis_completed" --payload "{\"sid\":\"$SID\"}"
```
Mark step.

### STEP 8 — complete

```bash
rm -f "${REPO_ROOT}/.vg/field-test/.active"
"${PYTHON_BIN:-python3}" .claude/scripts/vg-orchestrator mark-step field-test complete
# field_test.session_completed auto-emitted via MARKER_TO_AUTO_EVENT
```

Print summary banner with FIELD-REPORT.md path + KNOWN-ISSUES count + suggested next /vg:review --include-known-issues.
```

**Step 4: Mirror + test**

```bash
mkdir -p .claude/commands/vg
cp commands/vg/field-test.md .claude/commands/vg/field-test.md
python -m pytest tests/test_field_test_skill_structure.py -v
```
Expected: 6 PASS.

**Step 5: Commit**

```bash
git add commands/vg/field-test.md .claude/commands/vg/field-test.md \
        tests/test_field_test_skill_structure.py
git commit -m "feat(field-test): skill entry commands/vg/field-test.md (v1 inline)

Frontmatter declares 9 markers (0_preflight → complete), 3 telemetry
events (session_started, session_stopped, analysis_completed),
allowed-tools includes mcp__playwright1__* + Agent + AskUserQuestion +
TodoWrite. Body sequences 8 steps inline (no _shared split for v1).

Concurrency lock: .vg/field-test/.active gates concurrent invocations.
--resume=<sid> short-circuits the lock check.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Codex skill mirror via generator

**Files:**
- Modify: `scripts/generate-codex-skills.sh` (no source change needed if generator auto-discovers `commands/vg/*.md` — verify)
- Generate: `codex-skills/vg-field-test/SKILL.md`
- Test: `tests/test_field_test_codex_mirror.py`

**Step 1: Write failing test**

```python
"""tests/test_field_test_codex_mirror.py — codex-skills mirror exists + valid."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CODEX_SKILL = REPO_ROOT / "codex-skills" / "vg-field-test" / "SKILL.md"


def test_codex_skill_generated():
    assert CODEX_SKILL.is_file(), (
        "Run: bash scripts/generate-codex-skills.sh — codex mirror missing"
    )


def test_codex_skill_yaml_parses():
    yaml = pytest.importorskip("yaml")
    body = CODEX_SKILL.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", body, re.S)
    assert m
    fm = yaml.safe_load(m.group(1))
    assert fm["name"] == "vg-field-test"
    assert fm["description"]
```

**Step 2: Run — expect FAIL.**

**Step 3: Generate**

```bash
bash scripts/generate-codex-skills.sh
ls codex-skills/vg-field-test/
```

**Step 4: Re-run test → PASS.**

**Step 5: Commit**

```bash
git add codex-skills/vg-field-test/SKILL.md tests/test_field_test_codex_mirror.py
git commit -m "feat(field-test): codex skill mirror via generate-codex-skills.sh

Auto-generated by scripts/generate-codex-skills.sh from
commands/vg/field-test.md. Description scalar escapes any embedded
quotes per v3.6.1 generator hardening.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Final integration — release v3.7.0

**Files:**
- Modify: `VERSION` (3.6.4 → 3.7.0)
- Modify: `package.json` version field
- Modify: `CHANGELOG.md` (prepend v3.7.0 entry summarising tasks 1-8)
- Optional: `.gitignore` adds `.vg/field-test/` if not already covered by `.vg/` pattern

**Step 1: Verify `.gitignore`**

```bash
grep -E '^\.vg/|^\.vg/field-test' .gitignore
```
If `.vg/` already there, `.vg/field-test/` is covered. If not, append `.vg/field-test/`.

**Step 2: Bump VERSION + package.json**

```bash
echo "3.7.0" > VERSION
python -c "import json; p=open('package.json'); d=json.load(p); p.close(); d['version']='3.7.0'; open('package.json','w').write(json.dumps(d, indent=2))"
```

**Step 3: Write CHANGELOG entry**

Prepend to `CHANGELOG.md`:

```markdown
## v3.7.0 — /vg:field-test new skill (2026-05-11)

### Feature — user-driven field test capture

Adds `/vg:field-test` skill (distinct from AI-auto `/vg:roam`). Workflow:
1. AI opens MCP playwright1 browser at the resolved `base_url`.
2. AI injects vanilla overlay JS — floating top-right panel with
   Start/Stop/Mark buttons + per-Mark modal note textarea.
3. User clicks Start. AI begins polling browser console for `[VG_FT]`
   markers + spawns one tail process per configured API log source
   (`field_test.api_log_sources` in vg.config — supports type=file or
   type=command for docker/kubectl/pm2).
4. User roams the app, clicks Mark at each interesting view, types a
   note. AI captures full bundle per Mark (URL + nav chain + screenshot
   + DOM snapshot + ±30s console/network/api windows).
5. User clicks Stop. AI kills tails, runs build-bundle.py to apply
   redaction + correlate windows, spawns vg-field-test-analyzer subagent
   to produce FIELD-REPORT.md + append KNOWN-ISSUES.json.

### Architecture
- 8 new files under `scripts/field-test/` + `commands/vg/field-test.md`
  + `agents/vg-field-test-analyzer/` + `schemas/field-test-session.v1.json`.
- MARKER_TO_AUTO_EVENT extended: `('field-test','complete') →
  field_test.session_completed`.
- Concurrency lock at `.vg/field-test/.active` gates multiple sessions.
- Default redaction regex strips password/token/secret/api_key/email/phone.

### Test coverage
~25 new tests across 9 test files. Full design + plan committed under
`docs/plans/2026-05-11-field-test-capture-{design,plan}.md`.

### Compatibility
Phase-less default; optional `--phase=N` binds session to a phase.
Existing skills untouched. New skill is opt-in.
```

**Step 4: Final regression sweep**

```bash
python -m pytest tests/ -q --tb=no
```
Expect: prior baseline failure count (25 Windows-environmental); 0 new failures from this work.

**Step 5: Commit + tag + push**

```bash
git add VERSION package.json CHANGELOG.md
git commit -m "release: v3.7.0 — /vg:field-test new skill

User-driven field test capture distinct from /vg:roam (AI-auto).
8-component workflow: overlay JS, tail wrapper, bundle correlator,
deterministic analyzer + subagent narrative, marker auto-emit, codex
mirror. Full feature in tasks 1-8 of
docs/plans/2026-05-11-field-test-capture-plan.md.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

git push origin main
git tag v3.7.0
git push origin v3.7.0
```

**Step 6: Monitor CI**

```bash
gh run watch
```
Expect: green.

---

## Acceptance verification (post-merge, manual)

1. From a project with `field_test.api_log_sources` configured:
   ```
   /vg:field-test --phase=7 --preset=standard
   ```
2. Browser opens with overlay visible top-right. Click Start.
3. Roam 3-4 views. Click Mark on each. Type description. Submit.
4. Click Stop.
5. Confirm:
   - `.vg/field-test/ft-p7-*/FIELD-REPORT.md` exists with per-Mark sections
   - `.vg/KNOWN-ISSUES.json` has N new entries tagged with phase=7
   - `.vg/events.db` has session_started + N × mark_recorded + session_stopped + analysis_completed + session_completed events, hash-chained
   - `dev-phases/7/field-test/ft-p7-*/` mirror exists

Concurrent test:
6. In a second terminal, invoke `/vg:field-test` while the first is active → expect BLOCK with `--resume` hint.

Crash test:
7. Mid-session, manually close the playwright browser tab. AI should write `session.json.aborted=true` and still produce FIELD-REPORT.md from captured-so-far.

---

End of plan. **Tasks 1-9**, each commit individually. Estimated total: ~3-4 hours engineering wall-clock for a developer who already knows the codebase; ~6-8 hours for a fresh contributor using this plan verbatim.
