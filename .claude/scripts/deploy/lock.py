"""v2.82.1 Stage 6.4 — per-env deploy flock.

Prevents two parallel `/vg:deploy --envs=prod` invocations from racing on
the same env. One env-lock per env file: `.vg/deploy/.deploy.lock.<env>`.

Cross-platform implementation:
  - POSIX: `fcntl.flock()` LOCK_EX | LOCK_NB
  - Windows: `msvcrt.locking()` LK_NBLCK
  Both expose the same `acquire()` / `release()` semantics; non-blocking
  acquisition raises `DeployLockHeld` when another process holds it.

Lock file holds caller PID + start time so a stale-lock detector
(deferred to a future minor) can identify abandoned locks. Does NOT
auto-clear stale locks here — explicit `--force-unlock` flag will land in
the deploy executor (Stage 7) once the consumer migration touches it.

Usage:
    from deploy.lock import deploy_lock
    with deploy_lock(project_root, env="prod"):
        run_deploy_commands(...)
"""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class DeployLockHeld(RuntimeError):
    """Raised when another process already holds the deploy lock for env."""

    def __init__(self, env: str, holder: dict | None = None):
        self.env = env
        self.holder = holder or {}
        msg = f"deploy lock held for env={env!r}"
        if holder:
            msg += f" (pid={holder.get('pid')}, started={holder.get('started_at')})"
        super().__init__(msg)


def _lock_path(project_root: Path | str, env: str) -> Path:
    """One file per env. Trailing dot keeps glob `.deploy.lock.*` selective."""
    safe_env = env.replace("/", "_").replace("..", "_")
    return Path(project_root).resolve() / ".vg" / "deploy" / f".deploy.lock.{safe_env}"


@contextmanager
def deploy_lock(
    project_root: Path | str,
    env: str,
    *,
    holder_meta: dict | None = None,
) -> Iterator[Path]:
    """Acquire an exclusive non-blocking lock for `env`.

    Yields the lock file path. Releases (and removes the file) on exit.
    Raises `DeployLockHeld` when another process owns the lock.
    """
    path = _lock_path(project_root, env)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Open the lock file for read+write so flock has a non-empty inode to
    # latch onto. `O_CREAT` + 0o644 keeps the file world-readable for the
    # stale-lock detector (future minor).
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)

    if sys.platform == "win32":
        import msvcrt  # noqa: WPS433 — platform-specific import

        try:
            # Lock the first byte non-blocking (LK_NBLCK).
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        except OSError as e:
            os.close(fd)
            holder = _read_holder(path)
            raise DeployLockHeld(env, holder) from e
    else:
        import fcntl  # noqa: WPS433 — platform-specific import

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            holder = _read_holder(path)
            raise DeployLockHeld(env, holder) from e

    # Write holder metadata for stale-lock diagnostics.
    holder = {
        "pid": os.getpid(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "env": env,
    }
    if holder_meta:
        holder.update(holder_meta)
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    os.write(fd, json.dumps(holder).encode("utf-8"))

    try:
        yield path
    finally:
        if sys.platform == "win32":
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            except OSError:
                pass
        else:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            os.close(fd)
        except OSError:
            pass
        # Remove lock file so the next acquire starts clean. Tolerate races
        # (another acquirer may have already removed + re-created it).
        try:
            path.unlink()
        except OSError:
            pass


def _read_holder(path: Path) -> dict | None:
    """Best-effort read of holder metadata from a held lock file."""
    try:
        body = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None
