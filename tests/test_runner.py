from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import csv
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from tarvo_close.closing import close_month
from tarvo_close.inference import validate_decisions
from tarvo_close.llm_cache import ResponseCache
from tarvo_close.readers import read_inputs
from tarvo_close.resolver import FakeResolver
from tarvo_close.runner import run_closing, run_revision_closing
from test_cli_inference import PACK, VOLATILE, files, run, same_bytes

CLOSING = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
INFERENCE = json.loads((ROOT/'config/inference-policy.json').read_text(encoding='utf-8'))


def without_key():
    return mock.patch.dict(os.environ,{k:v for k,v in os.environ.items() if k != 'ANTHROPIC_API_KEY'},clear=True)


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        code, _, _ = run(cls.root/'cli','--no-llm')
        assert code == 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_llm_matches_the_cli(self):
        done = run_closing(PACK,CLOSING,None,'2026-09',self.root/'no-llm',use_llm=False)
        self.assertEqual((done['events'],done['audit'],done['aviso']),([],None,None))
        same_bytes(self,self.root/'cli',self.root/'no-llm')

    def test_without_key_returns_a_warning_and_no_audit(self):
        with without_key():
            done = run_closing(PACK,CLOSING,INFERENCE,'2026-09',self.root/'no-key',cache=ResponseCache(self.root/'c0'))
        self.assertIn('ANTHROPIC_API_KEY not set',done['aviso'])
        self.assertNotIn('auditoria.jsonl',files(self.root/'no-key'))
        same_bytes(self,self.root/'cli',self.root/'no-key')

    def layer(self):
        return run_closing(PACK,CLOSING,INFERENCE,'2026-09',self.root/'layer',resolver=FakeResolver(),cache=ResponseCache(self.root/'c1'))

    def test_fake_resolver_writes_audit_and_events(self):
        done = self.layer()
        self.assertIsNone(done['aviso'])
        self.assertEqual(len(done['events']),13)
        self.assertTrue((self.root/'layer'/'auditoria.jsonl').is_file())
        same_bytes(self,self.root/'cli',self.root/'layer',VOLATILE|{'auditoria.jsonl'})

    def test_revision_applies_an_approval(self):
        self.layer()
        known = next(e for e in close_month(read_inputs(PACK),CLOSING,'2026-09').exceptions if e.classe == 'DECISAO').excecao_id
        decisions = [{'excecao_id':known, 'decisao':'aprovar', 'decidido_por':'Helena', 'motivo':'ok'}]
        done = run_revision_closing(PACK,CLOSING,INFERENCE,'2026-09',self.root/'rev',self.root/'layer',decisions)
        self.assertEqual(done['revision']['numero'],1)
        with open(self.root/'rev'/'pendencias.csv',encoding='utf-8',newline='') as handle:
            rows = {r['id_saida']:r['status'] for r in csv.DictReader(handle,delimiter=';')}
        self.assertEqual(rows[known],'APROVADA')
        self.assertTrue((self.root/'rev'/'auditoria.jsonl').is_file())

    def test_validate_decisions_rejects_malformed_input(self):
        result = close_month(read_inputs(PACK),CLOSING,'2026-09')
        known = result.exceptions[0].excecao_id
        good = {'excecao_id':known, 'decisao':'aprovar', 'decidido_por':'Helena', 'motivo':'ok'}
        self.assertEqual(validate_decisions([good],result),[good])
        for bad in ({'a':1}, ['x'], [{**good,'decisao':'talvez'}], [{**good,'extra':1}], [{**good,'excecao_id':'nao-existe'}], [good,deepcopy(good)]):
            with self.assertRaises(ValueError):
                validate_decisions(bad,result)


if __name__ == '__main__':
    unittest.main()
