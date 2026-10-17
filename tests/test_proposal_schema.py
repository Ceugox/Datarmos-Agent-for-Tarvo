from pathlib import Path
import json
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.exceptions import CLASSES
from tarvo_close.resolver import AnthropicResolver

SCHEMA = json.loads((ROOT/'config/proposal.schema.json').read_text(encoding='utf-8'))
KEYWORDS = {'type','properties','required','additionalProperties','enum','const','items','anyOf','minItems','description'}
FORBIDDEN = re.compile('valor|amount|total|comissao|nota|taxa|spread|diferenca|confianca',re.IGNORECASE)


def walk(node, path='$'):
    """Yield (path, schema node); `properties` children are schemas, their names are not keywords."""
    yield path, node
    for name, child in node.get('properties',{}).items():
        yield from walk(child,f'{path}.{name}')
    if 'items' in node:
        yield from walk(node['items'],f'{path}[]')
    for index, child in enumerate(node.get('anyOf',[])):
        yield from walk(child,f'{path}|{index}')


STRICT_DOC_KEYWORDS = {'type','properties','required','additionalProperties','enum','const','items','anyOf','description'}  # doc: tool-use-concepts.md, strict mode
COMBINATORS = ('anyOf','oneOf','allOf')


def walk_all(node, path='$'):
    """Like walk, but also over oneOf/allOf, so the strict checks cannot miss a combinator branch."""
    yield path, node
    for name, child in node.get('properties',{}).items():
        yield from walk_all(child,f'{path}.{name}')
    if isinstance(node.get('items'),dict):
        yield from walk_all(node['items'],f'{path}[]')
    for key in COMBINATORS:
        for index, child in enumerate(node.get(key,[])):
            yield from walk_all(child,f'{path}|{key}{index}')


class StrictToolInputSchemaTests(unittest.TestCase):
    """The real tool input_schema sent for each class. In production (17/10) the API answered 400 first on `type`
    next to `anyOf`, then on the 8-variant anyOf as a strict grammar too large; each call now sends one class variant."""

    @classmethod
    def setUpClass(cls):
        resolver = AnthropicResolver(client=object())
        cls.tools = {name:resolver._tool(name) for name in CLASSES}
        cls.tool = cls.tools['MOVIMENTO_SEM_REGRA']
        cls.nodes = [item for tool in cls.tools.values() for item in walk_all(tool['input_schema'])]

    def test_each_call_sends_only_the_variant_of_its_class(self):
        for name, tool in self.tools.items():
            proposal = tool['input_schema']['properties']['proposta']
            self.assertNotIn('anyOf',proposal,name)
            self.assertEqual(proposal['properties']['classe'].get('const'),name)
            self.assertLess(len(json.dumps(tool['input_schema'])),len(json.dumps(SCHEMA))/4,name)

    def test_an_unknown_class_has_no_tool(self):
        with self.assertRaisesRegex(ValueError,'no single variant'):
            AnthropicResolver(client=object())._tool('CLASSE_NOVA')

    def test_resolver_version_enters_the_cache_key_whatever_the_stored_policy(self):
        self.assertTrue(AnthropicResolver(client=object(),prompt_version='2026-10-17.1').prompt_version.startswith('2026-10-17.1+'))

    def test_tool_is_strict(self):
        self.assertIs(self.tool['strict'],True)

    def test_no_node_mixes_type_with_a_combinator(self):
        for path, node in self.nodes:
            if 'type' in node:
                self.assertFalse(set(node) & set(COMBINATORS),path)

    def test_every_object_is_closed_and_fully_required(self):
        # The doc only requires additionalProperties: false; requiring every property is our own convention (brief da Fase 2).
        objects = [(path,node) for path, node in self.nodes if node.get('type') == 'object']
        self.assertGreater(len(objects),8)
        for path, node in objects:
            self.assertIs(node.get('additionalProperties'),False,path)
            self.assertEqual(set(node['required']),set(node['properties']),path)

    def test_only_keywords_the_strict_mode_accepts(self):
        found = set()
        for path, node in self.nodes:
            self.assertLessEqual(set(node),KEYWORDS,path)
            found |= set(node)
        self.assertLessEqual(found,STRICT_DOC_KEYWORDS)
        self.assertNotIn('minItems',found)

    def test_file_schema_still_demands_one_evidence(self):
        from tarvo_close.validators import check_shape
        item = {'excecao_id':'PEN-1', 'classe':'CADASTRO', 'tipo':'X'}
        proposal = {'excecao_id':'PEN-1', 'classe':'CADASTRO', 'acao':'ENCAMINHAR_HUMANO', 'parametros':{}, 'evidencias':[], 'justificativa':'x', 'requer_humano':True}
        self.assertTrue(check_shape(proposal,item))
        proposal['evidencias'] = [{'arquivo':'a', 'ref':'L1', 'trecho':'t'}]
        self.assertEqual(check_shape(proposal,item),[])


class ProposalSchemaTests(unittest.TestCase):
    def test_one_variant_per_class(self):
        variants = SCHEMA['anyOf']
        self.assertEqual(len(variants),8)
        self.assertEqual([v['properties']['classe']['const'] for v in variants],list(CLASSES))

    def test_no_monetary_or_self_declared_confidence_property_and_no_numeric_type(self):
        for path, node in walk(SCHEMA):
            for name in node.get('properties',{}):
                self.assertIsNone(FORBIDDEN.search(name),f'{path}.{name}')
            self.assertNotIn(node.get('type'),('number','integer'),path)

    def test_every_object_is_closed_and_fully_required(self):
        for path, node in walk(SCHEMA):
            if path=='$' or 'properties' not in node:
                continue
            self.assertIs(node.get('additionalProperties'),False,path)
            self.assertEqual(set(node['required']),set(node['properties']),path)

    def test_only_strict_mode_keywords(self):
        for path, node in walk(SCHEMA):
            self.assertLessEqual(set(node),KEYWORDS,path)

    def test_variant_shape(self):
        for variant in SCHEMA['anyOf']:
            props = variant['properties']
            self.assertEqual(set(props),{'excecao_id','classe','acao','parametros','evidencias','justificativa','requer_humano'})
            self.assertEqual(props['evidencias']['minItems'],1)
            self.assertEqual(set(props['evidencias']['items']['properties']),{'arquivo','ref','trecho'})

    def test_allowed_actions_per_class(self):
        for variant in SCHEMA['anyOf']:
            classe = variant['properties']['classe']['const']
            expected = ['CLASSIFICAR_CONTA','ENCAMINHAR_HUMANO'] if classe=='MOVIMENTO_SEM_REGRA' else ['ENCAMINHAR_HUMANO']
            self.assertEqual(variant['properties']['acao']['enum'],expected,classe)

    def test_parameters_per_class(self):
        for variant in SCHEMA['anyOf']:
            params = variant['properties']['parametros']
            if variant['properties']['classe']['const']=='MOVIMENTO_SEM_REGRA':
                self.assertEqual([set(o['properties']) for o in params['anyOf']],[{'conta_codigo'},set()])
            else:
                self.assertEqual((params['properties'],params['required']),({},[]))


if __name__ == '__main__':
    unittest.main()
