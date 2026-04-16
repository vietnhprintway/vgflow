---
name: vg:project
description: Define project identity, requirements, and constraints — foundation for roadmap and phases
argument-hint: "[--auto @doc.md] [--milestone]"
allowed-tools:
  - Read
  - Bash
  - Glob
  - Grep
  - Write
  - AskUserQuestion
  - Agent
---

<rules>
1. **VG-native** — no GSD delegation. This command is self-contained.
2. **Config-driven** — read .claude/vg.config.md for project paths, profile, models.
3. **Discussion first** — structured rounds, not free-form. Every round locks decisions.
4. **DISCUSSION-LOG is append-only** — never overwrite, never delete.
5. **Brownfield-aware** — detect existing code/graphify, offer codebase mapping first.
6. **Milestone support** — `--milestone` flag for adding v1.1+ after v1.0 ships.
</rules>

<objective>
First command in VG pipeline. Defines the project: what it is, who it's for, what to build.
Output: .planning/PROJECT.md + .planning/REQUIREMENTS.md

Pipeline: **project** → roadmap → map → prioritize → specs → scope → blueprint → build → review → test → accept
</objective>

<process>

<step name="0_parse_and_detect">
## Step 0: Parse arguments + detect project state

```bash
# Parse flags
AUTO_MODE=false
MILESTONE_MODE=false
DOC_PATH=""
for arg in $ARGUMENTS; do
  case "$arg" in
    --auto) AUTO_MODE=true ;;
    --milestone) MILESTONE_MODE=true ;;
    @*) DOC_PATH="${arg#@}" ;;
  esac
done

# Detect existing state
PLANNING_DIR=".planning"
PROJECT_FILE="${PLANNING_DIR}/PROJECT.md"
REQUIREMENTS_FILE="${PLANNING_DIR}/REQUIREMENTS.md"
ROADMAP_FILE="${PLANNING_DIR}/ROADMAP.md"

PROJECT_EXISTS=false
[ -f "$PROJECT_FILE" ] && PROJECT_EXISTS=true

HAS_CODE=false
for d in apps/ src/ packages/ lib/; do
  [ -d "$d" ] && HAS_CODE=true && break
done

HAS_GRAPHIFY=false
[ -f "graphify-out/graph.json" ] && HAS_GRAPHIFY=true

HAS_CODEBASE_MAP=false
[ -f "${PLANNING_DIR}/codebase-map.md" ] && HAS_CODEBASE_MAP=true
```

**Validation:**
- If `$PROJECT_EXISTS` AND NOT `$MILESTONE_MODE` → "PROJECT.md already exists. Use `/vg:project --milestone` to add a new milestone, or `/vg:roadmap` to update phases."
- If `$MILESTONE_MODE` AND NOT `$PROJECT_EXISTS` → "No PROJECT.md found. Run `/vg:project` first (without --milestone)."
- If `$AUTO_MODE` AND empty `$DOC_PATH` → "Auto mode requires a document: `/vg:project --auto @prd.md`"
</step>

<step name="1_brownfield_detect">
## Step 1: Brownfield detection

**If code exists but no codebase map:**

```
AskUserQuestion:
  header: "Codebase"
  question: "Detected existing code. Map codebase first for better project definition?"
  options:
    - "Map first (recommended)" — Run /vg:map to build graphify knowledge graph
    - "Skip" — Proceed without codebase context
```

If "Map first" → suggest user run `/vg:map` then come back.

**If codebase-map.md exists:** Read it silently — inject god nodes + communities into discussion context.

**If greenfield (no code):** Skip to Step 2.
</step>

<step name="2_project_discussion">
## Step 2: Structured Project Discussion

**If --auto mode:** Extract from provided document, skip interactive rounds. Jump to Step 3.

**If --milestone mode:** Load existing PROJECT.md, skip Rounds 1-2, start at Round 3 with "what's new in this milestone".

### Round 1 — Project Identity

```
AskUserQuestion:
  header: "Identity"
  question: "Tell me about the project — what is it, who is it for, what's the core value?"
  (open text — user describes freely)
```

AI extracts from response:
- **Project name** — the product/system name
- **Core value** — 1-2 sentences, the fundamental reason this exists
- **Domain** — industry/vertical (ad-tech, fintech, SaaS, etc.)
- **Target users** — who uses this and their roles
- **Scale** — expected load/size constraints

Confirm with user: "I understand: {name} is a {domain} platform that {core_value}. Users: {roles}. Correct?"

### Round 2 — Current State (brownfield) / Vision (greenfield)

**If brownfield:**
```
AskUserQuestion:
  header: "Current state"
  question: "What already exists and what needs to change?"
  (open text)
```

AI extracts:
- **Existing stack** — languages, frameworks, databases
- **What works** — features already built and stable
- **What needs rebuild** — parts that need replacement
- **Tech constraints** — locked choices (e.g., "must stay on MongoDB", "no Docker")

**If greenfield:**
```
AskUserQuestion:
  header: "Tech vision"
  question: "What tech stack and architecture do you envision?"
  (open text)
```

### Round 3 — Requirements

```
AskUserQuestion:
  header: "Requirements"
  question: "What features need to be built? List by category if possible (auth, billing, reports, etc.)"
  (open text — user lists features)
```

AI organizes into categories, assigns REQ-IDs:
```
AUTH-01: User registration + email verification
AUTH-02: Role-based access (admin, publisher, advertiser)
AUTH-03: JWT session management
BILL-01: Stripe integration for payments
BILL-02: Invoice generation
...
```

Confirm: "I've organized {N} requirements in {M} categories. Review:"
Show table → user adjusts.

