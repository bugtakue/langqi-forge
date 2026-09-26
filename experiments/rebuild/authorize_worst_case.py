"""Apply one explicit user decision locally; never a model-call retry switch."""
import argparse
import json
from pathlib import Path

from budget_gateway import Ledger


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--authorization', type=Path, required=True)
    args = parser.parse_args()
    if not args.ledger.is_file():
        parser.error('existing ledger required; do not create a replacement budget')
    ledger = Ledger(args.ledger)
    added = ledger.authorize_worst_case(json.loads(args.authorization.read_text()))
    state = ledger.status()
    print(json.dumps({'authorization_added': added, 'total_cny': state['total_cny'],
                      'unresolved_cost_lock': state['unresolved_cost_lock'],
                      'actual_cost_known': False, 'reservation_released': False}))


if __name__ == '__main__':
    main()
