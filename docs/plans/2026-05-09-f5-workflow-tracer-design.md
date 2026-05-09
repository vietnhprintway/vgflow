# F5 Workflow Tracer — Design

**Status:** DESIGN ONLY — no implementation yet. v2.64.0+ task.
**Author:** Claude (session 2026-05-09)
**Context:** Last deferred item from RTB blueprint→build investigation. v2.59-v2.63 closed P0-P2 + D1-D4. F5 is the architectural follow-up.

---

## 1. Goal

Catch FE flow drift the existing gates miss: form submit → API call → response handler → state update → UI feedback. Each step must trace to actual code (file:line) before phase ships.

**User pain (verbatim from session):** "save form lỗi nhiều loại" — FE-BE field name drift fixed by F3 (v2.62.0 FORM-API-MAP). But field names matching ≠ flow working. Bugs slip through:

- (e) Response shape FE không parse được — BE returns `{data: {...}}`, FE expects `{...}` flat
- (f) State sau response không update UI — fetch succeeds, setState never called, UI stuck on loading
- (a) FE gửi sai endpoint URL — form action attr OK but JS fetch hits wrong path

These are **wiring bugs across components**, not field-name bugs. Need cross-step evidence binding.

## 2. Schema

### 2a. Workflow definition (existing — reuse)

`${PHASE_DIR}/WORKFLOW-SPECS/WF-NN.md` already produced by `/vg:blueprint` Pass 3 (`vg-blueprint-workflows` agent). Contains YAML:

```yaml
id: WF-001
name: "User saves form"
actors: [user, FE, BE]
steps:
  - actor: user
    action: "click submit"
    selector: "button[type=submit]"
  - actor: FE
    action: "validate form"
    invariant: "all required fields non-empty"
  - actor: FE
    action: "POST /api/users"
    contract: API-CONTRACTS/users-create.md
  - actor: BE
    action: "validate + persist"
  - actor: FE
    action: "handle response"
    success_path: "navigate to /users/:id"
    error_path: "show toast.error(message)"
  - actor: FE
    action: "invalidate cache"
    queries: ["users.list"]
```

### 2b. Evidence binding (NEW — F5 adds)

`${PHASE_DIR}/WORKFLOW-EVIDENCE/<wf-id>.json` — runs after build. Per workflow step:

```json
{
  "workflow_id": "WF-001",
  "phase": "7.14",
  "generated_at": "2026-05-09T...",
  "steps": [
    {
      "step_idx": 0,
      "actor": "user",
      "action": "click submit",
      "evidence": {
        "file": "apps/web/src/components/forms/UserForm.tsx",
        "line": 42,
        "anchor": "onClick={handleSubmit}",
        "ast_node": "JSXAttribute"
      },
      "status": "found"
    },
    {
      "step_idx": 1,
      "actor": "FE",
      "action": "validate form",
      "evidence": {
        "file": "apps/web/src/components/forms/UserForm.tsx",
        "line": 38,
        "anchor": "form.handleSubmit",
        "ast_node": "MethodCall"
      },
      "status": "found"
    },
    {
      "step_idx": 2,
      "actor": "FE",
      "action": "POST /api/users",
      "evidence": {
        "file": "apps/web/src/api/users.ts",
        "line": 17,
        "anchor": "fetch('/api/users', { method: 'POST'",
        "ast_node": "CallExpression"
      },
      "status": "found"
    },
    {
      "step_idx": 3,
      "actor": "BE",
      "action": "validate + persist",
      "evidence": {
        "file": "apps/api/src/routes/users.ts",
        "line": 23,
        "anchor": "router.post('/users'",
        "ast_node": "MethodCall"
      },
      "status": "found"
    },
    {
      "step_idx": 4,
      "actor": "FE",
      "action": "handle response",
      "evidence": null,
      "status": "missing",
      "missing_reason": "no .then() / await response handler within 20 lines of step 2 fetch call"
    },
    {
      "step_idx": 5,
      "actor": "FE",
      "action": "invalidate cache",
      "evidence": null,
      "status": "missing",
      "missing_reason": "no queryClient.invalidateQueries(['users']) call found"
    }
  ],
  "summary": {
    "total_steps": 6,
    "found": 4,
    "missing": 2,
    "drift_severity": "warn"
  }
}
```

