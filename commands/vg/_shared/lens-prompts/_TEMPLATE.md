---
name: lens-<slug>
description: <one-line probe goal — what bug class, what surface>
bug_class: <authz | injection | auth | bizlogic | server-side | redirect | ui-mechanic>
applies_to_element_classes:
  - <element_class>
applies_to_phase_profiles:
  - feature
  - feature-legacy
  - hotfix
strix_reference: strix/skills/vulnerabilities/<file>.md
severity_default: <warn | block>
estimated_action_budget: <int>
output_schema_version: 3
---

# Lens: <Display Name>

## Threat model

<1-2 paragraphs. What can go wrong (the bug class in plain terms). Why a
white-box VG worker — with auth tokens, view-level snapshots, and live network
capture — is well placed to detect it. Keep abstract; concrete probes go below.>

## Activation context (auto-injected by VG)

The dispatcher (`scripts/spawn-recursive-probe.py`) substitutes these
placeholders before handing the prompt to the worker subprocess. Lens authors
MUST reference them via `${VAR}` exactly as written; never hard-code values.

- View: `${VIEW_PATH}`
- Element: `${ELEMENT_DESCRIPTION}` (selector: `${SELECTOR}`)
- Element class: `${ELEMENT_CLASS}`
- Resource: `${RESOURCE}` (scope: `${SCOPE}`)
- Role: `${ROLE}` with auth token `${TOKEN_REF}`
- Base URL: `${BASE_URL}`
- Peer credentials (cross-tenant probe, nullable): `${PEER_TOKEN_REF}`
- Run artifact output path: `${OUTPUT_PATH}`
- Action budget: `${ACTION_BUDGET}` browser actions max
- Recursion depth: `${DEPTH}`
- Wall-clock budget: 5 minutes

## Reconnaissance (1-2 steps to start)

Just enough to land on the element. Not a full script.

1. browser_navigate(`${BASE_URL}${VIEW_PATH}`) with `Authorization: Bearer ${TOKEN_REF}`
2. browser_snapshot — capture initial DOM, locate `${SELECTOR}`

Then START EXPLORING (see Objective + Probe ideas).

## Objective (exploratory)

Find <bug_class> vulnerabilities affecting `${ELEMENT_DESCRIPTION}` and any
sub-elements you discover during exploration. You are a security researcher,
not a test runner. Click anything that looks promising, follow workflows, dig
into anomalies. Adapt to what you observe — do not follow a fixed sequence.

## Probe ideas (suggestions — pick what fits, combine freely)

Bullet list of 4-8 concrete ideas relevant to this bug class. Each idea is 1-2
lines describing what to try, not a numbered step plan. The worker decides
which to combine, in what order, based on evidence.

- <idea 1 — short imperative, e.g. "Replay the captured request with `${PEER_TOKEN_REF}`; check if status 200 returns peer-owned data">
- <idea 2>
- <idea 3>
- <idea 4>
- <idea 5>
- <idea 6>
- <idea 7>
- <idea 8>

## How to explore recursively (anti-script discipline)

- Click the element, capture network response baseline.
- After each action, browser_snapshot. New buttons/forms/sub-views/modals →
  click those too (recursive within this element's reach).
- If a probe yields an anomaly (unexpected status, peer data leak, state
  bypass, …) → DIG: try the same with a different role, modify request body,
  check whether the anomaly affects neighbor records.
- DO NOT follow a fixed click sequence. Adapt to what you observe.
- DO NOT skip "boring-looking" elements without at least 1 click — coverage
  beats narrow-focus within budget.

## Stopping criteria

Stop and write the artifact when ANY of:

- Action budget `${ACTION_BUDGET}` exhausted
- Wall-clock 5 minutes reached
- High-confidence finding captured + ≥3 supporting probes done
- 2 consecutive actions yield no new anomaly AND no new clickables —
  diminishing returns

## Run artifact write (mandatory format)

When exploration ends (any stopping criterion), write JSON to `${OUTPUT_PATH}`.
Schema version 3 — see `commands/vg/_shared/templates/run-artifact-template.json`
for the canonical schema. Required top-level fields:

- `schema_version`: `3`
- `worker_tool`: `"gemini" | "codex" | "claude"`
- `run_id`: `<element-slug>-<lens>-<role>-<depth>`
- `lens`, `resource`, `role`, `element_class`, `selector_hash`, `view`, `depth`
- `actions_taken` (int), `stopping_reason` (`budget|timeout|confidence|diminishing_returns`)
- `steps[]`: each step has `name` (short observation), `status`
  (`pass|fail|inconclusive`), `observed` (raw evidence object),
  `evidence_ref[]` (network log refs)
- `coverage`: `{passed, failed, inconclusive}`
- `replay_manifest`: `{commit_sha, worker_prompt_version, fixtures_used, request_sequence}`
- `goal_stub`: `{id, lens, view, element_class, resource, parent_goal_id}` —
  NO `priority` field; aggregator assigns post-run.

## Termination

- After exploration ends → write the run artifact → call browser_close →
  output `DONE`.
- DO NOT navigate to other views (the VG manager handles cross-view recursion).
- DO NOT spawn child agents (deterministic dispatcher only).
- If action budget is exhausted before exploration feels complete, write a
  partial artifact with `stopping_reason: "budget"` — that is normal and the
  aggregator handles it.

## Probe-only contract reminder (HARD CONSTRAINT)

Worker MUST NOT:

- Propose code fixes or remediation ("To fix this, change X to Y" — NO).
- Assign severity ("This is critical / high / medium" — NO).
- Reason about exploit chains ("If combined with bug Z, attacker could…" — NO).

Worker MUST:

- Report factual `steps[].status = pass|fail|inconclusive`.
- Capture raw `observed` evidence (status code, body excerpt, DOM diff).
- Append a `finding_fact` to `runs/.broker-context.json` when a step fails —
  facts only:

```json
{"lens": "lens-<slug>", "view": "${VIEW_PATH}", "element": "${ELEMENT_DESCRIPTION}", "step": "<short name>", "status": "fail", "observed_excerpt": "<1-2 line raw>"}
```

NO severity field, NO summary, NO recommendation. Severity rollup is the
aggregator + `derive-findings.py` job downstream, computed from
`lens.severity_default` × `step.status` and cross-cutting context.
