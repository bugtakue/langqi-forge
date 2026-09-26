"""One bounded Octos arc.17 coding pass; never an acceptance authority.

Pinned upstream kernel/stdIO protocol is retained. The outer controller alone
grades a disposable app copy and owns working/accepted checkpoints.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import tempfile
import time

from grade import manifest

PINNED_KERNEL = '86c8bd509e2c566ae9b37c54f60911c3e4f1d5a1429aff2419e03b0b843b4578'
PIPELINE = 'langqi_coding_pass'
HERE = Path(__file__).resolve().parent


def upstream():
    sys.path.insert(0, '/upstream/arc')
    spec = importlib.util.spec_from_file_location('pinned_octos_main', '/upstream/arc/main.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed(source, destination):
    for part in ('frontend', 'backend'):
        if not (source / part).is_dir() or any(p.is_symlink() for p in (source / part).rglob('*')):
            raise ValueError('working source must have real application directories')
        shutil.copytree(source / part, destination / part,
                        ignore=shutil.ignore_patterns('node_modules', 'dist', '.git'))


def graph(module, prompt, seconds):
    # No verification/shell command is supplied by the model. The only shell
    # node is this fixed controller-owned initial source copy.
    body = module.dot_quote(module.untemplate(prompt))
    command = module.dot_quote(f'{sys.executable} {HERE}/kernel_pass.py --seed /source')
    return '\n'.join([
        f'digraph {PIPELINE} {{',
        f'graph [default_timeout_secs="{seconds}"]',
        'start [handler="noop"]',
        f'seed [handler="shell_check", timeout_secs="30", prompt="{command}"]',
        f'implement [handler="codergen", label="bounded implementation", reasoning_effort="none", '
        f'max_output_tokens="16000", tools="read_file,write_file,edit_file,glob,grep,list_dir", '
        f'max_iterations="20", max_retries="0", continue_on_error="true", '
        f'timeout_secs="{max(30, seconds - 45)}", prompt="{body}"]',
        'done [handler="noop"]',
        'start -> seed', 'seed -> implement',
        'implement -> done [condition="outcome.status == \\"pass\\" || outcome.status == \\"fail\\" || outcome.status == \\"error\\""]',
        '}'])


def build_prompt(catalog, tests, feedback):
    data = {'public_runtime_catalog': catalog, 'frozen_internal_acceptance': tests,
            'previous_independent_verifier_feedback': feedback}
    return (HERE / 'prompts/coding-pass.md').read_text() + '\n\nRUNTIME DATA:\n' + json.dumps(data, ensure_ascii=False)


def frozen_test_text(acceptance, frozen):
    """Read only explicitly frozen suite members, never discover other tests."""
    suite = acceptance / 'suite'
    if manifest(suite) != frozen['tests_sha256']:
        raise RuntimeError('frozen acceptance changed')
    names = sorted(name for name in frozen['tests_sha256'] if name.endswith('.spec.ts'))
    if not names:
        raise RuntimeError('no frozen behavior spec')
    return '\n\n'.join('// ' + name + '\n' + (suite / name).read_text() for name in names)


def dispatch_pipeline(session, end, launched, tool_seen, record):
    prompts = [
        f'Call the run_pipeline tool now with pipeline="{PIPELINE}" and '
        'input="Build the application described by the supplied runtime requirements". '
        'Call it exactly once and do not write any files yourself. After the tool call, finish.',
        f'No tool call was observed in your completed response. Do not answer ok without acting. '
        f'The run_pipeline schema explicitly lists {PIPELINE} as its permitted enum; its generic '
        'deep_research prose is not relevant here. Invoke run_pipeline now with '
        f'{{"pipeline":"{PIPELINE}","input":"Implement runtime contract"}}. Do not use spawn.'
    ]
    for number, prompt in enumerate(prompts, 1):
        # Match the bounded upstream request timeout; a 90s dispatch timer used
        # to kill the caller while its 240s request could still be in flight.
        ok, reply = session.run_turn(prompt, timeout=min(240, max(1, end-time.monotonic())))
        record('controller/dispatch_finished', {'attempt': number, 'ok': ok, 'reply': reply})
        if not ok:
            raise RuntimeError('dispatch failed; no transport/error retry')
        if launched() or tool_seen():
            # A tool call can be asynchronous or have failed validation.
            # Never repeat it merely because its run directory is not ready.
            return
    raise RuntimeError('two completed dispatch replies without a tool call; nothing launched')


def run(output, seconds):
    binary = Path('/runtime/octos')
    if hashlib.sha256(binary.read_bytes()).hexdigest() != PINNED_KERNEL:
        raise RuntimeError('kernel differs from selected arc.17 baseline')
    if os.environ.get('OPENAI_BASE_URL') != 'http://factory26-gateway:8021/v1':
        raise RuntimeError('experiment requires organizer cost gateway')
    output.mkdir(exist_ok=False)
    frozen = json.loads(Path('/acceptance/frozen.json').read_text())
    catalog = json.loads(Path('/acceptance/catalog.json').read_text())
    tests = frozen_test_text(Path('/acceptance'), frozen)
    feedback = Path('/feedback.txt').read_text()
    prompt = build_prompt(catalog, tests, feedback)
    (output / 'prompt.txt').write_text(prompt)
    module = upstream()
    pol = module.policy()
    pol.update(name=PIPELINE, run_timeout=seconds, final_reserve_seconds=0,
               llm_timeout=240, reasoning='none')
    secret = os.environ.get('OPENAI_API_KEY', '')
    started, end = time.time(), time.monotonic() + seconds
    with tempfile.TemporaryDirectory(prefix='lq-pass-') as tmp:
        data = Path(tmp)
        (data / 'pipelines').mkdir()
        dot = graph(module, prompt, seconds)
        (data / 'pipelines' / (PIPELINE + '.dot')).write_text(dot)
        (output / 'pipeline.dot').write_text(dot)
        env = module.kernel_env(pol, data / 'config')
        env['OCTOS_LLM_MAX_RETRIES'] = '0'
        meta = json.loads(env['_ARC'])
        events = output / 'events.jsonl'
        tool_activity = []
        def record(method, params):
            kind = str((params or {}).get('metadata', {}).get('kind', ''))
            if str(method).startswith('tool/') or (method == 'progress/updated' and 'tool' in kind):
                tool_activity.append(method)
            text = json.dumps({'time': time.time(), 'method': method, 'params': params}, ensure_ascii=False)
            if secret:
                text = text.replace(secret, '[SCOPED_TOKEN_REDACTED]')
            with events.open('a') as stream:
                stream.write(text + '\n')
        dispatch = data / 'dispatch'
        dispatch.mkdir()
        session = module.OctosStdioSession(str(binary), dispatch, env, data, on_event=record)
        summary = None
        try:
            session.bootstrap_profile(meta['provider'], meta['model'], meta['base_url'], meta['key_env'], timeout=30)
            session.open(timeout=30)
            dispatch_pipeline(session, end,
                lambda: bool(list(data.glob(f'profiles/*/data/pipeline-runs/{PIPELINE}-*'))),
                lambda: bool(tool_activity), record)
            while time.monotonic() < end and session.proc.poll() is None:
                summary = module.pipeline_summary(data, pol)
                if summary is not None:
                    break
                try:
                    event = session._notifications.get(timeout=min(3, max(.01, end-time.monotonic())))
                    record(event.get('method'), event.get('params'))
                except queue.Empty:
                    pass
        finally:
            session.close()
            record('controller/kernel_stopped', {'exit': session.proc.poll()})
        runs = list(data.glob(f'profiles/*/data/pipeline-runs/{PIPELINE}-*'))
        if len(runs) != 1:
            raise RuntimeError(f'expected exactly one own pipeline workspace; found {len(runs)}')
        # These are WORKING bytes only. No fallback may promote them as accepted.
        working = output / 'working'
        working.mkdir()
        seed(runs[0], working)
        result = {'kind': 'unverified_working_checkpoint', 'accepted': False,
                  'kernel_sha256': PINNED_KERNEL, 'started': started, 'finished': time.time(),
                  'pipeline_summary': summary, 'source_manifest': manifest(working)}
        (output / 'pass.json').write_text(json.dumps(result, indent=2))
        print(json.dumps({'working_exported': True, 'accepted': False,
                          'pipeline_complete': summary is not None}), flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seconds', type=int, default=360)
    args = parser.parse_args()
    if args.seed:
        seed(args.seed, Path.cwd())
        print('Working source copied; not verified', flush=True)
        return 0
    if not args.output or not 60 <= args.seconds <= 360:
        raise ValueError('bounded output/seconds required')
    return run(args.output, args.seconds)


if __name__ == '__main__':
    raise SystemExit(main())
