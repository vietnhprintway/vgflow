"""Stage 5 task 3/6 of meta-memory v1.1 — Phase 2 Gather Signal.

Tests the read-side enforcement of the Codex #9 attribution gate (design
Section 13.4): when consolidation reads `bootstrap.outcome_recorded` events
from events.db, it MUST drop procedural-rule rows whose attribution is
empty/missing. Otherwise an attacker-or-bug could insert a row directly
and poison tier promotion.

Tests cover:
  * empty/missing events.db → empty signals, rc=0
  * 3 attributed PASS for a procedural rule → tier_proposed = "A"
  * empty executed_step_ids → counted in dropped_no_attribution, NOT pass
  * 3 PASS + 3 FAIL same rule → contradiction=True, tier_proposed=None
  * window cutoff: events older than --since-days dropped
  * declarative rules don't need attribution → counted by outcome
  * mixed PASS column + payload outcome accepted ("PASS" / "success")
  * unknown event types ignored (only bootstrap.outcome_recorded gathered)

Test isolation: each test creates a fresh sqlite db at tmp_path/events.db
and points the script at it via VG_EVENTS_DB_PATH. State dir uses
VG_BOOTSTRAP_STATE_DIR like the other phases.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

CONSOLIDATE = ".claude/scripts/bootstrap-consolidate.py"


def _make_events_db(db_path: Path) -> None:
    """Create minimal events.db schema matching vg-orchestrator/db.py."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            command TEXT NOT NULL,
            phase TEXT NOT NULL,
            args TEXT,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            outcome TEXT,
            session_id TEXT,
            git_sha TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            event_type TEXT NOT NULL,
            phase TEXT NOT NULL,
            command TEXT NOT NULL,
            step TEXT,
            actor TEXT NOT NULL,
            outcome TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            this_hash TEXT NOT NULL UNIQUE
        );
        """)
        # one fake run row to satisfy any FK queries readers might make
        conn.execute(
            "INSERT INTO runs(run_id, command, phase, started_at) "
            "VALUES (?, ?, ?, ?)",
            ("fake-run", "test", "test", "2026-01-01T00:00:00Z"),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_event(db_path: Path, *, event_type: str, outcome: str,
                  payload: dict, ts_offset_seconds: float = 0.0) -> None:
    """Insert one event row. Computes a fake hash chain (consolidation
    reads payload_json + outcome only; doesn't verify the chain)."""
    ts_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=ts_offset_seconds)
    ts = ts_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    fake_hash = hashlib.sha256(
        (str(uuid.uuid4()) + payload_json).encode()).hexdigest()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO events(run_id, ts, event_type, phase, command, step, "
            "actor, outcome, payload_json, prev_hash, this_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("fake-run", ts, event_type, "test", "test", None,
             "test", outcome, payload_json, "0" * 64, fake_hash),
        )
        conn.commit()
    finally:
        conn.close()


