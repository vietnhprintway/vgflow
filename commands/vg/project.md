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
---

<NARRATION_POLICY>
**⛔ DO NOT USE TodoWrite / TaskCreate / TaskUpdate.**

Use markdown headers in your text output between tool calls (e.g. `## ━━━ Round 3: Tech ambiguities ━━━`). Long Bash > 30s → `run_in_background: true` + `BashOutput` polls.
</NARRATION_POLICY>

<rules>
1. **Single entry point** — replaces `/vg:init`. `/vg:init` is now a soft alias for `/vg:project --init-only`.
2. **7-round adaptive discussion** — heavy by design (high-precision projects). Skip rounds where no ambiguity, but never skip Round 4 (high-cost gate).
3. **Three artifacts written atomically** — `PROJECT.md`, `FOUNDATION.md`, `vg.config.md`. All-or-nothing commit.
4. **Foundation = load-bearing** — drives roadmap/init/scope/add-phase. Drift detection ở downstream commands.
5. **MERGE NOT OVERWRITE** — re-runs preserve existing decisions. Only [w] Rewrite resets (with backup).
6. **Resumable** — `.planning/.project-draft.json` checkpoints every round. Interrupt-safe.
7. **Brownfield aware** — `--migrate` extracts foundation from existing PROJECT.md + codebase scan.
</rules>

<objective>
First command in VG pipeline. Captures project identity, derives foundation (8 platform/runtime/data/auth/hosting/distribution/scale/compliance dimensions), and auto-generates `vg.config.md` from foundation. All downstream commands (roadmap, scope, blueprint) consume FOUNDATION.md.

Pipeline: **project** → roadmap → map → prioritize → specs → scope → blueprint → build → review → test → accept
</objective>

<process>

<step name="0_parse_args">
## Step 0: Parse args + load config

```bash
PLANNING_DIR=".planning"
PROJECT_FILE="${PLANNING_DIR}/PROJECT.md"
FOUNDATION_FILE="${PLANNING_DIR}/FOUNDATION.md"
CONFIG_FILE=".claude/vg.config.md"
DRAFT_FILE="${PLANNING_DIR}/.project-draft.json"
ARCHIVE_DIR="${PLANNING_DIR}/.archive"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$PLANNING_DIR"

# Mode flags (mutually exclusive)
MODE=""
DOC_PATH=""
INLINE_DESC=""

for arg in $ARGUMENTS; do
  case "$arg" in
    --view)        MODE="view" ;;
    --update)      MODE="update" ;;
    --milestone)   MODE="milestone" ;;
    --rewrite)     MODE="rewrite" ;;
    --migrate)     MODE="migrate" ;;
    --init-only)   MODE="init_only" ;;
    --auto)        MODE="auto" ;;
    @*)            DOC_PATH="${arg#@}" ;;
    *)             INLINE_DESC="${INLINE_DESC} ${arg}" ;;
  esac
done

INLINE_DESC=$(echo "$INLINE_DESC" | sed 's/^ *//; s/ *$//')

PROJECT_EXISTS=false; [ -f "$PROJECT_FILE" ] && PROJECT_EXISTS=true
FOUNDATION_EXISTS=false; [ -f "$FOUNDATION_FILE" ] && FOUNDATION_EXISTS=true
CONFIG_EXISTS=false; [ -f "$CONFIG_FILE" ] && CONFIG_EXISTS=true
DRAFT_EXISTS=false; [ -f "$DRAFT_FILE" ] && DRAFT_EXISTS=true

HAS_CODE=false
for d in apps src packages lib; do
  [ -d "$d" ] && HAS_CODE=true && break
done

echo "Mode=${MODE:-auto-detect}  project=${PROJECT_EXISTS}  foundation=${FOUNDATION_EXISTS}  config=${CONFIG_EXISTS}  draft=${DRAFT_EXISTS}  brownfield=${HAS_CODE}"
```
</step>

<step name="1_route_mode">
## Step 1: Route to mode

