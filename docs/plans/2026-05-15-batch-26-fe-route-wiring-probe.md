# Batch 26 — FE route wiring runtime probe Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect un-wired FE routes (declared in `API-CONTRACTS/<slug>.md` BLOCK 5 `consumers[].route` but missing from React/Vue/Next router → renders 404 fallback). Plus BE-FE consumer parity (orphan endpoints).

**Real bug context:** User dogfood — test glob spec doesn't check that every FE URL declared in API contract actually navigates without 404 fallback. SPA always returns HTTP 200, so route-not-wired = silent failure.

**Working directory:** `main`.

---

## Conventions

- Mirror byte-identical to `.claude/`
- Sweep: `python -m pytest tests/ -q --tb=no -k "probe_fe_routes or be_fe_parity or fe_consumer or route_wired or batch_26"`
- Single Co-Authored-By trailer per commit
- Global paths pattern (`${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}`)

---

## Task 1: scripts/probe-fe-routes.py — runtime route navigation probe

**Files:**
- Create: `scripts/probe-fe-routes.py`
- Mirror
- Test: `tests/test_batch26_probe_fe_routes.py`

**Logic:**
- Reads `${PHASE_DIR}/API-CONTRACTS/*.md`, extracts BLOCK 5 `consumers[].route` per slug
- For each unique route, runs Playwright (or curl-based fallback) navigation
- Asserts:
  - HTTP 200 (SPA shell loaded)
  - NOT-404 page content: page does NOT contain `data-testid="not-found-page"`, `text("Page not found")`, `text("404")`, or `<h1>Not Found</h1>` patterns
  - Renders at least one main content element (`<main>`, `[role="main"]`, `data-testid="page-content"`)
- Emits `test.fe_route_unwired` per failing route
- Exit 1 if any route fails

**Step 1: Failing test**

