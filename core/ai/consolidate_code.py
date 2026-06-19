#!/usr/bin/env python3
"""
Smart Land Management Copilot — Code Consolidation Script

Scans the entire project tree and writes every source file into a single
consolidated text file for easy review, archiving, or LLM ingestion.

Usage:
    python scripts/consolidate_code.py

Output:
    Smart_Land_Copilot_All_Code.txt  (project root)
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Extensions to include (with the special "Dockerfile" bare name)
INCLUDED_EXTENSIONS = {
    ".py", ".yml", ".yaml", ".json", ".txt", ".md",
}
INCLUDED_BASENAMES = {"Dockerfile"}

# Directories to skip entirely
EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    "dist",
    "build",
    "*.egg-info",
}

# Files to skip (by basename or suffix)
EXCLUDED_PATTERNS = {"*.pyc", "*.pyo", "*.so", "*.dylib"}

# The output path
OUTPUT_PATH = PROJECT_ROOT / "Smart_Land_Copilot_All_Code.txt"

# ── Helpers ──────────────────────────────────────────────────────────────────


def is_text_file(filepath: Path) -> bool:
    """
    Heuristic: try to decode the first chunk as UTF-8.
    Falls back to latin-1 for files that are textual but not pure UTF-8.
    Returns False for anything that looks binary.
    """
    try:
        chunk_size = 8192
        with open(filepath, "rb") as f:
            chunk = f.read(chunk_size)
        # Quick binary check: look for null bytes in first 1024 bytes
        if b"\x00" in chunk[:1024]:
            return False
        # Try UTF-8 decode
        chunk.decode("utf-8")
        return True
    except (UnicodeDecodeError, PermissionError, OSError):
        try:
            chunk.decode("latin-1")
            return True
        except Exception:
            return False


def should_include(filepath: Path) -> bool:
    """Decide whether a given file path should be consolidated."""
    # Skip the script itself
    if filepath.samefile(Path(__file__).resolve()):
        return False

    # Skip the output file
    try:
        if filepath.samefile(OUTPUT_PATH):
            return False
    except FileNotFoundError:
        pass

    # Check extension or special basename
    if filepath.suffix.lower() in INCLUDED_EXTENSIONS:
        return True
    if filepath.name in INCLUDED_BASENAMES:
        return True
    return False


def collect_files(root: Path) -> list[Path]:
    """Walk the project tree and return a sorted list of files to include."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)

        # Prune excluded directories in-place so os.walk skips them
        dirnames[:] = [
            d
            for d in dirnames
            if d not in EXCLUDED_DIRS
            and not any(d.endswith(suffix) for suffix in (".egg-info",))
        ]

        # Also skip the scripts directory's output
        for fname in sorted(filenames):
            fpath = current / fname

            # Skip compiled Python files
            if fname.endswith((".pyc", ".pyo")):
                continue

            if should_include(fpath) and is_text_file(fpath):
                files.append(fpath)

    return sorted(files)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"Scanning project: {PROJECT_ROOT}")
    print()

    files = collect_files(PROJECT_ROOT)

    if not files:
        print("ERROR: No files found to consolidate.")
        sys.exit(1)

    # Count total lines
    total_lines = 0
    file_contents: list[tuple[str, str]] = []  # (relative_path, content)

    for fpath in files:
        rel = fpath.relative_to(PROJECT_ROOT).as_posix()
        # Try UTF-8 first, fall back to latin-1
        try:
            content = fpath.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = fpath.read_text(encoding="latin-1", errors="replace")

        line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        total_lines += line_count
        file_contents.append((rel, content))

    # ── Write consolidated file ──────────────────────────────────────────

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    separator = "=" * 80

    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        out.write(f"{separator}\n")
        out.write("SMART LAND MANAGEMENT COPILOT — COMPLETE SOURCE CODE\n")
        out.write(f"{separator}\n")
        out.write(f"Generated: {now}\n")
        out.write(f"Total files: {len(files)}\n")
        out.write(f"Total lines: {total_lines}\n")
        out.write("Project: Smart Land Management Copilot v7.0 — Arabic Edition\n")
        out.write(
            "Architecture: 6-module Clean Architecture "
            "(api_gateway, services, infrastructure, web)\n"
        )
        out.write(f"{separator}\n")
        out.write("\n")

        for i, (rel, content) in enumerate(file_contents):
            file_sep = "-" * 80
            out.write(f"{file_sep}\n")
            out.write(f"--- FILE: {rel} ---\n")
            out.write(content)
            # Ensure file ends with a newline before the next separator
            if content and not content.endswith("\n"):
                out.write("\n")
            out.write("\n")

            # Progress dots
            if (i + 1) % 50 == 0 or i + 1 == len(file_contents):
                print(f"  Processed {i + 1}/{len(file_contents)} files...")

        # ── Footer ───────────────────────────────────────────────────────
        out.write(f"{separator}\n")
        out.write("END OF CONSOLIDATED SOURCE CODE\n")
        out.write(f"{separator}\n")

    print()
    print(f"Done! Consolidated {len(files)} files ({total_lines:,} lines)")
    print(f"Output: {OUTPUT_PATH}")
    print(f"Size:   {OUTPUT_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
