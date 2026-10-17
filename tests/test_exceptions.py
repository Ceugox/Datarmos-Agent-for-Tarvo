from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import re
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.closing import close_month
from tarvo_close.exceptions import CLASSES, DADO_INVALIDO, KINDS, LAYOUT_FONTE, classify
from tarvo_close.readers import read_inputs


def copy_pack(directory, *removed, replace=None):
    target = Path(directory)/'pack'
    shutil.copytree(ROOT/'Tarvo_Data_Pack_set2026',target)
    for pattern in removed:
        for path in target.glob(pattern):
            path.unlink()
    for pattern, content in (replace or {}).items():
        next(target.glob(pattern)).write_text(content,encoding='utf-8')
    return target


class TypedExceptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
        cls.result = close_month(read_inputs(ROOT/'Tarvo_Data_Pack_set2026'),cls.policy,'2026-09')

    def test_every_pending_item_has_one_typed_exception_with_the_same_identity_and_amount(self):
        pending = {row['id_saida']:row for row in self.result.tables['pendencias']}
        exceptions = {item.excecao_id:item for item in self.result.exceptions}
        self.assertEqual(set(pending),set(exceptions))
        self.assertEqual(len(exceptions),len(self.result.exceptions))
        for output_id, row in pending.items():
            item = exceptions[output_id]
            self.assertEqual((item.tipo,item.valor_brl,item.escopo,item.quem_decide,item.motivo),(row['tipo'],row['valor_brl'],row['escopo'],row['quem_decide'],row['motivo']))
            self.assertEqual(';'.join(sorted({ref['ref'] for ref in item.refs})),row['ref_origem'])
            self.assertIn(item.classe,CLASSES)
            self.assertTrue(item.falta)

    def test_september_exceptions_by_class(self):
        self.assertEqual(Counter(item.classe for item in self.result.exceptions),
                         {'DECISAO':8,'ESPERA_EVIDENCIA':2,'CONDICAO_COMERCIAL':2,'ESPERA_DADO':1})

    def test_refs_point_to_source_rows(self):
        transfer = next(item for item in self.result.exceptions if item.tipo=='TRANSFERENCIA_EM_TRANSITO')
        self.assertEqual(len(transfer.refs),1)
        self.assertEqual(transfer.refs[0]['ref'],'L92')
        self.assertTrue(transfer.refs[0]['arquivo'].startswith('05a_'))
        self.assertGreater(transfer.refs[0]['linha'],0)

    def test_every_kind_the_core_emits_has_a_class(self):
        code = (ROOT/'src/tarvo_close/closing.py').read_text(encoding='utf-8')
        literal = set(re.findall(r"pending\([^,]+,\s*'([A-Z_]+)'",code))
        dynamic = {'CADASTRO_OU_CONTRATO_AUSENTE','CONTRATO_AMBIGUO'}  # emitted through an f-string key
        self.assertIn("('CADASTRO_OU_CONTRATO_AUSENTE',unresolved),('CONTRATO_AMBIGUO',conflicts)",code)
        self.assertEqual(literal|dynamic,set(KINDS))

    def test_an_unknown_kind_stops_the_closing(self):
        with self.assertRaisesRegex(ValueError,'without exception class'):
            classify('TIPO_NOVO')

    def test_missing_source_is_invalid_data_and_unreadable_source_is_a_layout_exception(self):
        with TemporaryDirectory() as directory:
            missing = close_month(read_inputs(copy_pack(directory,'01_*.csv')),self.policy,'2026-09')
        with TemporaryDirectory() as directory:
            unreadable = close_month(read_inputs(copy_pack(directory,replace={'04_*.csv':'CONTA;NOME\n1;Caixa\n'})),self.policy,'2026-09')
        self.assertEqual([i.classe for i in missing.exceptions if i.tipo=='FONTE_BLOQUEADA'],[DADO_INVALIDO])
        layout = [i for i in unreadable.exceptions if i.tipo=='FONTE_BLOQUEADA']
        self.assertEqual([i.classe for i in layout],[LAYOUT_FONTE])
        self.assertIn('totais da própria fonte',layout[0].falta)


if __name__ == '__main__':
    unittest.main()
