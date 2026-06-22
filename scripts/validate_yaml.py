"""Validate all YAML files in the project."""
import glob
import sys

import yaml

errors = []
for f in glob.glob('**/*.yml', recursive=True) + glob.glob('**/*.yaml', recursive=True):
    if '.github/workflows/' in f:
        continue
    try:
        with open(f) as fh:
            yaml.safe_load(fh)
    except Exception as e:
        errors.append(f'{f}: {e}')

if errors:
    for e in errors:
        print(f'::error::{e}')
    sys.exit(1)

print('All YAML files valid.')