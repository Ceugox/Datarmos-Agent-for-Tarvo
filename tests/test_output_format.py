from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from tarvo_close.closing import close_month
from tarvo_close.readers import read_inputs
from tarvo_close.resolver import FakeResolver
from output_format import csv_errors, output_errors
from test_cli_inference import PACK, run
import test_revision
from test_revision import MSR, NO_FEES, inference_policy


class FormatCheckerTests(unittest.TestCase):
    """The checker itself must reject each way the fixed format can break."""
    GOOD = 'id_saida;cnpj;data;valor_brl;linha_origem\nX;01234567000189;2026-09-30;-1234.50;7\n'

    def errors(self, text, encoding='utf-8'):
        return csv_errors('t.csv',text.encode(encoding))

    def test_accepts_the_fixed_format(self):
        self.assertEqual(self.errors(self.GOOD),[])
        self.assertEqual(self.errors('id_saida;valor_brl\nX;\n'),[])  # unknown amount stays empty

    def test_rejects_each_deviation(self):
        cases = {
            'comma separator': self.GOOD.replace(';',','),
            'decimal comma': self.GOOD.replace('-1234.50','-1234,50'),
            'thousands separator': self.GOOD.replace('-1234.50','-1.234.50'),
            'scientific notation': self.GOOD.replace('-1234.50','1E+3'),
            'brazilian date': self.GOOD.replace('2026-09-30','30/09/2026'),
            'formatted CNPJ': self.GOOD.replace('01234567000189','01.234.567/0001-89'),
            'CNPJ without leading zero': self.GOOD.replace('01234567000189','1234567000189'),
            'CRLF': self.GOOD.replace('\n','\r\n'),
            'missing field': self.GOOD.replace(';7\n','\n'),
            'empty CNPJ': self.GOOD.replace('01234567000189',''),
        }
        for label, text in cases.items():
            with self.subTest(label):
                self.assertTrue(self.errors(text),label)
        self.assertTrue(csv_errors('t.csv',b'\xef\xbb\xbf'+self.GOOD.encode()))
        self.assertTrue(self.errors(self.GOOD.replace('X','Ç'),encoding='latin-1'))


class OutputFormatTests(unittest.TestCase):
    """Every path that writes CSVs: delivered saida/, a fresh run, IA-applied lines and a revision."""

    def assertFormat(self, directory):
        self.assertEqual(output_errors(directory),[])

    def test_delivered_saida(self):
        self.assertFormat(ROOT/'saida')

    def test_fresh_run_without_llm(self):
        with TemporaryDirectory() as directory:
            code, _, err = run(Path(directory)/'out','--no-llm')
            self.assertEqual(code,0,err)
            self.assertFormat(Path(directory)/'out')

    def test_lines_applied_by_the_inference_layer_and_a_revision(self):
        bundle = read_inputs(PACK)
        movements = [e.as_dict() for e in close_month(bundle,NO_FEES,'2026-09').exceptions if e.classe == MSR]
        entries = {f'{e["bank"]}:{e["_source"]["ref_origem"]}':e for e in bundle.bank_entries}
        responses = {m['excecao_id']:test_revision.RevisionTests.proposal(m,entries[m['escopo']]['description']) for m in movements}
        self.assertTrue(responses)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root/'closing-policy.json'
            policy.write_text(json.dumps(NO_FEES),encoding='utf-8')
            automatic = root/'automatico.json'
            automatic.write_text(json.dumps(inference_policy('automatico','0.90')),encoding='utf-8')
            suggest = root/'sugerir.json'
            suggest.write_text(json.dumps(inference_policy('sugerir')),encoding='utf-8')
            code, _, err = run(root/'auto','--policy',str(policy),'--inference-policy',str(automatic),'--cache-dir',str(root/'c1'),resolver=FakeResolver(responses))
            self.assertEqual(code,0,err)
            with open(root/'auto'/'lancamentos_classificados.csv',encoding='utf-8',newline='') as handle:
                applied = [r for r in csv.DictReader(handle,delimiter=';') if r['metodo'] == 'IA']
            self.assertEqual(len(applied),len(responses))
            self.assertTrue(all(r['confianca'] == '0.90' for r in applied))
            self.assertFormat(root/'auto')
            code, _, err = run(root/'suggest','--policy',str(policy),'--inference-policy',str(suggest),'--cache-dir',str(root/'c2'),resolver=FakeResolver(responses))
            self.assertEqual(code,0,err)
            decisions = root/'decisoes.json'
            decisions.write_text(json.dumps([{'excecao_id':key,'decisao':'aprovar','decidido_por':'Helena','motivo':'tarifa'} for key in responses]),encoding='utf-8')
            code, _, err = run(root/'rev1','--policy',str(policy),'--inference-policy',str(suggest),'--decisoes',str(decisions),'--revisao-de',str(root/'suggest'))
            self.assertEqual(code,0,err)
            with open(root/'rev1'/'lancamentos_classificados.csv',encoding='utf-8',newline='') as handle:
                approved = [r for r in csv.DictReader(handle,delimiter=';') if r['metodo'] == 'IA']
            self.assertEqual(len(approved),len(responses))
            self.assertFormat(root/'rev1')


if __name__ == '__main__':
    unittest.main()
