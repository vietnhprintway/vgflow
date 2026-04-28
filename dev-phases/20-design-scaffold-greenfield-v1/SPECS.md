# Phase 20 — Design Scaffold for Greenfield — SPECS

**Version:** v1 (draft 2026-04-28)
**Total decisions:** 11 (D-01..D-11; D-08..D-11 deferred to Wave B / v2.17.0)
**Source:** ROADMAP-ENTRY.md (this folder)
**Critical reality check:** Existing `/vg:design-extract` already supports 4 input handlers (`playwright_render` for HTML, `passthrough` for PNG/JPG, `pencil_mcp` for `.pen`, `penboard_mcp` for `.penboard`/`.flow`, `figma_fallback` for `.fig`). Phase 20 does NOT change extract. It produces files that drop into `design_assets.paths/` so extract picks them up unchanged.

---

## Existing infra audit

| Component | Hiện trạng | P20 action |
|---|---|---|
| `commands/vg/design-system.md` | Manage DESIGN.md tokens (palette/typography/spacing). 58 brand variants from getdesign.md. | KEEP — scaffold consumes DESIGN.md as input |
| `commands/vg/design-extract.md` | Normalize 4 handlers → `manifest.json` + screenshots/refs/scans. | KEEP — scaffold output feeds in |
| `scripts/design-normalize.py` | Per-handler implementation: `playwright_render`, `passthrough`, `pencil_mcp`, `penboard_mcp`, `figma_fallback`, `xml`/`pb` legacy. | KEEP |
| `commands/vg/specs.md` | Phase requirements + scope discussion entry. | EXTEND (D-05) — detect greenfield, suggest scaffold |
| `commands/vg/_shared/vg-planner-rules.md` | Rule 8: `<design-ref>` mandate, Form A/B. | EXTEND (D-06) — Form B `no-asset:greenfield-*` severity:critical |
| `commands/vg/accept.md` | Override-debt threshold gate (P19 D-07). | EXTEND (D-06) — block accept if greenfield-* unresolved |
| MCP: `mcp__pencil__batch_design`, `mcp__penboard__batch_design` | Available in repo runtime. Programmatic mockup creation. | NEW USE (D-02, D-08) |
| `gstack:design-shotgun` / `design-consultation` / `design-html` | Available skills from gstack ecosystem. | NEW USE (D-09 — Wave B) |

**Critical implication:** Phase 20 = 1 new entry command (`/vg:design-scaffold`), 1 routing change in `/vg:specs`, 2 rule extensions (planner + accept). Existing extract pipeline untouched. ~600 LOC across 7 commits in Wave A.

---

## D-01 — `/vg:design-scaffold` entry command + tool selector

**Problem:** Greenfield projects have no on-ramp from "ROADMAP exists" → "mockups land in `design_assets.paths/`". User has no prompt asking which tool, no per-tool flow, no validation that output landed correctly.

**Decision:** New command `/vg:design-scaffold` at `commands/vg/design-scaffold.md`. Mirrors `/vg:design-system` structure (modes via flags). Single entry, dispatches to per-tool sub-flow.

**API:**

```
/vg:design-scaffold                            # interactive — full flow
/vg:design-scaffold --tool=<name>              # skip tool prompt
/vg:design-scaffold --pages=<list>             # restrict to specific page slugs from ROADMAP
/vg:design-scaffold --dry-run                  # preview what would be generated
/vg:design-scaffold --help-tools               # show decision matrix
```

**Tool names** (canonical IDs):
- `pencil-mcp` — Tool A (in-VG automated)
- `penboard-mcp` — Tool B (in-VG, Wave B)
- `ai-html` — Tool C (in-VG automated)
- `claude-design` — Tool D (gstack ecosystem, Wave B)
- `stitch` — Tool E (external instructional)
- `v0` — Tool F (external + optional CLI hook in Wave B)
- `figma` — Tool G (external instructional)
- `manual-html` — Tool H (no scaffold needed, just config)

**Step structure:**