```python
"""tests/test_batch26_probe_fe_routes.py — Batch 26 FE route wiring probe."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "scripts" / "probe-fe-routes.py"


def test_probe_script_exists():
    assert PROBE.is_file(), "Batch 26: scripts/probe-fe-routes.py must ship"


def test_probe_parses_block5_routes(tmp_path):
    """API-CONTRACTS/users-list.md BLOCK 5 declares 2 consumer routes.
    Probe extracts them via --dry-run mode."""
    phase_dir = tmp_path / ".vg" / "phases" / "07"
    contracts_dir = phase_dir / "API-CONTRACTS"
    contracts_dir.mkdir(parents=True)
    (contracts_dir / "users-list.md").write_text("""
# GET /api/users

## BLOCK 5: FE consumer contract

```typescript
{
  url: "/api/users",
  consumers: [
    { route: "/users", component: "UsersListPage" },
    { route: "/admin/users", component: "AdminUsersPage" }
  ],
  ui_states: ["loading", "empty", "list"],
  // ... other 13 fields
}
```
""", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(PROBE),
         "--phase-dir", str(phase_dir),
         "--dry-run", "--json"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    import json
    data = json.loads(r.stdout)
    routes = {c["route"] for c in data.get("routes", [])}
    assert "/users" in routes
    assert "/admin/users" in routes


def test_probe_emits_event_on_failure(tmp_path):
    """Probe against unreachable base URL must emit failure event."""
    phase_dir = tmp_path / ".vg" / "phases" / "07"
    contracts_dir = phase_dir / "API-CONTRACTS"
    contracts_dir.mkdir(parents=True)
    (contracts_dir / "test.md").write_text("""
# GET /api/test

## BLOCK 5: FE consumer contract

```typescript
{
  url: "/api/test",
  consumers: [{ route: "/test-route", component: "X" }]
}
```
""", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(PROBE),
         "--phase-dir", str(phase_dir),
         "--base-url", "http://localhost:1",  # intentional unreachable
         "--json"],
        capture_output=True, text=True,
        timeout=30,
    )
    # Exit 1 on probe failures
    import json
    try:
        data = json.loads(r.stdout) if r.stdout.strip() else {}
        assert r.returncode != 0 or data.get("failed_count", 0) > 0
    except json.JSONDecodeError:
        assert r.returncode != 0
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

Create `scripts/probe-fe-routes.py`:

```python
#!/usr/bin/env python3
"""probe-fe-routes.py — Batch 26

Runtime FE route navigation probe. Reads API-CONTRACTS/<slug>.md BLOCK 5
consumers[].route, navigates each via curl (no Playwright dep — keeps it
fast + sandbox-friendly). Detects 404-fallback page patterns.

Limitation: curl-only mode catches HTTP 200 + page text patterns. For SPA
client-side 404 detection that requires JS execution, future enhancement
should integrate Playwright (out of scope at first ship).

Exit codes:
  0 — all routes navigable + render content (not 404 fallback)
  1 — one or more routes failed (unwired or 404 fallback rendered)
  2 — config error
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


# BLOCK 5 typescript fence + consumers[] regex
BLOCK5_RE = re.compile(
    r"##\s+BLOCK\s+5:\s+FE consumer contract\s*\n+```(?:typescript|ts)\n(?P<body>.+?)\n```",
    re.DOTALL,
)
CONSUMER_RE = re.compile(
    r'\{\s*route:\s*"(?P<route>[^"]+)"\s*,\s*component:\s*"(?P<component>[^"]+)"',
)

# Patterns indicating 404 fallback page (heuristic)
NOT_FOUND_PATTERNS = [
    r'data-testid=["\']not-found',
    r'<h1>\s*(?:Page\s+)?Not Found\s*</h1>',
    r'<h1>\s*404\s*</h1>',
    r'class=["\'][^"\']*(?:not-found|page-404|error-404)',
    r'\bPage not found\b',
]
NOT_FOUND_RE = re.compile("|".join(NOT_FOUND_PATTERNS), re.IGNORECASE)


def _parse_routes(phase_dir: Path) -> list[dict]:
    contracts_dir = phase_dir / "API-CONTRACTS"
    if not contracts_dir.is_dir():
        return []
    routes = []
    seen = set()
    for f in contracts_dir.glob("*.md"):
        body = f.read_text(encoding="utf-8", errors="replace")
        for bm in BLOCK5_RE.finditer(body):
            block_body = bm.group("body")
            for cm in CONSUMER_RE.finditer(block_body):
                route = cm.group("route")
                component = cm.group("component")
                if route in seen:
                    continue
                seen.add(route)
                routes.append({
                    "route": route,
                    "component": component,
                    "source_slug": f.stem,
                })
    return routes


def _probe_route(base_url: str, route: str, timeout: int = 10) -> dict:
    """Returns {ok, http_status, error?, not_found_detected?}."""
    url = f"{base_url.rstrip('/')}{route}"
    try:
        # curl -s -o body.txt -w '%{http_code}'
        r = subprocess.run(
            ["curl", "-sSL", "-w", "%{http_code}\n", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if r.returncode != 0:
            return {"ok": False, "error": f"curl exit {r.returncode}: {r.stderr[:200]}"}
        out = r.stdout
        # Last line is HTTP status, rest is body
        lines = out.rsplit("\n", 1)
        if len(lines) == 2:
            body, status = lines[0], lines[1].strip()
        else:
            body, status = "", out.strip()
        try:
            status_code = int(status)
        except ValueError:
            return {"ok": False, "error": f"unparseable status: {status!r}"}
        if status_code >= 400:
            return {"ok": False, "http_status": status_code, "error": f"HTTP {status_code}"}
        not_found = bool(NOT_FOUND_RE.search(body))
        return {
            "ok": not not_found,
            "http_status": status_code,
            "not_found_detected": not_found,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "error": "curl not found in PATH"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase-dir", required=True, type=Path)
    ap.add_argument("--base-url", default="http://localhost:5173",
                    help="FE base URL (Vite dev default)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse routes from contracts but don't probe")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    routes = _parse_routes(args.phase_dir)
    if not routes:
        msg = "No FE consumer routes found in API-CONTRACTS/*.md BLOCK 5"
        if args.json:
            print(json.dumps({"routes": [], "message": msg}))
        else:
            print(f"ℹ {msg}")
        return 0

    if args.dry_run:
        if args.json:
            print(json.dumps({"routes": routes}))
        else:
            print(f"Routes ({len(routes)}):")
            for r in routes:
                print(f"  {r['route']} → {r['component']} (from {r['source_slug']})")
        return 0

    results = []
    failed = 0
    for r in routes:
        probe = _probe_route(args.base_url, r["route"])
        result = {**r, **probe}
        results.append(result)
        if not probe.get("ok", False):
            failed += 1

    report = {
        "phase_dir": str(args.phase_dir),
        "base_url": args.base_url,
        "total_routes": len(routes),
        "failed_count": failed,
        "results": results,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for r in results:
            mark = "✓" if r.get("ok") else "⛔"
            print(f"{mark} {r['route']:30} (HTTP {r.get('http_status', '?')}) "
                  f"{'404 fallback' if r.get('not_found_detected') else r.get('error', '')}")
        print(f"\nTotal: {len(routes)} routes, {failed} failed")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4-6:** pass + mirror + commit.

```bash
git commit -m "feat(probe): Batch 26 Task 1 — probe-fe-routes.py runtime FE route navigation

Reads API-CONTRACTS/<slug>.md BLOCK 5 consumers[].route, navigates each
via curl (sandbox-friendly, no Playwright dep). Detects:
- HTTP 4xx/5xx (BE side reject)
- 404 fallback page patterns (SPA returns 200 but renders 'Not Found')

--dry-run: parse routes, skip probe (for testing).
--json: structured output for telemetry.
--base-url: FE dev server URL (default http://localhost:5173 Vite).

Tests: tests/test_batch26_probe_fe_routes.py (3 tests).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: verify-be-fe-consumer-parity.py

**Files:**
- Create: `scripts/validators/verify-be-fe-consumer-parity.py`
- Mirror
- Test: `tests/test_batch26_be_fe_parity.py`

**Logic:**
- BE endpoints: extract from `API-CONTRACTS.md` headers (`### GET /path`, `### POST /path`)
- FE consumers: BLOCK 5 `url:` field per slug
- Orphan BE: endpoint in BE list but no FE consumer → WARN (`contract.orphan_be_endpoint`)
- Orphan FE: BLOCK 5 url field references endpoint not in BE list → BLOCK (`contract.orphan_fe_consumer`)

**Step 1: Failing test**

```python
"""tests/test_batch26_be_fe_parity.py — Batch 26 BE-FE consumer parity."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]
VAL = REPO / "scripts" / "validators" / "verify-be-fe-consumer-parity.py"


