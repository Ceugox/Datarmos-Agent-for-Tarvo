"""rastro.csv must let anyone redo every number without asking (organization, 17/10): every output with an id_saida,
sums matching, the rule applied on each line and a record of each execution."""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from tarvo_close.closing import close_month, policy_rule_exists
from tarvo_close.domain import quantize
from tarvo_close.readers import read_inputs
from test_cli_inference import run

POLICY = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
AMOUNTS = {'COM':'comissoes_por_lojista','DIV':'divergencias_taxa','NFC':'notas_a_emitir'}


class RastroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = read_inputs(ROOT/'Tarvo_Data_Pack_set2026')
        cls.result = close_month(cls.bundle,POLICY,'2026-09')
        cls.contracts = {f"{c['_source']['arquivo_origem']}!{c['_source']['ref_origem']}":c for c in cls.bundle.contracts}

    def test_every_commission_divergence_and_invoice_line_names_a_rule_of_the_policy(self):
        for trace in self.result.traces:
            if trace['id_saida'][:3] in AMOUNTS:
                self.assertTrue(trace['regra'],trace)
            for rule in filter(None,trace['regra'].split(' + ')):
                self.assertTrue(policy_rule_exists(POLICY,rule),rule)

    def test_rules_say_what_was_applied(self):
        rules = defaultdict(set)
        for trace in self.result.traces:
            rules[trace['id_saida'][:3]].add(trace['regra'])
        self.assertIn('decisions/checkout-reversal',rules['COM'])
        self.assertIn('decisions/checkout-basis + commercial_conditions/casa-estudante-isencao-2026',rules['COM'])
        self.assertIn('remittance',rules['COM'])
        self.assertEqual(rules['DIV'],{'decisions/checkout-divergence','decisions/remittance-divergence'})
        reversal = next(t for t in self.result.traces if t['regra'] == 'decisions/checkout-reversal' and 'TX88444848' == t['ref_origem'])
        self.assertIn('estorno pela taxa da data da venda original (2026-08-22)',reversal['formula'])

    def test_every_checkout_number_is_redone_from_the_trace_and_the_rate_sheet(self):
        """Recompute each checkout commission and divergence line from rastro + 02_ only, then each output total."""
        totals = defaultdict(Decimal)
        checked = 0
        for trace in self.result.traces:
            totals[trace['id_saida']] += trace['valor']
            if not trace['ref_contrato'].startswith('02_'):
                continue
            contract = self.contracts[trace['ref_contrato']]
            if trace['id_saida'].startswith('COM'):
                gross, rate, key = re.match(r'[A-Z ]+: quantize\((-?[\d.]+)\*([\d.]+)\); half_up; taxa (\w+) vigente',trace['formula']).groups()
                expected_rate = Decimal(0) if 'commercial_conditions/' in trace['regra'] else contract[key]
                self.assertEqual(Decimal(rate),expected_rate,trace)
                self.assertEqual(quantize(Decimal(gross)*Decimal(rate)),trace['valor'],trace)
            elif trace['regra'] == 'decisions/checkout-divergence':
                gross, applied, contracted, key = re.match(r'quantize\((-?[\d.]+)\*\(([\d.]+)-([\d.]+)\)\).*\((\w+), vigente',trace['formula']).groups()
                self.assertEqual(Decimal(contracted),contract[key],trace)
                self.assertEqual(quantize(Decimal(gross)*(Decimal(applied)-Decimal(contracted))),trace['valor'],trace)
            elif trace['regra'] == 'decisions/remittance-divergence':
                spread, foreign, ptax, contracted = re.match(r'quantize\((-?[\d.]+)-([\d.]+)\*([\d.]+)\*([\d.]+)\)',trace['formula']).groups()
                self.assertEqual(Decimal(contracted),contract['spread'] if contract['spread'] is not None else Decimal(POLICY['remittance']['default_spread']),trace)
                self.assertEqual(quantize(Decimal(spread)-Decimal(foreign)*Decimal(ptax)*Decimal(contracted)),trace['valor'],trace)
            else:
                continue
            checked += 1
        self.assertGreater(checked,1900)
        for table in AMOUNTS.values():
            column = {'comissoes_por_lojista':'comissao_brl','divergencias_taxa':'diferenca_brl','notas_a_emitir':'valor_brl'}[table]
            for row in self.result.tables[table]:
                self.assertEqual(totals[row['id_saida']],row[column],row['id_saida'])

    def test_ponte_invoice_and_remittance_lines_are_redone_from_the_trace(self):
        invoice = next(r for r in self.result.tables['notas_a_emitir'] if r['linha_negocio'] == 'REMESSA')
        parts = [t for t in self.result.traces if t['id_saida'] == invoice['id_saida']]
        self.assertEqual(len(parts),228)
        for part in parts:
            self.assertEqual(part['regra'],'remittance')
            spread, share = re.match(r'quantize\((-?[\d.]+)\*([\d.]+)\)',part['formula']).groups()
            self.assertEqual(Decimal(share),Decimal(POLICY['remittance']['share']))
            self.assertEqual(quantize(Decimal(spread)*Decimal(share)),part['valor'])
        self.assertEqual(sum(p['valor'] for p in parts),invoice['valor_brl'])

    def test_a_rule_missing_from_the_policy_stops_the_closing(self):
        policy = deepcopy(POLICY)
        policy['decisions'] = [d for d in policy['decisions'] if d['id'] != 'checkout-reversal']
        with self.assertRaisesRegex(ValueError,'rule that is not in the policy: decisions/checkout-reversal'):
            close_month(self.bundle,policy,'2026-09')


class ExecutionRecordTests(unittest.TestCase):
    def test_manifest_records_files_lines_and_time_and_a_rerun_still_confirms(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)/'out'
            code, _, err = run(output,'--no-llm')
            self.assertEqual(code,0,err)
            manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
            execution = manifest['execucao']
            started = datetime.fromisoformat(execution['iniciada_em'])
            self.assertLessEqual(started,datetime.fromisoformat(execution['concluida_em']))
            self.assertIsNotNone(started.tzinfo)
            lines = {name:meta.get('linhas_lidas') for name,meta in manifest['sources'].items()}
            self.assertEqual(lines['01_orbe_relatorio_comissoes_set2026.csv']+lines['06_orbe_ajustes_tardios_set2026.csv'],1957)
            self.assertEqual(lines['PonteCambio_Relatorio_TARVO_092026.xlsx'],233)
            self.assertEqual(lines['05a_extrato_banco_aurora_cc4471_set2026.csv']+lines['05b_extrato_banco_meridiano_cc90233_set2026.ofx'],184)
            self.assertEqual(lines['04_plano_de_contas_fenix_erp.csv'],52)
            self.assertEqual(manifest['sources']['02_tabela_taxas_contratadas.xlsx']['linhas_por_aba'],{'Taxas vigentes':24})
            self.assertEqual(execution['linhas_lidas_total'],sum(v for v in lines.values() if v))
            code, _, err = run(output,'--no-llm')  # same content, new timestamps: confirmed, nothing overwritten
            self.assertEqual(code,0,err)
            self.assertEqual(json.loads((output/'manifest.json').read_text(encoding='utf-8'))['execucao'],execution)


if __name__ == '__main__':
    unittest.main()
