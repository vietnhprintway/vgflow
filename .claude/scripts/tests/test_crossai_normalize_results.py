from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
NORMALIZER = REPO_ROOT / ".claude" / "scripts" / "crossai-normalize-results.py"


def _run(output_dir: Path, label: str = "scope-review") -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(NORMALIZER),
            "--output-dir",
            str(output_dir),
            "--label",
            label,
            "--phase",
            "4.5",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _verdict(path: Path) -> str:
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    return (root.findtext("verdict") or "").strip()


def test_normalizes_auth_failure_to_inconclusive_xml(tmp_path):
    (tmp_path / "result-Codex.exit").write_text("1\n", encoding="utf-8")
    (tmp_path / "result-Codex.xml").write_text("", encoding="utf-8")
    (tmp_path / "result-Codex.err").write_text(
        "No active credentials for provider: openai\n",
        encoding="utf-8",
    )

    report = _run(tmp_path)

    assert report["verdict"] == "inconclusive"
    assert report["ok_count"] == 0
    assert report["total_clis"] == 1
    assert _verdict(tmp_path / "result-Codex.xml") == "inconclusive"
    assert _verdict(tmp_path / "scope-review.xml") == "inconclusive"


def test_preserves_valid_pass_and_reports_partial_ok(tmp_path):
    (tmp_path / "result-Codex.exit").write_text("0\n", encoding="utf-8")
    (tmp_path / "result-Codex.xml").write_text(
        "<crossai_review><reviewer>Codex</reviewer><verdict>pass</verdict><score>8</score></crossai_review>",
        encoding="utf-8",
    )
    (tmp_path / "result-Gemini.exit").write_text("1\n", encoding="utf-8")
    (tmp_path / "result-Gemini.err").write_text(
        "SELF_SIGNED_CERT_IN_CHAIN\n",
        encoding="utf-8",
    )

    report = _run(tmp_path, "blueprint-review")

    assert report["verdict"] == "pass"
    assert report["ok_count"] == 1
    assert report["total_clis"] == 2
    assert _verdict(tmp_path / "result-Gemini.xml") == "inconclusive"
    assert _verdict(tmp_path / "blueprint-review.xml") == "pass"
