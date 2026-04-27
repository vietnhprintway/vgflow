# Phase 19 D-09 — Read-tool Transcript Verification — RESEARCH

**Status:** RESEARCH SPIKE — implementation deferred pending Claude Code runtime hook surface area.

**Verdict:** **Direct transcript inspection is NOT feasible** with the public Claude Code surface today. **Sentinel-file fallback** is the recommended near-term implementation.

---

## Question

Can we prove an executor agent actually called the `Read` tool on each `<design-ref>` PNG, rather than just claiming to have done so in its summary text?

The strongest possible proof would be parsing the executor's tool-use transcript for `Read(file_path=PNG_PATH)` events and rejecting commits where any required PNG is missing from the call list. Without it, every layer above (L1 hard-gate, L2 fingerprint, L5 vision-self-verify) trusts the executor by default — the whole pipeline rests on whether the model decided to follow instructions.

## Public surface today (2026-04-28)

Investigated:

- **Hook events** documented for Claude Code: `SessionStart`, `Stop`, `SubagentStop`, `PostToolUse`, `PreToolUse`, `UserPromptSubmit`. Verified by inspecting `.claude/settings.json` schemas referenced in update-config skill and Claude Code docs.
- `PostToolUse` and `PreToolUse` fire on tool calls in the **parent** conversation, not inside a spawned `Task(subagent_type=...)` agent's session. The subagent's tool calls are encapsulated; the parent only sees the agent's final output.
- `SubagentStop` fires when a spawned agent finishes — but the event payload (per docs) contains the agent's final output text, not its full tool-use ledger.
- There is no documented API for `subagent_transcript`, `subagent_tool_calls`, or similar. The Anthropic Agents SDK exposes streaming events to the SDK caller, but that is a different surface than Claude Code's `Task` spawning.
- Inspected `.claude/scripts/` for any existing transcript-mining helper — none present. `vg-reflector` skill explicitly notes it queries `events.db` instead of reading transcripts to "avoid echo chamber" — meaning even VG's internal tooling does not have transcript access today.

Conclusion: **the executor's Read calls are not observable from outside the spawned agent**. Any direct verification approach is blocked at the runtime layer.

## What WOULD work if available

If Claude Code added one of these in a future release, the implementation is straightforward:

1. **`SubagentStop` payload includes `tool_calls: [...]`** — in the hook handler, scan for `Read(file_path=...)` entries, write to `${PHASE_DIR}/.executor-tools/{task}.json`, then verify against required PNG list at build step 9.
2. **`subagent_transcript` query API** — orchestrator calls after each `Task` spawn, parses streamed events for tool uses.
3. **Custom `output_capture: "tool_calls"` flag on `Task`** — opt-in serialization of tool-use ledger to a known file.

Implementation cost in any of those scenarios: ~80 LOC validator script + 15 LOC wire in build.md step 9. Complexity comparable to existing `verify-vision-self-verify.py`.

## Recommended fallback: sentinel evidence file

Until runtime hooks expose tool-call ledgers, force the executor to **emit evidence of its own tool calls**. Pattern:

1. After Read PNG, executor MUST write `${PHASE_DIR}/.read-evidence/task-${N}.json`:
   ```json
   {
     "task": 4,
     "slug": "home-dashboard",
     "read_paths": [
       ".vg/design-normalized/screenshots/home-dashboard.default.png",
       ".vg/design-normalized/refs/home-dashboard.structural.html"
     ],
     "read_at": "2026-04-28T12:00:00Z"
   }
   ```
2. New validator `verify-read-evidence.py` runs at build step 9:
   - For every task with `<design-ref>` slug, sentinel file MUST exist.
   - Sentinel must list at minimum the slug's `screenshots/{slug}.default.png` path.
   - Path values cross-checked against actual disk presence (must match files L1 already verified).
   - SHA256 hash of sentinel logged to telemetry; tampering detectable across re-runs.

**Limitation honestly stated:** the sentinel itself is just text the AI writes. A determined model could fake it. This is *forcing function* not *proof* — same category as L2 LAYOUT-FINGERPRINT. The hope is that requiring the sentinel content nudges the model toward actually performing the tool call (because writing the path correctly without having Read it is awkward), not that the sentinel is cryptographic evidence.

**Stronger nudge**: require the sentinel to include a SHA256 of the PNG file at the time of Read. Validator re-hashes the PNG and compares. A model that fabricates the sentinel would have to know the exact hash, which it cannot get without Reading the file. This is a **probabilistic proof** — the model can theoretically guess, but the search space is 2^256.

```json
{
  "task": 4,
  "slug": "home-dashboard",
  "read_paths": [
    {"path": ".vg/design-normalized/screenshots/home-dashboard.default.png",
     "sha256_at_read": "a1b2c3d4..."}
  ]
}
```

Validator computes SHA256 of the same file at gate-time. Mismatch = fabrication. Match = either (a) actual Read happened, or (b) the model has cryptographic clairvoyance.

## Recommendation

- **Phase 19 ships D-09 as RESEARCH only** (this document). No new validator written until upstream hook surface allows direct verification, OR the sentinel-with-hash approach is approved.
- **Track in dev-phases/19/RESEARCH.md** so future Claude Code release notes get checked against the question. If `SubagentStop` adds `tool_calls` payload, Phase N+1 can implement direct verification in ~1h.
- The sentinel-with-hash approach is implementable now (~100 LOC validator + executor rule update). It is meaningful but explicitly weaker than runtime-hook verification. Decision to ship it is up to user — recommend deferring until L1+L2+L5 dogfood data shows ongoing skip-without-Read incidents that the existing layers don't already catch.

## Cost summary

| Approach | LOC | Effort | Strength | Available now |
|---|---|---|---|---|
| Direct transcript inspection | ~80 | 1-2h once API exposed | High (cryptographic) | NO |
| Sentinel file (path only) | ~100 | 2-3h | Low (writeable) | YES |
| Sentinel with PNG SHA256 | ~120 | 3-4h | Medium-high (probabilistic) | YES |

## What this means for the broader plan

D-09's gap remains acknowledged but unblocked: the 4-layer pipeline + D-05 vision-self-verify + D-06 manual UAT do most of the work that direct transcript verification would do, just at higher latency. Combined `~95%` reliability target is still attainable without D-09. If user wants a `>97%` target, sentinel-with-hash becomes the next concrete step — but is not on the critical path for v2.14.0.