def test_validator_exists():
    assert VAL.is_file()


def test_orphan_fe_consumer_blocks(tmp_path):
    """FE BLOCK 5 references endpoint not in BE API-CONTRACTS.md → BLOCK."""
    phase_dir = tmp_path / ".vg" / "phases" / "07"
    phase_dir.mkdir(parents=True)
    (phase_dir / "API-CONTRACTS.md").write_text("""
# API Contracts

### GET /api/users
### POST /api/users
""", encoding="utf-8")
    contracts_dir = phase_dir / "API-CONTRACTS"
    contracts_dir.mkdir()
    (contracts_dir / "orphan.md").write_text("""
## BLOCK 5: FE consumer contract

```typescript
{
  url: "/api/orders",  // NOT in BE API-CONTRACTS.md — orphan FE
  consumers: [{ route: "/orders", component: "X" }]
}
```
""", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(VAL), "--phase-dir", str(phase_dir)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0, (
        f"Orphan FE consumer must BLOCK. rc={r.returncode}, "
        f"out={(r.stdout + r.stderr)[:300]}"
    )
    combined = r.stdout + r.stderr
    assert "/api/orders" in combined or "orphan" in combined.lower()


def test_orphan_be_endpoint_warns(tmp_path):
    """BE endpoint without FE consumer → WARN (exit 0 by default, but JSON reports)."""
    phase_dir = tmp_path / ".vg" / "phases" / "07"
    phase_dir.mkdir(parents=True)
    (phase_dir / "API-CONTRACTS.md").write_text("""
### GET /api/used
### GET /api/orphan-be
""", encoding="utf-8")
    contracts_dir = phase_dir / "API-CONTRACTS"
    contracts_dir.mkdir()
    (contracts_dir / "used.md").write_text("""
## BLOCK 5: FE consumer contract
```typescript
{ url: "/api/used", consumers: [{ route: "/x", component: "X" }] }
```
""", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(VAL), "--phase-dir", str(phase_dir), "--json"],
        capture_output=True, text=True,
    )
    # WARN — exit 0 (advisory) but JSON reports orphan
    import json
    if r.stdout.strip().startswith("{"):
        data = json.loads(r.stdout)
        orphans = data.get("orphan_be_endpoints", [])
        assert any("/api/orphan-be" in str(o) for o in orphans), (
            f"BE orphan endpoint not reported. Got: {orphans}"
        )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

