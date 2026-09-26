import copy
import unittest
from requirement_catalog import ContractError, compile_tree, render_node


def atom(nid, deps=None):
    return {'id':nid,'type':'ATOMIC','description':'contract '+nid,'dependencies':deps or []}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tree={'id':'ROOT','type':'FOLDER','description':'common persistence', 'children':[
            atom('seed'), {'id':'family','type':'FOLDER','description':'shared ARIA',
                'dependencies':['seed'],'children':[atom('member')]},atom('consumer',['family'])]}

    def test_inherited_contracts_and_folder_dependencies_are_preserved(self):
        original=copy.deepcopy(self.tree)
        c=compile_tree(self.tree)
        self.assertEqual([n['id'] for n in c['nodes']],['seed','member','consumer'])
        member=c['nodes'][1]
        self.assertEqual(member['dependencies'],['seed'])
        self.assertEqual(member['dependency_origins'][0]['declared_by'],'family')
        self.assertEqual(c['nodes'][2]['dependencies'],['member'])
        self.assertIn('common persistence',render_node(c,'member'))
        self.assertIn('shared ARIA',render_node(c,'member'))
        self.assertEqual(original,self.tree)

    def test_cycles_unknown_ids_and_duplicate_ids_fail_loudly(self):
        for children in ([atom('a',['b']),atom('b',['a'])], [atom('a',['missing'])], [atom('a'),atom('a')]):
            with self.subTest(children=children),self.assertRaises(ContractError):
                compile_tree({'id':'ROOT','type':'FOLDER','children':children})

    def test_higher_fanout_prerequisite_before_unrelated_leaf(self):
        c=compile_tree({'id':'ROOT','type':'FOLDER','children':[atom('independent'),atom('base'),
                       atom('one',['base']),atom('two',['base'])]})
        self.assertEqual(c['nodes'][0]['id'],'base')

    def test_scenarios_and_non_ascii_are_not_truncated(self):
        self.tree['description']='公共状态'*10000
        self.tree['scenarios']=[{'name':'root scenario','steps':[{'keyword':'THEN','content':'重新打开仍保存'}]}]
        text=render_node(compile_tree(self.tree),'member')
        self.assertIn(self.tree['description'],text)
        self.assertIn('重新打开仍保存',text)


if __name__=='__main__':unittest.main()