If `MODE` not explicitly set, auto-detect:
- Draft exists → ask resume/discard (route → resume_draft)
- Project + Foundation exist → route to **mode_menu** (ask user intent: View/Update/Milestone/Rewrite/Migrate)
- Project exists but Foundation missing → route to **migrate** (auto-suggested)
- Nothing exists → route to **first_time** (full 7 rounds)

```bash
if [ -z "$MODE" ]; then
  if [ "$DRAFT_EXISTS" = "true" ]; then
    MODE="resume_check"
  elif [ "$PROJECT_EXISTS" = "true" ] && [ "$FOUNDATION_EXISTS" = "true" ]; then
    MODE="mode_menu"
  elif [ "$PROJECT_EXISTS" = "true" ] && [ "$FOUNDATION_EXISTS" = "false" ]; then
    echo "⚠ PROJECT.md exists but FOUNDATION.md missing — migration recommended."
    MODE="migrate_suggested"
  else
    MODE="first_time"
  fi
fi
```

Branch on `MODE` — see step blocks below for each.
</step>

<step name="2a_resume_check">
## Step 2a: Resume draft check (if `.project-draft.json` exists)

Read draft, show progress, ask user:

```bash
if [ "$MODE" = "resume_check" ]; then
  ${PYTHON_BIN} - "$DRAFT_FILE" <<'PY'
import json, sys, datetime
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ts = d.get("started_at", "?")
try:
  started = datetime.datetime.fromisoformat(ts)
  age_min = int((datetime.datetime.now(started.tzinfo) - started).total_seconds() / 60)
except Exception:
  age_min = "?"
print(f"Draft from {ts} (age {age_min}m), at Round {d.get('current_round','?')}/7")
print(f"Captured description: {d.get('captured', {}).get('description', '(none)')[:120]}...")
PY
fi
```

Use AskUserQuestion:
- "Resume draft from Round X?" → [r] Resume / [d] Discard + restart / [v] View draft only

If resume → load draft state → jump to current round.
If discard → `rm -f $DRAFT_FILE` → set `MODE=first_time`.
If view → pretty-print draft → exit.
</step>

<step name="2b_mode_menu">
## Step 2b: Mode menu (when artifacts exist, no explicit mode flag)

Use AskUserQuestion with exact wording:

```
"PROJECT.md + FOUNDATION.md đã tồn tại. Bạn muốn:
 [v] View          — In hiện trạng, không đổi gì (default safe)
 [u] Update        — Discussion bổ sung, MERGE giữ phần không touch
 [m] New milestone — Append milestone mới + mô tả mục tiêu
 [w] Rewrite       — Reset toàn bộ (backup → .archive/{ts}/, full re-run)"
```

Map answer to MODE: v→view, u→update, m→milestone, w→rewrite. Default if cancelled = view.
</step>

<step name="3_mode_view">
## Step 3 (mode=view): Pretty-print current state

```bash
if [ "$MODE" = "view" ]; then
  echo ""
  echo "## ━━━ Project Overview ━━━"
  echo ""
  if [ -f "$FOUNDATION_FILE" ]; then
    # Print Foundation table + Decisions section
    sed -n '/^## Platform/,/^## Open/p' "$FOUNDATION_FILE"
    echo ""
    sed -n '/^## Decisions/,/^## /p' "$FOUNDATION_FILE" | head -60
  else
    echo "(no FOUNDATION.md — run /vg:project --migrate to create)"
  fi
  echo ""
  echo "## ━━━ Project ━━━"
  [ -f "$PROJECT_FILE" ] && head -50 "$PROJECT_FILE"
  echo ""
  echo "## ━━━ Config (auto-derived) ━━━"
  [ -f "$CONFIG_FILE" ] && grep -E "^(name|dev_command|build_command|deploy|infra_markers):" "$CONFIG_FILE" | head -20
  echo ""
  echo "Modes: --update | --milestone | --rewrite | --migrate"
  exit 0
fi
```
</step>

<step name="4_mode_first_time">
## Step 4 (mode=first_time): 7-round adaptive discussion

This is the heart. Each round is a model-driven conversational step. Save draft after each round.

