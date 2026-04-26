# Phase 17 — Test Session Reuse — Roadmap Entry

```yaml
id: phase-17
slug: test-session-reuse-v1
title: "Test Session Reuse — storage state + loginOnce + Playwright global setup"
estimated_hours: 8-10
priority: HIGH
risk: LOW
depends_on: [phase-15]
unblocks: []  # Standalone perf optimization; not gating other phases
created: 2026-04-27
status: planning  # planning | speccing | execute | shipped
profile: web-fullstack
deliverables:
  - "interactive-helpers.template.ts: loginOnce + useAuth exports (D-02)"
  - "10 Phase 15 D-16 templates updated: useAuth replaces beforeEach loginAs (D-03)"
  - "playwright-global-setup.template.ts (D-04)"
  - "vg.config.template.md test: block defaults (D-05)"
  - "verify-test-session-reuse.py validator (D-06)"
acceptance:
  - "Re-run /vg:test trên RTB Phase 7.14.3, wall-clock giảm ≥ 50% so với baseline"
  - "Browser process count trong run = workers count (4), không spike per spec"
  - "verify-test-session-reuse.py PASS trên specs đã regen"
```