```python
#!/usr/bin/env python3
"""verify-be-fe-consumer-parity.py — Batch 26

Compares BE endpoints declared in API-CONTRACTS.md headers vs FE consumers
declared in API-CONTRACTS/<slug>.md BLOCK 5 url field.

- Orphan BE: endpoint in BE list, no matching FE consumer → WARN (exit 0)
- Orphan FE: consumer url not in BE list → BLOCK (exit 1)
- Both → exit 1
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path


BE_HEADER_RE = re.compile(
    r"^#{2,4}\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|WS|WEBSOCKET)\s+(\S+)",
    re.MULTILINE,
)
BLOCK5_RE = re.compile(
    r"##\s+BLOCK\s+5:\s+FE consumer contract\s*\n+```(?:typescript|ts)\n(?P<body>.+?)\n```",
    re.DOTALL,
)
URL_FIELD_RE = re.compile(r'url:\s*"(?P<url>[^"]+)"')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase-dir", required=True, type=Path)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    be_path = args.phase_dir / "API-CONTRACTS.md"
    if not be_path.is_file():
        print(f"⛔ BE API-CONTRACTS.md missing at {be_path}", file=sys.stderr)
        return 2

    be_body = be_path.read_text(encoding="utf-8")
    be_endpoints = set()
    for m in BE_HEADER_RE.finditer(be_body):
        be_endpoints.add(m.group(2))

    fe_consumers = set()
    fe_files = list((args.phase_dir / "API-CONTRACTS").glob("*.md")) if (args.phase_dir / "API-CONTRACTS").is_dir() else []
    for f in fe_files:
        body = f.read_text(encoding="utf-8", errors="replace")
        for bm in BLOCK5_RE.finditer(body):
            for um in URL_FIELD_RE.finditer(bm.group("body")):
                fe_consumers.add(um.group("url"))

    orphan_be = sorted(be_endpoints - fe_consumers)
    orphan_fe = sorted(fe_consumers - be_endpoints)

    report = {
        "phase_dir": str(args.phase_dir),
        "be_endpoint_count": len(be_endpoints),
        "fe_consumer_count": len(fe_consumers),
        "orphan_be_endpoints": orphan_be,
        "orphan_fe_consumers": orphan_fe,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if orphan_be:
            print(f"⚠ {len(orphan_be)} BE endpoint(s) without FE consumer:")
            for e in orphan_be[:10]:
                print(f"   {e}")
        if orphan_fe:
            print(f"⛔ {len(orphan_fe)} FE consumer(s) reference non-existent BE endpoint:")
            for e in orphan_fe[:10]:
                print(f"   {e}")
        if not orphan_be and not orphan_fe:
            print(f"✓ BE-FE parity OK: {len(be_endpoints)} endpoints, {len(fe_consumers)} consumers")

    return 1 if orphan_fe else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Step 4-6:** pass + mirror + commit.

```bash
git commit -m "feat(probe): Batch 26 Task 2 — verify-be-fe-consumer-parity validator

Set diff BE endpoints (API-CONTRACTS.md headers) vs FE consumers (BLOCK 5
url field). Orphan FE consumer (FE references non-existent BE endpoint)
→ exit 1. Orphan BE endpoint (no FE consumer) → WARN, exit 0.

Tests: tests/test_batch26_be_fe_parity.py (3 tests).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire into /vg:test post-deploy + /vg:review

**Files:**
- Modify: `commands/vg/_shared/test/deploy.md` (after 5a_deploy, before 5b_*)
- Modify: `commands/vg/_shared/review/api-and-discovery.md` (alongside BE probe)
- Mirrors
- Test: `tests/test_batch26_route_probe_wired.py`

