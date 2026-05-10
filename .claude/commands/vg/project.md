---
name: vg:project
description: Entry point — project identity + foundation + auto-init via 7-round adaptive discussion. Replaces standalone /vg:init.
argument-hint: "[description] [--view] [--update] [--milestone] [--rewrite] [--migrate] [--init-only] [--auto @doc.md]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
  - BashOutput
mutates_repo: true
runtime_contract:
  must_emit_telemetry:
    - event_type: "project.started"
    - event_type: "project.completed"
---

<NARRATION_POLICY>
**⛔ DO NOT USE TodoWrite / TaskCreate / TaskUpdate.**

Use markdown headers in your text output between tool calls (e.g. `## ━━━ Round 3: Tech ambiguities ━━━`). Long Bash > 30s → `run_in_background: true` + `BashOutput` polls.

**Translate English terms (RULE)** — output có thuật ngữ tiếng Anh PHẢI thêm giải thích VN trong dấu ngoặc tại lần đầu xuất hiện. Tham khảo `_shared/term-glossary.md`. Ví dụ: `Foundation (nền tảng)`, `migrate (chuyển đổi)`, `merge (gộp) NOT overwrite (ghi đè)`, `legacy-v1 (định dạng cũ v1)`, `greenfield (dự án mới)`, `brownfield (dự án có codebase)`. Không áp dụng: file path (`PROJECT.md`), code identifier (`D-XX`, `pnpm`), config tag values (`web-saas`), lần lặp lại trong cùng message.
</NARRATION_POLICY>

<rules>
1. **Single entry point** — replaces `/vg:init`. `/vg:init` is now a soft alias for `/vg:project --init-only`.
2. **7-round adaptive discussion** — heavy by design (high-precision projects). Skip rounds where no ambiguity, but never skip Round 4 (high-cost gate).
3. **Three artifacts written atomically** — `PROJECT.md`, `FOUNDATION.md`, `vg.config.md`. All-or-nothing commit.
4. **Foundation = load-bearing** — drives roadmap/init/scope/add-phase. Drift detection ở downstream commands.
5. **MERGE NOT OVERWRITE** — re-runs preserve existing decisions. Only [w] Rewrite resets (with backup).
6. **Resumable** — `${PLANNING_DIR}/.project-draft.json` checkpoints every round. Interrupt-safe.
7. **Brownfield aware** — `--migrate` extracts foundation from existing PROJECT.md + codebase scan.
</rules>

<objective>
First command in VG pipeline. Captures project identity, derives foundation (8 platform/runtime/data/auth/hosting/distribution/scale/compliance dimensions), and auto-generates `vg.config.md` from foundation. All downstream commands (roadmap, scope, blueprint) consume FOUNDATION.md.

Pipeline: **project** → roadmap → map → prioritize → specs → scope → blueprint → build → review → test → accept
</objective>

<process>

### Preflight section (extracted v2.71.0 T1)

Read `_shared/project/preflight.md` and follow it exactly.
Includes 3 steps: 0_parse_args, 0b_print_state_summary, 0c_scan_existing_docs.

### Routing section (extracted v2.71.0 T2)

Read `_shared/project/routing.md` and follow it exactly.
Includes 4 steps: 1_route_mode, 2a_resume_check, 2b_mode_menu, 3_mode_view.

### First-time mode (Rounds 1-9, extracted v2.71.0 T3 — LARGEST section)

Read `_shared/project/first-time-rounds.md` and follow it exactly.
Includes 1 step + 9 rounds: 4_mode_first_time + Round 1 (Capture description), Round 2 (Parse + overview), Round 3 (Targeted dialog), Round 4 (Confirmation gate — MANDATORY), Round 5 (Constraints fill-in), Round 6 (Auto-derive vg.config.md), Round 7 (Architecture Lock), Round 8 (Security Testing Strategy), Round 9 (Atomic write + commit).

<!-- BEGIN_LEGACY_FIRST_TIME_PLACEHOLDER (extracted to _shared/project/first-time-rounds.md) -->
<!-- END_LEGACY_FIRST_TIME_PLACEHOLDER -->

