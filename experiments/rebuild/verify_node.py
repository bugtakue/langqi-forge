"""Restricted verifier overlay for the pinned Octos adapter."""
from pathlib import Path
import sys

from octos_adapter import upstream_module


def main():
    original = upstream_module('octos_upstream_verify', 'verify_node.py')
    original.playwright_root = lambda _env: (Path('/opt/arcbench'), {})
    original.install_browser = lambda *_args: False
    check = original.check

    def guarded_check(tests, port, specs):
        if tests != Path('/public-tests') or not specs:
            print('UNVERIFIED: no explicit public behavior tests; ARC_NO_MORE_REPAIRS')
            return 2
        for rel in specs:
            path = (tests / rel).resolve()
            if tests not in path.parents or not path.is_file():
                print('Rejected test outside frozen public suite; ARC_NO_MORE_REPAIRS')
                return 2
        return check(tests, port, specs)

    original.check = guarded_check
    return original.main(sys.argv[1:])


if __name__ == '__main__':
    raise SystemExit(main())