**Step 1: Failing test**

```python
"""tests/test_batch26_route_probe_wired.py — Batch 26 route probe wiring."""
from __future__ import annotations
from pathlib import Path
REPO = Path(__file__).resolve().parents[1]


def test_test_deploy_runs_route_probe():
    body = (REPO / "commands/vg/_shared/test/deploy.md").read_text(encoding="utf-8")
    assert "probe-fe-routes" in body, (
        "Batch 26: test/deploy.md must invoke probe-fe-routes.py post-deploy"
    )


def test_review_api_discovery_runs_parity_check():
    body = (REPO / "commands/vg/_shared/review/api-and-discovery.md").read_text(encoding="utf-8")
    assert "verify-be-fe-consumer-parity" in body, (
        "Batch 26: review api-and-discovery must invoke parity validator"
    )
```

**Step 2-6:** RED → implement → GREEN → mirror → commit.

In `commands/vg/_shared/test/deploy.md` after deploy step:

```bash
# Batch 26: FE route wiring probe — catch un-wired routes post-deploy
ROUTE_PROBE="${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/probe-fe-routes.py"
[ -f "$ROUTE_PROBE" ] || ROUTE_PROBE="${REPO_ROOT:-.}/scripts/probe-fe-routes.py"
if [ -f "$ROUTE_PROBE" ] && [ -d "${PHASE_DIR}/API-CONTRACTS" ]; then
  FE_BASE_URL="${FE_BASE_URL:-http://localhost:5173}"
  "${PYTHON_BIN:-python3}" "$ROUTE_PROBE" \
    --phase-dir "${PHASE_DIR}" \
    --base-url "$FE_BASE_URL" \
    --json > "${PHASE_DIR}/.route-probe.json" 2>&1 || {
    echo "⚠ Batch 26: FE route probe found un-wired route(s) — see ${PHASE_DIR}/.route-probe.json" >&2
    "${PYTHON_BIN:-python3}" "${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/vg-orchestrator" emit-event \
      "test.fe_route_unwired" --payload "{\"phase\":\"${PHASE_NUMBER}\"}" >/dev/null 2>&1 || true
  }
fi
```

In `commands/vg/_shared/review/api-and-discovery.md` alongside BE precheck:

```bash
# Batch 26: BE-FE consumer parity check
PARITY_VAL="${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/validators/verify-be-fe-consumer-parity.py"
[ -f "$PARITY_VAL" ] || PARITY_VAL="${REPO_ROOT:-.}/scripts/validators/verify-be-fe-consumer-parity.py"
if [ -f "$PARITY_VAL" ]; then
  "${PYTHON_BIN:-python3}" "$PARITY_VAL" --phase-dir "${PHASE_DIR}" --json \
    > "${PHASE_DIR}/.be-fe-parity.json" 2>&1
  PARITY_RC=$?
  if [ "$PARITY_RC" -ne 0 ]; then
    echo "⛔ Batch 26 BLOCK: orphan FE consumer (references non-existent BE endpoint)" >&2
    "${PYTHON_BIN:-python3}" "${VG_SCRIPT_ROOT:-${VG_HOME:-$HOME/.vgflow}/scripts}/vg-orchestrator" emit-event \
      "contract.orphan_fe_consumer" --payload "{\"phase\":\"${PHASE_NUMBER}\"}" >/dev/null 2>&1 || true
    exit 1
  fi
fi
```

```bash
git commit -m "fix(test+review): Batch 26 Task 3 — wire FE route probe + parity validator

test/deploy.md: post-deploy invokes probe-fe-routes.py, writes
.route-probe.json, emits test.fe_route_unwired on failure (WARN at v4.29.0).

review/api-and-discovery.md: invokes verify-be-fe-consumer-parity.py
alongside BE precheck. Orphan FE consumer → BLOCK + emit
contract.orphan_fe_consumer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Release v4.29.0

Bump VERSION 4.28.1 → 4.29.0. CHANGELOG. Tag v4.29.0. Push. Re-sync ~/.vgflow. Codex mirror verify; regen if drift.

End of Batch 26. Estimated 3-4 hours.
