#!/usr/bin/env python3
"""Verify post-build deep test-spec artifacts exist before /vg:review."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _common import Evidence, Output, emit_and_exit, find_phase_dir, timer  # noqa: E402

REQUIRED_FILES = (
    ("DEEP-TEST-SPECS.md", 400),
    ("LIFECYCLE-SPECS.json", 80),
    ("TEST-FIXTURE-DAG.json", 80),
    ("PLAYWRIGHT-SPEC-PLAN.md", 180),
    ("TEST-SPEC-GAPS.md", 40),
)

REQUIRED_STAGES = {
    "read_before",
    "create",
    "read_after_create",
    "update",
    "read_after_update",
    "delete",
    "read_after_delete",
}


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--severity", choices=["block", "warn"], default="block")
    args = parser.parse_args()

    out = Output(validator="deep-test-specs")
    with timer(out):
        phase_dir = find_phase_dir(args.phase)
        if phase_dir is None:
            out.add(Evidence(type="phase_not_found", message=f"Phase not found: {args.phase}"))
            emit_and_exit(out)

        for filename, min_bytes in REQUIRED_FILES:
            path = phase_dir / filename
            if not path.exists():
                out.add(
                    Evidence(
                        type="deep_test_spec_missing",
                        message=f"{filename} missing",
                        file=str(path),
                        expected=f"post-build /vg:test-spec artifact {filename}",
                        fix_hint=f"Run /vg:test-spec {args.phase} before /vg:review.",
                    ),
                    escalate=args.severity == "block",
                )
                continue
            if path.stat().st_size < min_bytes:
                out.add(
                    Evidence(
                        type="deep_test_spec_shallow",
                        message=f"{filename} is too small ({path.stat().st_size} bytes)",
                        file=str(path),
                        expected=f">= {min_bytes} bytes",
                        fix_hint=f"Regenerate with /vg:test-spec {args.phase}.",
                    ),
                    escalate=args.severity == "block",
                )

        lifecycle = read_json(phase_dir / "LIFECYCLE-SPECS.json")
        if lifecycle is None:
            out.add(
                Evidence(
                    type="lifecycle_specs_invalid_json",
                    message="LIFECYCLE-SPECS.json is missing or invalid JSON",
                    file=str(phase_dir / "LIFECYCLE-SPECS.json"),
                    fix_hint=f"Run /vg:test-spec {args.phase}.",
                ),
                escalate=args.severity == "block",
            )
        else:
            goals = lifecycle.get("goals") or {}
            if not isinstance(goals, dict):
                out.add(
                    Evidence(
                        type="lifecycle_goals_invalid",
                        message="LIFECYCLE-SPECS.json goals must be an object",
                        file=str(phase_dir / "LIFECYCLE-SPECS.json"),
                    ),
                    escalate=args.severity == "block",
                )
            for goal_id, spec in list(goals.items())[:200]:
                if not isinstance(spec, dict):
                    continue
                stages = {
                    str(step.get("stage"))
                    for step in spec.get("steps") or []
                    if isinstance(step, dict)
                }
                missing = sorted(REQUIRED_STAGES - stages)
                if missing:
                    out.add(
                        Evidence(
                            type="lifecycle_stage_missing",
                            message=f"{goal_id} missing lifecycle stages: {', '.join(missing)}",
                            file=str(phase_dir / "LIFECYCLE-SPECS.json"),
                            expected="full RCRURDR stages",
                            fix_hint=f"Regenerate with /vg:test-spec {args.phase}; repair TEST-GOALS if still missing.",
                        ),
                        escalate=args.severity == "block",
                    )

        dag = read_json(phase_dir / "TEST-FIXTURE-DAG.json")
        if dag is None:
            out.add(
                Evidence(
                    type="fixture_dag_invalid_json",
                    message="TEST-FIXTURE-DAG.json is missing or invalid JSON",
                    file=str(phase_dir / "TEST-FIXTURE-DAG.json"),
                ),
                escalate=args.severity == "block",
            )
        else:
            if "nodes" not in dag or "edges" not in dag:
                out.add(
                    Evidence(
                        type="fixture_dag_schema_invalid",
                        message="TEST-FIXTURE-DAG.json must contain nodes and edges",
                        file=str(phase_dir / "TEST-FIXTURE-DAG.json"),
                    ),
                    escalate=args.severity == "block",
                )

    emit_and_exit(out)


if __name__ == "__main__":
    main()
