"""tests/test_batch55_seed_helper_stub.py — Batch 55.

Codegen wraps test.each(variant) with runSeedRecipe(variant.id) /
cleanup(variant.id) (Batch 52). But those helpers DON'T EXIST unless
humans hand-write them → runtime ReferenceError or silent no-op.

Batch 55 emits a TypeScript/JavaScript helper stub at
PHASE_DIR/tests/_helpers/seed-recipes.{ts|js} with switch/case per
variant_id. Seed branches THROW by default (loud failure); cleanup
branches return (idempotent).

Coverage:
  1. Generator emits .ts by default with one case per variant.
  2. Generator emits .js with --lang js.
  3. observed_state from Batch 54 ends up in case comment.
  4. Empty SEED-RECIPE produces stub that throws on any call.
  5. Validator PASSES when helper exists + all variants have cases.
  6. Validator FAILS strict when helper missing.
  7. Validator FAILS strict when variant missing case.
  8. test-spec.md invokes generator + validator after generate-seed-recipes.
  9. Mirror parity .claude/scripts.
"""
from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GEN = REPO / "scripts" / "generate-seed-helper-stub.py"
GEN_MIRROR = REPO / ".claude" / "scripts" / "generate-seed-helper-stub.py"
VAL = REPO / "scripts" / "validators" / "verify-seed-helper-stub.py"
VAL_MIRROR = REPO / ".claude" / "scripts" / "validators" / "verify-seed-helper-stub.py"
TEST_SPEC = REPO / "commands" / "vg" / "test-spec.md"
TEST_SPEC_MIRROR = REPO / ".claude" / "commands" / "vg" / "test-spec.md"


def _load_gen_module():
    spec = importlib.util.spec_from_file_location("gen_helper_stub", GEN)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gen_helper_stub"] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def _write_recipe(phase_dir: Path, variants: list[dict]) -> None:
    """Write a SEED-RECIPE.md-like file with given variants."""
    lines = ["# SEED-RECIPE — phase test", ""]
    for v in variants:
        lines.append(f"### {v['variant_id']}")
        lines.append("```yaml")
        lines.append(f"variant_id: {v['variant_id']}")
        lines.append(f"goal_id: {v.get('goal_id', 'G-01')}")
        lines.append(f"kind: {v.get('kind', 'boundary')}")
        rs = v.get("requires_state", "x")
        lines.append(f'requires_state: "{rs}"')
        lines.append("seed_action: |")
        lines.append(f"  {v.get('seed_action', '<PLACEHOLDER>')}")
        lines.append("cleanup: |")
        lines.append(f"  {v.get('cleanup', '<PLACEHOLDER>')}")
        lines.append(f"idempotent: {str(v.get('idempotent', True)).lower()}")
        if v.get("observed_state"):
            obs = json.dumps(v["observed_state"], indent=2)
            lines.append("observed_state:")
            for ln in obs.splitlines():
                lines.append("  " + ln)
        lines.append("```")
        lines.append("")
    (phase_dir / "SEED-RECIPE.md").write_text("\n".join(lines), encoding="utf-8")


