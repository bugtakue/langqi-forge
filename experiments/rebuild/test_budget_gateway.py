import json
from pathlib import Path
import tempfile
import unittest
import sqlite3

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

    def test_comparison_model_uses_its_own_verified_price_for_reserve_and_settlement(self):
        payload = dict(self.payload, model='deepseek-v4-flash')
        _, prompt, output = request_bound(payload)
        rid, _ = self.ledger.reserve(self.trial(), payload)
        call = self.ledger.status()['calls'][0]
        self.assertEqual(call['model'], 'deepseek-v4-flash')
        self.assertEqual(call['reserve'], prompt * 3 + output * 9)
        self.ledger.settle(rid, {'usage': {'prompt_tokens': 100, 'completion_tokens': 200}, 'choices': [{}]})
        self.assertEqual(self.ledger.status()['calls'][0]['charged'], 2100)

    def test_schema_reopen_preserves_original_amounts_and_models(self):
        rid, _ = self.ledger.reserve(self.trial(), self.payload)
        self.ledger.close_trial('a1')
        self.ledger.authorize_worst_case(self.authorize(rid))
        state = self.ledger.status()
        self.assertEqual(Ledger(self.ledger.path).status(), state)

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

    def authorize(self, rid):
        call = next(c for c in self.ledger.status()['calls'] if c['id'] == rid)
        return {'call_id': rid, 'reserve_micro_cny': call['reserve'], 'authority': 'user',
                'decision': 'charge_full_reserve_actual_unknown', 'user_reply': 'explicit approval',
                'source_question_id': 'test-only-human-instruction'}

    def test_exact_exception_keeps_full_charge_and_actual_usage_unknown(self):
        rid, _ = self.ledger.reserve(self.trial(), self.payload)
        self.ledger.close_trial('a1')
        before = self.ledger.status()
        approval = self.authorize(rid)
        self.assertTrue(self.ledger.authorize_worst_case(approval))
        self.assertFalse(self.ledger.authorize_worst_case(approval))
        after = self.ledger.status()
        self.assertEqual(before['calls'], after['calls'])
        self.assertEqual(before['total_cny'], after['total_cny'])
        self.assertFalse(after['unresolved_cost_lock'])
        self.assertIsNone(after['calls'][0]['prompt_tokens'])
        with self.assertRaises(BudgetDenied):
            self.ledger.settle(rid, {'usage': {'prompt_tokens': 1, 'completion_tokens': 1}, 'choices': [{}]})
        token = self.trial('b1')
        self.ledger.reserve(token, self.payload)
        self.assertTrue(self.ledger.status()['unresolved_cost_lock'])
        with self.assertRaises(BudgetDenied): self.ledger.reserve(token, self.payload)

    def test_exception_requires_closed_trial_exact_amount_and_durable_instruction(self):
        rid, _ = self.ledger.reserve(self.trial(), self.payload)
        approval = self.authorize(rid)
        with self.assertRaises(BudgetDenied): self.ledger.authorize_worst_case(approval)
        self.ledger.close_trial('a1')
        for change in ({'reserve_micro_cny': 0}, {'authority': 'agent'}, {'user_reply': ''}, {'call_id': 'unknown'}):
            with self.subTest(change=change), self.assertRaises(BudgetDenied):
                self.ledger.authorize_worst_case(dict(approval, **change))
        self.ledger.authorize_worst_case(approval)
        with self.assertRaises(BudgetDenied):
            self.ledger.authorize_worst_case(dict(approval, user_reply='different'))
        with self.ledger.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM worst_case_authorizations')
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE worst_case_authorizations SET reserve=0')
        self.assertEqual(self.ledger.status(), Ledger(self.ledger.path).status())

    def test_exception_does_not_bypass_local_or_phase_budget_caps(self):
        rid, _ = self.ledger.reserve(self.trial(), self.payload)
        self.ledger.close_trial('a1')
        self.ledger.authorize_worst_case(self.authorize(rid))
        token = self.trial('b1', cap=.01)
        with self.assertRaises(BudgetDenied): self.ledger.reserve(token, self.payload)
        self.ledger.close_trial('b1')
        # Seed a fully consumed earlier phase only in this isolated test ledger.
        with self.ledger.connect() as db:
            db.execute('UPDATE calls SET reserve=20000000, charged=20000000 WHERE id=?', (rid,))
        # Tampering with the exact authorized reservation also closes the lock.
        self.assertTrue(self.ledger.status()['unresolved_cost_lock'])
        with self.assertRaises(BudgetDenied): self.trial('c1')


if __name__ == '__main__': unittest.main()
