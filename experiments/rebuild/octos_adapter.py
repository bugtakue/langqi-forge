"""Auditable safety overlay, not a fork of the Octos execution kernel.

Apache-2.0 Octos source is separately mounted read-only at /upstream/arc.
No guessing test locations, no inherited host secrets, no 200-only PASS.
"""
import importlib.util
import os
from pathlib import Path
import sys


def upstream_module(name, filename):
    path = Path('/upstream/arc') / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def explicit_tests(_tree):
    path = Path('/public-tests')
    if not path.is_dir() or not list(path.glob('*.spec.ts')):
        raise RuntimeError('explicit frozen public test mount required')
    return path


def main():
    sys.path.insert(0, '/upstream/arc')
    original = upstream_module('octos_upstream_main', 'main.py')
    original.locate_tests = explicit_tests
    # Redirect only verifier entry. Prompt/policy/template symlinks in /adapter
    # refer to the pinned upstream files, never mutable candidate files.
    original.BUNDLE_DIR = Path('/adapter')
    return original.main()


if __name__ == '__main__':
    raise SystemExit(main())
