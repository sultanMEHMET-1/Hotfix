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
    def __init__(self, settings: Settings):
        self.path = settings.selectors
        self.state = settings.backend / "state"
        self.check = validator(read_json(settings.root / "contracts/selectors.schema.json"))

    @asynccontextmanager
    async def lock(self, exclusive=False):
        self.state.mkdir(parents=True, exist_ok=True)
        with (self.state / "selectors.lock").open("a") as stream:
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

    def restore(self, baseline: dict):
        current = self.read()
        restored = {**baseline, "version": max(current["version"], baseline["version"]) + 1}
        self.write(restored)
        return restored["version"]
