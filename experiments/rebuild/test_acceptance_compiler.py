import copy
import json
from pathlib import Path
import tempfile
import unittest

from acceptance_compiler import freeze, render, select_catalog, syntax_check, validate_plan
from grade import manifest
from requirement_catalog import compile_tree


class AcceptanceCompilerTests(unittest.TestCase):
    def setUp(self):
        self.catalog = compile_tree({'id': 'ROOT', 'type': 'FOLDER', 'children': [
            {'id': 'one', 'type': 'ATOMIC', 'description': 'Click the named Increment button to increase the count.'}]})
        self.catalog['source_sha256'] = 'test-source-not-a-real-requirement'
        self.plan = {'helpers': '', 'cases': [{
            'id': 'increment', 'kind': 'positive', 'requirement_ids': ['one'],
            'source_quote': 'Click the named Increment button to increase the count.',
            'body': "await page.goto('/');\nawait expect(page.getByRole('button',{name:'Increment',exact:true})).toBeVisible();\nawait page.getByRole('button',{name:'Increment',exact:true}).click();\nawait expect(page.getByTestId('count')).toHaveText('1');"}]}

    def test_exact_source_and_complete_positive_coverage(self):
        self.assertEqual(validate_plan(self.plan, self.catalog), self.plan)
        for field, value in [('source_quote', 'a made-up statement not present in the public source'),
                             ('requirement_ids', ['unknown']), ('kind', 'negative'),
                             ('body', "await page.goto('/');")]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan = copy.deepcopy(self.plan)
                plan['cases'][0][field] = value
                validate_plan(plan, self.catalog)

    def test_parser_allows_real_ui_flow_and_rejects_escape_and_fake_passes(self):
        syntax_check(render(self.plan))
        bad = ["await page.evaluate(() => localStorage.clear());",
               "await page.getByRole('link').first().click();",
               "await request.get('/api/private');",
               "await expect(true).toBeTruthy();",
               "try { await page.click('a'); } catch(e) {}",
               "const expect = () => ({toBeVisible() {}});",
               "const f = Object.constructor;", "const f = Object['constructor'];",
               "process.exit(0);", "test.skip();", "await browser.newBrowserCDPSession();",
               "test('injected', async () => {});",
               "await expect(page.getByLabel('Email')).toHaveValue('unused-' + (await page.getByLabel('Email').inputValue()));"]
        for statement in bad:
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                plan = copy.deepcopy(self.plan)
                plan['cases'][0]['body'] += '\n' + statement
                syntax_check(render(plan))
        plan = copy.deepcopy(self.plan)
        plan['helpers'] = 'Object.keys({});'
        with self.assertRaises(ValueError):
            syntax_check(render(plan))

    def test_selection_keeps_dependency_closure_and_ancestors(self):
        catalog = compile_tree({'id':'ROOT','type':'FOLDER','children':[
            {'id':'a','type':'ATOMIC'}, {'id':'b','type':'ATOMIC','dependencies':['a']},
            {'id':'unused','type':'ATOMIC'}]})
        selected = select_catalog(catalog, ['b'])
        self.assertEqual([n['id'] for n in selected['nodes']], ['a','b'])
        self.assertEqual(set(selected['contracts']), {'ROOT','a','b'})
        self.assertEqual(selected['full_atomic_count'], 3)

    def test_successful_persistence_is_positive_coverage_without_duplicate_tests(self):
        plan = copy.deepcopy(self.plan)
        plan['cases'][0]['kind'] = 'persistence'
        with self.assertRaisesRegex(ValueError, 'real restart'):
            validate_plan(plan, self.catalog)
        plan['cases'][0]['body'] += "\nawait restart(request);\nawait page.reload();\nawait expect(page.getByTestId('count')).toHaveText('1');"
        self.assertEqual(validate_plan(plan, self.catalog), plan)

    def test_freeze_is_write_once_and_hashes_actual_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = freeze(self.plan, self.catalog, Path(tmp))
            self.assertEqual(result['tests_sha256'], manifest(Path(tmp)/'suite'))
            self.assertEqual(result['evidence_kind'], 'internal_not_official_tests')
            self.assertEqual(result['expected'], 1)
            self.assertEqual(json.loads((Path(tmp)/'frozen.json').read_text()), result)
            with self.assertRaises(FileExistsError):
                freeze(self.plan, self.catalog, Path(tmp))


if __name__ == '__main__':
    unittest.main()
