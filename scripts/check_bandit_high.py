"""Check Bandit JSON report for HIGH severity issues."""
import json
import sys

with open('bandit_report.json') as f:
    data = json.load(f)

high = [r for r in data.get('results', []) if r.get('issue_severity') == 'HIGH']
if high:
    print(f"::error::Bandit found {len(high)} HIGH severity issues!")
    for h in high:
        print(f"  - {h.get('issue_test_id')}: {h.get('issue_text')} at {h.get('filename')}:{h.get('line_number')}")
    sys.exit(1)
else:
    print("No HIGH severity issues found.")