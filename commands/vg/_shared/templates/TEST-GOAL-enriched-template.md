# TEST-GOAL enriched template (v2.2+)

Optional frontmatter fields for each goal in `TEST-GOALS.md`. Backward-
compatible: legacy goals without these fields still work. Blueprint step
2b5 should emit enriched format; consumers (review/test/accept) read when
present, gracefully degrade when absent.

## Schema

```yaml
---
id: G-XX
title: "Short user-observable behavior"
priority: critical | important | nice
surface: ui | api | data | integration | time-driven | custom

# v2.2 enrichment (all optional but recommended)
actor: <role + authentication state>
  # e.g. "publisher (role=publisher, authenticated)"
  #      "anonymous (unauthenticated visitor)"
  #      "cron (system, runs 0 */5 * * *)"

precondition:
  # List of system state required before goal can trigger
  - <imported_goal_or_UC_id>  # e.g. UC-GEN-AUTH-01 (logged in)
  - <explicit state>          # e.g. "has_verified_site"
  - <data requirement>        # e.g. "quota_available"

trigger: <user-observable action or event>
  # e.g. "Click 'Create Ad Unit' button"
  #      "POST /api/sites/{id}/ad-units from client"
  #      "Kafka message on topic bid-requests"

main_steps:
  # Ordered list of user-visible OR system actions. Each step = 1 observable.
  - S1: <action>              # e.g. "Open form modal"
  - S2: <action>              # e.g. "Fill name + size + type"
  - S3: <action>              # e.g. "Submit form"
  - S4: <action>              # e.g. "API validates + persists"
  - S5: <action>              # e.g. "List refresh with new entry"

alternate_flows:
  # Named failure modes + expected system behavior
  - name: <short_id>
    trigger: <what causes alternate flow>
    expected: <observable outcome>
  # e.g.
  # - name: validation_fail
  #   trigger: missing required field
  #   expected: inline errors shown, stay on modal
  # - name: quota_exceeded
  #   trigger: user at/above site quota
  #   expected: upgrade prompt shown, submission blocked

postcondition:
  # State after successful main_flow execution. MUST include side effects.
  - <db state change>         # e.g. "ad_unit row inserted with status=pending_review"
  - <event emission>          # e.g. "event 'ad_unit_created' emitted to Kafka"
  - <cache invalidation>      # e.g. "sites_list cache for publisher invalidated"
  - <ui state>                # e.g. "list UI shows new item at top"

# Verification binding (existing v1.14 fields)
verification: automated | manual | deferred | skipped
tests: [TS-XX, TS-YY]         # bind to test files via TS-XX markers

# ─────────────────────────────────────────────────────────────────────
# v2.5 Phase B enrichment — Security + Performance
# ─────────────────────────────────────────────────────────────────────
# Optional but REQUIRED for critical_goal_domains (auth/payment/billing).
# Severity logic in verify-goal-security.py:
#   - critical_goal_domain + section empty → HARD BLOCK
#   - mutation endpoint + csrf OR rate_limit empty → HARD BLOCK
#   - read-only GET + section empty → WARN + override debt

security_checks:
  # OWASP Top 10 2021 subset relevant cho endpoint (không phải hết 10).
  # Format: "AXX:name: justification" — validator cross-references với
  # API-CONTRACTS schema để auto-tick (vd Zod schema → A03 injection OK).
  owasp_top10_2021:
    - "A01:Broken-Access-Control: owner check on update via ownerId middleware"
    - "A03:Injection: Zod schema parameterized query via Prisma"
    - "A05:Security-Misconfig: CSP default-src 'self' inherits project baseline"
    # Relevant categories (add as applicable):
    # - "A02:Cryptographic-Failures: bcrypt work factor 12, no SHA1"
    # - "A04:Insecure-Design: rate-limit + step-up auth cho destructive op"
    # - "A06:Vulnerable-Components: lockfile integrity + CVE scan CI"
    # - "A07:Identification-Auth: session fixation prevented + logout server-side"
    # - "A08:Software-Integrity: signed commits + dependency provenance"
    # - "A09:Logging-Monitoring: audit log with user_id + IP + UA"
    # - "A10:SSRF: URL whitelist, block 169.254/10/172.16/192.168"

  # ASVS Level 2 controls (granular validation beyond OWASP Top 10).
  # Free-form string citing ASVS ID + justification.
  asvs_level2:
    - "V5.1.1: input validation per field via Zod schema"
    - "V5.3.3: output encoding context-aware (React auto-escape + CSP)"
    # - "V7.1.1: session generation cryptographically strong"
    # - "V9.1.2: TLS 1.2+ enforced cho all endpoints"

  # Rate limiting: per-user + per-IP. Required cho mutation endpoints.
  # Empty → HARD BLOCK cho mutation. Format: free-form description.
  rate_limit: "10/min per user, 30/min per IP, 5/min anonymous"

  # CSRF protection mechanism. Required cho state-changing endpoints
  # (POST/PUT/PATCH/DELETE) nếu accept cookie auth. Empty → HARD BLOCK
  # cho mutation + cookie auth (Bearer-only API có thể để trống).
  csrf: "SameSite=Strict session cookie + double-submit token verify"

  # XSS protection — framework default + explicit overrides.
  xss_protection: "React auto-escape + CSP strict default-src 'self'"

  # Auth model classification (cross-ref với API-CONTRACTS Block 1 auth line).
  # Values: public | authenticated | role:<name> | owner_only | multi
  auth_model: "owner_only"

  # PII fields (if endpoint accepts/returns PII). Encryption + masking policy.
  pii_fields: ["email", "phone", "dob"]

# Performance budget — Required cho mutation + list endpoints.
# Read-only single-record GET có thể để trống (default project baseline).
perf_budget:
  p50_ms: 80                    # median response time target
  p95_ms: 250                   # 95th percentile target (alarm threshold)
  p99_ms: 500                   # 99th percentile (outlier floor)
  n_plus_one_max: 3             # max DB round-trips per request
  bundle_kb_fe_route: 250       # FE route-split bundle size (only applicable cho ui surface)
  cache_strategy: "Redis 5min TTL + tag-invalidate on mutation"

# Evidence fields (populated by /vg:test, /vg:review)
status: NOT_SCANNED | READY | BLOCKED | UNREACHABLE | FAILED | DEFERRED | INFRA_PENDING | MANUAL
evidence_file: apps/web/e2e/xxx.spec.ts:42 | apps/api/test/xxx.test.ts
---

## Prose description (optional)

Narrative context for humans reviewing goal. Not parsed by validators.
```

