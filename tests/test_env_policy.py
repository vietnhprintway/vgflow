"""scripts/env_policy.py — per-env constraints (Task 26b).

policy_for(env: str) -> dict returns:
  - allow_mutations:   bool
  - mutation_budget:   int   (0 = none, -1 = unlimited)
  - allowed_lenses:    set[str] (subset of LENS_CATALOG)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "env_policy.py"


def _load():
    spec = importlib.util.spec_from_file_location("env_policy", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["env_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_local_full_unlimited():
    mod = _load()
    p = mod.policy_for("local")
    assert p["allow_mutations"] is True
    assert p["mutation_budget"] == -1
    assert len(p["allowed_lenses"]) == len(mod.LENS_CATALOG)


def test_sandbox_full_budget_50():
    mod = _load()
    p = mod.policy_for("sandbox")
    assert p["allow_mutations"] is True
    assert p["mutation_budget"] == 50
    assert "lens-business-logic" in p["allowed_lenses"]


def test_staging_no_input_injection():
    mod = _load()
    p = mod.policy_for("staging")
    assert p["allow_mutations"] is True
    assert p["mutation_budget"] == 25
    assert "lens-input-injection" not in p["allowed_lenses"], \
        "staging must drop input-injection (untrusted-input mutation)"


def test_prod_read_only_only_safe_lenses():
    mod = _load()
    p = mod.policy_for("prod")
    assert p["allow_mutations"] is False
    assert p["mutation_budget"] == 0
    # Only read-only / observation lenses allowed
    safe = {"lens-info-disclosure", "lens-auth-jwt"}
    assert p["allowed_lenses"] <= safe, \
        f"prod must only allow safe lenses; got: {p['allowed_lenses']}"
    assert p["allowed_lenses"], "prod still permits read-only lenses"


def test_unknown_env_raises():
    mod = _load()
    with pytest.raises(ValueError) as exc:
        mod.policy_for("preview")
    assert "preview" in str(exc.value)


def test_lens_catalog_size_16():
    mod = _load()
    # Sync with files in commands/vg/_shared/lens-prompts/
    assert len(mod.LENS_CATALOG) == 16, \
        f"LENS_CATALOG drift: {sorted(mod.LENS_CATALOG)}"