```
<step name="0_validate_prereqs">
  - Read ROADMAP.md → extract page list (slugs from <page-slug> tags or task <design-ref> Form B markers).
  - Read DESIGN.md (project/role/phase per resolution priority from /vg:design-system).
  - If neither → BLOCK with guidance: "Run /vg:design-system --browse first to pick brand tokens".
  - Read .claude/vg.config.md → resolve design_assets.paths (or default).

<step name="1_detect_existing_assets">
  - Glob design_assets.paths → if any matches → ask user: "found N existing assets, run /vg:design-extract directly OR scaffold ADDITIONAL pages?".

<step name="2_tool_selector">
  - If --tool=X provided → skip prompt, validate X is known.
  - Else AskUserQuestion with decision matrix table + recommendation:
    "Page list: <N pages from roadmap>. DESIGN.md: <yes|no>.
     Recommended: pencil-mcp (free, in-pipeline). Alternatives: ai-html, claude-design, stitch, v0, figma, manual-html.
     Pick one (or 'help' for matrix)."

<step name="3_per_tool_dispatch">
  - case $tool in pencil-mcp) source per-tool sub-flow at lib/scaffold-pencil.sh ;;
                  ai-html)    source lib/scaffold-ai-html.sh ;;
                  ... (one branch per tool)

<step name="4_validate_output">
  - For each tool's expected output extension:
    - Glob the expected paths.
    - If 0 files → BLOCK with tool-specific remediation.
    - Else → log scaffold telemetry event.

<step name="5_auto_extract">
  - SlashCommand: /vg:design-extract --auto
  - Verify manifest.json updated.

<step name="6_resume_pipeline">
  - Print: "Scaffold complete. <N> mockups land. Resume /vg:blueprint <phase> when ready."
```

**File changes:**
- `commands/vg/design-scaffold.md` — new ~250 LOC
- `commands/vg/_shared/lib/scaffold-{pencil,penboard,ai-html,stitch,v0,figma,manual,claude-design}.sh` — 8 new helpers, 30-150 LOC each
- `templates/vg/vg.config.template.md` — add `design_scaffold:` config block (default tool, fallback paths)

**Effort:** 1.5h entry shell + dispatch + validation + extraction wire (excluding per-tool sub-flows).

**Risk:** LOW. Pure additive command; no impact on existing flows unless user invokes it.

---

## D-02 — Tool A (Pencil MCP) automated sub-flow

**Problem:** Pencil MCP is the strongest in-VG option (free, automated, binary output ideal for downstream gates). No existing scaffold uses it programmatically — only design-extract reads existing `.pen` files.

**Decision:** Spawn Opus subagent with these inputs and tool grants:
- DESIGN.md tokens (color/typography/spacing)
- Page list from ROADMAP.md (slug + 1-line description per page)
- Project profile (admin SPA / public site / dashboard / mobile-rn)
- MCP tool access: `mcp__pencil__open_document`, `mcp__pencil__batch_design`, `mcp__pencil__set_themes`, `mcp__pencil__set_variables`, `mcp__pencil__save_document`

**Agent prompt (compact):**
```
You are a Pencil MCP design scaffolder. For each page in <page_list>, create a
.pen file at design_assets.paths/{slug}.pen with:
  1. open_document('new')  → empty .pen
  2. set_themes from DESIGN.md tokens (translate palette/typography/spacing)
  3. batch_design ops to compose the page layout from page description
     - Use semantic component names (Sidebar, TopBar, MainContent, KPICard, etc.)
     - Position per project profile defaults (sidebar 240px for admin SPA, etc.)
  4. save_document → produces .pen file

DO NOT invent components beyond page description. Match the page TYPE
(list / form / dashboard / wizard / detail) declared in ROADMAP.md.
Output: { "files": [{slug, path, status}] } JSON to stdout when complete.
```

**Output convergence:**
- Files: `${design_assets.paths}/<slug>.pen`
- Existing `pencil_mcp` handler in design-extract picks up automatically

