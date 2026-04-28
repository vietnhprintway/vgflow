# Phase 20 — Design Scaffold for Greenfield — Roadmap Entry

```yaml
id: phase-20
slug: design-scaffold-greenfield-v1
title: "Design scaffold for greenfield projects — multi-tool selector (Pencil/PenBoard/Figma/HTML/AI-shotgun/Stitch/v0/Claude-design) feeding /vg:design-extract"
estimated_hours: 18-30  # depends on automation scope per tool
priority: HIGH
risk: MEDIUM
depends_on:
  - phase-15-vg-design-fidelity-v1   # design-extract pipeline
  - phase-19-design-fidelity-95-pct  # gates that NEED mockup ground truth
unblocks: []
created: 2026-04-28
status: planning
profile: any   # only fires for projects with FE work
deliverables:
  - "/vg:design-scaffold entry command with --tool=<selector>"
  - "Per-tool sub-flow: 4 in-VG automated, 4 external-routed"
  - "Tool decision matrix + AskUserQuestion guide"
  - "Routing changes in /vg:specs (detect greenfield → suggest scaffold)"
  - "Form B 'no-asset:greenfield-*' deprecation path"
acceptance:
  - "Greenfield smoke phase (no DESIGN.md, no mockups, no /vg:design-system run): /vg:specs detects state, routes to /vg:design-scaffold, user picks tool, mockups produced, /vg:design-extract auto-fires, /vg:blueprint resumes with valid <design-ref> slugs"
  - "Tool A (Pencil MCP automated): Opus generates .pen via mcp__pencil__batch_design from page list, file lands at design_assets.paths, design-extract picks up via pencil_mcp handler"
  - "Tool C (AI HTML automated): Opus emits HTML+Tailwind per page using DESIGN.md tokens, file lands and renders via playwright_render handler"
  - "Tool E (Stitch/v0/external): instruction prompt with explicit 'go to URL, export HTML, save here' steps; gate verifies file landed before resuming"
  - "Form B 'no-asset:greenfield-*' raised to severity:critical in override-debt; /vg:accept BLOCKs until resolved via /vg:design-scaffold rerun"
ship_target: v2.16.0   # minor bump; new entry command
```

## Why this phase

Phase 19 stack (v2.13.0–v2.15.3) hardens design fidelity assuming **mockups already exist somewhere** (Pencil/PenBoard/Figma/HTML). For greenfield projects with **zero design assets**, the entire stack degenerates:

| Layer | Greenfield state |
|---|---|
| L1 hard-gate (PNG on disk) | BLOCK or bypassed via Form B `no-asset:` |
| L2 LAYOUT-FINGERPRINT | SKIP (no PNG to fingerprint) |
| L3 build-visual SSIM | SKIP (no baseline) |
| L4 review fidelity | SKIP (no baseline) |
| L5 vision-self-verify | SKIP (no PNG to compare) |
| L6 read-evidence | SKIP (no PNG to Read) |
| Manual UAT 3-file diff | SKIP (no diff produced) |

**Net result for greenfield**: every gate Form-B'd → executor ships AI-imagined UI → reliability drops back to ~30% (pre-v2.13 baseline). The L-002 anti-pattern (`flex items-center justify-center` admin landing page) is exactly what happens.

Phase 20 closes the upstream gap: **before** L1 fires, the project must have mockups. `/vg:design-scaffold` is the on-ramp.

## Tool ecosystem audit (April 2026)

Eight tool families, each with different automation potential:

