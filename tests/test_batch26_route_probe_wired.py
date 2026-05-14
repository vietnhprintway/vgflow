"""tests/test_batch26_route_probe_wired.py — Batch 26 route probe wiring."""
from __future__ import annotations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_test_deploy_runs_route_probe():
    body = (REPO / "commands/vg/_shared/test/deploy.md").read_text(encoding="utf-8")
    assert "probe-fe-routes" in body, (
        "Batch 26: test/deploy.md must invoke probe-fe-routes.py post-deploy"
    )


def test_review_api_discovery_runs_parity_check():
    body = (REPO / "commands/vg/_shared/review/api-and-discovery.md").read_text(encoding="utf-8")
    assert "verify-be-fe-consumer-parity" in body, (
        "Batch 26: review api-and-discovery must invoke parity validator"
    )