### 2c. Per-step status taxonomy

| Status | Meaning | Severity default |
|---|---|---|
| `found` | Evidence located via AST/regex | INFO |
| `missing` | Step declared in WORKFLOW-SPECS but no code found | **WARN** (default) / BLOCK (strict) |
| `divergent` | Code found but doesn't match step (e.g., POST → user_email, but step says email) | **WARN** (default) / BLOCK (strict) |
| `ambiguous` | Multiple candidates, can't disambiguate | INFO + log |
| `skipped` | Profile or flag exempts this workflow | INFO |

## 3. Gates

### 3a. Validator: `verify-workflow-evidence.py`

```
verify-workflow-evidence.py --phase {N} --fe-root {dir} --be-root {dir}
                            [--workflow-id WF-NN] [--strict] [--evidence-out PATH]
```

Exit codes:
- 0 = all workflows have evidence (all `found` or skipped)
- 1 = drift detected with `--strict` (BLOCK)
- 1 = drift detected without strict → emit WarningEvidence severity=warn (NOT block, mirror F4 pattern)
- 2 = invocation error / WORKFLOW-SPECS.md missing

### 3b. When validator runs

| Trigger | Effect |
|---|---|
| `/vg:build` post-execution gate | New `L4_workflow` gate (parallel to v2.63.0 F4 `L4_form`) |
| `/vg:test` preflight | Read WORKFLOW-EVIDENCE.json, generate test scenarios from `found` steps |
| `/vg:accept` Section C | Display workflow drift summary in UAT checklist |

### 3c. Profile coverage

| Profile | F5 enforcement |
|---|---|
| `feature` (web-fullstack) | enabled (warn-only default) |
| `web-frontend-only` | enabled (warn-only) |
| `web-backend-only` | enabled, BE steps only |
| `infra` / `hotfix` / `bugfix` / `migration` / `docs` | skipped |

## 4. Tooling

### 4a. Static AST parse (recommended for v2.64.0)

Use `tree-sitter` (or `babel-parser` for TS/JSX, `python-ast` for Python BE) to walk source tree and find:
- Click handlers attached to selectors (`onClick={fn}` → resolve `fn` reference)
- `fetch()` / `axios.post()` / framework HTTP calls with literal URL/method
- Form validation calls (`form.handleSubmit`, `react-hook-form` patterns)
- Cache invalidations (`queryClient.invalidateQueries`, `mutate(...)`)
- Backend route handlers (`router.post('/path', ...)`)

**Pros:** No runtime, fast, deterministic.
**Cons:** Misses dynamic imports, computed URLs, indirect refs.

### 4b. Runtime trace (defer to v2.65+)

Instrument FE + BE during `/vg:test` runtime, capture actual call graph. Higher fidelity but:
- Requires test coverage of every workflow path
- Instrumentation overhead
- Non-deterministic on flaky tests

**Recommendation:** Static AST for v2.64.0. Runtime as future opt-in.

### 4c. AST tooling choices

| Tool | Use for | Verdict |
|---|---|---|
| `tree-sitter` (CLI + Python bindings) | TS/JSX/Vue, Python, Go | RECOMMENDED |
| `@babel/parser` (Node) | TS/JSX deep parsing | Alternative if tree-sitter struggles with TSX |
| `ast` (Python stdlib) | Python BE | Sufficient |
| Regex fallback | Simple cases (literal URLs) | Last resort, log "regex match" provenance |

## 5. Gradual rollout

Mirror F3/F4 pattern:

| Version | Behavior |
|---|---|
| **v2.64.0** | Validator + L4_workflow gate exist. WARN-ONLY default. `--strict` opt-in. WORKFLOW-EVIDENCE.json emitted always. No config flag yet. |
| **v2.65.0** | `vg.config.md → build.l4_workflow_strict: true` flag added. Telemetry `build.l4_workflow_drift` accumulates. `/vg:gate-stats --gate L4_workflow` surfaces drift rate. |
| **v2.66.0** | If drift rate < 5% across user telemetry → flip strict default to `true`. Otherwise iterate validator. |

## 6. Risks

### 6a. False positives

