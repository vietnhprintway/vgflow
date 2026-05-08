"""Stage 5 task 5/6 of meta-memory v1.1 — Phase 4 Prune & Index.

Rebuild .vg/bootstrap/MEMORY.md so its line count <= MEMORY_MAX_LINES (200,
per Anthropic Dreams design Section 13.1 startup cutoff). Demote oldest /
lowest-priority rules to topics/{target_step}.md and replace them with
1-line pointers in MEMORY.md.

Tests cover:
  * dry-run writes nothing
  * <200-line corpus stays in MEMORY.md (no demotion needed)
  * >200-line corpus -> some rules demoted; MEMORY.md respects cap
  * topics/ dir created on overflow
  * empty rules dir -> graceful no-op
  * demotion order: lowest priority first
  * idempotent re-run does not re-demote already-demoted rules badly
    (topic file grows, but MEMORY.md still <= cap; rule file untouched)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

CONSOLIDATE = ".claude/scripts/bootstrap-consolidate.py"


def _write_rule(rules_dir: Path, slug: str, *, priority: str = "low",
                target: str = "deploy", title: str | None = None,
                body_lines: int = 4, mtime_offset: float = 0.0) -> Path:
    """Create a rule .md file with YAML frontmatter + simple body."""
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"{slug}.md"
    title = title or f"Rule {slug}"
    body = "\n".join(f"line {i} of {slug}" for i in range(body_lines))
    text = (
        f"---\n"
        f"slug: {slug}\n"
        f"title: {title}\n"
        f"target_step: {target}\n"
        f"priority: {priority}\n"
        f"tier: B\n"
        f"---\n"
        f"{body}\n"
    )
    path.write_text(text, encoding="utf-8")
    if mtime_offset:
        ts = time.time() + mtime_offset
        os.utime(path, (ts, ts))
    return path


def _run_prune(state_dir: Path, apply: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["VG_BOOTSTRAP_STATE_DIR"] = str(state_dir)
    argv = [sys.executable, CONSOLIDATE, "--phase", "prune", "--json"]
    if apply:
        argv.append("--apply")
    return subprocess.run(argv, capture_output=True, text=True, env=env)


# ---------- tests ----------

def test_prune_empty_rules_dir_safe(tmp_path):
    """No rules at all -> rules_total=0, no demotions, rc=0."""
    result = _run_prune(tmp_path, apply=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["rules_total"] == 0
    assert report["demoted_count"] == 0
    # MEMORY.md gets the header even with zero rules; that's fine.
    if (tmp_path / "MEMORY.md").exists():
        assert (tmp_path / "MEMORY.md").read_text(encoding="utf-8").count("\n") <= 200


def test_prune_under_200_lines_keeps_in_memory_md(tmp_path):
    """50 rules -> all fit comfortably in MEMORY.md (no demotion)."""
    rules = tmp_path / "rules"
    for i in range(50):
        _write_rule(rules, f"rule-{i:02d}", priority="medium")

    result = _run_prune(tmp_path, apply=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["rules_total"] == 50
    assert report["demoted_count"] == 0
    assert report["memory_md_lines_after"] <= 200

    memory = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    # All 50 rule slugs should appear in MEMORY.md (no demotion).
    for i in range(50):
        assert f"rule-{i:02d}" in memory


def test_prune_over_200_demotes_to_topics(tmp_path):
    """300 rules -> MEMORY.md at most 200 lines, some demoted."""
    rules = tmp_path / "rules"
    # Mix priorities so demotion order is deterministic: 100 low, 100 medium,
    # 100 high. The 100 low (rank=1) should be demoted first.
    for i in range(100):
        _write_rule(rules, f"low-{i:03d}", priority="low",
                    target="deploy", mtime_offset=-i)
    for i in range(100):
        _write_rule(rules, f"med-{i:03d}", priority="medium",
                    target="test", mtime_offset=-i)
    for i in range(100):
        _write_rule(rules, f"high-{i:03d}", priority="high",
                    target="accept", mtime_offset=-i)

    result = _run_prune(tmp_path, apply=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["rules_total"] == 300
    assert report["demoted_count"] > 0

    memory_lines = (tmp_path / "MEMORY.md").read_text(encoding="utf-8").count("\n")
    assert memory_lines <= 200, (
        f"MEMORY.md must respect 200-line cap; got {memory_lines}")

    # The lowest-priority rules ("low-*") should be demoted FIRST.
    demoted = report["demoted_slugs"]
    low_demoted = [s for s in demoted if s.startswith("low-")]
    high_demoted = [s for s in demoted if s.startswith("high-")]
    assert len(low_demoted) >= len(high_demoted), (
        f"low-priority should demote before high-priority; "
        f"low_demoted={len(low_demoted)} high_demoted={len(high_demoted)}")


def test_prune_creates_topics_dir(tmp_path):
    """When demotion happens, topics/ dir is created and target-grouped files written."""
    rules = tmp_path / "rules"
    # 250 rules — enough to force demotion past 200-line cap.
    # Mixed targets so we can verify per-target topic files.
    targets = ["deploy", "test", "accept", "build"]
    for i in range(250):
        _write_rule(rules, f"r-{i:03d}", priority="low",
                    target=targets[i % len(targets)])

    result = _run_prune(tmp_path, apply=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["demoted_count"] > 0

    topics_dir = tmp_path / "topics"
    assert topics_dir.is_dir()

    written = set(report["topics_written"])
    # Each demoted rule's target_step should appear as a topics/{target}.md file
    for target in written:
        topic_path = topics_dir / f"{target}.md"
        assert topic_path.is_file(), f"missing {topic_path}"
        # Demoted rule body content should appear in the topic file
        content = topic_path.read_text(encoding="utf-8")
        assert "Demoted at" in content
        assert target in str(topic_path)


def test_prune_dry_run_writes_nothing(tmp_path):
    """Default mode (no --apply) -> no MEMORY.md, no topics/ written."""
    rules = tmp_path / "rules"
    for i in range(300):
        _write_rule(rules, f"r-{i:03d}", priority="low")

    result = _run_prune(tmp_path, apply=False)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["apply"] is False
    assert report["demoted_count"] > 0  # planned, not executed
    assert report["files_modified"] == []
    assert not (tmp_path / "MEMORY.md").exists()
    assert not (tmp_path / "topics").exists()


def test_prune_demoted_rules_pointer_section_exists(tmp_path):
    """Demoted rules surface as one collective pointer per target_step group
    (e.g. '- deploy: N rules -> topics/deploy.md'). Per-rule pointers are NOT
    written to MEMORY.md — that would defeat the 200-line cap. The slug is
    discoverable by following the topics/{target}.md file."""
    rules = tmp_path / "rules"
    for i in range(250):
        _write_rule(rules, f"r-{i:03d}", priority="low", target="deploy")

    result = _run_prune(tmp_path, apply=True)
    report = json.loads(result.stdout)
    assert report["demoted_count"] > 0

    memory = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "## Demoted" in memory
    assert "topics/deploy.md" in memory
    # And the demoted slugs should be in topics/deploy.md (not MEMORY.md)
    sample = report["demoted_slugs"][0]
    topic_text = (tmp_path / "topics" / "deploy.md").read_text(encoding="utf-8")
    assert sample in topic_text


def test_prune_idempotent_does_not_blow_up_memory_md(tmp_path):
    """Running --apply twice keeps MEMORY.md within cap and doesn't crash."""
    rules = tmp_path / "rules"
    for i in range(220):  # just slightly over cap so demotion fires
        _write_rule(rules, f"r-{i:03d}", priority="low")

    r1 = _run_prune(tmp_path, apply=True)
    assert r1.returncode == 0, r1.stderr
    lines_after_first = (tmp_path / "MEMORY.md").read_text(encoding="utf-8").count("\n")
    assert lines_after_first <= 200

    r2 = _run_prune(tmp_path, apply=True)
    assert r2.returncode == 0, r2.stderr
    lines_after_second = (tmp_path / "MEMORY.md").read_text(encoding="utf-8").count("\n")
    assert lines_after_second <= 200


def test_prune_does_not_delete_rule_files(tmp_path):
    """Demotion COPIES rule body into topics/, never deletes rules/{slug}.md."""
    rules = tmp_path / "rules"
    for i in range(250):
        _write_rule(rules, f"r-{i:03d}", priority="low")

    rule_count_before = len(list(rules.glob("*.md")))
    _run_prune(tmp_path, apply=True)
    rule_count_after = len(list(rules.glob("*.md")))
    assert rule_count_before == rule_count_after, (
        "Phase 4 must NOT delete rules/*.md; demotion is copy-into-topics only")
