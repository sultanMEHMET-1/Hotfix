"""Restore selectors under the same lock as execution: from a backup, or the committed original."""

import argparse
import asyncio
import json
from pathlib import Path

from .config import Settings, read_json
from .store import SelectorStore


async def restore(path):
    settings = Settings.from_env()
    baseline = read_json(path)
    store = SelectorStore(settings, baseline["workflow_id"])
    store.check.validate(baseline)
    async with store.lock(exclusive=True):
        if store.read()["workflow_id"] != baseline["workflow_id"]:
            raise ValueError("Backup belongs to another workflow")
        version = store.restore(baseline)
    print(f"Baseline restored as selector version {version}")


async def committed_selectors(settings, workflow_id):
    """The selector map in git HEAD. Runtime heals never commit, so this is the pre-chaos state."""
    relative = settings.selectors_for(workflow_id).relative_to(settings.root).as_posix()
    process = await asyncio.create_subprocess_exec(
        "git", "show", f"HEAD:{relative}", cwd=settings.root,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise ValueError("The committed selector map is unavailable")
    return json.loads(stdout)


def restore_original(store, original):
    """Restore a committed map as a new higher version. The caller holds the exclusive lock."""
    store.check.validate(original)
    if store.read()["workflow_id"] != original["workflow_id"]:
        raise ValueError("The committed selector map belongs to another workflow")
    return store.restore(original)


async def restore_committed(workflows):
    settings = Settings.from_env()
    names = workflows or sorted(path.stem for path in (settings.root / "contracts/selectors").glob("*.json"))
    originals = {name: await committed_selectors(settings, name) for name in names}  # all or nothing
    for workflow_id in names:
        store = SelectorStore(settings, workflow_id)
        async with store.lock(exclusive=True):
            version = restore_original(store, originals[workflow_id])
        print(f"{workflow_id}: original selectors restored as selector version {version}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path, nargs="?", help="baseline-<run_id>.json from backend state/")
    parser.add_argument("--original", action="store_true", help="restore the committed maps (server stopped)")
    parser.add_argument("--workflow", action="append", help="with --original: only this workflow (repeatable)")
    args = parser.parse_args()
    if args.original == (args.backup is not None):
        parser.error("give either a backup path or --original")
    asyncio.run(restore_committed(args.workflow) if args.original else restore(args.backup))
