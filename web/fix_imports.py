#!/usr/bin/env python3
"""
fix_imports.py — AST-Based Import Path Fixer for Clean Architecture
=====================================================================
Smart Land Management Copilot

Uses Python's ast module (NOT regex) to safely parse, transform,
and validate every import statement across the entire project.

Features:
  1. AST-safe parsing — never breaks valid Python syntax
  2. Precise module-level mapping (longest-prefix-first matching)
  3. Placeholder comment removal (# نوع التعديل, # TODO, etc.)
  4. Generates import_map.json for future reference
  5. Validates all files with ast.parse after transformation
  6. Scans OLD directories and identifies dead code

Usage:
  python fix_imports.py                  # dry-run (show changes only)
  python fix_imports.py --apply          # apply changes to files
  python fix_imports.py --apply --clean  # apply + delete old dirs
  python fix_imports.py --validate       # validate all files only
  python fix_imports.py --gen-map        # generate import_map.json only
"""

import ast
import json
import os
import re
import sys
import shutil
import argparse
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from collections import defaultdict
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# Project Root
# ══════════════════════════════════════════════════════════════
PROJECT_ROOT = Path(__file__).resolve().parent

# ══════════════════════════════════════════════════════════════
# Complete Import Mapping: old_module -> new_module
# Sorted by length (longest first) to prevent partial matches
# ══════════════════════════════════════════════════════════════
IMPORT_MAP: Dict[str, str] = {
    # ── data/ -> core/domain/ ──
    "data.land_database":               "core.domain.land_database",
    "data":                             "core.domain",

    # ── root search_engine.py -> core/matchmaking/ ──
    "search_engine":                    "core.matchmaking.service",

    # ── ai/ -> core/ai/llm/ or core/ai/tft/ ──
    "ai.glm_client":                    "core.ai.llm.glm_client",
    "ai.ollama_service":                "core.ai.llm.ollama_service",
    "ai.llm_router":                    "core.ai.llm.router",
    "ai.tft_model":                     "core.ai.tft.model",
    "ai.tft_training":                  "core.ai.tft.training",
    "ai.tft_airflow_dag":               "core.ai.tft.airflow_dag",

    # ── geological/ -> core/geological/ + infrastructure/external/geological/ ──
    "geological.groundwater_service":   "core.geological.groundwater_service",
    "geological.soil_service":          "core.geological.soil_service",
    "geological.egsma_reader":          "infrastructure.external.geological.egsma_reader",
    "geological.gee_client":            "infrastructure.external.geological.gee_client",
    "geological.service":               "core.geological.service",

    # ── payment/ -> core/financial/ + infrastructure/external/payment/ ──
    "payment.transaction_service":      "core.financial.service",
    "payment.fawry_gateway":            "infrastructure.external.payment.fawry_gateway",
    "payment.stripe_gateway":           "infrastructure.external.payment.stripe_gateway",
    "payment.base":                     "core.financial.base",

    # ── customer_service/ -> core/customer_service/ + infrastructure/external/ ──
    "customer_service.whatsapp_service": "infrastructure.external.customer_service.whatsapp_service",
    "customer_service.zendesk_client":   "infrastructure.external.customer_service.zendesk_client",
    "customer_service.rag_chatbot":      "core.customer_service.rag_chatbot",
    "customer_service.survey_service":   "core.customer_service.survey_service",
    "customer_service.hub":              "core.customer_service.hub",

    # ── microservices/shared -> core/domain/entities ──
    "shared":                           "core.domain.entities",

    # ── bare module imports that were used via sys.path hacks ──
    "account_store":                    "core.account.store",

    # ── incomplete/incorrect paths written during earlier refactoring ──
    "infrastructure.external.zendesk_client": "infrastructure.external.customer_service.zendesk_client",
    "infrastructure.external.whatsapp_service": "infrastructure.external.customer_service.whatsapp_service",
}

# Sorted keys: longest first to prevent partial prefix matches
SORTED_MAP_KEYS = sorted(IMPORT_MAP.keys(), key=len, reverse=True)