### Update modes (extracted v2.71.0 T4)

Read `_shared/project/update-modes.md` and follow it exactly.
Includes 3 steps: 5_mode_update, 6_mode_milestone, 7_mode_rewrite.


### Migrate + init-only + complete (extracted v2.71.0 T5 — final extraction)

Read `_shared/project/migrate-and-init.md` and follow it exactly.
Includes 3 steps: 8_mode_migrate, 9_mode_init_only, 10_complete.


</process>

## FOUNDATION.md template

```markdown
# Foundation — {Project Name}

**Locked:** {ISO timestamp}
**Source:** {first-time | --update | --migrate | --rewrite}
**Source description:** {first 200 chars of user description}

## 1. Platform & Topology (8 dimensions)

**Namespace:** All FOUNDATION decisions use `F-XX` (project-level, stable across milestones). Per-phase decisions live in `${PLANNING_DIR}/phases/*/CONTEXT.md` as `P{phase}.D-XX`.

| # | Dimension | Value | Decision | Confidence |
|---|-----------|-------|----------|------------|
| 1 | Platform type | web-saas / mobile-native / mobile-cross / desktop / cli / hybrid | F-01 | derived/confirmed |
| 2 | Frontend runtime | browser / iOS / Android / Electron / none | F-02 | ... |
| 3 | Frontend framework | React+Vite / Next.js / Vue+Vite / Svelte / Flutter / RN / native-iOS / native-Android | F-03 | ... |
| 4 | Backend topology | none / monolith / microservices / serverless / edge / BaaS | F-04 | ... |
| 5 | Data layer | none / Postgres / MySQL / SQLite / MongoDB / Redis / blob / hybrid | F-05 | ... |
| 6 | Auth model | none / own / OAuth / SSO / passwordless / 3rd-party (Auth0/Clerk) | F-06 | ... |
| 7 | Hosting | VPS / AWS / GCP / Vercel / Netlify / on-prem / app-store / hybrid | F-07 | ... |
| 8 | Distribution | URL / app-store / npm / docker-hub / physical-device | F-08 | ... |

## 2. Tech Stack (concrete choices, derived from above)

- Frontend: {framework + key libs} (F-XX)
- Backend: {framework + key libs} (F-XX)
- Database: {engine + version} (F-XX)
- Build/monorepo: {pnpm+turborepo / npm / cargo / go-mod / ...} (F-XX)
- Test: {vitest / jest / pytest / playwright / maestro / ...} (F-XX)
- Deploy: {SSH+PM2 / git-push / docker / Ansible / ...} (F-XX)

## 3. Constraints

- **Scale:** ~{N users, X QPS}
- **Latency budget:** {p50/p99 targets}
- **Compliance:** {none / GDPR / HIPAA / SOC2 / multiple}
- **Team size:** {solo / 2-5 / 6-20 / 20+}
- **Budget tier:** {hobbyist / bootstrapped / funded / enterprise}

## 4. Decisions

### F-01: Platform = {value}
**Reasoning:** {derivation/discussion summary}
**Reverse cost:** HIGH/MEDIUM/LOW — {what breaks if reversed}
**Confirmed:** {date} by user
**Source:** {description / Round 4 confirm / scan / migration}

(F-02 ... F-N — same structure)

**Namespace rule:** These IDs are `F-XX` (Foundation-scope). Do NOT reuse `D-XX` — that's reserved for per-phase CONTEXT.md as `P{phase}.D-XX`.

## 5. Open Questions

{none if all locked, else list of Q-XX with proposed defaults}

## 6. Drift Check

**Last check:** {date}  
**Status:** ✅ no drift / ⚠ drift detected (see below)  
**Drift entries:** {none, or phase {X} introduced keyword 'mobile' — review platform decision}
```

## vg.config.md derivation rules (Round 6 logic)

**v1.13.0+ (2026-04-18):** Logic lives in `.claude/scripts/vg_generate_config.py`.
This markdown table is reference-only — the authoritative derivation tables
(`FRAMEWORK_PORT`, `BACKEND_PORT`, `BACKEND_HEALTH`, `DATA_PORT`,
`HOSTING_DEPLOY_PROFILE`, `TEST_RUNNER_BY_STACK`) are constants at the top
of `vg_generate_config.py`. Update there, not here.

The generator also emits dynamic blocks: `crossai_clis` / `models` scale with
`team_size`; `services` + `credentials` + `apps` + `infra_deps.services`
derive from `data` / `auth.roles` / `monorepo.apps` / etc. Template:
`.claude/templates/vg/vg.config.template.md` (~700 lines, full schema).

Reference table (indicative — check script for current values):

| Foundation field | → vg.config.md fields |
|------------------|----------------------|
| `frontend.framework: vite` | `worktree_ports.base.web: 5173`, `dev_command: {pm} dev` |
| `frontend.framework: next` | `worktree_ports.base.web: 3000` |
| `backend.framework: fastify` | `worktree_ports.base.api: 3001`, `health: /health` |
| `backend.framework: express` | `worktree_ports.base.api: 3000` |
| `hosting: vps` | `deploy_profile: pm2`, `run_prefix: ssh {{ssh_alias}}` |
| `hosting: vercel` | `deploy_profile: git_push` |
| `data.primary: postgres` | `ports.database: 5432`, `services.local.postgres check` |
| `data.primary: mongodb` | `ports.database: 27017`, `services.local.mongodb check` |
| `monorepo: turborepo` | `build_gates.typecheck_cmd: pnpm turbo typecheck` |
| `team_size: solo` | `models.executor: sonnet`, `models.planner: opus` (cost-aware) |
| `team_size: 6-20+` | `models.executor: opus`, `crossai_clis: [codex, gemini]` (quality-priority) |

User only asked về fields marked `<ASK>` (typically: ssh_alias, deploy.path, domain, secrets). Other fields auto-fill silent.

## Resumable draft format

`${PLANNING_DIR}/.project-draft.json`:
```json
{
  "started_at": "2026-04-17T...",
  "current_round": 4,
  "captured": {
    "description": "<user free-form>",
    "template_responses": {...}
  },
  "derived": {
    "foundation_v1": {
      "platform": "web-saas",
      "frontend_framework": "vite",
      ...
    },
    "ambiguities": [
      {"dim": "auth", "options": ["own", "oauth"], "default": "own"}
    ]
  },
  "decisions": [
    {"id": "F-01", "dim": "platform", "value": "web-saas", "confirmed": true, "round": 4}
  ],
  "status": "in_progress"
}
```

Atomic write after every round (write to `.project-draft.json.tmp` → rename).

## Telemetry

Each `/vg:project` invocation logs to telemetry:
```jsonl
{"ts": "...", "cmd": "vg:project", "mode": "first_time|update|...", "rounds_completed": N, "foundation_changed": true|false, "config_changed": true|false}
```

## Success criteria

- First-time run produces 3 atomic artifacts: PROJECT.md + FOUNDATION.md + vg.config.md
- Re-run with no flag → mode menu (View default)
- `--update`, `--milestone`, `--rewrite`, `--migrate`, `--init-only`, `--view` all routable
- Draft checkpointed every round, resumable on interrupt
- High-cost confirm gate (Round 4) NEVER skipped
- Existing decisions F-XX preserved across `--update` (MERGE NOT OVERWRITE)
- **Namespace enforcement:** FOUNDATION.md uses `F-XX`; phase CONTEXT.md uses `P{phase}.D-XX`. Legacy bare `D-XX` accepted until v1.10.0, then rejected. Migration tool: `.claude/scripts/migrate-d-xx-namespace.py`
- `--rewrite` always backs up to `.archive/{ts}/`
- vg.config.md auto-derived 80-90%, only `<ASK>` fields prompt user
- Foundation drift detection in roadmap/add-phase/scope (separate commands)
