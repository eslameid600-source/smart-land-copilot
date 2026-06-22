#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AST-based import rewriter with backup and Windows UTF-8 path handling
Parses root_reorg_log.txt to create module mapping and rewrites imports across repo
"""

import ast
import re
import shutil
import sys
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure UTF-8 handling on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


class ModuleMapper:
    """Parse reorg log and build module mapping."""
    
    def __init__(self, reorg_log_path: str):
        self.mapping: Dict[str, str] = {}  # old_module -> new_module
        self.parse_log(reorg_log_path)
    
    def parse_log(self, log_path: str):
        """Parse reorg log and extract old->new module mappings."""
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if 'moved:' in line and '->' in line:
                    # Extract "moved: account.py -> services\account.py"
                    match = re.search(r'moved:?\s+(.+?\.py)\s*->\s*(.+?\.py)', line.strip())
                    if match:
                        old_file = match.group(1)
                        new_path = match.group(2)
                        
                        # Extract module name (without .py)
                        old_module = old_file.replace('.py', '').replace('(1)', '').replace('(2)', '')
                        new_module_parts = new_path.replace('\\', '.').replace('/', '.').replace('.py', '')
                        
                        # Normalize module names
                        old_module = old_module.replace('_', '_').strip()
                        
                        # Skip __init__ files and conflict files
                        if '__init__' not in old_module and 'from_root' not in new_module_parts:
                            self.mapping[old_module] = new_module_parts
    
    def get_new_module(self, old_module: str) -> str:
        """Get new module path for old module name."""
        return self.mapping.get(old_module, None)


class ImportRewriter(ast.NodeTransformer):
    """AST transformer to rewrite imports."""
    
    def __init__(self, module_mapping: Dict[str, str]):
        self.module_mapping = module_mapping
        self.changes: List[str] = []
    
    def visit_Import(self, node: ast.Import) -> ast.Import:
        """Rewrite 'import X' statements."""
        for alias in node.names:
            module = alias.name.split('.')[0]
            if module in self.module_mapping:
                new_module = self.module_mapping[module]
                if alias.asname:
                    self.changes.append(f"import {module} as {alias.asname} -> import {new_module} as {alias.asname}")
                    alias.name = new_module
                else:
                    self.changes.append(f"import {module} -> import {new_module}")
                    alias.name = new_module
        return node
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        """Rewrite 'from X import Y' statements."""
        if node.module:
            base_module = node.module.split('.')[0]
            if base_module in self.module_mapping:
                new_module = self.module_mapping[base_module]
                # Preserve relative path components
                remaining = node.module[len(base_module):]
                if remaining:
                    new_module = new_module + remaining
                self.changes.append(f"from {node.module} import ... -> from {new_module} import ...")
                node.module = new_module
        return node


class PythonFileProcessor:
    """Process Python files and rewrite imports."""
    
    def __init__(self, root_dir: str, module_mapper: ModuleMapper, backup_dir: str):
        self.root_dir = Path(root_dir)
        self.module_mapper = module_mapper
        self.backup_dir = Path(backup_dir)
        self.modified_files: List[Tuple[str, int, List[str]]] = []
        self.errors: List[Tuple[str, str]] = []
        self.skipped_files = 0
    
    def create_backup(self, file_path: Path) -> bool:
        """Create backup of original file."""
        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            # Create relative path in backup
            rel_path = file_path.relative_to(self.root_dir)
            backup_path = self.backup_dir / rel_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(file_path), str(backup_path))
            return True
        except Exception as e:
            self.errors.append((str(file_path), f"Backup failed: {str(e)}"))
            return False
    
    def process_file(self, file_path: Path) -> bool:
        """Process single Python file."""
        try:
            # Read with UTF-8
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # Parse AST
            try:
                tree = ast.parse(original_content, filename=str(file_path))
            except SyntaxError as e:
                self.errors.append((str(file_path), f"Parse error: {e.msg} at line {e.lineno}"))
                return False
            
            # Apply transformations
            rewriter = ImportRewriter(self.module_mapper.mapping)
            new_tree = rewriter.visit(tree)
            
            if not rewriter.changes:
                self.skipped_files += 1
                return False
            
            # Generate new code
            ast.fix_missing_locations(new_tree)
            new_content = ast.unparse(new_tree)
            
            # Create backup before modification
            if not self.create_backup(file_path):
                return False
            
            # Write modified content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            # Record changes
            rel_path = file_path.relative_to(self.root_dir)
            self.modified_files.append((str(rel_path), len(rewriter.changes), rewriter.changes))
            return True
        
        except Exception as e:
            self.errors.append((str(file_path), f"Processing error: {str(e)}"))
            return False
    
    def process_directory(self) -> Tuple[int, int, int]:
        """Process all Python files in directory tree."""
        py_files = list(self.root_dir.rglob('*.py'))
        # Exclude backup dir
        py_files = [f for f in py_files if not str(f).startswith(str(self.backup_dir))]
        
        print(f"Processing {len(py_files)} Python files...")
        
        success = 0
        for file_path in py_files:
            if self.process_file(file_path):
                success += 1
        
        return success, len(self.errors), self.skipped_files


def generate_report(processor: PythonFileProcessor) -> str:
    """Generate concise report of modifications."""
    report = StringIO()
    
    report.write("\n" + "="*70 + "\n")
    report.write("IMPORT REWRITE REPORT\n")
    report.write("="*70 + "\n\n")
    
    # Summary statistics
    modified_count = len(processor.modified_files)
    error_count = len(processor.errors)
    skipped_count = processor.skipped_files
    
    report.write(f"✓ Files modified:     {modified_count}\n")
    report.write(f"✗ Errors encountered: {error_count}\n")
    report.write(f"- Files skipped:      {skipped_count}\n\n")
    
    # Modified files
    if processor.modified_files:
        report.write("MODIFIED FILES:\n")
        report.write("-" * 70 + "\n")
        for rel_path, change_count, changes in processor.modified_files[:20]:  # First 20
            report.write(f"  {rel_path} ({change_count} imports)\n")
            for change in changes[:2]:  # Show first 2 changes
                report.write(f"    • {change}\n")
        if len(processor.modified_files) > 20:
            report.write(f"  ... and {len(processor.modified_files) - 20} more files\n")
        report.write("\n")
    
    # Errors
    if processor.errors:
        report.write("ERRORS:\n")
        report.write("-" * 70 + "\n")
        for file_path, error in processor.errors[:10]:  # First 10
            report.write(f"  {file_path}\n    → {error}\n")
        if len(processor.errors) > 10:
            report.write(f"  ... and {len(processor.errors) - 10} more errors\n")
        report.write("\n")
    
    report.write("BACKUP LOCATION:\n")
    report.write("  Backups saved to: .backup_root_py_*\n\n")
    
    report.write("="*70 + "\n")
    
    return report.getvalue()


def main():
    """Main entry point."""
    root_dir = Path(__file__).parent.resolve()
    reorg_log = root_dir / 'root_reorg_log.txt'
    
    if not reorg_log.exists():
        print(f"Error: {reorg_log} not found")
        return 1
    
    # Create timestamped backup directory
    timestamp = datetime.now().strftime('%Y%m%dT%H%M%S')
    backup_dir = root_dir / f'.backup_root_py_{timestamp}'
    
    print(f"Loading module mapping from {reorg_log}...")
    mapper = ModuleMapper(str(reorg_log))
    print(f"Loaded {len(mapper.mapping)} module mappings\n")
    
    print("Starting import rewrite process...")
    print(f"Backup directory: {backup_dir}\n")
    
    processor = PythonFileProcessor(str(root_dir), mapper, str(backup_dir))
    success, errors, skipped = processor.process_directory()
    
    # Generate and print report
    report = generate_report(processor)
    print(report)
    
    # Save report to file
    report_file = root_dir / f'import_rewrite_report_{timestamp}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"Report saved to: {report_file}\n")
    
    return 0 if errors == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
