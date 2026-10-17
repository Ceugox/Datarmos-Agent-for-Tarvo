from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.closing import close_month, select_contract
from tarvo_close.domain import allocate_shares, cnpj, decimal, parse_rate, quantize
from tarvo_close.readers import read_checkout, read_inputs, read_aurora
from tarvo_close.reporting import publish_result


class MonetaryRulesTests(unittest.TestCase):
    def test_signed_allocation_preserves_the_rounded_aggregate(self):
        amounts = {'a':Decimal('131.005'),'b':Decimal('-343.760'),'c':Decimal('209.795')}
        allocated = allocate_shares(amounts,'aggregate')
        self.assertEqual(sum(allocated.values()),Decimal('-2.96'))
        self.assertLess(allocated['b'],0)
        self.assertTrue(all(abs(allocated[k]-v)<Decimal('.01') for k,v in amounts.items()))

    def test_allocation_does_not_depend_on_input_order(self):
        amounts = {'z':Decimal('1.005'),'a':Decimal('1.005'),'b':Decimal('-1.005')}
        self.assertEqual(allocate_shares(amounts,'aggregate'),allocate_shares(dict(reversed(list(amounts.items()))),'aggregate'))
        self.assertNotEqual(allocate_shares(amounts,'aggregate'),allocate_shares(amounts,'per_operation'))

    def test_numeric_cnpj_retains_the_missing_initial_zero(self):
        self.assertEqual(cnpj(3229837000103),'03229837000103')
        self.assertEqual(cnpj('00.520.815/0001-00'),'00520815000100')
        with self.assertRaises(ValueError):
            cnpj('invalid identity')

    def test_missing_numeric_values_do_not_become_zero(self):
        with self.assertRaises(ValueError):
            decimal('')
        with self.assertRaises(ValueError):
            decimal('NaN')
        self.assertIsNone(parse_rate('padrão'))
        self.assertEqual(parse_rate('1,49%'),Decimal('.0149'))


class SourceAndClosingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = read_inputs(ROOT/'Tarvo_Data_Pack_set2026')
        cls.policy = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))

    def test_the_supplied_pack_follows_the_finance_rules(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        metrics = result.metrics
        self.assertEqual(metrics['checkout_lidos'],1957)
        self.assertEqual(metrics['checkout_sem_contrato'],0)
        self.assertEqual(metrics['checkout_nao_faturado'],57)
        self.assertEqual(metrics['checkout_bruto_nao_faturado'],Decimal('262138.61'))
        self.assertEqual(metrics['comissao_checkout'],Decimal('203735.34'))
        self.assertEqual(metrics['valor_notas'],Decimal('243284.29'))
        self.assertEqual(metrics['status'],'CALCULADO')
        self.assertEqual(metrics['divergencias_checkout'],92)
        self.assertEqual(metrics['diferenca_checkout_brl'],Decimal('1576.23'))
        self.assertEqual(metrics['remessas_elegiveis'],228)
        self.assertEqual(metrics['remessas_contestadas'],4)
        self.assertEqual(metrics['participacao_remessas'],Decimal('39543.45'))
        self.assertEqual(metrics['diferenca_remessa_brl'],Decimal('1418.88'))
        self.assertEqual(metrics['devolucao_condicao_comercial'],Decimal('15396.77'))
        self.assertEqual(len(result.tables['notas_a_emitir']),21)
        self.assertEqual(len(result.tables['lancamentos_classificados']),184)
        self.assertEqual(len(result.coverage),2374)
        self.assertFalse(any(r['confianca']=='0' for r in result.tables['lancamentos_classificados']))
        lojistas = {(r['cnpj'],r['linha_negocio']) for r in result.tables['divergencias_taxa']}
        self.assertEqual({cnpj for cnpj,_ in lojistas},{'95927868000148','22224579000109','17217888000111'})

    def test_late_orbe_adjustments_enter_september_at_the_original_rates(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        traces = {(t['arquivo_origem'],t['ref_origem']):t for t in result.traces if t['id_saida'].startswith('COM-')}
        late = {ref:t for (name,ref),t in traces.items() if name=='06_orbe_ajustes_tardios_set2026.csv'}
        self.assertEqual(len(late),14)
        self.assertEqual(sum((t['valor'] for t in late.values()),Decimal(0)),Decimal('-3304.39'))
        self.assertEqual(late['AN88447152']['valor'],Decimal('-967.69'))
        self.assertEqual(late['TX88447225']['valor'],Decimal('174.81'))

    def test_registered_name_is_used_on_both_business_lines(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        names = {r['lojista'] for r in result.tables['comissoes_por_lojista'] if r['cnpj']=='95927868000148'}
        self.assertEqual(names,{'Rota Global Intercâmbio Ltda'})
        self.assertEqual({r['lojista'] for r in result.tables['divergencias_taxa'] if r['linha_negocio']=='REMESSA'},{'Mundo Aberto'})
        repeated = [c['lojista'] for c in result.contests['PONTE'] if c['motivo']=='OPERACAO_REPETIDA']
        self.assertTrue(repeated)
        self.assertNotIn('BAGAGEM LIVRE TURISM',repeated)

    def test_unreadable_late_adjustment_blocks_checkout(self):
        with TemporaryDirectory() as directory:
            pack = self.pack_without(directory,replace={'06_*.csv':'a;b\n1;2\n'})
            result = close_month(read_inputs(pack),self.policy,'2026-09')
        self.assertEqual(result.metrics['etapas_bloqueadas'],['checkout'])
        self.assertIsNone(result.metrics['comissao_checkout'])
        self.assertEqual(result.metrics['participacao_remessas'],Decimal('39543.45'))

    def test_duplicated_source_blocks_its_stage(self):
        with TemporaryDirectory() as directory:
            pack = self.pack_without(directory)
            shutil.copy(next(pack.glob('03_*.eml')),pack/'03_copia.eml')
            result = close_month(read_inputs(pack),self.policy,'2026-09')
        self.assertEqual(result.metrics['etapas_bloqueadas'],['remessa'])
        self.assertIsNone(result.metrics['participacao_remessas'])
        self.assertEqual(result.metrics['comissao_checkout'],Decimal('203735.34'))

    def test_missing_rates_block_checkout_and_remittance(self):
        with TemporaryDirectory() as directory:
            result = close_month(read_inputs(self.pack_without(directory,'02_*.xlsx')),self.policy,'2026-09')
        self.assertEqual(result.metrics['etapas_bloqueadas'],['checkout','remessa'])
        self.assertEqual(result.tables['comissoes_por_lojista'],[])
        self.assertEqual(len(result.tables['lancamentos_classificados']),184)

    def test_missing_statement_is_reported_and_transfers_are_not_guessed(self):
        with TemporaryDirectory() as directory:
            result = close_month(read_inputs(self.pack_without(directory,'05b_*.ofx')),self.policy,'2026-09')
        self.assertEqual(result.metrics['etapas_bloqueadas'],['bancos:MERIDIANO'])
        transfers = [p for p in result.tables['pendencias'] if p['tipo']=='TRANSFERENCIA_EM_TRANSITO']
        self.assertTrue(transfers)
        self.assertTrue(all('bloqueado' in p['motivo'] for p in transfers))

    def test_blocked_counts_are_unknown_and_cross_stage_totals_are_partial(self):
        with TemporaryDirectory() as directory:
            result = close_month(read_inputs(self.pack_without(directory,'02_*.xlsx')),self.policy,'2026-09')
        for key in ['checkout_nao_faturado','checkout_sem_contrato','divergencias_checkout','remessas_elegiveis','remessas_contestadas']:
            self.assertIsNone(result.metrics[key],key)
        self.assertEqual(result.metrics['movimentos_bancarios_exportados'],184)
        self.assertEqual(result.metrics['totais_parciais'],['checkout','remessa'])

    def test_provisional_report_and_command_render_blocked_values(self):
        with TemporaryDirectory() as directory:
            pack = self.pack_without(directory,'01_*.csv')
            completed = subprocess.run([sys.executable,str(ROOT/'run_engine.py'),'--input',str(pack),'--policy',str(ROOT/'config/closing-policy.json'),'--period','2026-09','--output',str(Path(directory)/'out')],cwd=ROOT,capture_output=True,text=True)
            page = (Path(directory)/'out'/'index.html').read_text(encoding='utf-8')
        self.assertEqual(completed.returncode,3,completed.stderr)
        self.assertIn('Checkout commission: BRL BLOCKED',completed.stdout)
        self.assertIn('(PARTIAL: blocked checkout)',completed.stdout)
        summary = page.split('<h2>Verificações</h2>')[0]
        self.assertIn('<strong>bloqueado</strong>',summary)
        self.assertIn('parcial: sem as etapas bloqueadas checkout',summary)
        self.assertNotIn('None',summary)

    def test_a_folder_without_sources_fails_instead_of_closing_empty(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'No source files'):
                read_inputs(directory)

    def pack_without(self, directory, *patterns, replace=None):
        target = Path(directory)/'pack'
        shutil.copytree(ROOT/'Tarvo_Data_Pack_set2026',target)
        for pattern in patterns:
            for path in target.glob(pattern):
                path.unlink()
        for pattern, content in (replace or {}).items():
            next(target.glob(pattern)).write_text(content,encoding='utf-8')
        return target

    def test_missing_orbe_report_blocks_only_checkout(self):
        with TemporaryDirectory() as directory:
            result = close_month(read_inputs(self.pack_without(directory,'01_*.csv')),self.policy,'2026-09')
        self.assertEqual(result.metrics['status'],'PROVISORIO')
        self.assertEqual(result.metrics['etapas_bloqueadas'],['checkout'])
        blocks = [p for p in result.tables['pendencias'] if p['tipo']=='FONTE_BLOQUEADA']
        self.assertEqual([(p['escopo'],p['quem_decide']) for p in blocks],[('01_*.csv','Helena (financeiro)')])
        self.assertFalse(any(r['linha_negocio']=='CHECKOUT' for r in result.tables['comissoes_por_lojista']))
        self.assertEqual(result.metrics['participacao_remessas'],Decimal('39543.45'))
        self.assertEqual([r['linha_negocio'] for r in result.tables['notas_a_emitir']],['REMESSA'])
        self.assertEqual(len(result.tables['lancamentos_classificados']),184)
        self.assertTrue(all(c['status']=='BLOQUEADO' for c in result.coverage if c['tipo_origem']=='CHECKOUT'))

    def test_changed_chart_layout_blocks_only_bank_classification(self):
        with TemporaryDirectory() as directory:
            pack = self.pack_without(directory,replace={'04_*.csv':'CONTA;NOME\n1;Caixa\n'})
            result = close_month(read_inputs(pack),self.policy,'2026-09')
        self.assertEqual(result.metrics['etapas_bloqueadas'],['bancos'])
        self.assertIn('layout diferente',next(p['motivo'] for p in result.tables['pendencias'] if p['tipo']=='FONTE_BLOQUEADA'))
        self.assertEqual(result.tables['lancamentos_classificados'],[])
        self.assertEqual(result.metrics['comissao_checkout'],Decimal('203735.34'))
        self.assertEqual(sum(1 for c in result.coverage if c['status']=='BLOQUEADO'),184)

    def test_late_adjustments_are_optional(self):
        with TemporaryDirectory() as directory:
            result = close_month(read_inputs(self.pack_without(directory,'06_*.csv')),self.policy,'2026-09')
        self.assertEqual(result.metrics['status'],'CALCULADO')
        self.assertEqual(result.metrics['comissao_checkout'],Decimal('207039.73'))

    def test_the_command_signals_a_provisional_closing(self):
        with TemporaryDirectory() as directory:
            pack = self.pack_without(directory,'05b_*.ofx')
            completed = subprocess.run([sys.executable,str(ROOT/'run_engine.py'),'--input',str(pack),'--policy',str(ROOT/'config/closing-policy.json'),'--period','2026-09','--output',str(Path(directory)/'out')],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(completed.returncode,3,completed.stderr)
            self.assertIn('BLOCKED SOURCE 05b_*.ofx',completed.stderr)
            self.assertIn('Fechamento provisório',(Path(directory)/'out'/'index.html').read_text(encoding='utf-8'))

    def test_one_remittance_invoice_goes_to_ponte_and_checkout_invoices_are_per_merchant(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        remittance = [r for r in result.tables['notas_a_emitir'] if r['linha_negocio']=='REMESSA']
        self.assertEqual(len(remittance),1)
        self.assertEqual(remittance[0]['valor_brl'],Decimal('39543.45'))
        self.assertIn('PONTE',remittance[0]['tomador'].upper())
        checkout = [r['tomador_cnpj'] for r in result.tables['notas_a_emitir'] if r['linha_negocio']=='CHECKOUT']
        self.assertEqual(len(checkout),len(set(checkout)))
        self.assertTrue(all(r['valor_brl']>0 for r in result.tables['notas_a_emitir']))

    def test_casa_do_estudante_exemption_refunds_and_keeps_the_august_rate_on_its_reversal(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        casa = '00520815000100'
        commission = next(r for r in result.tables['comissoes_por_lojista'] if r['cnpj']==casa and r['linha_negocio']=='CHECKOUT')
        self.assertEqual(commission['comissao_brl'],Decimal('-5.50'))
        self.assertFalse(any(r['tomador_cnpj']==casa for r in result.tables['notas_a_emitir']))
        kinds = {r['tipo'] for r in result.tables['pendencias'] if r['escopo']==casa}
        self.assertEqual(kinds,{'SALDO_NAO_POSITIVO_SEM_NOTA','DEVOLUCAO_CONDICAO_COMERCIAL'})
        self.assertFalse(any(r['cnpj']==casa for r in result.tables['divergencias_taxa']))
        refund = next(r for r in result.tables['pendencias'] if r['tipo']=='DEVOLUCAO_CONDICAO_COMERCIAL')
        self.assertEqual(refund['valor_brl'],Decimal('15396.77'))
        self.assertIn('= 15397.42 (+0.65 em 67 de 118 lançamentos',refund['motivo'])
        self.assertIn('devolveria 0.65 a mais do que o lojista pagou',refund['motivo'])
        self.assertIn('o que foi descontado de fato',refund['motivo'])

    def test_refund_reason_follows_the_sign_of_the_recomputed_gap(self):
        bundle = deepcopy(self.bundle)
        for row in bundle.checkout:
            if row['cod_estabelecimento']=='1018325654' and row['valor_taxa']:
                row['valor_taxa'] = quantize(row['valor_bruto']*row['taxa_aplicada_pct']/100,'half_up')
        refund = next(r for r in close_month(bundle,self.policy,'2026-09').tables['pendencias'] if r['tipo']=='DEVOLUCAO_CONDICAO_COMERCIAL')
        self.assertIn('igual ao valor cobrado',refund['motivo'])
        self.assertNotIn('descartada',refund['motivo'])
        for row in bundle.checkout:
            if row['cod_estabelecimento']=='1018325654' and row['tipo_lancamento']=='VENDA':
                row['valor_taxa'] += Decimal('0.01')
        refund = next(r for r in close_month(bundle,self.policy,'2026-09').tables['pendencias'] if r['tipo']=='DEVOLUCAO_CONDICAO_COMERCIAL')
        self.assertIn('a menos do que o lojista pagou',refund['motivo'])

    def test_august_reversal_reduces_september_at_the_original_sale_rate(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        trace = next(t for t in result.traces if t['ref_origem']=='TX88444848' and t['id_saida'].startswith('COM-'))
        self.assertEqual(trace['valor'],Decimal('-83.12'))
        self.assertIn('2026-08-22',trace['formula'])

    def test_negative_spreads_are_contested_and_the_repeated_operation_counts_once(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        negative = {r['operation'] for r in self.bundle.remittances if r['spread']<0}
        fx_ids = {r['id_saida'] for r in result.tables['comissoes_por_lojista'] if r['linha_negocio']=='REMESSA'}
        contributions = [t['ref_origem'] for t in result.traces if t['id_saida'] in fx_ids]
        self.assertFalse(negative & set(contributions))
        self.assertEqual(contributions.count('PC-0926-0162'),1)
        ponte = {(c['motivo'],c['ref_origem']) for c in result.contests['PONTE']}
        self.assertTrue({('SPREAD_NEGATIVO',op) for op in negative} <= ponte)
        self.assertIn(('OPERACAO_REPETIDA','PC-0926-0162'),ponte)
        self.assertIn('PC-0926-0002',contributions)

    def test_missing_partner_signature_yields_a_single_pending_item(self):
        bundle = deepcopy(self.bundle)
        bundle.email_body = bundle.email_body.replace('Backoffice Parceiros','Equipe')
        result = close_month(bundle,self.policy,'2026-09')
        self.assertEqual(sum(r['tipo']=='TOMADOR_NAO_IDENTIFICADO' for r in result.tables['pendencias']),1)
        self.assertFalse(any(r['linha_negocio']=='REMESSA' for r in result.tables['notas_a_emitir']))

    def test_only_the_new_merchant_without_history_raises_an_advance_alert(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        alerts = [r['escopo'] for r in result.tables['pendencias'] if r['tipo']=='ALERTA_ANTECIPACAO']
        self.assertEqual(alerts,['1076801732'])

    def test_advance_alert_uses_advances_open_on_the_date(self):
        # HIPOTESES.md D3: a later reversal does not erase the alert; a reversal counts from its own date.
        result = close_month(self.bundle,self.policy,'2026-09')
        alert = next(r for r in result.tables['pendencias'] if r['tipo']=='ALERTA_ANTECIPACAO')
        self.assertEqual(alert['valor_brl'],Decimal('179592.82'))
        self.assertEqual(alert['ref_origem'].split(';'),['AN88445637','AN88445646','AN88445703','AN88445766'])
        self.assertIn(str(alert['valor_brl']),alert['motivo'])
        self.assertIn('Revertidas depois: AN88445637 em 2026-09-17',alert['motivo'])

    def test_partial_and_orphan_reversals_adjust_the_open_advances(self):
        bundle = deepcopy(self.bundle)
        rows = {r['id_transacao']:r for r in bundle.checkout if r['cod_estabelecimento']=='1076801732'}
        rows['AN88446030']['valor_bruto'] = Decimal('-10000.00')
        rows['AN88446517']['valor_bruto'] = Decimal('200000.00')
        rows['AN88446660']['id_referencia'] = 'AN00000000'
        result = close_month(bundle,self.policy,'2026-09')
        alert = next(r for r in result.tables['pendencias'] if r['tipo']=='ALERTA_ANTECIPACAO')
        parts = {t['ref_origem']:t['valor'] for t in result.traces if t['id_saida']==alert['id_saida']}
        self.assertEqual(parts['AN88445637'],Decimal('42361.86'))
        self.assertEqual(parts['AN88446517'],Decimal('200000.00'))
        self.assertEqual(alert['valor_brl'],sum(parts.values()))
        self.assertNotIn('Revertidas depois: AN88445637',alert['motivo'])
        orphan = next(r for r in result.tables['pendencias'] if r['tipo']=='REVERSAO_SEM_ANTECIPACAO')
        self.assertIn('AN00000000',orphan['motivo'])
        self.assertEqual(orphan['valor_brl'],rows['AN88446660']['valor_bruto'])

    def test_irregular_reversals_become_pending_items(self):
        bundle = deepcopy(self.bundle)
        rows = {r['id_transacao']:r for r in bundle.checkout if r['cod_estabelecimento']=='1076801732'}
        rows['AN88446030']['valor_bruto'] = Decimal('-60000.00')
        rows['AN88446660']['valor_bruto'] = Decimal('56350.28')
        result = close_month(bundle,self.policy,'2026-09')
        irregular = {r['ref_origem'] for r in result.tables['pendencias'] if r['tipo']=='REVERSAO_IRREGULAR'}
        self.assertEqual(irregular,{'AN88446030','AN88446660'})

    def test_partial_reversal_after_the_peak_is_described_as_partial(self):
        bundle = deepcopy(self.bundle)
        rows = {r['id_transacao']:r for r in bundle.checkout if r['cod_estabelecimento']=='1076801732'}
        rows['AN88446030']['valor_bruto'] = Decimal('-10000.00')
        result = close_month(bundle,self.policy,'2026-09')
        alert = next(r for r in result.tables['pendencias'] if r['tipo']=='ALERTA_ANTECIPACAO')
        self.assertIn('AN88445637 em 2026-09-17 (parcial, -10000.00)',alert['motivo'])

    def test_report_source_links_stay_inside_the_project(self):
        import re
        html = (ROOT/'saida/index.html').read_text(encoding='utf-8')
        links = re.findall(r'<li><a href="([^"]+)">',html)
        self.assertTrue(links)
        for href in links:
            self.assertFalse(href.startswith(('/','file:')) or ':' in href.split('/')[0],href)
            target = (ROOT/'saida'/href.replace('%20',' ')).resolve()
            self.assertTrue(target.is_relative_to(ROOT.resolve()),href)
            self.assertTrue(target.is_file(),href)

    def test_full_same_day_reversal_is_applied_without_pending_items(self):
        bundle = deepcopy(self.bundle)
        rows = {r['id_transacao']:r for r in bundle.checkout if r['cod_estabelecimento']=='1076801732'}
        rows['AN88446030']['date'] = rows['AN88445637']['date']
        rows['AN88446030']['id_transacao'] = 'AN00000001'
        result = close_month(bundle,self.policy,'2026-09')
        kinds = {r['tipo'] for r in result.tables['pendencias']}
        self.assertFalse({'REVERSAO_SEM_ANTECIPACAO','REVERSAO_IRREGULAR'} & kinds)
        alert = next(r for r in result.tables['pendencias'] if r['tipo']=='ALERTA_ANTECIPACAO')
        # Same day: the four advances are processed before the reversal, so the peak keeps all four open.
        self.assertEqual(alert['valor_brl'],Decimal('179592.82'))
        self.assertIn('Revertidas depois: AN88445637 em 2026-09-15;',alert['motivo'])

    def test_bridge_uses_different_contracts_at_the_date_boundary(self):
        row = deepcopy(next(r for r in self.bundle.checkout if r['cod_estabelecimento']=='1075624862'))
        row['date'] = row['date'].replace(day=14)
        before = select_contract(row,self.bundle.contracts,self.policy)
        row['date'] = row['date'].replace(day=15)
        after = select_contract(row,self.bundle.contracts,self.policy)
        self.assertEqual(before[0]['credit'],Decimal('.0259'))
        self.assertEqual(after[0]['credit'],Decimal('.0219'))

    def test_reordering_records_preserves_commissions_and_output_ids(self):
        reordered = deepcopy(self.bundle)
        reordered.checkout.reverse()
        reordered.remittances.reverse()
        reordered.bank_entries.reverse()
        original = close_month(self.bundle,self.policy,'2026-09')
        changed = close_month(reordered,self.policy,'2026-09')
        for name in ['comissoes_por_lojista','divergencias_taxa','notas_a_emitir','lancamentos_classificados']:
            self.assertEqual(original.tables[name],changed.tables[name])

    def test_conflicting_operation_versions_are_not_selected_by_arrival_order(self):
        bundle = deepcopy(self.bundle)
        conflict = deepcopy(bundle.remittances[4])
        operation = conflict['operation']
        conflict['spread'] += 1
        conflict['_source']['linha_origem'] = 9999
        bundle.remittances.append(conflict)
        result = close_month(bundle,self.policy,'2026-09')
        self.assertTrue(any(p['tipo']=='CONFLITO_DE_VERSAO' and p['escopo']==operation for p in result.tables['pendencias']))
        commission_ids = {r['id_saida'] for r in result.tables['comissoes_por_lojista']}
        self.assertFalse(any(t['id_saida'] in commission_ids and t['ref_origem']==operation for t in result.traces))

    def test_compliance_caveats_do_not_change_the_participation(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        fx_ids = {r['id_saida'] for r in result.tables['comissoes_por_lojista'] if r['linha_negocio']=='REMESSA'}
        contributions = {t['ref_origem'] for t in result.traces if t['id_saida'] in fx_ids}
        caveats = {r['operation'] for r in self.bundle.remittances if r['status']=='APROVADO C/ RESSALVA' and r['spread']>=0}
        self.assertTrue(caveats.issubset(contributions))

    def test_settlement_competence_moves_month_end_operations_out(self):
        policy = deepcopy(self.policy)
        policy['remittance']['competence_event'] = 'settled'
        result = close_month(self.bundle,policy,'2026-09')
        self.assertEqual(result.metrics['remessas_elegiveis'],222)

    def test_unknown_ec_is_not_matched_by_similar_merchant_name(self):
        bundle = deepcopy(self.bundle)
        row = bundle.checkout[0]
        row['cod_estabelecimento'] = '9999999999'
        row['nome_estabelecimento'] = 'Escola Bridge de Idiomas Ltda'
        identity = row['id_transacao']
        result = close_month(bundle,self.policy,'2026-09')
        self.assertTrue(any(p['tipo']=='CADASTRO_OU_CONTRATO_AUSENTE' and p['escopo']=='9999999999' and p['quem_decide']=='Comercial' for p in result.tables['pendencias']))
        commission_ids = {r['id_saida'] for r in result.tables['comissoes_por_lojista']}
        self.assertFalse(any(t['id_saida'] in commission_ids and t['ref_origem']==identity for t in result.traces))

    def test_the_transfer_in_transit_and_unknown_credits_are_pending(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        kinds = {p['tipo'] for p in result.tables['pendencias']}
        self.assertTrue({'CREDITO_NAO_IDENTIFICADO','REPASSE_DEVOLVIDO','LOJISTA_NAO_FATURAR'} <= kinds)
        transfer = [p for p in result.tables['pendencias'] if p['tipo']=='TRANSFERENCIA_EM_TRANSITO']
        self.assertEqual(len(transfer),1)
        self.assertEqual(transfer[0]['ref_origem'],'L92')
        self.assertEqual(transfer[0]['valor_brl'],Decimal('-300000.00'))

    def test_the_calculation_accepts_a_new_month_without_embedded_september_counts(self):
        bundle = deepcopy(self.bundle)
        for row in bundle.checkout:
            row['date'] = row['date'].replace(month=10)
        for row in bundle.remittances:
            row['contracted'] = row['contracted'].replace(month=row['contracted'].month+1)
            row['settled'] = row['settled'].replace(month=row['settled'].month+1)
        for row in bundle.bank_entries:
            row['date'] = row['date'].replace(month=10)
        result = close_month(bundle,self.policy,'2026-10')
        self.assertEqual(result.metrics['periodo'],'2026-10')
        self.assertEqual(result.metrics['remessas_elegiveis'],228)
        self.assertEqual(result.metrics['movimentos_bancarios_exportados'],184)
        self.assertTrue(all(r['data'].startswith('2026-10-') for r in result.tables['lancamentos_classificados']))

    def test_unknown_columns_and_missing_amounts_fail_instead_of_disappearing(self):
        path = next((ROOT/'Tarvo_Data_Pack_set2026').glob('01_*.csv'))
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        with TemporaryDirectory() as directory:
            altered = Path(directory)/'checkout.csv'
            altered.write_text(lines[0]+';unknown\n'+lines[1]+';unexpected\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'columns'):
                read_checkout(altered)
            cells = lines[1].split(';')
            cells[10] = ''
            altered.write_text(lines[0]+'\n'+';'.join(cells)+'\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'numeric'):
                read_checkout(altered)

    def test_running_balance_corruption_is_rejected(self):
        path = next((ROOT/'Tarvo_Data_Pack_set2026').glob('05a_*.csv'))
        content = path.read_text(encoding='utf-8-sig').replace('66.026,00','66.027,00',1)
        with TemporaryDirectory() as directory:
            altered = Path(directory)/'bank.csv'
            altered.write_text(content,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'balance mismatch'):
                read_aurora(altered)

    def test_synthetic_accounts_and_unsupported_policy_modes_are_rejected(self):
        policy = deepcopy(self.policy)
        policy['bank_rules'][0]['account'] = '1'
        with self.assertRaisesRegex(ValueError,'Invalid posting account'):
            close_month(self.bundle,policy,'2026-09')
        policy = deepcopy(self.policy)
        policy['schema_version'] = 1
        with self.assertRaisesRegex(ValueError,'version 2 policy'):
            close_month(self.bundle,policy,'2026-09')
        policy = deepcopy(self.policy)
        policy['commercial_conditions'][0]['evidence'] = ' '
        with self.assertRaisesRegex(ValueError,'evidence'):
            close_month(self.bundle,policy,'2026-09')
        with self.assertRaisesRegex(ValueError,'YYYY-MM'):
            close_month(self.bundle,self.policy,'2026-9')

    def test_saved_csvs_reconcile_to_their_traces_and_reruns_do_not_overwrite(self):
        result = close_month(self.bundle,self.policy,'2026-09')
        with TemporaryDirectory() as directory:
            output = Path(directory)/'closing'
            first = publish_result(self.bundle,result,self.policy,'2026-09',output)
            second = publish_result(self.bundle,result,self.policy,'2026-09',output)
            self.assertEqual(first,second)
            def read(name):
                with (output/(name+'.csv')).open(encoding='utf-8') as stream:
                    return list(csv.DictReader(stream,delimiter=';'))
            trace_totals = {}
            for trace in read('rastro'):
                trace_totals[trace['id_saida']] = trace_totals.get(trace['id_saida'],Decimal(0))+Decimal(trace['valor'])
            for name,column in [('comissoes_por_lojista','comissao_brl'),('divergencias_taxa','diferenca_brl'),('notas_a_emitir','valor_brl'),('lancamentos_classificados','valor'),('pendencias','valor_brl')]:
                for row in read(name):
                    if row[column] != '':
                        self.assertEqual(Decimal(row[column]),trace_totals[row['id_saida']])
            for name,digest in first['output_sha256'].items():
                self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(),digest)
            original = (output/'comissoes_por_lojista.csv').read_bytes()
            altered_policy = deepcopy(self.policy)
            altered_policy['remittance']['competence_event'] = 'settled'
            changed = close_month(self.bundle,altered_policy,'2026-09')
            with self.assertRaisesRegex(ValueError,'No files were overwritten'):
                publish_result(self.bundle,changed,altered_policy,'2026-09',output)
            self.assertEqual((output/'comissoes_por_lojista.csv').read_bytes(),original)

    def test_the_public_command_creates_all_required_outputs(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)/'first-run'
            completed = subprocess.run([sys.executable,str(ROOT/'run_engine.py'),'--input',str(ROOT/'Tarvo_Data_Pack_set2026'),'--policy',str(ROOT/'config/closing-policy.json'),'--period','2026-09','--output',str(output)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr)
            self.assertIn('Closing saved',completed.stdout)
            for name in ['comissoes_por_lojista','divergencias_taxa','notas_a_emitir','lancamentos_classificados','pendencias','rastro']:
                self.assertTrue((output/(name+'.csv')).is_file())
            self.assertTrue((output/'index.html').is_file())
            self.assertTrue((output/'contestacoes/rascunho_ponte.txt').is_file())
            manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
            self.assertTrue(manifest['slack_read'])
            self.assertNotIn(str(ROOT),json.dumps(manifest))

    def test_the_original_zip_requires_no_manual_extraction(self):
        with TemporaryDirectory() as directory:
            zipped = Path(directory)/'pack.zip'
            with ZipFile(zipped,'w') as stream:
                for path in sorted((ROOT/'Tarvo_Data_Pack_set2026').glob('0*')):
                    stream.write(path,path.name)
            archive = read_inputs(zipped)
        folder_result = close_month(self.bundle,self.policy,'2026-09')
        archive_result = close_month(archive,self.policy,'2026-09')
        self.assertEqual(folder_result.tables,archive_result.tables)
        with TemporaryDirectory() as directory:
            output = Path(directory)/'archive-closing'
            publish_result(archive,archive_result,self.policy,'2026-09',output)
            self.assertTrue((output/'anexos/03_email_ponte_cambio_relatorio_set2026.eml').is_file())
            self.assertEqual((output/'anexos/01_orbe_relatorio_comissoes_set2026.csv').read_bytes(),(ROOT/'Tarvo_Data_Pack_set2026/01_orbe_relatorio_comissoes_set2026.csv').read_bytes())

    def test_archive_paths_cannot_escape_the_input_directory(self):
        with TemporaryDirectory() as directory:
            archive = Path(directory)/'unsafe.zip'
            with ZipFile(archive,'w') as stream:
                stream.writestr('../outside.csv','content')
            with self.assertRaisesRegex(ValueError,'flat filenames'):
                read_inputs(archive)


if __name__ == '__main__':
    unittest.main()
