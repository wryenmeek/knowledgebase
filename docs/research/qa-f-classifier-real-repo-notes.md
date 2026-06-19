# QA-F classifier real-repo prep notes

- Gate-start commit SHA: `c0b96cd5fd5ffb11eab6ea4d40ba0663bcf164c9`
- Findings artifact: `/home/runner/work/knowledgebase/knowledgebase/docs/research/qa-f-classifier-real-repo-findings.json`
- Real-repo scope: `.github/copilot-instructions.md`, `AGENTS.md`

## Invocation used

```bash
cd /home/runner/work/knowledgebase/knowledgebase
python3 - <<'PY'
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

repo = Path('/home/runner/work/knowledgebase/knowledgebase').resolve()
logic = repo / '.github' / 'skills' / 'audit-knowledgebase-workspace' / 'logic'
out_path = repo / 'docs' / 'research' / 'qa-f-classifier-real-repo-findings.json'
gate_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()

def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module

skill_cache = load('skill_corpus_cache', logic / 'skill_corpus_cache.py')
stale = load('stale_generator', logic / 'stale_generator.py')
redundancy = load('redundancy_generator', logic / 'redundancy_generator.py')
friction = load('friction_queries', logic / 'friction_queries.py')

sources = ('.github/copilot-instructions.md', 'AGENTS.md')

skill_corpus = skill_cache.get_skill_corpus(
    repo / '.github' / 'skills',
    repo / '.github' / 'skills' / 'audit-knowledgebase-workspace' / '.cache',
)

def command_runner(command, cwd, timeout):
    if len(command) >= 3 and command[0] == 'gh' and command[1] == 'issue' and command[2] == 'view':
        return subprocess.CompletedProcess(command, 0, stdout='OPEN\n', stderr='')
    return subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )

assembled_findings = []
source_runs = []
for source_file in sources:
    source_path = repo / source_file
    source_text = source_path.read_text(encoding='utf-8')
    source_sha256 = hashlib.sha256(source_text.encode('utf-8')).hexdigest()

    stale_findings = []
    stale_error = None
    try:
        stale_findings = list(
            stale.generate_stale_findings(
                source_text,
                source_file=source_file,
                source_section='qa-f real-repo pass',
                repo_root=repo,
                cache_strategy=skill_cache.CACHE_STRATEGY,
                command_runner=command_runner,
            )
        )
    except Exception as exc:  # noqa: BLE001 - artifact captures deterministic failure shape
        stale_error = f'{type(exc).__name__}: {exc}'

    redundancy_result = redundancy.generate_redundancy_findings(
        repo_root=repo,
        source_file=source_file,
        source_section='qa-f real-repo pass',
        source_text=source_text,
        skill_corpus=skill_corpus,
        llm_caller=lambda _prompt: '{"claims": []}',
    )

    assembled_findings.extend(stale_findings)
    assembled_findings.extend(redundancy_result['findings'])

    source_runs.append(
        {
            'source_file': source_file,
            'source_sha256': source_sha256,
            'stale_generator': {
                'finding_count': len(stale_findings),
                'error': stale_error,
            },
            'redundancy_generator': {
                'finding_count': redundancy_result['finding_count'],
                'soft_skipped': bool(redundancy_result['soft_skipped']),
                'llm_mode': 'deterministic-fixture-no-claims',
            },
        }
    )

friction_templates = friction.all_friction_queries(repo='wryenmeek/knowledgebase', days=7)
missing_cache_strategy_count = sum(
    1 for finding in assembled_findings if not isinstance(finding.get('cache_strategy'), str) or not finding['cache_strategy']
)

payload = {
    'gate_start_commit_sha': gate_sha,
    'repository': 'wryenmeek/knowledgebase',
    'classifier_scope': list(sources),
    'invocation': {
        'assembled_run': 'python3 (importlib) stale_generator + redundancy_generator + friction_queries templates',
        'gh_issue_state_stub': 'OPEN (offline deterministic command_runner for stale_generator gh issue probes)',
    },
    'source_runs': source_runs,
    'friction_query_templates': {
        'template_count': len(friction_templates),
        'template_keys': sorted(friction_templates.keys()),
        'all_templates_include_time_filter': all('now() - INTERVAL' in t['primary'] and 'now() - INTERVAL' in t['broader'] for t in friction_templates.values()),
    },
    'assembled_findings': assembled_findings,
    'assembled_finding_count': len(assembled_findings),
    'cache_strategy_verification': {
        'missing_cache_strategy_count': missing_cache_strategy_count,
        'all_emitted_findings_include_cache_strategy': missing_cache_strategy_count == 0,
    },
}

out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(f'wrote {out_path}')
PY
```

## Phase 7 cache_strategy verification

- `assembled_finding_count`: `0`
- `missing_cache_strategy_count`: `0`
- Result: every emitted finding (none emitted) satisfies cache-strategy field requirements.

## Cache adversarial fixtures (under tests/)

- Fixture A (touch SKILL.md, no content change, cache miss then same content):
  - `tests/kb/test_audit_workspace_cache.py::SkillCorpusCacheTests::test_touch_without_content_change_is_accepted_cache_miss_edge_case`
- Fixture B (modify body + preserve first paragraph + restore mtime via `os.utime`, stale cache hit accepted):
  - `tests/kb/test_audit_workspace_cache.py::SkillCorpusCacheTests::test_force_write_with_mtime_reset_hits_stale_cache_as_q11_false_negative`

## Mandatory-citation adversarial fixture

- Fixture (near-match non-existent skill path):
  - `tests/kb/test_audit_workspace_redundancy_generator.py::AuditWorkspaceRedundancyGeneratorTests::test_nonexistent_near_match_skill_citation_is_dropped_silently`
- Drop evidence:
  - Claims submitted: `1`
  - Findings emitted: `0`
  - Dropped finding count: `1`
  - Drop reason class: citation artifact path not present in the allowed lower-locality corpus map.

## Friction-query SQL audit notes

Reviewed `/home/runner/work/knowledgebase/knowledgebase/.github/skills/audit-knowledgebase-workspace/logic/friction_queries.py` templates.

- Injection hardening:
  - `repo` input is validated by `_REPO_PATTERN` and then quoted by `_repo_literal()`.
  - `days` is type-checked and range-bounded (`1..365`) before interval interpolation.
  - No caller-controlled freeform SQL fragments are accepted.
- Mandatory time-filter coverage:
  - Every template’s `primary` and `broader` SQL includes `> now() - INTERVAL '<N> days'` predicates.
  - Additional bounded windows exist for retry-loop matching (`RETRY_WINDOW_MINUTES`).
