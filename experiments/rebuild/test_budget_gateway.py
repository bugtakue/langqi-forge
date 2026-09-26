import json
from pathlib import Path
import tempfile
import unittest

from budget_gateway import BudgetDenied, Ledger, micro_cost, request_bound


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Ledger(Path(self.tmp.name) / 'ledger.sqlite')
        self.payload = {'model': 'glm-5.3-flash', 'messages': [{'role': 'user', 'content': 'build'}], 'max_tokens': 32768}

    def trial(self, name='a1', cap=1.5):
        return self.ledger.create_trial(name, 'baseline', cap, 900)

    def test_reserve_before_usage_settlement(self):
        rid, _ = self.ledger.reserve(self.trial(), self.payload)
        self.assertGreater(self.ledger.status()['total_cny'], 0.1)
        self.ledger.settle(rid, {'usage': {'prompt_tokens': 100, 'completion_tokens': 200}, 'choices': [{}]})
        self.assertEqual(self.ledger.status()['total_cny'], micro_cost(100, 200)/1e6)

    def test_unresolved_call_blocks_retry_and_next_trial(self):
        token = self.trial()
        self.ledger.reserve(token, self.payload)
        with self.assertRaises(BudgetDenied): self.ledger.reserve(token, self.payload)
        self.ledger.close_trial('a1')
        with self.assertRaises(BudgetDenied): self.trial('b1')

    def test_missing_usage_does_not_release_reservation(self):
        rid, _ = self.ledger.reserve(self.trial(), self.payload)
        before = self.ledger.status()['total_cny']
        with self.assertRaises(BudgetDenied): self.ledger.settle(rid, {'choices': [{}]})
        self.assertEqual(before, self.ledger.status()['total_cny'])

    def test_caps_are_checked_before_request(self):
        with self.assertRaises(BudgetDenied): self.ledger.reserve(self.trial(cap=.01), self.payload)
        self.assertEqual(self.ledger.status()['calls'], [])

    def test_model_streaming_multimodal_and_unbounded_output_denied(self):
        for change in ({'model': 'unpriced'}, {'stream': True}, {'max_tokens': 99999},
                       {'messages': [{'role': 'user', 'content': [{'type': 'image_url'}]}]}, {'n': 2}):
            with self.subTest(change=change), self.assertRaises(BudgetDenied):
                request_bound(dict(self.payload, **change))

    def test_parallel_trials_denied(self):
        self.trial()
        with self.assertRaises(BudgetDenied): self.trial('b1')

    def test_reopen_ledger_retains_budget_and_token_not_plaintext(self):
        token = self.trial()
        self.ledger.reserve(token, self.payload)
        fresh = Ledger(self.ledger.path)
        self.assertEqual(fresh.status(), self.ledger.status())
        self.assertNotIn(token, json.dumps(fresh.status()))
        self.assertNotIn(token.encode(), self.ledger.path.read_bytes())

    def test_usage_exceeding_bound_fails_closed(self):
        rid, _ = self.ledger.reserve(self.trial(), self.payload)
        with self.assertRaises(BudgetDenied):
            self.ledger.settle(rid, {'usage': {'prompt_tokens': 999999999, 'completion_tokens': 5}, 'choices': [{}]})
        self.assertEqual(self.ledger.status()['calls'][0]['status'], 'reserved')

    def test_only_one_active_request_even_with_multiple_ledger_instances(self):
        token = self.trial()
        second = Ledger(self.ledger.path)
        self.ledger.reserve(token, self.payload)
        with self.assertRaises(BudgetDenied): second.reserve(token, self.payload)

    def test_error_evidence_does_not_unblock_or_release_unknown_cost(self):
        token = self.trial()
        rid, _ = self.ledger.reserve(token, self.payload)
        self.ledger.record_failure(rid, TimeoutError('not written to ledger'), True)
        state = self.ledger.status()
        self.assertEqual(state['failures'][0]['error_type'], 'TimeoutError')
        self.assertEqual(state['calls'][0]['status'], 'reserved')
        self.assertEqual(state['calls'][0]['charged'], state['calls'][0]['reserve'])
        with self.assertRaises(BudgetDenied): self.ledger.reserve(token, self.payload)


if __name__ == '__main__': unittest.main()
