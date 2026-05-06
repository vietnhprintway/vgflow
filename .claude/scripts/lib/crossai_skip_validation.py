"""CrossAI skip-override anti-rationalization validator.

Closes architectural gap (PV3 build 4.2 dogfood, 2026-05-05): AI can emit
`vg-orchestrator override --flag=skip-build-crossai` with a reason that
claims "Codex CLI not configured per .claude/vg.config.md" — but the
file actually configures Codex AND `which codex` returns a binary path.
Override-debt logged but the claim is FALSE.

This module fact-checks the override reason against:
  1. `.claude/vg.config.md` `crossai_clis:` list
  2. `shutil.which(<name>)` for each configured CLI

Skip is **legitimate** ONLY when no CrossAI CLI is both:
  - Configured in vg.config.md crossai_clis
  - Installed on PATH

Otherwise the loop physically CAN run, and the override is a
rationalization attempting to bypass the build-crossai-required gate.

Public API:
    validate_skip_legitimate(repo_root, override_reason) -> SkipValidationResult

Used by:
    - scripts/vg-orchestrator/__main__.py::cmd_override (pre-validation)
    - scripts/validators/build-crossai-required.py (terminal-event check)
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path


CONFIG_PATHS = (
    Path(".claude/vg.config.md"),
    Path(".vg/vg.config.md"),
    Path("vg.config.md"),
)

# Patterns that, in an override reason, make a falsifiable claim about
# CLI availability. Match group(1) is the CLI name.
FALSIFIABLE_CLAIMS = [
    re.compile(r"no\s+([A-Za-z][A-Za-z0-9_+-]*)\s+CLI\s+configured", re.I),
    re.compile(r"([A-Za-z][A-Za-z0-9_+-]*)\s+CLI\s+not\s+configured", re.I),
    re.compile(r"([A-Za-z][A-Za-z0-9_+-]*)\s+CLI\s+not\s+installed", re.I),
    re.compile(r"([A-Za-z][A-Za-z0-9_+-]*)\s+not\s+available\s+locally", re.I),
    re.compile(r"missing\s+([A-Za-z][A-Za-z0-9_+-]*)\s+CLI", re.I),
]


@dataclass
class SkipValidationResult:
    legitimate: bool
    configured_clis: list[str] = field(default_factory=list)
    installed_clis: list[str] = field(default_factory=list)
    false_claims: list[str] = field(default_factory=list)
    reasoning: str = ""


def _find_config(repo_root: Path) -> Path | None:
    for rel in CONFIG_PATHS:
        p = repo_root / rel
        if p.is_file():
            return p
    return None


def _parse_crossai_clis(config_text: str) -> list[str]:
    """Extract CLI names from `crossai_clis:` block in vg.config.md.

    Format (markdown, indented YAML-ish):
        crossai_clis:
          - name: "Codex"
            command: 'cat ...'
          - name: "Gemini"
    Returns: ['codex', 'gemini'] (lowercased).
    """
    names: list[str] = []
    in_block = False
    for line in config_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("crossai_clis:"):
            in_block = True
            continue
        if in_block:
            # Block ends at next top-level YAML key (no leading whitespace + colon)
            if line and not line[0].isspace() and ":" in line and not stripped.startswith("- "):
                break
            m = re.match(r'-\s*name:\s*"?([A-Za-z][A-Za-z0-9_+-]*)"?', stripped)
            if m:
                names.append(m.group(1).lower())
    return names


def _which(cli_name: str) -> str | None:
    """shutil.which wrapper — returns abs path or None."""
    return shutil.which(cli_name)


def validate_skip_legitimate(
    repo_root: Path,
    override_reason: str,
) -> SkipValidationResult:
    """Fact-check a `skip-*-crossai*` override reason.

    Args:
        repo_root: project root (contains .claude/ or .vg/)
        override_reason: text from --reason= flag

    Returns:
        SkipValidationResult with legitimate=False if any of:
          - ≥1 configured CLI is installed (loop COULD run)
          - reason makes a false CLI-availability claim
    """
    repo_root = Path(repo_root).resolve()
    cfg = _find_config(repo_root)

    if cfg is None:
        # No config file → cannot prove rationalization. Allow with WARN.
        return SkipValidationResult(
            legitimate=True,
            reasoning="No vg.config.md found — cannot verify CLI configuration.",
        )

    config_text = cfg.read_text(encoding="utf-8", errors="replace")
    configured = _parse_crossai_clis(config_text)
    installed = [n for n in configured if _which(n)]

    false_claims: list[str] = []
    for pat in FALSIFIABLE_CLAIMS:
        for m in pat.finditer(override_reason or ""):
            claimed_cli = m.group(1).lower()
            if claimed_cli in configured:
                false_claims.append(
                    f"Reason claims \"{m.group(0)}\" — but {claimed_cli} IS in "
                    f"vg.config.md crossai_clis at {cfg.relative_to(repo_root)}"
                )
            if _which(claimed_cli):
                false_claims.append(
                    f"Reason claims \"{m.group(0)}\" — but `which {claimed_cli}` "
                    f"returns {_which(claimed_cli)} (binary IS installed)"
                )

    if installed:
        return SkipValidationResult(
            legitimate=False,
            configured_clis=configured,
            installed_clis=installed,
            false_claims=false_claims,
            reasoning=(
                f"Skip rejected — {len(installed)} CrossAI CLI(s) "
                f"({', '.join(installed)}) are configured in "
                f"{cfg.relative_to(repo_root)} AND installed on PATH. The loop "
                f"physically CAN run. If a specific CLI is failing, fix the "
                f"infrastructure (network/quota/timeout) instead of overriding."
            ),
        )

    if false_claims:
        return SkipValidationResult(
            legitimate=False,
            configured_clis=configured,
            installed_clis=installed,
            false_claims=false_claims,
            reasoning=(
                "Skip rejected — override reason contains "
                f"{len(false_claims)} false claim(s) about CLI availability."
            ),
        )

    return SkipValidationResult(
        legitimate=True,
        configured_clis=configured,
        installed_clis=installed,
        reasoning=(
            f"Skip legitimate — 0 CrossAI CLI installed (configured: "
            f"{configured or 'none'})."
        ),
    )


def format_rejection(result: SkipValidationResult) -> str:
    """Render a multi-line rejection message for stderr/event payloads."""
    lines = [
        "Override --flag=skip-*-crossai* REJECTED — anti-rationalization gate.",
        "",
        result.reasoning,
        "",
        f"  Configured in vg.config.md: {result.configured_clis or '(none)'}",
        f"  Installed on PATH:          {result.installed_clis or '(none)'}",
    ]
    if result.false_claims:
        lines.append("")
        lines.append("  False claims in --reason:")
        for fc in result.false_claims:
            lines.append(f"    - {fc}")
    lines.append("")
    lines.append(
        "Fix: run the CrossAI loop with the configured+installed CLI(s):"
    )
    lines.append("  python3 .claude/scripts/vg-build-crossai-loop.py \\")
    lines.append("    --phase <PHASE> --iteration 1 --max-iterations 5")
    return "\n".join(lines)