**Validation:**
- Each expected slug has a `.pen` file ≥ 100 bytes (sanity)
- Subsequent `/vg:design-extract` runs without error

**Cost:** ~$0.10-0.20/page Opus (vision + MCP tool calls). Phase with 5 pages ≈ $1.

**Effort:** 3-4h (prompt design + MCP tool grants + smoke on 2 fixture pages).

**Risk:** MEDIUM. Pencil MCP `batch_design` op syntax is strict (per skill instruction "MAKE SURE TO FOLLOW THE OPERATION SYNTAX"). Wrong syntax = fails silently. Mitigation: include MCP skill `pencil` doc in agent context.

---

## D-03 — Tool C (AI HTML) automated sub-flow

**Problem:** Pencil MCP requires the runtime to have `mcp__pencil__*` tools available. Standard installs without Pencil MCP need a fallback. Plain HTML is universal, cheaper, and doesn't depend on optional MCP servers.

**Decision:** Spawn Opus to write HTML+Tailwind mockup per page. Output drops to `${design_assets.paths}/<slug>.html` and existing `playwright_render` handler converts to PNG + structural HTML.

**Agent prompt:**
```
Generate static HTML+Tailwind mockup for page <slug>: <description>.
Constraints:
  1. Use ONLY Tailwind utility classes; no inline styles, no scripts beyond
     basic state toggles (data-* attributes).
  2. Apply DESIGN.md tokens via Tailwind theme extension OR by mapping
     hex/spacing to nearest Tailwind value. Inline a <style> block with
     CSS variables matching tokens.
  3. Layout per project profile (admin SPA: full Sidebar+TopBar+MainContent).
     Match page TYPE declared in ROADMAP (list/form/dashboard/wizard/detail).
  4. Include realistic copy for headings, button labels, table headers,
     form fields. Lorem ipsum is BANNED — use plausible domain text.
  5. Self-contained: no external CSS/JS imports beyond a Tailwind CDN <script>.
  6. Single file, no separate JS/CSS.
  7. Include semantic HTML (header/main/nav/aside/section) — playwright_render
     extracts structural-html from this.

Output: pure HTML file content. No markdown fences. No commentary.
```

**Cost:** ~$0.05-0.10/page Opus. Cheaper than D-02 because no MCP tool overhead.

**Output:** `${design_assets.paths}/<slug>.html`

**Effort:** 2-3h.

**Risk:** MED-LOW. AI-generated HTML without designer eye risks generic look. Mitigation: D-09 (Wave B) escalates to design-shotgun for variants if user dissatisfied with first pass.

**Trade-off vs D-02:** HTML is more inspectable (designer can hand-edit) but visually-imagined (AI generated, no real-world reference). Pencil MCP is more constrained-by-tokens but binary (less editable post-gen). Both valid; user picks per project.

---

## D-04 — Tools E/F/G/H instructional sub-flows

**Problem:** Stitch, v0, Figma, manual HTML are external — VG cannot drive them programmatically (Stitch has no public API; v0 export is paid + CLI-limited; Figma export is manual; manual is by definition manual). But VG can ROUTE the user with explicit instructions and verify the output landed.

**Decision:** Per-tool instruction prompt printed via `AskUserQuestion`/echo, followed by a wait-for-files validation loop.

### Tool E — Stitch

```
Print:
  ╭─ Google Stitch ────────────────────────────────────────────╮
  │ 1. Open https://stitch.withgoogle.com/                      │
  │ 2. Use 5-screen canvas (free tier 350 generations/month).   │
  │ 3. Describe each page with prompt template below.           │
  │ 4. Export each page as HTML (Stitch → Export → HTML/CSS).   │
  │ 5. Save HTML files to: ${design_assets.paths[0]}/<slug>.html│
  │ 6. Press Enter when all <N> files are saved.                │
  ╰─────────────────────────────────────────────────────────────╯

Print prompt template per page:
  "Page: {slug}
   Type: {list/form/dashboard/...}
   Description: {1-line from ROADMAP}
   Tokens: {palette + typography from DESIGN.md (compact)}"

AskUserQuestion (with timeout 1 hour OR explicit user 'continue'):
  "Press [c]ontinue when files saved | [s]kip | [r]edo prompt"
```