# ══════════════════════════════════════════════════════════════
# Old directories / files (candidates for deletion with --clean)
# ══════════════════════════════════════════════════════════════
OLD_DIRS = ["ai", "customer_service", "data", "geological", "payment"]
OLD_ROOT_FILES = ["search_engine.py", "app.py", "Dockerfile.streamlit",
                   "docker-compose-ollama.yml"]

# ══════════════════════════════════════════════════════════════
# Directories to skip during scanning
# ══════════════════════════════════════════════════════════════
SKIP_DIRS = {
    "__pycache__", ".git", "node_modules", ".eggs",
    "dist", "build", ".mypy_cache", ".pytest_cache",
    # Keep microservices as-is (Docker volume mount design)
}

# ══════════════════════════════════════════════════════════════
# Placeholder comment patterns to remove from import lines
# ══════════════════════════════════════════════════════════════
PLACEHOLDER_PATTERNS = [
    re.compile(r'\s*#\s*(نوع التعديل|TODO|FIXME|HACK|XXX|NOQA|type:\s*ignore).*$', re.IGNORECASE),
    re.compile(r'\s*#\s*تحتاج تعديل.*$', re.IGNORECASE),
    re.compile(r'\s*#\s*needs\s+(update|fix|change|refactor).*$', re.IGNORECASE),
    re.compile(r'\s*#\s*placeholder.*$', re.IGNORECASE),
    re.compile(r'\s*#\s*بديل مؤقت.*$', re.IGNORECASE),
    re.compile(r'\s*#\s*temp(orary)?.*$', re.IGNORECASE),
]

# ══════════════════════════════════════════════════════════════
# Standard library modules (never refactor these)
# ══════════════════════════════════════════════════════════════
STDLIB_MODULES = {
    "abc", "aifc", "argparse", "array", "ast", "asyncio", "atexit",
    "base64", "binascii", "bisect", "builtins", "bz2", "calendar",
    "cgi", "cgitb", "chunk", "cmath", "cmd", "code", "codecs",
    "collections", "colorsys", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "csv", "ctypes",
    "dataclasses", "datetime", "dbm", "decimal", "difflib", "dis",
    "distutils", "doctest", "email", "encodings", "enum", "errno",
    "faulthandler", "fcntl", "filecmp", "fileinput", "fnmatch",
    "fractions", "ftplib", "functools", "gc", "getopt", "getpass",
    "gettext", "glob", "graphlib", "grp", "gzip", "hashlib", "heapq",
    "hmac", "html", "http", "imaplib", "importlib", "inspect", "io",
    "ipaddress", "itertools", "json", "keyword", "lib2to3", "linecache",
    "locale", "logging", "lzma", "mailbox", "mailcap", "marshal",
    "math", "mimetypes", "mmap", "modulefinder", "multiprocessing",
    "netrc", "nis", "nntplib", "numbers", "operator", "optparse", "os",
    "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
    "platform", "plistlib", "poplib", "posix", "posixpath", "pprint",
    "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
    "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
    "sqlite3", "ssl", "stat", "statistics", "string", "struct",
    "subprocess", "sunau", "symtable", "sys", "sysconfig", "syslog",
    "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test",
    "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "trace", "traceback", "tracemalloc", "tty", "turtle",
    "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib",
    "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
    "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp",
    "zipfile", "zipimport", "zlib", "zoneinfo",
}


# ══════════════════════════════════════════════════════════════
# Core: Module Path Resolver
# ══════════════════════════════════════════════════════════════

def resolve_module(old_module: str) -> Optional[str]:
    """
    Find the new module path for an old import.
    Uses longest-prefix-first matching to avoid partial replacements.
    Returns None if no mapping exists (stdlib or third-party).
    """
    for old_key in SORTED_MAP_KEYS:
        # Exact match
        if old_module == old_key:
            return IMPORT_MAP[old_key]
        # Prefix match: old_module starts with old_key + "."
        if old_module.startswith(old_key + "."):
            remainder = old_module[len(old_key) + 1:]  # skip the dot
            new_base = IMPORT_MAP[old_key]
            return f"{new_base}.{remainder}"
    return None


