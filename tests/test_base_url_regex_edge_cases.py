"""Edge cases cho resolve_base_url regex."""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_module():
    spec = importlib.util.spec_from_file_location(
        "spawn_crud", REPO_ROOT / "scripts" / "spawn-crud-roundtrip.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("config_text,expected", [
    # Comment line above real value — must skip comment
    ("# base_url: http://commented-out\nbase_url: http://real:1234\n", "http://real:1234"),
    # Inline trailing comment — must NOT include `#`
    ("base_url: http://x:1 # primary\n", "http://x:1"),
    # Quoted form double
    ('base_url: "http://quoted:5678"\n', "http://quoted:5678"),
    # Quoted form single
    ("base_url: 'http://single-quoted:9999'\n", "http://single-quoted:9999"),
    # Tab-indented (nested under review:)
    ("review:\n\tauth:\n\t\tbase_url: http://tabbed:1111\n", "http://tabbed:1111"),
    # CRLF line endings
    ("base_url: http://crlf:2222\r\n", "http://crlf:2222"),
    # Top-level + nested both present — first match wins
    (
        "base_url: http://top:3333\nreview:\n  auth:\n    base_url: http://nested:4444\n",
        "http://top:3333",
    ),
])
def test_base_url_regex_handles_edge_cases(tmp_path, config_text, expected, monkeypatch):
    phase = tmp_path / "phase"
    phase.mkdir()
    (phase / "vg.config.md").write_text(config_text, encoding="utf-8")
    mod = load_module()
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path / "no-fallback")
    result = mod.resolve_base_url(phase)
    assert result == expected, f"Failed for input: {config_text!r}"


def test_base_url_returns_none_for_malformed_no_value(tmp_path, monkeypatch):
    """When key exists but no value (next line is different key), MUST return None — no bleed."""
    phase = tmp_path / "phase"
    phase.mkdir()
    (phase / "vg.config.md").write_text(
        "base_url:\n  some_other: yes\n", encoding="utf-8"
    )
    mod = load_module()
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path / "no-fallback-here")
    result = mod.resolve_base_url(phase)
    # After I-1 fix, regex should NOT bleed to next line
    assert result is None, f"Regex bleed: captured {result!r} from malformed YAML"