**Priority assignment:**
```
AskUserQuestion:
  header: "Priority"
  question: "Which categories are must-have vs should-have vs nice-to-have?"
  options:
    - Show categorized list, user marks priority per category
```

### Round 4 — Non-functional Requirements

```
AskUserQuestion:
  header: "Constraints"
  question: "Any performance, security, infrastructure, or compliance constraints?"
  (open text)
```

AI extracts:
- Performance targets (latency, QPS)
- Security requirements (encryption, compliance)
- Infrastructure constraints (single VPS, cloud, budget)
- Deployment model (CI/CD, manual, Ansible)

### Loop Check

```
AskUserQuestion:
  header: "Complete?"
  question: "Anything else to discuss about the project?"
  options:
    - "Done — generate PROJECT.md" (recommended)
    - "More to discuss" — opens free-form round
```

If "More" → new round (repeat until "Done").
</step>

<step name="3_write_artifacts">
## Step 3: Write artifacts

### PROJECT.md format:

```markdown
# {Project Name}

> {Core Value — 1-2 sentences}

## Context

**Domain:** {domain}
**Target Users:** {roles list}
**Scale:** {scale constraints}
**Stack:** {confirmed tech choices}
**Infrastructure:** {deployment model}

## Current State

{What exists, what works, what needs change — brownfield only}

## Requirements

### Must-Have
| ID | Category | Requirement | Acceptance Criteria |
|----|----------|-------------|---------------------|
| AUTH-01 | Auth | User registration + email verify | User can register, receives email, clicks link, account active |
| AUTH-02 | Auth | Role-based access | Admin/Publisher/Advertiser roles enforced on every endpoint |
...

### Should-Have
| ID | Category | Requirement | Acceptance Criteria |
...

### Nice-to-Have
| ID | Category | Requirement | Acceptance Criteria |
...

## Non-Functional Requirements
| Constraint | Target | Notes |
|------------|--------|-------|
| Latency | RTB ≤50ms | Drives Rust choice |
| Scale | 10k QPS | Single VPS constraint |
...

## Key Decisions
- D-P01: {project-level decision, e.g., "Monorepo with Turborepo"}
- D-P02: {e.g., "MongoDB native driver, not Mongoose"}
...

## Milestones
| Version | Name | Status | Requirements |
|---------|------|--------|-------------|
| v1.0 | {name} | active | AUTH-*, BILL-*, ... |

## Evolution
<!-- Auto-updated by /vg:amend and /vg:roadmap -->
```

### REQUIREMENTS.md format:

```markdown
# Requirements — {Project Name}

Generated: {ISO date}
Total: {N} requirements ({must} must-have, {should} should-have, {nice} nice-to-have)

## By Category

### Auth ({N} requirements)
| ID | Requirement | Priority | Phase | Status |
|----|-------------|----------|-------|--------|
| AUTH-01 | User registration | must-have | — | pending |
...

### Billing ({N} requirements)
...

## Traceability Matrix
| REQ ID | Phase | Tasks | Verified |
|--------|-------|-------|----------|
<!-- Filled by /vg:roadmap and /vg:blueprint -->
```

### Write files:

```bash
mkdir -p "${PLANNING_DIR}"
# Write PROJECT.md and REQUIREMENTS.md (content generated above)
```

### Write DISCUSSION-LOG:

Append full Q&A trail to `${PLANNING_DIR}/PROJECT-DISCUSSION-LOG.md`:
```markdown
# Project Discussion Log — {Project Name}

## Session 1 — {ISO date}

### Round 1: Project Identity
**Q:** Tell me about the project...
**A:** {user's full response}
**Extracted:** name={X}, core_value={Y}, domain={Z}

### Round 2: Current State
...

### Round 3: Requirements
...
```

**APPEND-ONLY** — milestone discussions append new sessions, never overwrite.
</step>

<step name="4_milestone_mode">
## Step 4: Milestone Mode (--milestone only)

If `$MILESTONE_MODE`:

1. Read existing PROJECT.md — show current milestones
2. Ask: "What ships in the next milestone?"
3. Gather new requirements (Round 3 only — project identity already locked)
4. Assign REQ-IDs continuing from last ID per category
5. Update PROJECT.md: add new milestone row, new requirements
6. Update REQUIREMENTS.md: append new REQs with "pending" status
7. Append to PROJECT-DISCUSSION-LOG.md: "Milestone {N} session"

```
AskUserQuestion:
  header: "Milestone"
  question: "What's the name and goal of the next milestone?"
  (open text)
```
</step>

<step name="5_commit_and_next">
## Step 5: Commit + suggest next

```bash
git add "${PLANNING_DIR}/PROJECT.md" "${PLANNING_DIR}/REQUIREMENTS.md" "${PLANNING_DIR}/PROJECT-DISCUSSION-LOG.md"
git commit -m "docs(project): define ${PROJECT_NAME} — ${REQ_COUNT} requirements in ${CAT_COUNT} categories

Co-Authored-By: Claude <noreply@anthropic.com>"
```

Display:
```
Project defined: {name}
  Requirements: {N} ({must} must-have, {should} should-have, {nice} nice-to-have)
  Categories: {list}
  Artifacts: PROJECT.md + REQUIREMENTS.md + PROJECT-DISCUSSION-LOG.md
  
  Next: /vg:roadmap → derive phases from requirements
```
</step>

</process>

<success_criteria>
- PROJECT.md exists with Core Value, Context, Requirements, Key Decisions, Milestones
- REQUIREMENTS.md exists with categorized REQs, REQ-IDs, priorities, traceability skeleton
- PROJECT-DISCUSSION-LOG.md exists with full Q&A trail
- All artifacts committed to git
- Next step guidance shows /vg:roadmap
</success_criteria>