def test_generator_emits_ts_with_one_case_per_variant(tmp_path):
    phase_dir = tmp_path / "phases" / "7"
    phase_dir.mkdir(parents=True)
    _write_recipe(phase_dir, [
        {"variant_id": "G-01-b1", "kind": "boundary"},
        {"variant_id": "G-01-n1", "kind": "unauthorized_401"},
    ])
    r = subprocess.run(
        ["python", str(GEN), "--phase", "7", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    out_path = phase_dir / "tests" / "_helpers" / "seed-recipes.ts"
    assert out_path.is_file()
    body = out_path.read_text(encoding="utf-8")
    assert "runSeedRecipe" in body
    assert "cleanup" in body
    assert "case 'G-01-b1'" in body
    assert "case 'G-01-n1'" in body
    assert "throw new Error" in body  # loud failure default
    assert "import type { APIRequestContext, Page }" in body


def test_generator_emits_js_with_lang_flag(tmp_path):
    phase_dir = tmp_path / "phases" / "8"
    phase_dir.mkdir(parents=True)
    _write_recipe(phase_dir, [{"variant_id": "G-01-b1", "kind": "boundary"}])
    r = subprocess.run(
        ["python", str(GEN), "--phase", "8", "--phase-dir", str(phase_dir),
         "--lang", "js", "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    out_path = phase_dir / "tests" / "_helpers" / "seed-recipes.js"
    assert out_path.is_file()
    body = out_path.read_text(encoding="utf-8")
    assert "module.exports" in body
    assert "import type" not in body  # no TS types in .js
    assert "case 'G-01-b1'" in body


def test_observed_state_lands_in_case_comment(tmp_path):
    phase_dir = tmp_path / "phases" / "9"
    phase_dir.mkdir(parents=True)
    _write_recipe(phase_dir, [{
        "variant_id": "G-01-f1",
        "kind": "filter_combination",
        "observed_state": {"real_filters": [{"name": "Status", "options": ["a", "b"]}]},
    }])
    r = subprocess.run(
        ["python", str(GEN), "--phase", "9", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    body = (phase_dir / "tests" / "_helpers" / "seed-recipes.ts").read_text(encoding="utf-8")
    assert "observed_state:" in body
    assert "Status" in body
    assert "real_filters" in body


def test_empty_recipe_produces_throwing_stub(tmp_path):
    phase_dir = tmp_path / "phases" / "10"
    phase_dir.mkdir(parents=True)
    (phase_dir / "SEED-RECIPE.md").write_text("# Empty\n", encoding="utf-8")
    r = subprocess.run(
        ["python", str(GEN), "--phase", "10", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    body = (phase_dir / "tests" / "_helpers" / "seed-recipes.ts").read_text(encoding="utf-8")
    assert "throw new Error" in body  # default branch must still throw


def test_validator_passes_when_all_cases_present(tmp_path):
    phase_dir = tmp_path / "phases" / "11"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(
        json.dumps({"goals": {"G-01": {"edge_cases": [{"kind": "boundary"}]}}}),
        encoding="utf-8",
    )
    _write_recipe(phase_dir, [{"variant_id": "G-01-b1", "kind": "boundary"}])
    subprocess.run(
        ["python", str(GEN), "--phase", "11", "--phase-dir", str(phase_dir), "--force"],
        capture_output=True, text=True, check=True,
    )
    r = subprocess.run(
        ["python", str(VAL), "--phase", "11", "--phase-dir", str(phase_dir), "--strict"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"


def test_validator_fails_strict_when_helper_missing(tmp_path):
    phase_dir = tmp_path / "phases" / "12"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(
        json.dumps({"goals": {"G-01": {"edge_cases": [{"kind": "boundary"}]}}}),
        encoding="utf-8",
    )
    # NO helper file generated
    r = subprocess.run(
        ["python", str(VAL), "--phase", "12", "--phase-dir", str(phase_dir), "--strict"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "missing" in (r.stderr + r.stdout).lower()


def test_validator_fails_strict_when_variant_missing_case(tmp_path):
    phase_dir = tmp_path / "phases" / "13"
    phase_dir.mkdir(parents=True)
    (phase_dir / "LIFECYCLE-SPECS.json").write_text(
        json.dumps({"goals": {"G-01": {"edge_cases": [
            {"kind": "boundary"}, {"kind": "unicode_special"}
        ]}}}),
        encoding="utf-8",
    )
    # Helper only covers G-01-b1, NOT G-01-u2
    helper_dir = phase_dir / "tests" / "_helpers"
    helper_dir.mkdir(parents=True)
    (helper_dir / "seed-recipes.ts").write_text(
        "export async function runSeedRecipe(variantId: string) {\n"
        "  switch (variantId) {\n"
        "    case 'G-01-b1': return;\n"
        "    default: throw new Error('unknown');\n"
        "  }\n"
        "}\n"
        "export async function cleanup(variantId: string) { return; }\n",
        encoding="utf-8",
    )
    r = subprocess.run(
        ["python", str(VAL), "--phase", "13", "--phase-dir", str(phase_dir), "--strict"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "G-01-u2" in (r.stderr + r.stdout)


def test_test_spec_invokes_generator_and_validator():
    body = TEST_SPEC.read_text(encoding="utf-8")
    assert "generate-seed-helper-stub.py" in body
    assert "verify-seed-helper-stub.py" in body
    assert "--allow-seed-helper-shortfall" in body
    assert "test_spec.seed_helper_shortfall" in body


def test_module_helpers_parse_yaml_fence():
    mod = _load_gen_module()
    block = """variant_id: G-01-b1
goal_id: G-01
kind: boundary
requires_state: "x"
seed_action: |
  INSERT row
cleanup: |
  DELETE row
idempotent: true
"""
    rec = mod._parse_yaml_block(block)
    assert rec["variant_id"] == "G-01-b1"
    assert rec["kind"] == "boundary"
    assert "INSERT row" in rec["seed_action"]
    assert "DELETE row" in rec["cleanup"]
    assert rec["idempotent"] is True


def test_mirrors_in_sync():
    assert GEN.read_text(encoding="utf-8") == GEN_MIRROR.read_text(encoding="utf-8")
    assert VAL.read_text(encoding="utf-8") == VAL_MIRROR.read_text(encoding="utf-8")
    assert TEST_SPEC.read_text(encoding="utf-8") == TEST_SPEC_MIRROR.read_text(encoding="utf-8")