def is_project_module(module_name: str) -> bool:
    """
    Check if a module name is a project-local module (not stdlib/third-party).
    Project modules start with one of our known prefixes.
    """
    first_part = module_name.split(".")[0]
    project_prefixes = {
        "core", "infrastructure", "config", "api", "web",
        # Old prefixes (before refactor)
        "data", "search_engine", "ai", "geological", "payment",
        "customer_service", "shared", "account_store",
    }
    return first_part in project_prefixes


def clean_placeholder_comment(line: str) -> str:
    """
    Remove placeholder/todo/fake comments from an import line.
    Preserves legitimate inline comments.
    """
    for pattern in PLACEHOLDER_PATTERNS:
        cleaned = pattern.sub("", line)
        if cleaned != line:
            # Remove trailing whitespace left behind
            return cleaned.rstrip()
    return line


# ══════════════════════════════════════════════════════════════
# Core: AST-Based Import Transformer
# ══════════════════════════════════════════════════════════════

class ImportFixer(ast.NodeTransformer):
    """
    AST NodeTransformer that rewrites import statements.
    Tracks all changes for reporting.
    """

    def __init__(self, source_lines: List[str]):
        super().__init__()
        self.source_lines = source_lines
        self.changes: List[Dict] = []  # [{line_no, old, new, type}]

    def _resolve_and_record(self, old_module: str, node, import_type: str) -> str:
        """Resolve a module and record the change if any."""
        new_module = resolve_module(old_module)
        if new_module and new_module != old_module:
            self.changes.append({
                "line": node.lineno,
                "old": old_module,
                "new": new_module,
                "type": import_type,
            })
            return new_module
        return old_module

    def visit_Import(self, node: ast.Import) -> ast.Import:
        """Handle: import X [as Y]"""
        new_aliases = []
        for alias in node.names:
            resolved = self._resolve_and_record(alias.name, node, "import")
            new_aliases.append(ast.alias(
                name=resolved,
                asname=alias.asname,
            ))
        node.names = new_aliases
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        """Handle: from X import Y [as Z]"""
        if node.module is None:
            # Relative import like "from . import X" — skip
            return node

        resolved = self._resolve_and_record(node.module, node, "from")
        node.module = resolved
        return node


class LineBasedPostProcessor:
    """
    Post-processes source lines to:
    1. Update the text representation of transformed AST nodes
    2. Remove placeholder comments from import lines
    3. Preserve original formatting (indentation, blank lines, etc.)
    """

    def __init__(self, source_lines: List[str], changes: List[Dict]):
        self.lines = list(source_lines)  # mutable copy
        self.changes = changes

    def apply(self) -> Tuple[str, int]:
        """
        Apply changes to source lines.
        Returns (new_source, total_line_changes).
        """
        total = 0

        for change in self.changes:
            line_no = change["line"]
            idx = line_no - 1  # 0-based index

            if idx < 0 or idx >= len(self.lines):
                continue

            old_line = self.lines[idx]

            # Determine the import pattern and replace the module part
            if change["type"] == "import":
                new_line = self._fix_import_line(old_line, change["old"], change["new"])
            elif change["type"] == "from":
                new_line = self._fix_from_line(old_line, change["old"], change["new"])
            else:
                new_line = old_line

            # Remove placeholder comments
            new_line = clean_placeholder_comment(new_line)

            if new_line != old_line:
                self.lines[idx] = new_line
                total += 1

        # Also scan ALL import lines for placeholder comments (even if not remapped)
        for i, line in enumerate(self.lines):
            stripped = line.lstrip()
            if (stripped.startswith("import ") or stripped.startswith("from ")):
                cleaned = clean_placeholder_comment(line)
                if cleaned != line and cleaned not in self.lines:
                    self.lines[i] = cleaned

        return "\n".join(self.lines), total

    @staticmethod
    def _fix_import_line(line: str, old_mod: str, new_mod: str) -> str:
        """Fix: import old_mod [as alias]"""
        # Pattern: import X [as Y]
        pattern = re.compile(
            r'^(import\s+)'
            r'(?:' + re.escape(old_mod) + r')'
            r'(\s*(?:as\s+\w+)?)\s*$'
        )
        m = pattern.match(line.strip())
        if m:
            indent = len(line) - len(line.lstrip())
            return " " * indent + f"import {new_mod}{m.group(2)}"

        # Broader pattern for lines with extra content
        pattern2 = re.compile(r'\b' + re.escape(old_mod) + r'\b')
        return pattern2.sub(new_mod, line)

    @staticmethod
    def _fix_from_line(line: str, old_mod: str, new_mod: str) -> str:
        """Fix: from old_mod import ..."""
        pattern = re.compile(
            r'^(from\s+)'
            r'(?:' + re.escape(old_mod) + r')'
            r'(\s+import\s+.*)$'
        )
        m = pattern.match(line.strip())
        if m:
            indent = len(line) - len(line.lstrip())
            return " " * indent + f"from {new_mod}{m.group(2)}"

        # Broader pattern
        pattern2 = re.compile(r'\b' + re.escape(old_mod) + r'\b')
        return pattern2.sub(new_mod, line)


