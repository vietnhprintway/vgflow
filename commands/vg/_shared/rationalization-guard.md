# Rationalization Guard (Shared Reference)

Referenced by gates in: execute-verify.md, crossai-check.md, test-specs.md, verify.md, sandbox-test.md.

When enforcing a gate, check if you're rationalizing a skip. If any thought below crosses your mind — STOP and follow the counter.

## Evidence Gate (execute-verify, sandbox-test)

| Thought | Reality | Counter |
|---------|---------|---------|
| "Should work now" | You haven't run the command | Run it. Read output. Then claim. |
| "Tests passed earlier" | That was cached/stale | Run FRESH. Every time. |
| "I'm confident it passes" | Confidence ≠ evidence | No output = no claim. |
| "Agent reported success" | Agent may have hallucinated | Independent verification required. |
| "Just this one time" | Exceptions become habits | No exceptions. Run the gate. |
| "The diff looks correct" | Diffs show intent, not correctness | Tests prove correctness. Run them. |

## Coverage Gate (test-specs test-review)

| Thought | Reality | Counter |
|---------|---------|---------|
| "Close enough to 85%" | 82% means 18% untested | Add test steps or defer decisions explicitly. |
| "The uncovered decisions are minor" | Minor decisions cause major bugs | Cover them or mark as deferred in CONTEXT.md. |
| "I'll cover them in --deepen later" | Later never comes | Cover now or document why deferred. |
| "CrossAI will catch any gaps" | CrossAI checks breadth, not completeness | Coverage gate is a hard number. Meet it. |

## Scope Guard (crossai-check auto-fix)

| Thought | Reality | Counter |
|---------|---------|---------|
| "This fix is small, won't hurt" | Small fixes to old code cause regressions | Out-of-scope = log only. Period. |
| "The finding is valid even if old" | Valid ≠ in-scope for THIS phase | Log it for the relevant phase. Don't fix here. |
| "I'll fix it while I'm here" | Scope creep through auto-fix | This phase has its own goals. Stay focused. |
| "It's just a one-line change" | One-line changes break things too | Check git blame. Not your phase = not your fix. |

## Pre-Completion Checklist (verify)

| Thought | Reality | Counter |
|---------|---------|---------|
| "Sandbox wasn't required for this phase" | All phases need sandbox unless pure docs | Check CLAUDE.md: sandbox is mandatory. |
| "Tests pass locally" | Local ≠ sandbox. Missing dependencies, services, etc. | Memory rule: test on sandbox environment, NOT local-only — apply to all phases. |
| "UAT can catch what sandbox missed" | UAT is human time — expensive | Sandbox catches 80% of bugs for free. Don't skip. |
| "FLOW-SPEC doesn't exist so skip flows" | It might need one | Check: does phase have state machines? If yes, generate. |

## Verify-Before-Implement (crossai-check feedback)

| Thought | Reality | Counter |
|---------|---------|---------|
| "Great point, I'll fix all of these" | Did you verify each is reproducible? | Reproduce → verify scope → YAGNI → then fix. One at a time. |
| "This endpoint isn't used but I'll fix it properly" | YAGNI violation | Grep codebase. Not imported = not used = don't fix. |
| "The finding makes sense theoretically" | Theory ≠ reality in THIS codebase | Check the actual code. Finding may be wrong. |
| "I'll implement now, verify later" | Later = never | Verify FIRST. Fix SECOND. Always. |

## How to Use This File

When you hit a gate and feel the urge to skip/shortcut/rationalize:
1. Read the table for that gate
2. Find the thought closest to yours
3. Follow the counter column exactly
4. If your thought isn't in the table — it's probably a new rationalization. Follow the gate anyway.
