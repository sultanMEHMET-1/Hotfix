"""Locking and atomic selector writes, shared by execution and reset."""

import asyncio
from contextlib import asynccontextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile

from .config import Settings, read_json, validator


def atomic_json(path: Path, value: dict):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class SelectorStore:
    def __init__(self, settings: Settings, workflow_id: str):
        self.workflow_id = workflow_id
        self.path = settings.selectors_for(workflow_id)
        self.state = settings.backend / "state"
        self.check = validator(read_json(settings.root / "contracts/selectors.schema.json"))

    @asynccontextmanager
    async def lock(self, exclusive=False):
        self.state.mkdir(parents=True, exist_ok=True)
        with (self.state / f"{self.workflow_id}.lock").open("a") as stream:
            operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            try:
                while True:
                    try:
                        fcntl.flock(stream, operation | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        await asyncio.sleep(0.02)
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def read(self):
        value = read_json(self.path)
        self.check.validate(value)
        return value

    def write(self, value: dict):
        self.check.validate(value)
        atomic_json(self.path, value)

    def backup(self, run_id: str, baseline: dict):
        path = self.state / f"baseline-{run_id}.json"
        atomic_json(path, baseline)
        return path

    @property
    def inflight(self):
        return self.state / f"inflight-{self.workflow_id}.json"

    def mark_inflight(self, backup_path: Path, version: int):
        """Written with the baseline backup. If the process dies mid-recovery, this is how startup knows to restore."""
        atomic_json(self.inflight, {"workflow": self.workflow_id, "baseline": str(backup_path), "version": version})

    def clear_inflight(self):
        self.inflight.unlink(missing_ok=True)

    def recover_inflight(self):
        """Restore the baseline of an interrupted recovery as a new higher version; None if nothing was interrupted.

        Old baseline-*.json backups are never restored on their own: only a marker says a recovery was in flight.
        When in doubt this restores the original, which is always safe (the next request simply heals again).
        """
        if not self.inflight.is_file():
            return None
        info = read_json(self.inflight)
        baseline = read_json(Path(info["baseline"]))
        self.check.validate(baseline)
        if baseline["workflow_id"] != self.workflow_id:
            raise ValueError("The interrupted recovery's backup belongs to another workflow")
        version = self.restore(baseline)
        self.clear_inflight()
        return version

    def restore(self, baseline: dict):
        current = self.read()
        restored = {**baseline, "version": max(current["version"], baseline["version"]) + 1}
        self.write(restored)
        return restored["version"]
