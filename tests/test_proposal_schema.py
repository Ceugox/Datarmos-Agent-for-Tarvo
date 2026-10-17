from pathlib import Path
import json
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.exceptions import CLASSES

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