# ══════════════════════════════════════════════════════════════
# Core: File Processor
# ══════════════════════════════════════════════════════════════

def process_file(filepath: Path, apply: bool = False) -> Dict:
    """
    Process a single .py file:
    1. Read source
    2. Parse with AST
    3. Transform imports
    4. Post-process lines (placeholder removal)
    5. Validate result with ast.parse
    6. Optionally write back

    Returns dict with stats and details.
    """
    result = {
        "path": str(filepath.relative_to(PROJECT_ROOT)),
        "status": "skipped",
        "changes": [],
        "line_changes": 0,
        "error": None,
    }

    try:
        source = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError) as e:
        result["status"] = "error"
        result["error"] = f"Cannot read: {e}"
        return result

    source_lines = source.split("\n")

    # Step 1: Parse original
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as e:
        result["status"] = "error"
        result["error"] = f"Original syntax error at line {e.lineno}: {e.msg}"
        return result

    # Step 2: Transform imports via AST
    fixer = ImportFixer(source_lines)
    new_tree = fixer.visit(tree)
    ast.fix_missing_locations(new_tree)

    if not fixer.changes:
        result["status"] = "clean"
        return result

    result["changes"] = fixer.changes

    # Step 3: Post-process lines (text-level fixes + placeholder removal)
    post_processor = LineBasedPostProcessor(source_lines, fixer.changes)
    new_source, line_changes = post_processor.apply()
    result["line_changes"] = line_changes

    # Step 4: Validate the result
    try:
        ast.parse(new_source, filename=str(filepath))
    except SyntaxError as e:
        result["status"] = "error"
        result["error"] = f"Syntax error AFTER transform at line {e.lineno}: {e.msg}"
        # Rollback: don't apply broken code
        return result

    # Step 5: Write back if --apply
    if apply:
        filepath.write_text(new_source, encoding="utf-8")
        result["status"] = "applied"
    else:
        result["status"] = "pending"

    return result


# ══════════════════════════════════════════════════════════════
# Core: Project Scanner
# ══════════════════════════════════════════════════════════════

def should_skip(rel_path: Path) -> bool:
    """Check if a file should be skipped based on its path."""
    return any(part in SKIP_DIRS for part in rel_path.parts)


