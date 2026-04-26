# Phase 16 — Task Fidelity Lock — Roadmap Entry

```yaml
id: phase-16
slug: task-fidelity-lock-v1
title: "Task Fidelity Lock — SHA256 hash check + structured task schema + R4 enriched-mode"
estimated_hours: 14-18
priority: HIGH
risk: MEDIUM
depends_on: [phase-15]   # T11.2 persist mechanism is the foundation
unblocks: []             # Standalone safety; not gating other phases
created: 2026-04-27
status: planning
profile: any  # applies to all build flows
deliverables:
  - "pre-executor-check.py: SHA256 hash + .meta.json persist (D-01)"
  - "Structured task schema YAML frontmatter contract + verify-task-schema.py (D-02)"
  - "vg_completeness_check.py Check E: body line cap BLOCK gate (D-03)"
  - "pre-executor-check.py: R4 conditional caps for cross_ai_enriched (D-04)"
  - "crossai-invoke.md contract update + verify-crossai-output.py (D-05)"
  - "verify-task-fidelity.py post-spawn hash audit (D-06)"
acceptance:
  - "Fixture phase với cross-AI enriched PLAN run /vg:build PASS không truncate"
  - "Fixture phase orchestrator paraphrase task body 30% → verify-task-fidelity.py BLOCK"
  - "Cross-AI enrichment thêm 50 dòng prose vào task body → BLOCK với migration hint"
  - "Toàn bộ 6 validators registered + acceptance smoke pass"
notes:
  - "Defer Phase 17 (test session reuse) cho consumer dogfood Phase 16 nhanh hơn"
  - "Risk MEDIUM: đụng pre-executor-check.py critical path. Need feature flag rollout."
```
