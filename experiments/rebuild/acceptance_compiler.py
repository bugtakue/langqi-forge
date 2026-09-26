"""Generate and freeze internal behavior tests BEFORE any implementation.

Only explicit public requirements enter the model request. No app or holdout
source is readable through this API. The local budget gateway reserves calls.
These tests are internal evidence, never official/hidden test claims.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request

from grade import manifest
from requirement_catalog import compile_tree

HERE = Path(__file__).resolve().parent
SLUG = re.compile(r'^[a-z][a-z0-9-]{0,63}$')
UI_ASSERT = re.compile(r'await\s+expect\([^;]+?\)\s*\.(?:not\.)?to(?:HaveText|ContainText|BeVisible|BeHidden|HaveValue|HaveAttribute|HaveURL|HaveCount|BeChecked|BeEnabled|BeDisabled)\s*\(', re.S)


def source_for_case(case, catalog):
    nodes = {n['id']: n for n in catalog['nodes']}
    ids = case.get('requirement_ids')
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids) or any(i not in nodes for i in ids):
        raise ValueError('case needs known, unique atomic requirement IDs')
    allowed = {key for nid in ids for key in [*nodes[nid]['ancestors'], nid]}
    quote = case.get('source_quote')
    if not isinstance(quote, str) or len(quote) < 20 or not any(quote in catalog['contracts'][key] for key in allowed):
        raise ValueError('case must cite a verbatim public contract quote')


def validate_plan(plan, catalog):
    if not isinstance(plan, dict) or set(plan) != {'helpers', 'cases'}:
        raise ValueError('exactly helpers and cases required')
    if not isinstance(plan['helpers'], str) or len(plan['helpers']) > 20000:
        raise ValueError('helpers must be bounded JavaScript text')
    cases = plan['cases']
    if not isinstance(cases, list) or not 1 <= len(cases) <= 3 * len(catalog['nodes']):
        raise ValueError('case count outside declared bounds')
    seen, positives = set(), set()
    fields = {'id', 'kind', 'requirement_ids', 'source_quote', 'body'}
    for case in cases:
        if not isinstance(case, dict) or set(case) != fields or not SLUG.fullmatch(str(case.get('id', ''))):
            raise ValueError('invalid case shape or ID')
        if case['id'] in seen or case['kind'] not in ('positive', 'negative', 'persistence', 'permission'):
            raise ValueError('duplicate case ID or invalid case kind')
        seen.add(case['id'])
        source_for_case(case, catalog)
        body = case['body']
        if not isinstance(body, str) or len(body) > 20000 or len(UI_ASSERT.findall(body)) < 2:
            raise ValueError('case requires at least two awaited UI assertions')
        if case['kind'] == 'persistence' and 'await restart(request)' not in body:
            raise ValueError('persistence case must include a real restart and recheck: ' + case['id'])
        # A successful create/change followed by restart is both a positive
        # journey and persistence evidence; do not demand duplicate tests.
        if case['kind'] in ('positive', 'persistence'):
            positives.update(case['requirement_ids'])
    missing = {n['id'] for n in catalog['nodes']} - positives
    if missing:
        raise ValueError('missing successful positive/persistence journeys for: ' + ', '.join(sorted(missing)))
    return plan


def render(plan):
    parts = ["// GENERATED FROM PUBLIC REQUIREMENTS; INTERNAL, NOT OFFICIAL TESTS.\n",
             "import {test, expect} from '@playwright/test';\nimport {restart} from './restart';\n",
             plan['helpers'], '\n']
    for case in plan['cases']:
        title = 'contract:' + case['id'] + ':' + ','.join(case['requirement_ids'])
        parts.append('test(' + json.dumps(title) + ', async ({page,browser,request}) => {\n' + case['body'] + '\n});\n')
    return ''.join(parts)


def syntax_check(source):
    proc = subprocess.run(['node', str(HERE / 'acceptance_syntax.cjs')],
                          input=json.dumps({'source': source}), capture_output=True, text=True, timeout=20)
    if proc.returncode:
        raise ValueError('acceptance syntax policy: ' + proc.stdout.strip()[:1200])


def collect_suite(suite, plan):
    """Verify actual Playwright collection, not just a model-declared count."""
    with tempfile.TemporaryDirectory(prefix='acceptance-collect-') as tmp:
        target = Path(tmp)
        shutil.copytree(suite, target / 'suite')
        (target / 'suite/node_modules').symlink_to('/opt/arcbench/node_modules')
        config = target / 'suite/playwright.config.cjs'
        config.write_text("module.exports={testDir:'.',testMatch:'**/*.spec.ts',retries:0,workers:1}")
        proc = subprocess.run(['/opt/arcbench/node_modules/.bin/playwright', 'test', '--list',
                               '--reporter=json', '-c', str(config)], capture_output=True, text=True, timeout=30)
        if proc.returncode:
            raise ValueError('test collection failed: ' + (proc.stdout + proc.stderr)[-1500:])
        report = json.loads(proc.stdout)
        titles = []
        def visit(node):
            for spec in node.get('specs', []):
                if not spec.get('tests') or any(t.get('expectedStatus') != 'passed' for t in spec['tests']):
                    raise ValueError('disabled or missing test in collection')
                titles.append(spec['title'])
            for child in node.get('suites', []):
                visit(child)
        visit(report)
        expected = ['contract:' + c['id'] + ':' + ','.join(c['requirement_ids']) for c in plan['cases']]
        if report.get('errors') or titles != expected:
            raise ValueError('collected tests differ from declared frozen cases')
        return {'expected': len(titles), 'titles': titles, 'errors': []}


def select_catalog(catalog, included):
    """Experiment selection only; keep every declared transitive prerequisite."""
    if not included:
        return catalog
    nodes = {n['id']: n for n in catalog['nodes']}
    selected, pending = set(), list(included)
    while pending:
        nid = pending.pop()
        if nid not in nodes:
            raise ValueError('unknown selected atomic requirement: ' + nid)
        if nid not in selected:
            selected.add(nid)
            pending.extend(nodes[nid]['dependencies'])
    keys = {key for nid in selected for key in [nid, *nodes[nid]['ancestors']]}
    return {**catalog, 'requested_ids': included, 'full_atomic_count': len(nodes),
            'nodes': [n for n in catalog['nodes'] if n['id'] in selected],
            'contracts': {k: v for k, v in catalog['contracts'].items() if k in keys}}


def completion(messages, destination):
    # A candidate never receives the organizer credential, only a scoped token.
    base = os.environ.get('OPENAI_BASE_URL', '')
    if base != 'http://factory26-gateway:8021/v1' or not os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('this experimental compiler requires the cost-reserving organizer gateway')
    payload = {'model': 'glm-5.3-flash', 'messages': messages, 'max_tokens': 16000,
               'temperature': 0, 'stream': False}
    (destination / 'request.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    req = urllib.request.Request(base + '/chat/completions', data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']})
    # No transport retry. The gateway owns unknown-cost locking and raw evidence.
    with urllib.request.urlopen(req, timeout=260) as response:
        result = json.load(response)
    stored = json.dumps(result, ensure_ascii=False, indent=2).replace(os.environ['OPENAI_API_KEY'], '[SCOPED_TOKEN_REDACTED]')
    (destination / 'response.json').write_text(stored)
    choice = result['choices'][0]
    if choice.get('finish_reason') != 'stop':
        raise ValueError('incomplete acceptance response; cannot freeze truncated tests')
    return choice['message']['content']


def freeze(plan, catalog, output):
    validate_plan(plan, catalog)
    source = render(plan)
    syntax_check(source)
    # Validate collection on a scratch copy before writing a frozen suite.
    with tempfile.TemporaryDirectory(prefix='acceptance-pre-freeze-') as tmp:
        pending = Path(tmp)
        (pending / 'contract.spec.ts').write_text(source)
        shutil.copy2(HERE / 'runtime_restart.ts', pending / 'restart.ts')
        collection = collect_suite(pending, plan)
    suite = output / 'suite'
    suite.mkdir(exist_ok=False)
    (suite / 'contract.spec.ts').write_text(source)
    shutil.copy2(HERE / 'runtime_restart.ts', suite / 'restart.ts')
    spec = {'schema': 'generated-acceptance-v1', 'evidence_kind': 'internal_not_official_tests',
            'requirements_sha256': catalog['source_sha256'], 'tests_sha256': manifest(suite),
            'case_ids': [c['id'] for c in plan['cases']], 'expected': len(plan['cases']),
            'collection': collection, 'sensitivity_verified': False,
            'cases': [{k: v for k, v in c.items() if k != 'body'} for c in plan['cases']],
            'frozen_at': time.time()}
    (output / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    (output / 'frozen.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2))
    return spec


def compile_acceptance(requirements, output, included=None):
    import yaml
    raw = requirements.read_bytes()
    catalog = select_catalog(compile_tree(yaml.safe_load(raw)), included)
    catalog['source_sha256'] = hashlib.sha256(raw).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
    prompt = (HERE / 'prompts/acceptance.md').read_text()
    messages = [{'role': 'system', 'content': prompt},
                {'role': 'user', 'content': json.dumps(catalog, ensure_ascii=False)}]
    # One schema/syntax correction is allowed before any application exists.
    # Never change frozen assertions based on application performance.
    for attempt in (1, 2):
        dest = output / f'compile-{attempt}'
        dest.mkdir()
        body = completion(messages, dest)
        try:
            plan = validate_plan(json.loads(body), catalog)
            syntax_check(render(plan))
            return freeze(plan, catalog, output)
        except (ValueError, TypeError) as exc:
            (dest / 'rejection.txt').write_text(str(exc))
            if attempt == 2:
                raise
            messages += [{'role': 'assistant', 'content': body},
                         {'role': 'user', 'content': 'Fix only this compiler contract error; no app exists: ' + str(exc)}]
            continue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('requirements', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--include', action='append', help='explicit experiment subset; transitive dependency closure is retained')
    args = parser.parse_args()
    result = compile_acceptance(args.requirements, args.output, args.include)
    print(json.dumps({'frozen': True, 'expected': result['expected'], 'requirements_sha256': result['requirements_sha256']}), flush=True)


if __name__ == '__main__':
    main()
