"""v2.74.0 T5 — slim codex-skills/vg-scope-review/SKILL.md.

Replaces inline <step name="X">...</step> blocks inside <process>...</process>
with slim routing entries that read from `_shared/scope-review/*.md`.

Mirrors the v2.73.0 T12 strategy used for vg-update
(scripts/v273_t12_slim_codex_update.py).
"""
from pathlib import Path
import re


SCOPE_REVIEW_GROUPS = [
    {
        "title": "### Preflight section (extracted v2.74.0 T1)",
        "shared": "_shared/scope-review/preflight.md",
        "steps": ["0_parse_and_collect", "incremental_check"],
        "blurb": (
            "Includes 2 steps: 0_parse_and_collect (parse --skip-crossai / "
            "--phases / --full flags, scan ${PHASES_DIR} for scoped phases, "
            "extract decisions/endpoints/modules/test scenarios/dependencies "
            "from CONTEXT.md, also enumerate DONE phases for scope-creep "
            "Check E) and incremental_check (read .scope-review-baseline.json "
            "to compute changed/new/dependent SCAN_SET, default-on incremental "
            "mode, --full forces complete rescan)."
        ),
        "codex_note": None,
    },
    {
        "title": "### Cross-ref + review + write (extracted v2.74.0 T2)",
        "shared": "_shared/scope-review/cross-ref-review-write.md",
        "steps": ["1_cross_reference", "2_crossai_review", "3_write_report"],
        "blurb": (
            "Includes 3 steps: 1_cross_reference (5 deterministic checks "
            "A-E across SCAN_SET — decision conflicts, module overlaps, "
            "endpoint collisions, dependency gaps, scope creep vs DONE "
            "phases), 2_crossai_review (config-driven CrossAI fan-out — "
            "skip if --skip-crossai / no CLIs / single phase), and "
            "3_write_report (write ${PLANNING_DIR}/SCOPE-REVIEW.md with "
            "structured findings + delta summary header + gate verdict)."
        ),
        "codex_note": (
            "CODEX NOTE: Step 2's CrossAI fan-out uses the shared CrossAI "
            "engine. On Codex, follow the adapter contract above (Tool "
            "mapping table) — spawn configured CLI agents in the main "
            "Codex thread, do not delegate to a Claude subagent."
        ),
    },
    {
        "title": "### Resolve + close (extracted v2.74.0 T3 — final)",
        "shared": "_shared/scope-review/resolve-and-close.md",
        "steps": [
            "4_resolution",
            "4.5_baseline_write_and_telemetry",
            "5_commit_and_next",
        ],
        "blurb": (
            "Includes 3 closing steps: 4_resolution (interactive — present "
            "blocking conflicts/gaps to user with resolution options, never "
            "AI auto-fix), 4.5_baseline_write_and_telemetry (atomic write "
            "of .scope-review-baseline.json after every run including BLOCK "
            "+ emit scope-review-incremental telemetry with "
            "changed/new/conflicts counts), and 5_commit_and_next (commit "
            "SCOPE-REVIEW.md + baseline to git, suggest /vg:blueprint for "
            "first unblueprinted phase)."
        ),
        "codex_note": (
            "CODEX NOTE: Step 4's interactive resolution prompts use "
            "AskUserQuestion on Claude. On Codex, ask the same Yes/No / "
            "multiple-choice questions inline in the main Codex thread "
            "per the adapter contract above (Tool mapping table)."
        ),
    },
]


def slim_step_blocks(text: str, groups: list) -> str:
    """Replace each step block listed in `groups` with a slim routing entry."""
    step_to_group = {}
    for gi, g in enumerate(groups):
        for s in g["steps"]:
            step_to_group[s] = gi

    emitted = set()
    output_chunks = []
    pos = 0
    pattern = re.compile(r'<step name="([^"]+)">', re.MULTILINE)
    last_known_group = None

    while True:
        m = pattern.search(text, pos)
        if not m:
            output_chunks.append(text[pos:])
            break
        step_name = m.group(1)
        close_idx = text.find("</step>", m.end())
        if close_idx == -1:
            raise RuntimeError(f"Unclosed <step name='{step_name}'>")
        close_end = close_idx + len("</step>")

        gi = step_to_group.get(step_name)

        between = text[pos:m.start()]
        if last_known_group is not None and gi == last_known_group:
            # Same group — drop interstitial prose
            pass
        else:
            output_chunks.append(between)

        if gi is None:
            output_chunks.append(text[m.start():close_end])
            last_known_group = None
        else:
            if gi not in emitted:
                g = groups[gi]
                steps_csv = ", ".join(g["steps"])
                routing = (
                    f"{g['title']}\n\n"
                    f"Read `{g['shared']}` and follow it exactly.\n"
                    f"{g['blurb']}\n\n"
                    f"Step coverage: {steps_csv}.\n"
                )
                if g.get("codex_note"):
                    routing += f"\n{g['codex_note']}\n"
                output_chunks.append(routing)
                emitted.add(gi)
            last_known_group = gi

        pos = close_end
        while pos < len(text) and text[pos] == "\n":
            pos += 1
        output_chunks.append("\n")

    return "".join(output_chunks)


def slim_file(path: Path, groups: list) -> tuple[int, int]:
    original = path.read_text(encoding="utf-8")
    before = len(original.splitlines())
    new_text = slim_step_blocks(original, groups)
    new_text = re.sub(r"\n{3,}", "\n\n", new_text)
    path.write_text(new_text, encoding="utf-8")
    after = len(new_text.splitlines())
    return before, after


def main() -> None:
    before, after = slim_file(
        Path("codex-skills/vg-scope-review/SKILL.md"), SCOPE_REVIEW_GROUPS
    )
    print(f"vg-scope-review: {before} -> {after} lines")


if __name__ == "__main__":
    main()