### Round 1: Capture description

If `$INLINE_DESC` non-empty → use as description, skip prompt.
If `$DOC_PATH` set → read file, use as description.
Else → AskUserQuestion:

```
"Mô tả dự án bằng ngôn ngữ tự nhiên. Càng chi tiết càng tốt — AI sẽ tự suy ra
 foundation và config. Có thể dán paragraph tự do hoặc trả lời theo template:

 - Tên / mục tiêu (vấn đề giải quyết):
 - Người dùng (ai sẽ dùng, bao nhiêu người):
 - Tech stack (nếu đã có ý kiến): 
 - Deploy target (VPS/cloud/app-store/...):
 - Constraint quan trọng (latency/scale/compliance/budget):
 - Brownfield? (có codebase sẵn không, đường dẫn ở đâu)"
```

User responds (1 paragraph or template-filled). Save raw to draft.

```bash
${PYTHON_BIN} - <<PY
import json, datetime
from pathlib import Path
draft = {
  "started_at": datetime.datetime.now().isoformat(),
  "current_round": 1,
  "captured": {"description": """<USER_RESPONSE_HERE>"""},
  "derived": {},
  "decisions": [],
  "status": "in_progress"
}
Path("${DRAFT_FILE}").write_text(json.dumps(draft, indent=2), encoding="utf-8")
PY
```

### Round 2: Parse + present overview

Model parses description into 8 dimensions. Present as table with status flags:
- ✓ derived (clearly stated in description)
- ? ambiguous (mentioned but not specific — "React" without Vite/Next)
- ⚠ missing (not mentioned, default applied)
- 🔒 high-cost (always require Round 4 confirm regardless of source)

```
## Foundation derived (Round 2)

| # | Dimension | Value | Status | Notes |
|---|-----------|-------|--------|-------|
| 1 | Platform | web-saas | ✓🔒 | "SaaS quản lý nhân sự" |
| 2 | Frontend runtime | browser | ✓ | implied |
| 3 | Frontend framework | React | ?🔒 | Vite vs Next.js? |
| 4 | Backend topology | monolith | ✓🔒 | Fastify mentioned |
| 5 | Data layer | SQL (Postgres?) | ✓🔒 | Postgres mentioned |
| 6 | Auth model | own | ⚠ | not mentioned, default |
| 7 | Hosting | VPS | ✓🔒 | "deploy lên VPS" |
| 8 | Distribution | URL | ✓ | implied web |
| 9 | Scale | small (50 users) | ✓ | mentioned |
| 10| Compliance | none | ⚠ | not mentioned |

Routing:
- ? items → Round 3 (targeted dialog)
- 🔒 items → Round 4 (high-cost gate, mandatory confirm)
- ⚠ items → Round 5 (constraints fill-in)
- ✓ + non-🔒 → no further dialog
```

Save draft with `current_round=2, derived.foundation_v1=<table>`.

Ask AskUserQuestion: "OK với suy luận này? [y] Yes proceed / [a] Adjust dimension / [d] Discuss deeper from start"

### Round 3: Targeted dialog (skip if no `?` items)

For EACH `?` dimension, model presents OPTIONS with TRADE-OFFS, asks user:

```
"Dimension {N}: Frontend framework
 Bạn nhắc 'React' nhưng có nhiều route đi:

 - Vite + React Router    — SPA thuần, simple, không SEO. Phù hợp internal tool.
 - Next.js (app router)   — SSR + SEO + RSC. Phù hợp public-facing có search.
 - Remix                  — SSR + nested routing tốt. Ít user hơn Next.js.

 Mình đề xuất: Vite (vì internal tool 50 users, SEO không cần).
 [v] Vite (recommended) [n] Next.js [r] Remix [s] Skip — quyết sau"
```

User answers → record D-XX trong decisions array.

### Round 4: High-cost confirmation gate (MANDATORY — never skip)

Model presents ALL `🔒` decisions as a single confirm gate:

