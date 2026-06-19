#!/usr/bin/env python3
"""Organize duplicated __init__ files into package folders based on first line markers.

Rules (check EXACT first line):
- "# Data package"    -> move to data/__init__.py
- "# Tests package"   -> move to tests/__init__.py
- "# UI package"      -> move to ui/__init__.py
- "# Config package"  -> move to config/__init__.py
- "# Models package"  -> move to models/__init__.py
- "# Services package"-> move to services/__init__.py
- "# ai package"      -> move to ai/__init__.py

This script only moves files (no code modifications). If a target __init__.py
already exists, the incoming file is renamed to __init__.N.py to avoid data loss.
"""

from pathlib import Path
import shutil
import sys

MARKERS = {
    "# Data package": "data",
    "# Tests package": "tests",
    "# UI package": "ui",
    "# Config package": "config",
    "# Models package": "models",
    "# Services package": "services",
    "# ai package": "ai",
}

def first_line(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as f:
            line = f.readline()
            if not line:
                return ""
            return line.strip().lstrip("\ufeff")
    except Exception:
        return ""

def unique_target(target_dir: Path) -> Path:
    base = target_dir / "__init__.py"
    if not base.exists():
        return base
    # find next available __init__.N.py
    i = 1
    while True:
        candidate = target_dir / f"__init__.{i}.py"
        if not candidate.exists():
            return candidate
        i += 1

def main(root: Path):
    moved = []
    skipped = []
    for p in sorted(root.iterdir()):
        if not p.is_file():
            continue
        name = p.name
        if not name.startswith("__init__") or not name.endswith(".py"):
            continue
        fl = first_line(p)
        tgt_dirname = MARKERS.get(fl)
        if not tgt_dirname:
            skipped.append((p, fl))
            continue
        tgt_dir = root / tgt_dirname
        tgt_dir.mkdir(parents=True, exist_ok=True)
        dst = unique_target(tgt_dir)
        try:
            shutil.move(str(p), str(dst))
            moved.append((p, dst))
        except Exception as e:
            skipped.append((p, f"move_error:{e}"))

    # Print summary
    if moved:
        print("Moved files:")
        for s,d in moved:
            print(f"- {s.name} -> {d.relative_to(root)}")
    else:
        print("No files moved.")

    if skipped:
        print("\nSkipped or unrecognized files:")
        for s,reason in skipped:
            print(f"- {s.name}: {reason}")

    print(f"\nDone. Processed in {root.resolve()}")


if __name__ == "__main__":
    start = Path.cwd()
    if len(sys.argv) > 1:
        start = Path(sys.argv[1])
    main(start)
