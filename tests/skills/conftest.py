"""Shared fixtures for VG skill (commands/vg/*.md) static tests."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS_DIR = REPO_ROOT / "commands" / "vg"
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm = yaml.safe_load(text[4:end])
    body = text[end + 5:]
    return (fm or {}), body


@pytest.fixture
def skill_loader():
    def _load(name: str) -> dict:
        path = COMMANDS_DIR / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"skill {name} not at {path}")
        text = path.read_text(encoding="utf-8")
        fm, body = _split_frontmatter(text)

        # `lines` reflects the canonical file only (used by slim-size tests).
        canonical_lines = text.count("\n") + (0 if text.endswith("\n") else 1)

        # v2.72.0/v2.73.0 — merge in `_shared/<name>/*.md` sub-files so static
        # tests asserting on body content survive the slim-routing extractions.
        # The slim entry in <name>.md still routes to these files, so semantically
        # the body now includes both the slim entry and the routed-to content.
        shared_dir = COMMANDS_DIR / "_shared" / name
        if shared_dir.is_dir():
            for sub in sorted(shared_dir.glob("*.md")):
                body += "\n" + sub.read_text(encoding="utf-8")
                text += "\n" + sub.read_text(encoding="utf-8")

        return {
            "name": name,
            "path": path,
            "text": text,
            "lines": canonical_lines,
            "frontmatter": fm,
            "body": body,
        }
    return _load


@pytest.fixture
def agent_loader():
    def _load(name: str) -> dict:
        # Agents may be stored as `<name>.md` OR as `<name>/` directory.
        md_path = AGENTS_DIR / f"{name}.md"
        dir_path = AGENTS_DIR / name
        path = md_path if md_path.exists() else (dir_path / "agent.md" if (dir_path / "agent.md").exists() else None)
        if path is None or not path.exists():
            raise FileNotFoundError(f"agent {name} not at {md_path} or {dir_path}/agent.md")
        text = path.read_text(encoding="utf-8")
        fm, body = _split_frontmatter(text)
        return {"name": name, "path": path, "text": text, "frontmatter": fm, "body": body}
    return _load


def grep_count(body: str, pattern: str) -> int:
    return len(re.findall(pattern, body, flags=re.MULTILINE))