```
"⚠ HIGH-COST DECISIONS (irreversible — confirm explicit trước khi lock):

  🔒 Platform: web-saas
     Đổi sau = rewrite ~80% UI (sang mobile/desktop). 

  🔒 Frontend framework: Vite
     Đổi sang Next.js sau = re-architect routing + data fetching.

  🔒 Backend topology: monolith Fastify
     Đổi sang serverless = re-architect deploy + state management.

  🔒 Database: Postgres
     Đổi sang NoSQL = data layer rewrite + migration script.

  🔒 Hosting: VPS
     Đổi sang Vercel/cloud = redeploy infra + CI/CD redo.

 Confirm tất cả? [y] Yes / [r] Revisit dimension cụ thể / [a] Abort"
```

NEVER auto-skip Round 4. Even with `--auto` mode, must confirm.

### Round 5: Constraints fill-in (skip if all answered)

For each `⚠` dimension still missing or default-applied, ask:

```
"Constraint: Compliance
 Bạn không nhắc — default 'none'. Có cần GDPR/HIPAA/SOC2 không?
 [n] None [g] GDPR [h] HIPAA [s] SOC2 [m] Multiple (specify)"
```

Cover: scale (precise users), latency budget, compliance, team size, budget tier.

### Round 6: Auto-derive vg.config.md from foundation

Model derives config tự động dựa trên foundation. Show preview:

```
## vg.config.md preview (auto-derived from FOUNDATION)

```yaml
project:
  name: <from PROJECT description>
  type: web-saas

frontend:
  framework: vite
  port: 5173
  dev_command: pnpm dev --filter web

backend:
  framework: fastify
  port: 3001
  dev_command: pnpm dev --filter api
  health_endpoint: /health

build_gates:
  typecheck_cmd: pnpm turbo typecheck
  test_cmd: pnpm turbo test
  e2e_cmd: pnpm turbo e2e

deploy:
  target: vps
  ssh_alias: <NEED_USER_INPUT>     ← chỉ field này cần hỏi
  health_url: https://<your-domain>/health  ← cần xác nhận

models:
  executor: sonnet
  planner: opus

(... các field khác auto-fill từ foundation)
```

Hỏi user chỉ những field có `<NEED_USER_INPUT>` placeholder. Không hỏi gì thêm nếu foundation đủ rõ.
```

### Round 7: Atomic write + commit

Write all 3 files trong 1 transaction:

```bash
# Write to staging files first
${PYTHON_BIN} - <<PY
# Write PROJECT.md.staged, FOUNDATION.md.staged, vg.config.md.staged
# from draft + derived foundation + config
...
PY

# Atomic promote (mv all-or-nothing)
mv "${PROJECT_FILE}.staged"     "$PROJECT_FILE"
mv "${FOUNDATION_FILE}.staged" "$FOUNDATION_FILE"
mv "${CONFIG_FILE}.staged"     "$CONFIG_FILE"

# Remove draft
rm -f "$DRAFT_FILE"

# Commit
git add "$PROJECT_FILE" "$FOUNDATION_FILE" "$CONFIG_FILE"
git commit -m "project: foundation locked

Per discussion rounds 1-7. See FOUNDATION.md for D-XX decisions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

Print summary + next steps:
```
✅ Foundation locked. Artifacts:
  - PROJECT.md (project identity + milestones)
  - FOUNDATION.md (8 dimensions + N decisions)
  - vg.config.md (auto-derived from foundation)

