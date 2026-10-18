"""Restore selectors under the same lock as execution: from a backup, or the committed original."""

import argparse
import asyncio
import json
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


async def committed_selectors(settings):
    """The selector map in git HEAD. Runtime heals never commit, so this is the pre-chaos state."""
    relative = settings.selectors.relative_to(settings.root).as_posix()
    process = await asyncio.create_subprocess_exec(
        "git", "show", f"HEAD:{relative}", cwd=settings.root,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise ValueError("The committed selector map is unavailable")
    return json.loads(stdout)


async def restore_original(settings, store):
    """Restore the committed map as a new higher version. The caller holds the exclusive lock."""
    original = await committed_selectors(settings)
    store.check.validate(original)
    if store.read()["workflow_id"] != original["workflow_id"]:
        raise ValueError("The committed selector map belongs to another workflow")
    return store.restore(original)


async def restore_committed():
    settings = Settings.from_env()
    store = SelectorStore(settings)
    async with store.lock(exclusive=True):
        version = await restore_original(settings, store)
    print(f"Original selectors restored as selector version {version}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path, nargs="?", help="baseline-<run_id>.json from backend state/")
    parser.add_argument("--original", action="store_true", help="restore the committed map (server stopped)")
    args = parser.parse_args()
    if args.original == (args.backup is not None):
        parser.error("give either a backup path or --original")
    asyncio.run(restore_committed() if args.original else restore(args.backup))
