Scope: `commands/vg/**` source tree. Note: `.claude/commands/vg/_shared/blueprint/lens-walk.md` exists, but `commands/vg/_shared/blueprint/lens-walk.md` does not. Source drift.

| Marker | Status | Evidence file:line | Notes |
|---|---|---|---|
| 0_design_discovery | REAL_BASH | commands/vg/_shared/blueprint/preflight.md:37 | Runs UI scope/design preflight scripts; mark after checks. |
| 0_amendment_preflight | REAL_BASH | commands/vg/_shared/blueprint/preflight.md:152 | Runs run-start + amendment preflight; mark after success. |
| 1_parse_args | REAL_BASH | commands/vg/_shared/blueprint/preflight.md:231 | Emits tasklist + validates `--from`; mark after guard. |
| create_task_tracker | REAL_BASH | commands/vg/_shared/blueprint/preflight.md:373 | `tasklist-projected` must pass before mark. |
| 2_verify_prerequisites | REAL_BASH | commands/vg/_shared/blueprint/preflight.md:445 | Generates/validates `INTERFACE-STANDARDS.*`; mark after validator path. |
| 2_fidelity_profile_lock | PARTIAL | commands/vg/_shared/blueprint/design.md:36 | Bash exists, but no marker on “no design/FE work” branch. |
| 2a_plan | REAL_BASH | commands/vg/_shared/blueprint/plan-overview.md:326 | Mandatory planner Agent; schema validation before mark. |
| 2a5_cross_system_check | REAL_BASH | commands/vg/_shared/blueprint/plan-overview.md:504 | Grep checks + caller graph; mark after script path. |
| 2b_contracts | REAL_BASH | commands/vg/_shared/blueprint/contracts-overview.md:49 | Contracts Agent + CRUD/schema guards before mark. |
| 2b5_test_goals | REAL_BASH | commands/vg/_shared/blueprint/contracts-overview.md:164 | Persistence/RCRURD/schema checks before mark. |
| 2b5a_codex_test_goal_lane | REAL_BASH | commands/vg/_shared/blueprint/contracts-overview.md:336 | Codex spawn writes proposal + delta; mark after nonempty/delta pass. |
| 2b5d_expand_from_crud_surfaces | PARTIAL | commands/vg/_shared/blueprint/contracts-overview.md:458 | Script failure only warns; marker still fires. |
| 2b5e_a_lens_walk | SCAFFOLD | commands/vg/blueprint.md:338 | Confirmed local finding in source tree: referenced file missing; only Part 5 prose at contracts-delegation.md:621. |
| 2b5e_edge_cases | REAL_BASH | commands/vg/_shared/blueprint/edge-cases.md:25 | Has orchestration + output checks before mark. |
| 2b6_ui_spec | PARTIAL | commands/vg/_shared/blueprint/design.md:488 | Agent spawn is placeholder/comment; flat concat only; `FORM-API-MAP.md` skip handled but generator never called. |
| 2b6b_ui_map | PARTIAL | commands/vg/_shared/blueprint/design.md:596 | UI-MAP writer is prose/echo; marker only if file already exists or external agent acted. |
| 2b6c_view_decomposition | REAL_BASH | commands/vg/_shared/blueprint/design.md:108 | Agent + aggregation writes `VIEW-COMPONENTS.md`; validator before mark. |
| 2b6d_fe_contracts | SCAFFOLD | commands/vg/_shared/blueprint/fe-contracts-overview.md:17 | Confirmed local finding: prose only, no `step-active`, no bash, no mark-step. |
| 2b7_flow_detect | PARTIAL | commands/vg/_shared/blueprint/contracts-overview.md:501 | Detect bash runs; FLOW-SPEC generation is commented Agent; mark fires without FLOW-SPEC check. |
| 2b8_rcrurdr_invariants | SCAFFOLD | commands/vg/blueprint.md:166 | Confirmed local finding: no owner file, no bash, no mark-step. |
| 2b9_workflows | SCAFFOLD | commands/vg/_shared/blueprint/workflows-overview.md:13 | Confirmed local finding: prose/delegation only, no bash, no mark-step. |
| 2c_verify | REAL_BASH | commands/vg/_shared/blueprint/verify.md:36 | Grep verifier blocks high mismatch count before mark. |
| 2c_verify_plan_paths | PARTIAL | commands/vg/_shared/blueprint/verify.md:141 | Real validator if present; missing checker still marks. |
| 2c_utility_reuse | PARTIAL | commands/vg/_shared/blueprint/verify.md:190 | Real validator if present; missing checker/project still marks. |
| 2c_compile_check | PARTIAL | commands/vg/_shared/blueprint/verify.md:247 | Extracts blocks, but compile only runs if `COMPILE_CMD` set. |
| 2d_validation_gate | PARTIAL | commands/vg/_shared/blueprint/verify.md:489 | Core threshold decision is pseudocode; validators exist, but mark not tied to computed miss percentages. |
| 2d_test_type_coverage | REAL_BASH | commands/vg/_shared/blueprint/verify.md:682 | Tester-pro validator before mark. |
| 2d_goal_grounding | REAL_BASH | commands/vg/_shared/blueprint/verify.md:734 | Goal-grounding validator before mark. |
| 2d_crossai_review | PARTIAL | commands/vg/_shared/blueprint/verify.md:597 | Sources markdown ref, not executable shell; marker can fire without `crossai/result-*.xml`. |
| 2e_bootstrap_reflection | REAL_BASH | commands/vg/_shared/blueprint/close.md:28 | Reflection Agent path; no must_write artifact. |
| 3_complete | PARTIAL | commands/vg/_shared/blueprint/close.md:230 | Marker fires before traceability/BLOCK5/workflow/slice/run-complete gates. |

Counts:
- REAL_BASH: 16
- PARTIAL: 11
- SCAFFOLD: 4

NEW scaffold markers not in local-4 list: none. Local 4 confirmed for `commands/vg/**`.

Top 5 worst:
1. `2b8_rcrurdr_invariants` — `commands/vg/blueprint.md:166`; no implementation files.
2. `2b6d_fe_contracts` — `commands/vg/_shared/blueprint/fe-contracts-overview.md:17`; prose only.
3. `2b9_workflows` — `commands/vg/_shared/blueprint/workflows-overview.md:13`; prose only.
4. `2b5e_a_lens_walk` — `commands/vg/blueprint.md:338`; referenced source file missing.
5. `2d_crossai_review` — `commands/vg/_shared/blueprint/verify.md:597`; markdown sourced as shell, marker not tied to result XML.