- Dynamic URLs (`fetch(\`/api/${resource}\`)`) — AST sees template literal, can't resolve. Solution: `?` status, log INFO, don't block.
- Indirect refs (`const url = config.api.users; fetch(url)`) — AST follows symbol if defined in same module; if cross-module, log AMBIGUOUS.
- HOC/wrapper patterns (`withAuth(handler)`) — handler step may be inside higher-order function. Solution: walk up scope chain N=2 levels max.

### 6b. AST parse limits

- TSX deeply nested types may stack-overflow tree-sitter. Mitigation: 5MB file size cap; emit AMBIGUOUS for skipped files.
- Vue SFC parse needs separate vue-eslint-parser or template-compiler. Effort: +2h for vue support; defer to v2.65.
- Svelte / SolidJS / others: not supported v2.64; emit `skipped` with reason `unsupported_framework`.

### 6c. Runtime instrumentation cost (deferred)

Not a v2.64 risk. Documented for v2.65+ planning.

### 6d. Schema drift between WORKFLOW-SPECS and reality

Workflow specs may declare actions that don't translate to AST patterns (e.g., "user reads notification banner"). Solution: introduce `ast_search_hint` in spec YAML — if absent, validator marks as INFO not WARN.

## 7. Open questions (require user decision before impl)

| # | Question | Default if no decision |
|---|---|---|
| 1 | Should F5 validator BLOCK on missing evidence in strict mode, or only `divergent`? | BLOCK on both (matches F3 strict behavior) |
| 2 | Should every WORKFLOW-SPECS step require evidence, or only `actor: FE` + `actor: BE` steps (skip `actor: user`)? | Only FE+BE (user clicks generally testable in /vg:test) |
| 3 | Is per-step `ast_search_hint` mandatory in WORKFLOW-SPECS YAML, or optional? | Optional — auto-derive from action verb |
| 4 | Effort budget for v2.64.0 — full F5 (1.5 days) or skeleton-only (4h scaffold + warn-only, no AST yet)? | **Skeleton-only recommended** — ship validator + gate scaffolding first, AST parsing iterates |
| 5 | Workflow ID stable across phases? Or per-phase scoped? | Per-phase (mirrors API-CONTRACTS scoping) |
| 6 | Should validator also check **temporal order** (step 2 before step 5 in code execution)? | NO for v2.64 — too brittle. Defer to runtime trace v2.65+ |

## 8. Effort estimate

| Increment | Scope | Effort |
|---|---|---|
| **v2.64.0 skeleton** | Validator scaffolding + L4_workflow gate wiring + WORKFLOW-EVIDENCE.json schema + 1 framework support (TSX) | 4-6h |
| **v2.64.1** | Vue SFC support, AMBIGUOUS handling, `ast_search_hint` derivation | +3h |
| **v2.65.0** | Config flag + strict mode + telemetry-driven dogfood | 2h |
| **v2.65.x** | Runtime trace (separate workstream) | 1-2 days |

## 9. Decision required

User picks before v2.64.0 impl:
1. Skeleton-only v2.64.0 (recommended) or full F5 in one shot?
2. TSX-only v2.64.0 or include Vue?
3. Validator BLOCK on `missing` + `divergent` in strict, or only `divergent`?

## 10. Out of scope (v2.64.x)

- E2E test generation from WORKFLOW-EVIDENCE
- IDE integration (VS Code workflow viewer)
- Real-time workflow editor
- Workflow versioning across phases

---

## Appendix A — Why not just runtime test coverage?

`/vg:test` already verifies behavior. Why static workflow tracer?

Because tests verify outputs, not architecture. A test passing because login redirects to /home doesn't tell you whether the redirect is in `LoginForm.tsx` (good — owns the side effect) or `auth-router.ts` (smell — implicit coupling). F5 surfaces architectural intent vs implementation drift, not behavior drift.

## Appendix B — Comparison with F3 + F4

| Layer | What it checks | Granularity |
|---|---|---|
| F3 FORM-API-MAP | Form input `name` attr ↔ API field name | Field-level |
| F4 L4_form gate | F3 runs in build post-exec | Field-level (auto) |
| **F5 Workflow tracer** | Multi-step flow has code at each step | Flow-level |

F3/F4 protect against `user_email` vs `email` drift. F5 protects against "fetch succeeded but setState never called" drift.

---

**Status:** DESIGN COMPLETE. Awaiting user decision on §9 before v2.64.0 impl.
