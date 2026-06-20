import json

with open('.fleet/2026_06_20/issue_tasks.json', 'r') as f:
    data = json.load(f)

# Update the task prompt to mention test_contracts.py
for task in data['tasks']:
    if task['id'] == 'task-fix-check-approval-flag':
        task['prompt'] += "\n\nAdditionally, in `tests/kb/test_contracts.py`, update `test_approval_flag_ratchet_baseline_is_declared_and_exported` to expect `MAX_APPROVAL_FLAG_SCRIPTS` to be 7 (or whatever the new count is) instead of 8 to reflect the tightened ratchet."

# Add to file ownership
data['file_ownership']['tests/kb/test_contracts.py'] = 'task-fix-check-approval-flag'

with open('.fleet/2026_06_20/issue_tasks.json', 'w') as f:
    json.dump(data, f, indent=2)