## Example — real goal (phase 14 G-01)

```yaml
---
id: G-01
title: "Publisher login respects domain-role fit"
priority: critical
surface: api + ui
actor: publisher (role=publisher, unauthenticated before login)
precondition:
  - has_verified_account
  - domain_route_configured (ssp.vollx.com → publisher app)
trigger: "POST /api/v1/auth/login from ssp.vollx.com origin"
main_steps:
  - S1: Client POST credentials + domain header to /api/v1/auth/login
  - S2: API validates domain-role fit via AuthDomain enum
  - S3: API issues JWT with domain=ssp claim + refresh cookie scoped to ssp domain
  - S4: Client redirected to publisher dashboard
  - S5: Subsequent requests include JWT — middleware validates JWT.domain matches Origin header
alternate_flows:
  - name: domain_role_mismatch
    trigger: admin account attempts login from ssp.vollx.com
    expected: 403 with VG_ERR_DOMAIN_ROLE_UNFIT + Vietnamese toast "Tài khoản không có quyền cho domain này"
  - name: invalid_origin
    trigger: request from unapproved domain (e.g. evil.com)
    expected: 403 via CORS preflight + VG_ERR_DOMAIN_ORIGIN_INVALID logged
postcondition:
  - jwt_issued with domain=ssp in payload
  - refresh_cookie set with Domain=.ssp.vollx.com Path=/api/v1/auth
  - session row in Redis with key "session:ssp:{user_id}:{device_id}"
  - event "auth.login" emitted with {domain, user_id, success: true}
verification: automated
tests: [TS-01, TS-02]
status: READY
evidence_file: apps/web/e2e/auth-domain-isolation.spec.ts:23
---

Publisher can only log in from their designated SSP domain. Cross-domain
attempts (admin credentials on SSP domain) are rejected with clear error
message in Vietnamese. Session cookies scoped to domain prevent cross-
site token leak.
```

## Migration

- **Existing goals** (v1.14 format): no action needed. Missing fields = validators skip enrichment checks.
- **New phases** (scope/blueprint v2+): blueprint step 2b5 SHOULD emit enriched format. AI reads this template to infer structure.
- **Manual enrichment**: user edits TEST-GOALS.md adding fields. Validators re-run, may unlock additional coverage.

## Consumer behavior

| Command | Reads enriched fields | Effect |
|---------|----------------------|--------|
| `/vg:blueprint` step 2b5 | Generates via AI prompt | AI pattern-matches template → uses enriched format |
| `/vg:build` executor | Reads `precondition` + `alternate_flows` | Task context includes error handling requirements |
| `/vg:review` goal comparison | Reads `main_steps` + `postcondition` | Maps to RUNTIME-MAP observed sequences |
| `/vg:test` codegen | Reads all enriched fields | Generates Playwright scenarios per `alternate_flows` names |
| `/vg:accept` UAT checklist | Reads `actor` + `postcondition` | User UAT items phrased in enriched language |

Each consumer's enrichment is **additive** — absence of field = legacy path.