def scan_project(apply: bool = False, verbose: bool = False) -> Dict:
    """
    Scan all .py files in the project and fix imports.

    Returns comprehensive stats dict.
    """
    stats = {
        "files_scanned": 0,
        "files_clean": 0,
        "files_pending": 0,
        "files_applied": 0,
        "files_error": 0,
        "total_import_changes": 0,
        "total_line_changes": 0,
        "errors": [],
        "details": [],
    }

    # Target directories to scan (clean architecture layers + root)
    scan_dirs = ["config", "core", "infrastructure", "api", "web", "alembic"]

    py_files = []
    for d in scan_dirs:
        dpath = PROJECT_ROOT / d
        if dpath.is_dir():
            py_files.extend(dpath.rglob("*.py"))

    # Root-level .py files (except this script and other tools)
    tool_scripts = {"fix_imports.py", "refactor_imports.py", "super_organizer.py"}
    for fp in PROJECT_ROOT.glob("*.py"):
        if fp.name not in tool_scripts:
            py_files.append(fp)

    py_files = sorted(set(py_files))

    for filepath in py_files:
        rel = filepath.relative_to(PROJECT_ROOT)
        if should_skip(rel):
            continue

        stats["files_scanned"] += 1
        result = process_file(filepath, apply=apply)

        if result["status"] == "clean":
            stats["files_clean"] += 1
        elif result["status"] == "pending":
            stats["files_pending"] += 1
            stats["total_import_changes"] += len(result["changes"])
            stats["total_line_changes"] += result["line_changes"]
            stats["details"].append(result)
            if verbose:
                _print_file_result(result, verbose=True)
            else:
                _print_file_result(result, verbose=False)
        elif result["status"] == "applied":
            stats["files_applied"] += 1
            stats["total_import_changes"] += len(result["changes"])
            stats["total_line_changes"] += result["line_changes"]
            stats["details"].append(result)
            _print_file_result(result, verbose=False)
        elif result["status"] == "error":
            stats["files_error"] += 1
            stats["errors"].append(result)
            print(f"  [ERROR] {result['path']}: {result['error']}")

    return stats


def _print_file_result(result: Dict, verbose: bool = False):
    """Print a file result to stdout."""
    path = result["path"]
    changes = result["changes"]
    line_changes = result["line_changes"]

    if result["status"] == "applied":
        icon = "\u2705"  # checkmark
        label = f"{line_changes} lines fixed"
    else:
        icon = "\U0001f50d"  # magnifier
        label = f"{line_changes} lines to fix"

    print(f"  {icon} {path} ({len(changes)} imports, {label})")

    if verbose:
        for c in changes:
            print(f"      L{c['line']:>4d}: {c['old']}  ->  {c['new']}")


# ══════════════════════════════════════════════════════════════
# Core: Validator
# ══════════════════════════════════════════════════════════════

def validate_all_files() -> Tuple[int, int, List[Dict]]:
    """
    Validate ALL .py files with ast.parse.
    Returns (valid_count, invalid_count, error_list).
    """
    valid = 0
    invalid = 0
    errors = []

    for fp in sorted(PROJECT_ROOT.rglob("*.py")):
        rel = fp.relative_to(PROJECT_ROOT)
        if should_skip(rel):
            continue

        try:
            source = fp.read_text(encoding="utf-8")
            ast.parse(source, filename=str(fp))
            valid += 1
        except SyntaxError as e:
            invalid += 1
            errors.append({
                "file": str(rel),
                "line": e.lineno,
                "message": e.msg,
                "text": e.text,
            })
        except Exception as e:
            invalid += 1
            errors.append({
                "file": str(rel),
                "line": None,
                "message": f"{type(e).__name__}: {e}",
                "text": None,
            })

    return valid, invalid, errors


# ══════════════════════════════════════════════════════════════
# Core: import_map.json Generator
# ══════════════════════════════════════════════════════════════

