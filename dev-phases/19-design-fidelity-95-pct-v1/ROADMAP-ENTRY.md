# Phase 19 — Design Fidelity 95% — Roadmap Entry

```yaml
id: phase-19
slug: design-fidelity-95-pct-v1
title: "Design fidelity 95% — upstream view-decomposition + downstream vision-self-verify, closing the loop on L-002"
estimated_hours: 14-22
priority: HIGH
risk: MEDIUM  # touches hot path (blueprint UI-SPEC + build executor spawn) but each decision is opt-in via config gate
depends_on:
  - phase-15-vg-design-fidelity-v1   # design-extract pipeline + manifest schema
  - v2.13.0                          # 4-layer pixel pipeline (L1 hard-gate, L2 fingerprint, L3 build-visual, L4 review SSIM)
unblocks: []                         # standalone reliability lift, no downstream gating
created: 2026-04-28
status: planning
profile: any   # applies to every build profile that has FE work
deliverables:
  - "Stage 1 (upstream) — D-01..D-04: blueprint reads view CHÍNH XÁC có những component gì"
  - "Stage 2 (downstream) — D-05..D-09: enforcement closing the gap between rule and reality"
acceptance:
  - "Smoke phase với 1 PNG complex (5+ components) → blueprint emit fine-grained tasks (≥5 component tasks thay vì 1 page task)"
  - "L5 vision-self-verify catch deliberately-wrong UI (test fixture: ship `<main className=\"flex items-center\">` with HomeDashboard.png as <design-ref>) → BLOCK at /vg:build step 9"
  - "L9 manual UAT prompt user xác nhận diff PNG; user reject → /vg:accept blocked"
  - "L7 phase với 3 design override-debt entries kind=design-* → /vg:accept BLOCK với nudge tới /vg:override-resolve"
  - "L6 pre-commit hook reject UI-touching commit thiếu `Per design/{slug}.png` HOẶC `Design: no-asset (...)` citation"
  - "Combined gate stack reduces design-drift incidents from ~30% (anecdotal pre-v2.13) to <5% on dogfood phases"
ship_target: v2.14.0   # minor bump; primary focus = design fidelity completeness
```

## Why this phase

v2.13.0 đóng được 4 layer downstream + 1 planner-side coverage validator. Đánh giá thật về reliability:

| Layer hiện tại | Đảm bảo gì | Lỗ hổng còn lại |
|---|---|---|
| Planner Rule 8 + verify-design-ref-coverage | PLAN có `<design-ref>` cho mọi FE task | Task vẫn ở mức "page", không decompose thành component → executor scope quá rộng |
| L1 hard-gate disk PNG | File tồn tại trước spawn | Không verify executor THỰC SỰ Read PNG |
| L2 LAYOUT-FINGERPRINT | File có 4 sections ≥60 chars | Có thể bịa nội dung mà không cần xem PNG |
| L3 build-visual | Pixel-diff vs baseline | SKIP nếu dev server / Node / pixelmatch missing → silent miss |
| L4 review SSIM | BLOCK on threshold | Phụ thuộc browser session navigate đúng URL |

**Gap chiến lược:** thượng nguồn (blueprint) hiện tại chỉ "biết slug" chứ chưa biết view gồm những component gì cụ thể; hạ nguồn (executor) tin lời rule mà không có proof actual reading PNG. Phase 19 đóng cả hai đầu.

## Sequencing rationale

Cost/leverage table cho 9 quyết định, sequence theo ROI:

| Step | Decision | Type | Effort (h) | Risk | Notes |
|---|---|---|---|---|---|
| 1 | D-01 — consume scan.json vào blueprint UI-SPEC step 2b6 | upstream | 1-2 | LOW | tận dụng spend đã có ở design-extract; ~30 dòng change |
| 2 | D-05 — vision-self-verify (Lớp 5) post-task | downstream | 3-4 | MED | new validator + Haiku spawn; pattern reuse từ rationalization-guard |
| 3 | D-06 — manual UAT visual check ở /vg:accept | downstream | 1 | LOW | interactive prompt + diff PNG side-by-side |
| 4 | D-02 — vision view-decomposition step 2b6c | upstream | 4-6 | MED | new step + Opus vision spawn + VIEW-COMPONENTS.md schema |
| 5 | D-07 — override-debt threshold gate ở /vg:accept | downstream | 1-2 | LOW | extend `verify-override-debt-sla.py` filter kind=design-* |
| 6 | D-08 — pre-commit hook bắt citation `Per design/{slug}.png` | downstream | 2 | LOW | native git hook; robust regex |
| 7 | D-03 — cross-AI vision gap-hunt cho VIEW-COMPONENTS | upstream | 1-2 | LOW | reuse vg-design-gap-hunter pattern |
| 8 | D-04 — re-emit fine-grained PLAN từ VIEW-COMPONENTS | upstream | 4-6 | HIGH | thay đổi planner output shape; can break existing fixtures |
| 9 | D-09 — Read-tool transcript proof | downstream | 3-5 | HIGH | research; cần Claude Code expose subagent transcript hooks |

Khuyến nghị thực thi theo waves:

- **Wave A (immediate, 3-4 commit):** D-01 + D-05 + D-06 — 80% reliability lift với 5-7h work. Ship v2.13.1 patch.
- **Wave B (vision upstream, 2 commit):** D-02 + D-03 — view-decomposition core. Ship v2.13.2.
- **Wave C (forcing functions, 2 commit):** D-07 + D-08 — closing back doors. Ship v2.13.3.
- **Wave D (advanced, 2 commit):** D-04 + D-09 — fine-grained planning + transcript proof. Ship v2.14.0 (breaking shape change for D-04 → minor bump).

Wave A đứng độc lập — có thể stop sau Wave A nếu đo lường thấy reliability đủ. Wave B-D bổ sung cho dogfood production.

## Out of scope

- Thay thế hoàn toàn AI judgment bằng deterministic gate. Không khả thi (visual hierarchy là semantic).
- Re-architecting design-extract pipeline. Giữ nguyên 4-layer Haiku/Opus extraction.
- Mobile design fidelity (mobile.devices flow). Dùng existing `/vg:_review:phase2_5_mobile_visual_checks` — không touch.
- Performance optimization của Playwright render (L3 already auto-skip — tradeoff acceptable).
