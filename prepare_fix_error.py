import shutil
from pathlib import Path

# Create folder
folder = Path('fix_error')
folder.mkdir(exist_ok=True)

# Copy ALL project Python files to ensure nothing is missed
exclude_dirs = {'.git', 'fix_error', 'azure-devops-mcp', 'cloned_repo', 'mcp-servers'}
copied = 0
for p in Path('.').rglob('*.py'):
    # Skip excluded directories
    if any(part in exclude_dirs for part in p.parts):
        continue
    # Skip hidden directories
    if any(part.startswith('.') and part != '.git' for part in p.parts):
        continue
    target = folder / p
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, target)
    copied += 1

# Copy ruff_errors.txt
shutil.copy2('ruff_errors.txt', folder / 'ruff_errors.txt')

print(f'Copied {copied} Python files to fix_error/')
print(f'fix_error/ruff_errors.txt: {(folder / "ruff_errors.txt").exists()}')