Next: /vg:roadmap  (derive phases from project + foundation)
```
</step>

<step name="5_mode_update">
## Step 5 (mode=update): Targeted update preserving existing data

Load existing FOUNDATION.md + PROJECT.md vào context.

AskUserQuestion: "Bạn muốn update phần nào?
- 'general' (mô tả tự nhiên thay đổi) → AI tự detect dimensions liên quan
- Hoặc chọn dimension cụ thể: platform / frontend / backend / data / auth / host / scale / compliance / requirements / milestone-N"

User answers + nói rõ thay đổi.

Model:
1. Identify affected dimensions (parse user input)
2. Load existing decisions D-XX cho dimensions đó
3. Run mini-dialog (1-3 rounds) chỉ trên dimensions affected
4. Generate new D-(N+1) marked "supersedes D-XX"
5. **Preservation gate** (MERGE NOT OVERWRITE):
   - Write `FOUNDATION.md.staged` với chỉ dimensions changed updated
   - Other dimensions: copy verbatim từ existing
   - Run `difflib.SequenceMatcher` ≥ 80% similarity gate trên untouched sections
   - Fail gate → abort, original untouched, staged kept for review
6. If gate pass → atomic promote + commit

Cascade impact:
- If frontend/backend/build dimension changed → SUGGEST: "Tech stack changed → re-derive vg.config.md? [y/n]"
- If yes → run Round 6 (config derivation) chỉ cho fields affected
- Commit message: `project(update): <dimension(s)> changed — D-XX supersedes D-YY`
</step>

<step name="6_mode_milestone">
## Step 6 (mode=milestone): Append new milestone

Load existing PROJECT.md. Detect highest milestone number (search for `## Milestone X` headings).

AskUserQuestion: "Mô tả milestone mới (1-2 câu mục tiêu):"

User responds. Required field — không skip.

Model:
1. Parse description for **drift signals**:
   - Keywords: mobile/iOS/Android/native/desktop/Electron/serverless/lambda/embedded
   - If any match AND foundation.platform != matched type → emit warning:
     ```
     ⚠ Milestone description hint shift platform: 'mobile app' nhưng foundation = 'web-saas'.
        Recommend: /vg:project --update foundation TRƯỚC khi tiếp tục.
        Continue anyway? [y/n]
     ```
2. If user proceeds → append `## Milestone {N+1}` section to PROJECT.md
3. FOUNDATION.md untouched (foundation = stable across milestones)
4. vg.config.md untouched
5. Commit: `project(milestone): add milestone {N+1} — {short title}`

Output: pointer to next step "Run /vg:roadmap để add phases cho milestone mới"
</step>

<step name="7_mode_rewrite">
## Step 7 (mode=rewrite): Destructive reset

Double confirm via AskUserQuestion:
```
"⛔ REWRITE = destructive. Existing PROJECT.md + FOUNDATION.md + vg.config.md sẽ được:
 - Backup → .planning/.archive/{timestamp}/
 - Replaced với artifacts mới sau full re-run

 Confirm? [y] Yes — proceed / [n] No — abort"
```

If yes → second confirm:
```
"Last chance. Type 'rewrite-confirmed' để proceed."
```

If matched → execute:
```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_DIR="${ARCHIVE_DIR}/${TS}"
mkdir -p "$BACKUP_DIR"
[ -f "$PROJECT_FILE" ]    && cp "$PROJECT_FILE"    "$BACKUP_DIR/"
[ -f "$FOUNDATION_FILE" ] && cp "$FOUNDATION_FILE" "$BACKUP_DIR/"
[ -f "$CONFIG_FILE" ]     && cp "$CONFIG_FILE"     "$BACKUP_DIR/"

echo "🗄  Backed up to: ${BACKUP_DIR}"
rm -f "$PROJECT_FILE" "$FOUNDATION_FILE"
# Keep config but mark invalidated
[ -f "$CONFIG_FILE" ] && mv "$CONFIG_FILE" "$BACKUP_DIR/vg.config.md.pre-rewrite"
```

Then `MODE="first_time"` and re-enter step 4 (full 7-round flow).
</step>

<step name="8_mode_migrate">
## Step 8 (mode=migrate): Extract foundation từ existing artifacts

Use case: project có sẵn PROJECT.md + vg.config.md cũ (no FOUNDATION.md). Cần slim PROJECT.md, sinh FOUNDATION.md từ data có sẵn.

```bash
# Confirm intent
echo "Migration: extract FOUNDATION.md từ existing PROJECT.md + scan codebase + vg.config.md"
echo "Backup PROJECT.md cũ → .archive/{ts}/PROJECT.v1.md"
```

