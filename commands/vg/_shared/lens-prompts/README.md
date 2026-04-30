# Lens prompts (v2.40+)

These prompts are loaded by `scripts/spawn-recursive-probe.py` and fed as the
system prompt to the worker subprocess (Gemini Flash / Codex / Claude). One
worker run per `(element × lens × role)` tuple.

## Authoring rules

- Follow `_TEMPLATE.md` structure exactly. Frontmatter MUST include all 9
  required fields (`name`, `description`, `bug_class`,
  `applies_to_element_classes`, `applies_to_phase_profiles`,
  `strix_reference`, `severity_default`, `estimated_action_budget`,
  `output_schema_version`).
- **Exploratory style ONLY** — NO scripted "Variation A: Steps: 1.X 2.Y, Pass:
  …, Fail: …" blocks. Workers explore recursively and adapt to evidence.
  "Probe ideas" is a bullet list of suggestions the worker combines freely;
  it is NOT a numbered run sheet.
- Action budget = max browser actions for the full exploration. The manager
  enforces it; lens authors set the cap via `estimated_action_budget`.
- DO NOT instruct the LLM to recurse to other views — the VG manager handles
  cross-view recursion. The lens stays within the element's local reach
  (sub-modals, sub-buttons, response payloads).
- DO NOT respec the output schema beyond what `_TEMPLATE.md` already says —
  the canonical schema lives in
  `commands/vg/_shared/templates/run-artifact-template.json`.

## Probe-only contract (HARD CONSTRAINT)

Worker prompts MUST NOT instruct the LLM to:

- Propose code fixes or remediation.
- Assign severity (`critical | high | medium | low`).
- Reason about exploit chains.
- Recommend further probing beyond the lens's declared scope.

Worker prompts MUST instruct the LLM to:

- Explore freely within the action budget.
- Report `steps[].status = pass | fail | inconclusive` — factual, not graded.
- Capture raw `observed` evidence (status code, response body excerpt, DOM
  diff).
- Append `finding_fact` entries to `runs/.broker-context.json` — facts only,
  no judgment.

Severity rollup happens downstream in `derive-findings.py`, computed from
`lens.severity_default × step.status` plus cross-cutting context. See the
design doc section "Probe-only discipline".

## Per-tool isolation

Run artifacts are written to `runs/<tool>/recursive-*.json` where
`<tool> ∈ {codex, gemini, claude}`. The dispatcher resolves `${OUTPUT_PATH}`
per-tool to avoid overwrite when running cross-tool validation. Lens prompts
MUST always reference `${OUTPUT_PATH}` rather than hard-coding a path.

## Loading

`spawn-recursive-probe.py`:

1. Reads each `lens-*.md` file in this directory.
2. Parses the frontmatter, in particular `applies_to_element_classes` and
   `applies_to_phase_profiles`.
3. Looks up element classifications from `recursive-classification.json`
   (produced by `scripts/identify-interesting-clickables.py`).
4. Dispatches one worker subprocess per `(element × lens × role)` tuple,
   substituting `${VAR}` placeholders with concrete values.

## Reference

- Strix originals: see the `strix_reference` field in each lens frontmatter
  (`C:/Users/Lionel Messi/AppData/Local/Temp/strix/strix/skills/vulnerabilities/`).
- Design doc: `docs/plans/2026-04-30-v2.40-recursive-lens-probe.md`.
- Implementation plan: `docs/plans/2026-04-30-v2.40-implementation.md` (Tasks
  8-21 cover the template + 14 lens files).