### Tool F — v0

Same as Stitch but with v0 URL ([v0.app](https://v0.app/)) and React export note. Wave B may add `npx v0 generate` CLI hook for users with paid subscription.

### Tool G — Figma

Reuses existing `figma_fallback` instruction in `scripts/design-normalize.py`. Scaffold layer just routes user to it:

```
Print:
  ╭─ Figma ──────────────────────────────────────────────────────╮
  │ 1. Open Figma → create file with frames per page in ROADMAP.│
  │ 2. Apply DESIGN.md tokens manually (palette + spacing).      │
  │ 3. For each frame: Export → PNG (2x).                        │
  │ 4. Save .fig file + .png exports to:                         │
  │      ${design_assets.paths[0]}/{slug}.fig (optional)        │
  │      ${design_assets.paths[0]}/{slug}.png (REQUIRED)        │
  ╰──────────────────────────────────────────────────────────────╯
```

### Tool H — manual HTML

```
Print:
  ╭─ Manual HTML ────────────────────────────────────────────────╮
  │ Save your hand-written HTML mockups to:                      │
  │   ${design_assets.paths[0]}/{slug}.html                      │
  │ Each file: self-contained, semantic HTML, optional Tailwind. │
  │ /vg:design-extract will render to PNG via Playwright.        │
  ╰──────────────────────────────────────────────────────────────╯
```

**Validation loop (all four):**
```bash
EXPECTED_SLUGS=(slug1 slug2 ...)
ATTEMPTS=0
while [ $ATTEMPTS -lt 6 ]; do  # 6 × 10min wait = 1 hour ceiling
  MISSING=()
  for slug in "${EXPECTED_SLUGS[@]}"; do
    found=0
    for ext in html png fig pen; do
      [ -f "${design_assets.paths[0]}/${slug}.${ext}" ] && found=1 && break
    done
    [ $found -eq 0 ] && MISSING+=("$slug")
  done
  [ ${#MISSING[@]} -eq 0 ] && break
  echo "Missing: ${MISSING[*]}. Press [c]ontinue when ready, [s]kip, or wait..."
  AskUserQuestion: ...
done
```

**Effort:** 6h total (1.5h × 4 tools, mostly prompt copy + validation loop).

**Risk:** LOW. No automation; just routing. Worst case user skips → Form B path engages with severity:critical.

---

## D-05 — `/vg:specs` greenfield detection routing

**Problem:** User running `/vg:phase` on greenfield reaches `/vg:blueprint` step 4b, which BLOCKs with "design assets missing". User has to read error, find `/vg:design-extract`, realize it's empty, eventually find scaffold. Friction.

**Decision:** `/vg:specs` (early in pipeline) detects greenfield state and proactively suggests scaffold path:

```bash
# After /vg:specs gathers requirements:
NEEDS_FE=$(grep -cE "(apps/(admin|web|merchant|vendor)|packages/ui)" "${PHASE_DIR}/SPECS.md" || echo 0)
HAS_DESIGN_MD=$(test -f "${PLANNING_DIR}/design/DESIGN.md" && echo 1 || echo 0)
HAS_MOCKUPS=$(find "${design_assets.paths[0]:-/dev/null}" -type f 2>/dev/null | head -1 | wc -l)

if [ "$NEEDS_FE" -gt 0 ]; then
  if [ "$HAS_DESIGN_MD" = "0" ]; then
    echo "ℹ This phase has FE work but no DESIGN.md. Recommend:"
    echo "    /vg:design-system --browse  OR  --create"
  fi
  if [ "$HAS_MOCKUPS" = "0" ]; then
    echo "ℹ No mockups detected at design_assets.paths. Recommend:"
    echo "    /vg:design-scaffold       (interactive tool selector)"
    echo "    /vg:design-scaffold --tool=pencil-mcp   (auto-generate via Pencil MCP)"
    echo ""
    echo "  Without mockups, planner Rule 8 will require Form B"
    echo "  ('no-asset:greenfield-*'), and accept gate will BLOCK on stack."
  fi
fi
```

Doesn't BLOCK — just suggests. User retains agency.

**File changes:** `commands/vg/specs.md` — add post-discovery suggestion block (~30 LOC).

**Effort:** 1h.

**Risk:** LOW.

---

## D-06 — Form B `no-asset:greenfield-*` raised to severity:critical

**Problem:** Currently Form B `<design-ref>no-asset:reason</design-ref>` logs override-debt severity:medium and continues. For greenfield, this is the silent-failure escape hatch — every gate skipped, AI ships imagined UI.

**Decision:** Two-pronged:

1. **Planner-side detection** (`vg-planner-rules.md` Rule 8 update):
   - Form B reasons starting with `greenfield-` (e.g. `greenfield-no-mockup`, `greenfield-stitch-pending`) get **severity:critical** in override-debt.
   - Other Form B reasons stay severity:medium (legitimate gaps like "wizard-step3-not-extracted-yet" are different category).

2. **Accept gate hardening** (`accept.md` step 3c, P19 D-07 gate extension):
   - `verify-override-debt-threshold.py` already has `--kind 'design-*'`. Add second invocation: `--kind 'design-greenfield-*' --threshold 1` (any single greenfield Form B in phase BLOCKs accept).
   - Override `--allow-greenfield-shipped` requires rationalization-guard with concrete rationale (not just "ship it").

3. **Suggestion in BLOCK message:**
   ```
   ⛔ Phase has 1 greenfield design Form-B entry. Resolution:
      /vg:design-scaffold    (recommended — generates mockup in-place)
      OR
      /vg:override-resolve <ID> --rationale="<why ship without design>"
   ```

**File changes:**
- `commands/vg/_shared/vg-planner-rules.md` Rule 8 (~15 LOC)
- `commands/vg/accept.md` step 3c — add second validator call (~20 LOC)
- `scripts/validators/verify-override-debt-threshold.py` — already supports glob; just configure call site

**Effort:** 1h.

**Risk:** LOW-MED. May break greenfield projects mid-flight if they're using Form B as expected escape. Mitigation: ship behind config flag `accept_gates.greenfield_block: false` for first release; flip true after dogfood validates `/vg:design-scaffold` actually works for users.

---

## D-07 — validators registry + install/update propagation

**Problem:** Phase 19 lesson — new validators must register in `scripts/validators/registry.yaml` to surface in `/vg:doctor`, `/vg:gate-stats`, drift checks. Phase 20 adds 0 new validators (D-06 reuses existing `verify-override-debt-threshold.py`), but the new `/vg:design-scaffold` command should appear in Codex mirrors.

**Decision:**
1. After D-01..D-06 land, run `bash scripts/generate-codex-skills.sh --force` to regenerate `codex-skills/vg-design-scaffold/` mirror.
2. CI gate from v2.15.3 will catch any drift if step 1 forgotten.
3. install.sh recursive `cp` already covers new command + helpers.
4. /vg:update path mapping covers `commands/vg/*.md` already.

**No code change.** This decision exists to make explicit that the regen step is required at release time.

**Effort:** 30min (run + commit + verify CI).

**Risk:** ZERO — process documentation only.

---

## Wave B decisions (deferred to v2.17.0)

### D-08 — Tool B (PenBoard MCP) automated

PenBoard MCP equivalent of D-02. More complex because PenBoard has flows + docs + entities + connections — multi-page workspace versus single-file `.pen`. Likely requires VIEW-COMPONENTS.md from P19 D-02 as input to lay out pages with consistent navigation.

**Effort:** 3-4h.

### D-09 — Tool D (Claude design-shotgun) integration

Spawn `gstack:design-shotgun` via SlashCommand. design-shotgun produces variants → user picks → design-html finalizes. Output: HTML files saved to `design_assets.paths`. Wraps existing gstack ecosystem cleanly.

**Effort:** 2-3h. Risk: gstack skill availability not guaranteed across all installs (gstack is opt-in plugin).

### D-10 — Tool F (v0) CLI hook

For users with paid v0 subscription, add optional `npx v0 generate <prompt>` CLI hook that pulls component code into `design_assets.paths`. Skipped if `v0` CLI not on PATH or unauthenticated.

**Effort:** 2-3h.

### D-11 — VIEW-COMPONENTS-aware scaffold

After P19 D-02 runs once (vision view-decomposition), feed the canonical component list back into D-02/D-03 as authoritative input. Tighter mockups: instead of "design HomePage", "design HomePage with [Sidebar, TopBar, KPICard×3, GettingStartedPanel]". Closes the loop between scaffold output and downstream verification.

**Effort:** 3-4h. Requires Wave A stable + dogfood data.

---

## Acceptance smoke fixtures (Wave A)

`dev-phases/20-design-scaffold-greenfield-v1/fixtures/`:

1. **Greenfield admin SPA fixture** — empty project, ROADMAP with 3 pages (HomeDashboard, SettingsPanel, UsersList). Run `/vg:design-scaffold --tool=pencil-mcp` → 3 .pen files appear. `/vg:design-extract` produces 3 entries in manifest.json. `/vg:blueprint` resumes with valid `<design-ref>` slugs.

2. **Greenfield with DESIGN.md fixture** — same as above + `/vg:design-system --import="ssp-admin-stripe-clean"` first. Token application verified by inspecting Pencil JSON for token references.

3. **Stitch routing fixture** — instruction prompt printed correctly, validation loop waits for user file save, completes when files appear.

4. **Form B critical block fixture** — phase with `<design-ref>no-asset:greenfield-no-time</design-ref>`, attempt /vg:accept → BLOCK with suggestion to run /vg:design-scaffold.

5. **Multi-tool mixed fixture** — 5 pages, user picks pencil-mcp for 3 + figma for 2. Both sub-flows complete, manifest.json has 5 entries.

End-to-end: dogfood Phase 20 itself by treating it as a greenfield "FE phase" (it isn't, but the fixture stands).

---

## Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| D-02 Pencil MCP `batch_design` syntax brittleness | MED | MED | Inject `pencil` skill doc into agent context; smoke 2 fixtures before ship |
| D-03 AI HTML output too generic — users still complain | MED | MED | Form B `greenfield-*` blocks at accept; force user to upgrade to D / E / G; dogfood feedback loop |
| D-04 user abandons external flow midway | HIGH | LOW | Validation loop has 1-hour timeout + skip option; Form B captures the abandon |
| D-06 critical block breaks legitimate phases | LOW | HIGH | Config flag `accept_gates.greenfield_block` default false in v2.16.0; flip true v2.17.0 |
| Cost balloon (Opus per page × N pages × M iterations) | MED | MED | Default `--pages` to single-page; user opts into bulk; cache by ROADMAP hash |
| Tool ecosystem churn (Stitch API ships, v0 export changes) | HIGH | LOW | External tools are routed-only; updating instruction text is a doc PR |

## Open questions

1. **Default tool when user picks "auto"**: pencil-mcp (binary, automated) vs ai-html (cheaper, more inspectable). Recommend pencil-mcp because L1-L6 prefer binary but flag for user discussion.
2. **Multi-page bulk vs page-by-page interactive**: bulk faster, page-by-page allows mid-flight correction. Recommend bulk default with `--interactive` opt-in.
3. **Should `/vg:design-scaffold` regenerate mockups when DESIGN.md changes?** I.e. token version awareness. Skip for Wave A; revisit if dogfood shows token-drift issues.
4. **Wave A vs B split — is D-04 instructional sub-flow really needed in Wave A?** Could ship Wave A with only A+C automated and route everything else to "manual: drop file in path" until Wave B. Faster ship but worse UX. Lean toward Wave A as scoped (covers all 8 tools) for completeness.