def generate_import_map(output_path: Optional[Path] = None) -> Dict:
    """
    Generate a comprehensive import_map.json with:
    - Full mapping table
    - Metadata (timestamp, version)
    - Reverse mapping (new -> old)
    - Per-layer grouping
    """
    if output_path is None:
        output_path = PROJECT_ROOT / "import_map.json"

    # Group by target layer
    layers = defaultdict(list)
    for old, new in IMPORT_MAP.items():
        # Determine target layer
        if new.startswith("core.domain"):
            layer = "core/domain"
        elif new.startswith("core.matchmaking"):
            layer = "core/matchmaking"
        elif new.startswith("core.ai.llm"):
            layer = "core/ai/llm"
        elif new.startswith("core.ai.tft"):
            layer = "core/ai/tft"
        elif new.startswith("core.ai"):
            layer = "core/ai"
        elif new.startswith("core.geological"):
            layer = "core/geological"
        elif new.startswith("core.financial"):
            layer = "core/financial"
        elif new.startswith("core.customer_service"):
            layer = "core/customer_service"
        elif new.startswith("core.account"):
            layer = "core/account"
        elif new.startswith("core.prediction"):
            layer = "core/prediction"
        elif new.startswith("infrastructure.external"):
            layer = "infrastructure/external"
        elif new.startswith("infrastructure"):
            layer = "infrastructure"
        else:
            layer = "other"

        layers[layer].append({"old": old, "new": new})

    # Reverse map
    reverse_map = {v: k for k, v in IMPORT_MAP.items()}

    # Collect all actual imports found in the project
    found_imports = _collect_all_project_imports()

    data = {
        "_meta": {
            "generated_at": datetime.now().isoformat(),
            "project": "Smart Land Management Copilot",
            "version": "4.0-clean-architecture",
            "total_mappings": len(IMPORT_MAP),
        },
        "mapping": IMPORT_MAP,
        "reverse_mapping": reverse_map,
        "by_layer": dict(layers),
        "found_imports": found_imports,
        "old_dirs_to_delete": OLD_DIRS,
        "old_files_to_delete": OLD_ROOT_FILES,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def _collect_all_project_imports() -> Dict[str, List[str]]:
    """
    Scan all .py files and collect every project-local import.
    Returns {module_name: [file_paths]}.
    """
    imports_map = defaultdict(list)

    scan_dirs = ["config", "core", "infrastructure", "api", "web", "alembic"]
    py_files = []
    for d in scan_dirs:
        dpath = PROJECT_ROOT / d
        if dpath.is_dir():
            py_files.extend(dpath.rglob("*.py"))
    for fp in PROJECT_ROOT.glob("*.py"):
        if fp.name not in {"fix_imports.py", "refactor_imports.py", "super_organizer.py"}:
            py_files.append(fp)

    for filepath in sorted(set(py_files)):
        rel = filepath.relative_to(PROJECT_ROOT)
        if should_skip(rel):
            continue

        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if is_project_module(alias.name):
                        imports_map[alias.name].append(str(rel))
            elif isinstance(node, ast.ImportFrom):
                if node.module and is_project_module(node.module):
                    imports_map[node.module].append(str(rel))

    return dict(imports_map)


# ══════════════════════════════════════════════════════════════
# Core: Old Directory Cleanup
# ══════════════════════════════════════════════════════════════

def clean_old_files(apply: bool = False) -> List[str]:
    """
    Delete old directories and root files after successful migration.
    Returns list of deleted (or would-delete) paths.
    """
    removed = []

    # Root files
    for filename in OLD_ROOT_FILES:
        fpath = PROJECT_ROOT / filename
        if fpath.exists():
            if apply:
                fpath.unlink()
                print(f"  [DELETED] {filename}")
            else:
                print(f"  [WOULD DELETE] {filename}")
            removed.append(str(fpath))

    # Old directories
    for dirname in OLD_DIRS:
        dpath = PROJECT_ROOT / dirname
        if not dpath.is_dir():
            continue

        py_count = len(list(dpath.rglob("*.py")))
        if py_count > 0:
            if apply:
                print(f"  [SKIP] {dirname}/ — still has {py_count} .py files")
            else:
                print(f"  [WOULD SKIP] {dirname}/ — still has {py_count} .py files")
        else:
            if apply:
                shutil.rmtree(dpath)
                print(f"  [DELETED] {dirname}/")
            else:
                print(f"  [WOULD DELETE] {dirname}/")
            removed.append(str(dpath))

    return removed


# ══════════════════════════════════════════════════════════════
# CLI: Main Entry Point
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="AST-Based Import Fixer — Clean Architecture Migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python fix_imports.py                  # dry-run (show only)
              python fix_imports.py --apply          # apply changes
              python fix_imports.py --apply --clean  # apply + delete old dirs
              python fix_imports.py --validate       # validate all files
              python fix_imports.py --gen-map        # generate import_map.json
              python fix_imports.py --apply -v       # apply with verbose output
        """),
    )
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes to files (default: dry-run)")
    parser.add_argument("--clean", action="store_true",
                        help="Delete old dirs/files after apply (requires --apply)")
    parser.add_argument("--validate", action="store_true",
                        help="Validate all .py files with ast.parse")
    parser.add_argument("--gen-map", action="store_true",
                        help="Generate import_map.json and exit")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show detailed per-import changes")

    args = parser.parse_args()

    # ── Generate map only ──
    if args.gen_map:
        print("\n  Generating import_map.json ...")
        data = generate_import_map()
        out_path = PROJECT_ROOT / "import_map.json"
        print(f"  Saved to: {out_path}")
        print(f"  Mappings: {data['_meta']['total_mappings']}")
        print(f"  Layers:   {len(data['by_layer'])}")
        print(f"  Found project imports: {len(data['found_imports'])} unique modules")
        return 0

    # ── Validate only ──
    if args.validate:
        print("\n  Validating all .py files with ast.parse ...")
        valid, invalid, errors = validate_all_files()
        print(f"\n  Valid:   {valid} files")
        print(f"  Invalid: {invalid} files")
        if errors:
            print("\n  Errors:")
            for err in errors:
                line_info = f":{err['line']}" if err['line'] else ""
                print(f"    [FAIL] {err['file']}{line_info} — {err['message']}")
        else:
            print("\n  All files pass ast.parse!")
        return 0 if invalid == 0 else 1

    # ── Main: Scan and Fix ──
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'=' * 72}")
    print(f"  fix_imports.py — AST-Based Import Fixer [{mode}]")
    print(f"{'=' * 72}")
    print(f"  Project:  {PROJECT_ROOT}")
    print(f"  Mappings: {len(IMPORT_MAP)}")
    print()

    stats = scan_project(apply=args.apply, verbose=args.verbose)

    # ── Summary ──
    print(f"\n{'=' * 72}")
    print(f"  SUMMARY")
    print(f"{'=' * 72}")
    print(f"  Files scanned:     {stats['files_scanned']}")
    print(f"  Files clean:       {stats['files_clean']}")
    print(f"  Files to fix:      {stats['files_pending']}")
    print(f"  Files fixed:       {stats['files_applied']}")
    print(f"  Files with errors: {stats['files_error']}")
    print(f"  Import changes:    {stats['total_import_changes']}")
    print(f"  Line changes:      {stats['total_line_changes']}")

    if stats["errors"]:
        print(f"\n  ERRORS ({len(stats['errors'])}):")
        for err in stats["errors"]:
            print(f"    {err['path']}: {err['error']}")

    # ── Delete old files ──
    if args.clean:
        if not args.apply:
            print("\n  [--clean requires --apply]")
            return 1
        print(f"\n{'=' * 72}")
        print(f"  CLEANUP — Removing old files/dirs")
        print(f"{'=' * 72}")
        clean_old_files(apply=True)

    # ── Post-apply validation ──
    if args.apply:
        print(f"\n{'=' * 72}")
        print(f"  POST-APPLY VALIDATION (ast.parse)")
        print(f"{'=' * 72}")
        valid, invalid, errors = validate_all_files()
        print(f"  Valid:   {valid} files")
        print(f"  Invalid: {invalid} files")
        if invalid > 0:
            print("\n  Failed files:")
            for err in errors:
                line_info = f":{err['line']}" if err['line'] else ""
                print(f"    [FAIL] {err['file']}{line_info} — {err['message']}")
            return 1
        else:
            print("  All files pass ast.parse!")

        # Auto-generate import_map.json after apply
        print(f"\n  Generating import_map.json ...")
        generate_import_map()
        print(f"  Done: import_map.json saved.")

    print(f"\n{'=' * 72}")
    if not args.apply:
        print("  Add --apply to write changes to files")
        print("  Add --apply --clean to also delete old directories")
        print("  Add --gen-map to generate import_map.json")
    else:
        print("  Import migration complete!")
    print(f"{'=' * 72}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())