def _run_gather(state_dir: Path, db_path: Path | None = None,
                extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["VG_BOOTSTRAP_STATE_DIR"] = str(state_dir)
    if db_path is not None:
        env["VG_EVENTS_DB_PATH"] = str(db_path)
    argv = [sys.executable, CONSOLIDATE, "--phase", "gather", "--json"]
    if extra_args:
        argv.extend(extra_args)
    return subprocess.run(argv, capture_output=True, text=True, env=env)


# ---------- tests ----------

def test_gather_no_db_returns_empty_signals(tmp_path):
    """No events.db -> graceful degrade, rc=0, empty rule_signals."""
    db = tmp_path / "events.db"  # intentionally NOT created
    result = _run_gather(tmp_path, db)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["phase"] == "gather"
    assert report["events_processed"] == 0
    assert report["rule_signals"] == {}


def test_gather_attributed_pass_promotes_to_tier_a(tmp_path):
    """3+ attributed PASS for a procedural rule -> tier_proposed = 'A'."""
    db = tmp_path / "events.db"
    _make_events_db(db)
    payload = {
        "slug": "deploy-fly-prebuild",
        "rule_type": "procedural",
        "attribution": {
            "executed_step_ids": ["s1", "s2"],
            "total_steps": 2,
            "matched_signals_count": 2,
        },
    }
    for _ in range(4):
        _insert_event(db, event_type="bootstrap.outcome_recorded",
                      outcome="PASS", payload=payload)

    result = _run_gather(tmp_path, db)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    sig = report["rule_signals"]["deploy-fly-prebuild"]
    assert sig["attributed_pass"] == 4
    assert sig["attributed_fail"] == 0
    assert sig["tier_proposed"] == "A"
    assert sig["contradiction"] is False


def test_gather_empty_executed_steps_dropped(tmp_path):
    """Codex #9 cargo-cult prevention: attribution.executed_step_ids = []
    must be COUNTED in dropped_no_attribution and NOT in attributed_pass."""
    db = tmp_path / "events.db"
    _make_events_db(db)

    # 2 cargo-cult outcomes (empty executed_step_ids)
    for _ in range(2):
        _insert_event(db, event_type="bootstrap.outcome_recorded",
                      outcome="PASS",
                      payload={
                          "slug": "test-rule",
                          "rule_type": "procedural",
                          "attribution": {"executed_step_ids": [],
                                          "total_steps": 2,
                                          "matched_signals_count": 0},
                      })
    # 1 legit outcome
    _insert_event(db, event_type="bootstrap.outcome_recorded",
                  outcome="PASS",
                  payload={
                      "slug": "test-rule",
                      "rule_type": "procedural",
                      "attribution": {"executed_step_ids": ["s1", "s2"],
                                      "total_steps": 2,
                                      "matched_signals_count": 2},
                  })

    result = _run_gather(tmp_path, db)
    report = json.loads(result.stdout)
    sig = report["rule_signals"]["test-rule"]
    assert sig["attributed_pass"] == 1, (
        f"only the 1 legit outcome should count, not the 2 cargo-cult; "
        f"got {sig}")
    assert sig["dropped_no_attribution"] == 2
    assert sig["tier_proposed"] is None  # < 3 attributed PASS
    assert report["events_dropped_no_attribution"] == 2


def test_gather_missing_attribution_dropped(tmp_path):
    """Procedural rule WITHOUT attribution key entirely -> dropped."""
    db = tmp_path / "events.db"
    _make_events_db(db)

    for _ in range(3):
        _insert_event(db, event_type="bootstrap.outcome_recorded",
                      outcome="PASS",
                      payload={"slug": "no-attr-rule",
                               "rule_type": "procedural"})
    result = _run_gather(tmp_path, db)
    report = json.loads(result.stdout)
    sig = report["rule_signals"]["no-attr-rule"]
    assert sig["attributed_pass"] == 0
    assert sig["dropped_no_attribution"] == 3


def test_gather_contradiction_pass_then_fail(tmp_path):
    """3 PASS + 3 FAIL on same rule -> contradiction=True, tier_proposed=None."""
    db = tmp_path / "events.db"
    _make_events_db(db)
    base_payload = {
        "slug": "flaky-rule",
        "rule_type": "procedural",
        "attribution": {"executed_step_ids": ["s1"], "total_steps": 1,
                        "matched_signals_count": 1},
    }
    for _ in range(3):
        _insert_event(db, event_type="bootstrap.outcome_recorded",
                      outcome="PASS", payload=base_payload)
    for _ in range(3):
        _insert_event(db, event_type="bootstrap.outcome_recorded",
                      outcome="FAIL", payload=base_payload)

    result = _run_gather(tmp_path, db)
    report = json.loads(result.stdout)
    sig = report["rule_signals"]["flaky-rule"]
    assert sig["attributed_pass"] == 3
    assert sig["attributed_fail"] == 3
    assert sig["contradiction"] is True
    assert sig["tier_proposed"] is None  # contradiction wins, no auto-promote


def test_gather_window_cutoff_drops_old_events(tmp_path):
    """Events older than --since-days should not appear in events_processed."""
    db = tmp_path / "events.db"
    _make_events_db(db)
    payload = {"slug": "old-rule", "rule_type": "declarative"}

    # 2 events from 60 days ago (outside default 30-day window)
    for _ in range(2):
        _insert_event(db, event_type="bootstrap.outcome_recorded",
                      outcome="PASS", payload=payload,
                      ts_offset_seconds=-60 * 86400)
    # 1 fresh event
    _insert_event(db, event_type="bootstrap.outcome_recorded",
                  outcome="PASS", payload=payload)

    result = _run_gather(tmp_path, db)
    report = json.loads(result.stdout)
    # Only fresh event counted
    assert report["events_processed"] == 1
    assert report["rule_signals"]["old-rule"]["attributed_pass"] == 1


def test_gather_declarative_no_attribution_required(tmp_path):
    """Declarative rules don't need attribution; outcome counted as-is."""
    db = tmp_path / "events.db"
    _make_events_db(db)
    payload = {"slug": "decl-rule", "rule_type": "declarative"}
    for _ in range(3):
        _insert_event(db, event_type="bootstrap.outcome_recorded",
                      outcome="PASS", payload=payload)

    result = _run_gather(tmp_path, db)
    report = json.loads(result.stdout)
    sig = report["rule_signals"]["decl-rule"]
    assert sig["rule_type"] == "declarative"
    assert sig["attributed_pass"] == 3
    assert sig["dropped_no_attribution"] == 0
    assert sig["tier_proposed"] == "A"


def test_gather_ignores_other_event_types(tmp_path):
    """Only bootstrap.outcome_recorded should be aggregated."""
    db = tmp_path / "events.db"
    _make_events_db(db)
    # bootstrap.rule_fired - should be ignored
    _insert_event(db, event_type="bootstrap.rule_fired",
                  outcome="INFO",
                  payload={"slug": "fired-rule", "rule_type": "procedural"})
    # phase.deploy_completed - should be ignored
    _insert_event(db, event_type="phase.deploy_completed",
                  outcome="PASS", payload={"slug": "x"})

    result = _run_gather(tmp_path, db)
    report = json.loads(result.stdout)
    assert report["events_processed"] == 0
    assert report["rule_signals"] == {}
