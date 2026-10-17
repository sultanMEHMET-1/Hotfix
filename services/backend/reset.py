"""Restore a backend baseline backup under the same lock as execution."""

import argparse
import asyncio
from pathlib import Path

from .config import Settings, read_json
from .store import SelectorStore


async def restore(path):
    store = SelectorStore(Settings.from_env())
    baseline = read_json(path)
    store.check.validate(baseline)
    async with store.lock(exclusive=True):
        if store.read()["workflow_id"] != baseline["workflow_id"]:
            raise ValueError("Backup belongs to another workflow")
        version = store.restore(baseline)
    print(f"Baseline restored as selector version {version}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    asyncio.run(restore(parser.parse_args().backup))
