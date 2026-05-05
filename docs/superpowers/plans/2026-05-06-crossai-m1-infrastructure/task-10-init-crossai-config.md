# Task 10: Orchestrator `cmd_init_crossai_config()`

**Goal:** Add a new `init-crossai` subcommand to `vg-orchestrator` that auto-detects available CLI binaries (`shutil.which()`), reads the project's existing profile (if any), and emits a complete `vg.config.md` snippet with `crossai_clis` + `crossai_stages` + `crossai.policy` + `crossai.heuristic_thresholds`. Supports `--dry-run` (print to stdout) and `--write` (append to `.claude/vg.config.md`).

**Files:**
- Modify: `scripts/vg-orchestrator/__main__.py`
- Mirror: `.claude/scripts/vg-orchestrator/__main__.py`
- Test: `scripts/tests/test_crossai_init_wizard.py` (new)

---

- [ ] **Step 1: Create the failing test file**

Create `scripts/tests/test_crossai_init_wizard.py`:

```python
"""Tests for `vg-orchestrator init-crossai` command (M1 Task 10).
Auto-detects CLIs, profile, emits valid vg.config.md snippet."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCH = REPO_ROOT / ".claude" / "scripts" / "vg-orchestrator"


def _run_orch(args, env=None, cwd=None):
    full_env = {"PATH": "/usr/bin:/bin", **(env or {})}
    return subprocess.run(
        [sys.executable, str(ORCH), *args],
        capture_output=True, text=True, cwd=cwd, env=full_env,
    )


def test_init_crossai_dry_run_emits_config_block(tmp_path):
    """--dry-run prints a valid config snippet to stdout, no file write."""
    proc = _run_orch(["init-crossai", "--dry-run"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "crossai_clis:" in out
    assert "crossai_stages:" in out
    assert "crossai:" in out
    assert "policy:" in out
    assert "heuristic_thresholds:" in out
    # No file written
    assert not (tmp_path / ".claude" / "vg.config.md").exists()


def test_init_crossai_dry_run_includes_detected_clis(tmp_path):
    """Detected CLIs (codex/gemini/claude/python3) appear in crossai_clis block."""
    proc = _run_orch(["init-crossai", "--dry-run"], cwd=tmp_path)
    out = proc.stdout
    # python3 is always available (we run with it). At least one CLI block:
    assert 'name: "python3"' in out or 'command:' in out


def test_init_crossai_dry_run_default_stages_block(tmp_path):
    """Stages block contains scope/blueprint/build keys."""
    proc = _run_orch(["init-crossai", "--dry-run"], cwd=tmp_path)
    out = proc.stdout
    assert "scope:" in out
    assert "blueprint:" in out
    assert "build:" in out
    assert "primary_clis:" in out
    assert "verifier_cli:" in out


def test_init_crossai_write_appends_to_config(tmp_path):
    """--write appends config block to .claude/vg.config.md."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "vg.config.md").write_text("# existing config\n")
    proc = _run_orch(["init-crossai", "--write"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    content = (tmp_path / ".claude" / "vg.config.md").read_text()
    assert "# existing config" in content  # original preserved
    assert "crossai_clis:" in content
    assert "crossai_stages:" in content


def test_init_crossai_write_skips_if_already_present(tmp_path):
    """If crossai_stages already exists, --write is a no-op (avoid duplicate)."""
    (tmp_path / ".claude").mkdir()
    existing = "# existing\ncrossai_stages:\n  scope:\n    primary_clis: []\n"
    (tmp_path / ".claude" / "vg.config.md").write_text(existing)
    proc = _run_orch(["init-crossai", "--write"], cwd=tmp_path)
    assert proc.returncode == 0
    # Stderr should mention idempotent skip
    assert "already" in proc.stderr.lower() or "skip" in proc.stderr.lower()
    content = (tmp_path / ".claude" / "vg.config.md").read_text()
    # Should not duplicate the block
    assert content.count("crossai_stages:") == 1


def test_init_crossai_resolved_config_loads(tmp_path):
    """After --write, resolve_stage_config() works on the produced file."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "vg.config.md").write_text("")
    proc = _run_orch(["init-crossai", "--write"], cwd=tmp_path)
    assert proc.returncode == 0
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "lib"))
    from crossai_config import resolve_stage_config
    cfg = resolve_stage_config("blueprint", tmp_path)
    assert cfg.stage == "blueprint"
    assert len(cfg.primary_clis) >= 1
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
python3 -m pytest scripts/tests/test_crossai_init_wizard.py -v
```