Steps:
1. Read existing PROJECT.md, extract sections related to foundation (Tech Stack, Constraints, Architecture)
2. Scan codebase: `package.json`, `tsconfig.json`, framework manifests, `infra/`, `docker-compose.yml`, `.github/workflows/*.yml`
3. Read existing vg.config.md for already-confirmed config
4. Auto-derive 8 foundation dimensions (high confidence — codebase ground truth)
5. Show diff to user:
   ```
   ## Migration preview

   Will create: FOUNDATION.md (extracted)
   | Dimension | Source | Value |
   |-----------|--------|-------|
   | Platform | scan: apps/web/ React | web-saas |
   | Frontend | package.json: vite | React + Vite |
   | Backend | scan: apps/api/ Fastify | Fastify monolith |
   | ...

   PROJECT.md sẽ được slim down — di chuyển foundation fields ra FOUNDATION.md.
   Backup PROJECT.md cũ → .planning/.archive/{ts}/PROJECT.v1.md
   ```
6. AskUserQuestion: "Confirm migration? [y/n]"
7. If yes:
   - Backup PROJECT.md → archive
   - Write FOUNDATION.md (new file)
   - Rewrite PROJECT.md (slim — keep identity/users/requirements/milestones, remove tech stack/architecture)
   - vg.config.md untouched (already exists, foundation matches)
   - Commit: `project(migrate): extract FOUNDATION.md from v1 PROJECT.md + codebase scan`
</step>

<step name="9_mode_init_only">
## Step 9 (mode=init_only): Re-derive vg.config.md from existing FOUNDATION.md

Use case: foundation OK nhưng vg.config.md outdated (vd: thêm crossai CLI, đổi model selection, port shift).

Required: FOUNDATION.md exists. If not → error: "FOUNDATION.md missing. Run /vg:project (no flag) trước."

```bash
if [ ! -f "$FOUNDATION_FILE" ]; then
  echo "⛔ FOUNDATION.md không tồn tại."
  echo "   /vg:project --init-only chỉ chạy được khi đã có foundation."
  echo "   Run /vg:project (first time) hoặc /vg:project --migrate trước."
  exit 1
fi
```

Re-run Round 6 only (config derivation). Show diff vs current vg.config.md.
Ask user: "Apply changes? [y/n]"
If yes → atomic write + commit.
</step>

<step name="10_complete">
## Step 10: Pipeline-state + next-step pointer

```bash
# Update PIPELINE-STATE.json at root level (not phase-specific)
PIPELINE_STATE="${PLANNING_DIR}/PIPELINE-STATE.json"
${PYTHON_BIN} - <<PY 2>/dev/null
import json
from pathlib import Path
import datetime
p = Path("${PIPELINE_STATE}")
s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
s["project_status"] = "ready"
s["foundation_locked_at"] = datetime.datetime.now().isoformat()
s["last_mode"] = "${MODE}"
p.write_text(json.dumps(s, indent=2), encoding="utf-8")
PY
```

Print next-step pointer based on mode:
- first_time / migrate / rewrite → "Next: /vg:roadmap"
- update / init_only → "Foundation/config updated. Re-check: /vg:progress"
- milestone → "Next: /vg:roadmap để add phases cho milestone"
- view → (no next step)
</step>

</process>

## FOUNDATION.md template