| # | Tool | Type | Automation in VG | Integration path |
|---|---|---|---|---|
| A | **Pencil MCP** (`.pen`) | In-VG MCP | ✅ Full automate via `mcp__pencil__batch_design` | Existing `pencil_mcp` handler |
| B | **PenBoard MCP** (`.penboard`/`.flow`) | In-VG MCP | ✅ Full automate via `mcp__penboard__batch_design` + `add_page` | Existing `penboard_mcp` handler |
| C | **AI HTML** (Opus emits HTML+Tailwind) | In-VG | ✅ Full automate (Opus + DESIGN.md tokens) | Existing `playwright_render` handler |
| D | **Claude design** (gstack:design-shotgun, design-consultation, design-html) | In-VG (gstack ecosystem) | 🟡 Semi-automate (variants generation auto, user picks) | Saves HTML → `playwright_render` |
| E | **Google Stitch** ([stitch.withgoogle.com](https://stitch.withgoogle.com/)) | External web | 🔴 No public API; instructional flow | User exports HTML/Figma → drops to `design_assets.paths/` |
| F | **v0 by Vercel** ([v0.app](https://v0.app/)) | External web/CLI | 🟡 Has CLI, paid; instructional + optional CLI hook | User exports HTML → drops in |
| G | **Figma** (`.fig` + manual PNG export) | External | 🔴 Existing `figma_fallback` instruction | User exports PNG manually |
| H | **Manual HTML** (designer writes by hand) | External | ✅ Trivial — drop into path | Existing `playwright_render` |

Galileo AI is excluded — it was [acquired by Google](https://www.banani.co/blog/galileo-ai-features-and-alternatives) and merged into Stitch. Uizard has an MCP server but its niche (wireframes) overlaps Pencil — defer to v2.17 if user demand surfaces.

## Decision matrix — recommend tool per project context

| Project context | Top recommendation | Rationale |
|---|---|---|
| Solo dev, no design budget, want fast scaffold | **A (Pencil MCP)** | Free, in-pipeline, MCP automates layout from text; binary output is best for L1-L6 verification |
| Has DESIGN.md tokens but no mockups | **C (AI HTML)** then A | Tokens injected into Opus prompt; HTML cheap; A as upgrade if HTML feels too generic |
| Wants visual exploration / variants before commit | **D (Claude design-shotgun)** | Multi-variant comparison board reuses gstack pattern; user picks 1 |
| Has external designer using Figma | **G (Figma)** | Designer-driven; VG provides drop folder + extract instruction |
| Wants Stitch's polished aesthetic | **E (Stitch)** | Best out-of-box look; manual export overhead acceptable for hero pages |
| Has v0 subscription, React shop | **F (v0)** | React-first export aligns with build target |
| Has hand-written HTML mockups already | **H (manual)** | Trivial; just configure path |
| Multi-surface project (web + mobile) | **A + G** mixed | Pencil for web, Figma for mobile (designer-shared) |

**Default for unfamiliar user**: AskUserQuestion → A (Pencil MCP) as recommendation, with full table shown for override.

## Sequencing rationale — 2 implementation waves

Wave A (MVP, ship in v2.16.0):
- D-01: `/vg:design-scaffold` entry command + tool selector + AskUserQuestion (~1.5h)
- D-02: Tool A (Pencil MCP) automated sub-flow + smoke (~3-4h)
- D-03: Tool C (AI HTML) automated sub-flow + smoke (~2-3h)
- D-04: Tools E/F/G/H instructional sub-flows (no automation, just routing) (~1.5h each, 6h total)
- D-05: `/vg:specs` routing — detect greenfield, suggest scaffold (~1h)
- D-06: Form B `no-asset:greenfield-*` severity:critical + accept gate hardening (~1h)
- D-07: validators registry catalog entries + install/update propagation (~30min)

Wave B (deepen automation, ship in v2.17.0):
- D-08: Tool B (PenBoard MCP) automated sub-flow (~3-4h)
- D-09: Tool D (Claude design-shotgun) integration via SlashCommand spawn (~2-3h)
- D-10: Tool F (v0) CLI hook for users with paid subscription (~2-3h)
- D-11: VIEW-COMPONENTS-aware scaffold (D-02 P19 output → tool input → tighter mockup) (~3-4h)

Wave A alone gives 70-80% greenfield value (covers solo dev + DESIGN.md + Figma + manual workflows). Wave B adds polish for power users.

## Out of scope (Phase 20)

- Reverse-engineering existing live UI into mockups (different problem; could be Phase 21)
- Programmatic Figma generation via Figma API (manual export is acceptable; API requires user OAuth)
- Mobile-specific mockup tools (Sketch, Marvel, ProtoPie) — defer until mobile profile dogfood
- Replacing `/vg:design-system` (DESIGN.md token management) — orthogonal; scaffold consumes its output
- Auto-detecting which tool is "best" for a project — keep user-driven
