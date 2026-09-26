"""Run remaining registered trials serially, never choose a best-of sample."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from run_trial import CACHE, ROOT, control
from summarize import REPLACEMENTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['smoke', 'ticket'], required=True)
    args = parser.parse_args()
    tasks = ['smoke--counter', 'smoke--dice'] if args.stage == 'smoke' else ['ticket-booking--ticket-booking']
    for task in tasks:
        for repeat in (1, 2):
            for candidate in ('A', 'B'):
                name = f'{candidate.lower()}-{task}-{repeat}'
                out = CACHE / 'runs' / name
                if name in REPLACEMENTS:
                    out = CACHE / 'runs' / REPLACEMENTS[name]
                if out.exists():
                    manifest = json.loads((out/'manifest.json').read_text())
                    if 'finished' not in manifest:
                        raise RuntimeError('nonterminal prior operation: ' + str(out))
                    print('Retain existing result:', out.name, flush=True)
                    continue
                state = control('/status', {'read': True})
                if state.get('unresolved_cost_lock', True):
                    raise RuntimeError('unsettled cost: stop, reconcile with meter')
                command = [sys.executable, str(ROOT/'experiments/rebuild/run_trial.py'), candidate, task, str(repeat)]
                if name in REPLACEMENTS:
                    command.append('--environment-retry')
                proc = subprocess.run(command)
                print(name, 'exit', proc.returncode, flush=True)
                if not (out/'manifest.json').is_file() or 'finished' not in json.loads((out/'manifest.json').read_text()):
                    raise RuntimeError('trial controller did not finish; no automatic retry')
    print('Matrix stage complete. Review evidence before next stage.', flush=True)


if __name__ == '__main__': main()