Expected: 6 failures (`init-crossai` subcommand doesn't exist).

- [ ] **Step 3: Add subcommand to `scripts/vg-orchestrator/__main__.py`**

Locate the argparse subparser registration block (search for `sub.add_parser("`). Add a new subparser `init-crossai`:

```python
    s = sub.add_parser(
        "init-crossai",
        help="Generate vg.config.md crossai sections (auto-detect CLIs)",
    )
    grp = s.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true",
                     help="Print config snippet to stdout, no file write")
    grp.add_argument("--write", action="store_true",
                     help="Append config to .claude/vg.config.md (idempotent)")
    s.set_defaults(func=cmd_init_crossai_config)
```

Add the implementation function (place near other `cmd_*` functions):

```python
def cmd_init_crossai_config(args) -> int:
    """Generate crossai sections for vg.config.md. Auto-detects available
    CLIs (codex, gemini, claude, python3 as fallback) and emits a complete
    snippet with crossai_clis registry, crossai_stages bindings, and
    crossai.policy + crossai.heuristic_thresholds defaults.

    --dry-run: print to stdout
    --write: append to .claude/vg.config.md (idempotent — skip if
             crossai_stages already present)
    """
    import shutil

    candidates = [
        ("Codex-GPT-5.5", "codex",
         'cat {context} | codex exec -m gpt-5.5 "{prompt}"',
         "Codex GPT 5.5", "primary"),
        ("Gemini-Pro-1M", "gemini",
         'cat {context} | gemini -m cx/gemini-3.1-pro-preview -p "{prompt}" --yolo',
         "Gemini 3.1 Pro Preview (1M context)", "primary"),
        ("Claude-Sonnet-4.6", "claude",
         'cat {context} | claude --model sonnet -p "{prompt}"',
         "Claude Sonnet 4.6", "verifier"),
    ]
    detected: list[tuple[str, str, str, str, str]] = []
    for name, binary, cmd, label, role in candidates:
        if shutil.which(binary):
            detected.append((name, cmd, label, role))

    # Ensure at least one primary + one verifier in registry. Fallback
    # python3 entry when no real CLI installed (test environments).
    primary_names = [n for n, _, _, role in detected if role == "primary"]
    verifier_names = [n for n, _, _, role in detected if role == "verifier"]
    if not primary_names:
        detected.append(("python3-fallback",
                         "python3 -c \"import sys; print(sys.stdin.read())\"",
                         "Python3 (fallback)", "primary"))
        primary_names = ["python3-fallback"]
    if not verifier_names:
        # Use first primary as verifier fallback
        verifier_names = [primary_names[0]]

    # Build config block
    lines = []
    lines.append("")
    lines.append("# === CrossAI configuration (generated by `vg-orchestrator init-crossai`) ===")
    lines.append("crossai_clis:")
    for name, cmd, label, role in detected:
        lines.append(f'  - name: "{name}"')
        lines.append(f"    command: '{cmd}'")
        lines.append(f'    label: "{label}"')
        lines.append(f'    role: "{role}"')
    lines.append("")
    lines.append("crossai_stages:")
    primary_arr = ", ".join(f'"{n}"' for n in primary_names[:2])  # max 2 for parallel
    verifier_first = verifier_names[0]
    for stage in ("scope", "blueprint", "build"):
        lines.append(f"  {stage}:")
        lines.append(f"    primary_clis: [{primary_arr}]")
        lines.append(f'    verifier_cli: "{verifier_first}"')
    lines.append("")
    lines.append("crossai:")
    lines.append('  policy: "auto"  # strict | auto | off (M2)')
    lines.append("  heuristic_thresholds:")
    lines.append("    min_endpoints: 3")
    lines.append("    min_critical_goals: 2")
    lines.append("    min_plan_tasks: 5")
    lines.append("# ===========================================================================")
    lines.append("")
    block = "\n".join(lines)

    if args.dry_run:
        sys.stdout.write(block)
        return 0

    # --write: append idempotently
    target = Path(".claude") / "vg.config.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    if "crossai_stages:" in existing:
        print(
            "\033[33mcrossai_stages already present in "
            f"{target}; skipping (idempotent).\033[0m",
            file=sys.stderr,
        )
        return 0
    with target.open("a", encoding="utf-8") as f:
        f.write(block)
    print(f"Appended crossai config block to {target}", file=sys.stderr)
    return 0
```

- [ ] **Step 4: Sync mirror + run tests**

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
cp scripts/vg-orchestrator/__main__.py .claude/scripts/vg-orchestrator/__main__.py
python3 -m pytest scripts/tests/test_crossai_init_wizard.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd "/Users/dzungnguyen/Vibe Code/Code/vgflow-bugfix"
git add scripts/vg-orchestrator/__main__.py \
        .claude/scripts/vg-orchestrator/__main__.py \
        scripts/tests/test_crossai_init_wizard.py
git commit -m "feat(orchestrator): cmd_init_crossai_config + init-crossai subcommand

M1 Task 10 — generate vg.config.md crossai sections from detected CLIs.
Auto-detect codex/gemini/claude on PATH; emit registry + stages +
policy + thresholds. --dry-run prints to stdout, --write appends
idempotently to .claude/vg.config.md (no duplicate when block present).

Fallback python3-fallback CLI when no real CLI installed (test envs).
Primary list capped at 2 for parallel pattern (Q9-mod 2-primary
consensus).

Tests: 6 (dry-run emit, detected CLIs, stages block, write append,
idempotent skip, resolved config loads).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```