```markdown
# Foundation — {Project Name}

**Locked:** {ISO timestamp}
**Source:** {first-time | --update | --migrate | --rewrite}
**Source description:** {first 200 chars of user description}

## 1. Platform & Topology (8 dimensions)

| # | Dimension | Value | Decision | Confidence |
|---|-----------|-------|----------|------------|
| 1 | Platform type | web-saas / mobile-native / mobile-cross / desktop / cli / hybrid | D-01 | derived/confirmed |
| 2 | Frontend runtime | browser / iOS / Android / Electron / none | D-02 | ... |
| 3 | Frontend framework | React+Vite / Next.js / Vue+Vite / Svelte / Flutter / RN / native-iOS / native-Android | D-03 | ... |
| 4 | Backend topology | none / monolith / microservices / serverless / edge / BaaS | D-04 | ... |
| 5 | Data layer | none / Postgres / MySQL / SQLite / MongoDB / Redis / blob / hybrid | D-05 | ... |
| 6 | Auth model | none / own / OAuth / SSO / passwordless / 3rd-party (Auth0/Clerk) | D-06 | ... |
| 7 | Hosting | VPS / AWS / GCP / Vercel / Netlify / on-prem / app-store / hybrid | D-07 | ... |
| 8 | Distribution | URL / app-store / npm / docker-hub / physical-device | D-08 | ... |

## 2. Tech Stack (concrete choices, derived from above)

- Frontend: {framework + key libs} (D-XX)
- Backend: {framework + key libs} (D-XX)
- Database: {engine + version} (D-XX)
- Build/monorepo: {pnpm+turborepo / npm / cargo / go-mod / ...} (D-XX)
- Test: {vitest / jest / pytest / playwright / maestro / ...} (D-XX)
- Deploy: {SSH+PM2 / git-push / docker / Ansible / ...} (D-XX)

## 3. Constraints

- **Scale:** ~{N users, X QPS}
- **Latency budget:** {p50/p99 targets}
- **Compliance:** {none / GDPR / HIPAA / SOC2 / multiple}
- **Team size:** {solo / 2-5 / 6-20 / 20+}
- **Budget tier:** {hobbyist / bootstrapped / funded / enterprise}

## 4. Decisions

### D-01: Platform = {value}
**Reasoning:** {derivation/discussion summary}
**Reverse cost:** HIGH/MEDIUM/LOW — {what breaks if reversed}
**Confirmed:** {date} by user
**Source:** {description / Round 4 confirm / scan / migration}

(D-02 ... D-N — same structure)

## 5. Open Questions

{none if all locked, else list of Q-XX with proposed defaults}

## 6. Drift Check

**Last check:** {date}  
**Status:** ✅ no drift / ⚠ drift detected (see below)  
**Drift entries:** {none, or phase {X} introduced keyword 'mobile' — review platform decision}
```

## vg.config.md derivation rules (Round 6 logic)

When foundation values are known, derive config defaults:

| Foundation field | → vg.config.md fields |
|------------------|----------------------|
| `frontend.framework: vite` | `dev_command: pnpm dev`, `port: 5173`, `e2e: playwright` |
| `frontend.framework: next` | `dev_command: pnpm dev`, `port: 3000`, `e2e: playwright`, ssr_markers |
| `frontend.framework: flutter` | `dev_command: flutter run`, mobile profile, no port |
| `frontend.framework: react-native + expo` | `dev_command: npx expo start`, mobile profile |
| `backend.framework: fastify` | `port: 3001`, `health: /health` |
| `backend.framework: express` | `port: 3000`, `health: /healthz` |
| `backend.topology: serverless` | `deploy.git_push: true`, no SSH alias |
| `hosting: vps` | `deploy.ssh_alias: <ASK>`, `deploy.path: <ASK>` |
| `hosting: vercel` | `deploy.git_push: true`, `domain: <ASK>` |
| `data: postgres` | `db.engine: postgres`, `db.driver: postgres-js` |
| `monorepo: turborepo` | `build_gates.typecheck_cmd: pnpm turbo typecheck` |
| `team_size: solo` | `models.executor: sonnet`, `models.planner: opus` (cost-aware) |
| `team_size: 6-20+` | `models.executor: opus`, `crossai_clis: [codex, gemini]` (quality-priority) |

User only asked về fields marked `<ASK>` (typically: ssh_alias, deploy.path, domain, secrets). Other fields auto-fill silent.

## Resumable draft format

`.planning/.project-draft.json`:
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
    {"id": "D-01", "dim": "platform", "value": "web-saas", "confirmed": true, "round": 4}
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
- Existing decisions D-XX preserved across `--update` (MERGE NOT OVERWRITE)
- `--rewrite` always backs up to `.archive/{ts}/`
- vg.config.md auto-derived 80-90%, only `<ASK>` fields prompt user
- Foundation drift detection in roadmap/add-phase/scope (separate commands)
