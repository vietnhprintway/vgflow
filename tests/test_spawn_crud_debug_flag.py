import importlib.util
import subprocess
from pathlib import Path


def test_debug_flag_writes_log(tmp_path):
    phase = tmp_path / "phase"
    phase.mkdir()
    (phase / "CRUD-SURFACES.md").write_text("# resources: []\n")
    (phase / "runs").mkdir()
    result = subprocess.run(
        ["python", "scripts/spawn-crud-roundtrip.py",
         "--phase-dir", str(phase), "--debug", "--dry-run"],
        capture_output=True, text=True
    )
    debug_logs = list((phase / "runs").glob(".debug-*.log"))
    assert result.returncode == 0
    # Dry-run with no resources still emits debug log header
    assert "DEBUG MODE" in result.stdout or any(debug_logs)


def test_debug_log_format(tmp_path, monkeypatch):
    """Verify spawn_worker writes properly formatted debug log when debug_log_path set.

    Critically asserts the prompt content does NOT leak into the log file —
    auth tokens are embedded in the prompt and must remain redacted.
    """
    spec = importlib.util.spec_from_file_location(
        "spawn_crud", "scripts/spawn-crud-roundtrip.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fake = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="hello world", stderr="warning msg"
    )
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **kw: fake)

    log_path = tmp_path / ".debug-test123.log"
    result = mod.spawn_worker(
        "dummy prompt with secret", "gemini-2.5-flash", "playwright1", 60, log_path
    )

    assert result["exit_code"] == 0
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert "=== CMD ===" in content
    assert "=== EXIT 0" in content
    assert "=== STDOUT (full" in content
    assert "hello world" in content
    assert "=== STDERR (full" in content
    assert "warning msg" in content
    # CRITICAL: verify prompt does NOT leak (contains auth tokens in production)
    assert "dummy prompt with secret" not in content
    # And confirm redaction marker IS present
    assert "<REDACTED" in content
