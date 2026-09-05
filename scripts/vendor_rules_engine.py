"""Replace the engine snapshot with the exact files from a production Git commit."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

PINNED_COMMIT = "ad26d54a8b57fd359b3ff3c0b9addf87f9b43f3f"
SOURCE_PREFIX = "src/rules_engine/"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Local production rules_engine Git checkout")
    parser.add_argument("--commit", default=PINNED_COMMIT)
    args = parser.parse_args()
    commit = subprocess.check_output(
        ["git", "-C", str(args.source), "rev-parse", f"{args.commit}^{{commit}}"], text=True
    ).strip()
    archive = subprocess.check_output(
        ["git", "-C", str(args.source), "archive", commit, "src/rules_engine"]
    )
    # Read the archive before replacing anything; never copy working-tree changes.
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as snapshot:
        for member in snapshot.getmembers():
            if not member.isfile():
                continue
            relative = Path(member.name.removeprefix(SOURCE_PREFIX))
            if not member.name.startswith(SOURCE_PREFIX) or relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unexpected engine archive path: {member.name}")
            source = snapshot.extractfile(member)
            if source is None:
                raise ValueError(f"Cannot read engine archive member: {member.name}")
            files[relative] = source.read()
    if Path("__init__.py") not in files:
        raise ValueError("Source commit does not contain the rules_engine package")

    project = Path(__file__).resolve().parents[1]
    destination = (project / "rules_engine").resolve()
    if destination.parent != project or destination.name != "rules_engine":
        raise ValueError("Snapshot destination is outside the Studio workspace")
    destination.mkdir(exist_ok=True)
    for existing in destination.rglob("*.py"):
        if existing.relative_to(destination) not in files:
            existing.unlink()
    for relative, content in files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = {
        "repository": "https://github.com/arbaizam/rules_engine",
        "commit": commit,
        "files": {
            relative.as_posix(): hashlib.sha256(content).hexdigest()
            for relative, content in sorted(files.items())
        },
    }
    (project / "docs" / "rules_engine_snapshot.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Vendored {len(files)} files from {commit}")


if __name__ == "__main__":
    main()
