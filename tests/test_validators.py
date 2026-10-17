from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.closing import bank_rule_for, close_month
from tarvo_close.exceptions import CLASSES, ClosingException
from tarvo_close.readers import read_inputs
from tarvo_close.validators import ACTIONS, VALIDATORS, check_evidence, check_schema, check_shape, known_pairs, load_schema, source_line, validator_for


def proposal(excecao_id='PEN-X', classe='MOVIMENTO_SEM_REGRA', acao='CLASSIFICAR_CONTA', parametros=None, evidencias=None):
    return {'excecao_id':excecao_id, 'classe':classe, 'acao':acao,
            'parametros':{'conta_codigo':'4.2.01'} if parametros is None else parametros,
            'evidencias':[{'arquivo':'a.csv','ref':'L1','trecho':'x'}] if evidencias is None else evidencias,
            'justificativa':'teste', 'requer_humano':False}


def synthetic(refs, excecao_id='PEN-X'):
    return ClosingException(excecao_id,'MOVIMENTO_SEM_REGRA','CONCILIACAO_BANCARIA','AURORA:L1','Helena','motivo','conta',None,refs)


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = load_schema()

    def test_valid_proposal_passes(self):
        self.assertEqual(check_schema(proposal(),self.schema),[])
        self.assertEqual(check_schema(proposal(acao='ENCAMINHAR_HUMANO',parametros={}),self.schema),[])

    def test_invalid_proposals_fail(self):
        extra = proposal()
        extra['valor'] = 1
        wrong_type = proposal()
        wrong_type['requer_humano'] = 'false'
        for bad in (proposal(acao='APROVAR'), extra, proposal(evidencias=[]), wrong_type,
                    proposal(classe='DECISAO'), proposal(classe='DECISAO',acao='CLASSIFICAR_CONTA')):
            self.assertTrue(check_schema(bad,self.schema),bad)

    def test_actions_table_comes_from_the_schema(self):
        self.assertEqual(set(ACTIONS),set(CLASSES))
        self.assertEqual(ACTIONS['MOVIMENTO_SEM_REGRA']['CLASSIFICAR_CONTA'],['conta_codigo'])
        self.assertEqual(ACTIONS['MOVIMENTO_SEM_REGRA']['ENCAMINHAR_HUMANO'],[])
        self.assertEqual(ACTIONS['DECISAO'],{'ENCAMINHAR_HUMANO':[]})


class ShapeTests(unittest.TestCase):
    def test_shape(self):
        item = synthetic([])
        self.assertEqual(check_shape(proposal(),item),[])
        self.assertTrue(check_shape(proposal(excecao_id='PEN-OUTRO'),item))
        self.assertTrue(check_shape(proposal(parametros={}),item))
        self.assertTrue(check_shape(proposal(acao='ENCAMINHAR_HUMANO'),item))
        self.assertTrue(check_shape(proposal(classe='DECISAO',acao='ENCAMINHAR_HUMANO',parametros={}),item))


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
        cls.bundle = read_inputs(ROOT/'Tarvo_Data_Pack_set2026')
        cls.result = close_month(cls.bundle,cls.policy,'2026-09')

    def test_every_ref_of_every_september_exception_resolves(self):
        refs = [ref for item in self.result.exceptions for ref in item.refs]
        self.assertTrue(refs)
        for ref in refs:
            self.assertTrue(source_line(self.bundle,ref).strip(),ref)

    def test_transfer_in_transit_contains_the_movement_description(self):
        transfer = next(item for item in self.result.exceptions if item.tipo=='TRANSFERENCIA_EM_TRANSITO')
        entry = next(e for e in self.bundle.bank_entries if e['_source']['ref_origem']==transfer.refs[0]['ref'] and e['bank']=='AURORA')
        self.assertIn(entry['description'],source_line(self.bundle,transfer.refs[0]))

    def test_ofx_block_contains_the_memo(self):
        entry = next(e for e in self.bundle.bank_entries if e['bank']=='MERIDIANO')
        name = entry['_source']['arquivo_origem']
        self.assertTrue(name.startswith('05b_'))
        text = source_line(self.bundle,{'arquivo':name,'aba':'','ref':entry['_source']['ref_origem'],'linha':entry['_source']['linha_origem']})
        self.assertIn(entry['description'],text)
        self.assertIn(entry['_source']['ref_origem'],text)

    def test_xlsx_attachment_row_contains_the_operation_number(self):
        source = self.bundle.remittances[0]['_source']
        text = source_line(self.bundle,{'arquivo':source['arquivo_origem'],'aba':source['aba_origem'],'ref':source['ref_origem'],'linha':source['linha_origem']})
        self.assertIn(source['ref_origem'],text)
        self.assertIn(';',text)

    def test_xlsx_path_source_and_unknown_sheet(self):
        source = self.bundle.contracts[0]['_source']
        ref = {'arquivo':source['arquivo_origem'],'aba':source['aba_origem'],'ref':source['ref_origem'],'linha':source['linha_origem']}
        self.assertIn(self.bundle.contracts[0]['cnpj'][:8],source_line(self.bundle,ref).replace('.','').replace('/',''))
        with self.assertRaises(ValueError):
            source_line(self.bundle,{**ref,'aba':'Inexistente'})

    def test_missing_source_or_line_raises(self):
        with self.assertRaises(ValueError):
            source_line(self.bundle,{'arquivo':'nao_existe.csv','aba':'','ref':'L1','linha':1})
        with self.assertRaises(ValueError):
            source_line(self.bundle,{'arquivo':next(n for n in self.bundle.sources if n.startswith('05a_')),'aba':'','ref':'L1','linha':99999})


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        policy = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
        cls.bundle = read_inputs(ROOT/'Tarvo_Data_Pack_set2026')
        close_month(cls.bundle,policy,'2026-09')
        cls.entry = next(e for e in cls.bundle.bank_entries if e['bank']=='AURORA')
        source = cls.entry['_source']
        cls.ref = {'arquivo':source['arquivo_origem'],'aba':'','ref':source['ref_origem'],'linha':source['linha_origem']}
        cls.item = synthetic([cls.ref])

    def evidence(self, **changes):
        data = {'arquivo':self.ref['arquivo'],'ref':self.ref['ref'],'trecho':self.entry['description']}
        data.update(changes)
        return proposal(evidencias=[data])

    def test_literal_snippet_passes(self):
        self.assertEqual(check_evidence(self.evidence(),self.item,self.bundle),[])
        self.assertEqual(check_evidence(self.evidence(trecho=self.entry['description'][:6]),self.item,self.bundle),[])

    def test_invalid_evidence_fails(self):
        for changes in ({'trecho':'TRECHO QUE NAO EXISTE'}, {'ref':'L999999'}, {'arquivo':'05b_outro.ofx'}, {'trecho':''}, {'trecho':'   '}):
            self.assertTrue(check_evidence(self.evidence(**changes),self.item,self.bundle),changes)
        self.assertTrue(check_evidence(proposal(evidencias=[]),self.item,self.bundle))

    def test_masked_snippet_passes(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'extrato.csv'
            path.write_text('cabecalho\n01/09/2026;PIX CONTA 12345-6 FULANO;100\n',encoding='utf-8')
            bundle = SimpleNamespace(sources={'extrato.csv':{'path':str(path)}},attachments={})
            ref = {'arquivo':'extrato.csv','aba':'','ref':'L2','linha':2}
            item = synthetic([ref])
            def run(snippet):
                return check_evidence(proposal(evidencias=[{'arquivo':'extrato.csv','ref':'L2','trecho':snippet}]),item,bundle)
            self.assertEqual(run('CONTA 12345-6'),[])
            self.assertEqual(run('CONTA *****-*'),[])
            self.assertTrue(run('CONTA 99999-9'))

    def test_same_file_and_ref_in_two_sheets_matches_any_candidate(self):
        from openpyxl import Workbook
        with TemporaryDirectory() as directory:
            path = Path(directory)/'duas.xlsx'
            workbook = Workbook()
            workbook.active.title = 'A'
            workbook['A'].append(['primeira aba'])
            workbook.create_sheet('B').append(['segunda aba UNICA'])
            workbook.save(path)
            workbook.close()
            bundle = SimpleNamespace(sources={'duas.xlsx':{'path':str(path)}},attachments={})
            item = synthetic([{'arquivo':'duas.xlsx','aba':'A','ref':'R1','linha':1},{'arquivo':'duas.xlsx','aba':'B','ref':'R1','linha':1}])
            def run(snippet):
                return check_evidence(proposal(evidencias=[{'arquivo':'duas.xlsx','ref':'R1','trecho':snippet}]),item,bundle)
            self.assertEqual(run('segunda aba UNICA'),[])
            self.assertEqual(run('primeira aba'),[])
            self.assertTrue(run('nenhuma'))

    def test_zip_input_reads_from_attachments(self):
        import zipfile
        with TemporaryDirectory() as directory:
            archive = Path(directory)/'pacote.zip'
            with zipfile.ZipFile(archive,'w') as handle:
                for path in sorted((ROOT/'Tarvo_Data_Pack_set2026').iterdir()):
                    if path.is_file():
                        handle.write(path,path.name)
            bundle = read_inputs(archive)
        self.assertEqual(check_evidence(self.evidence(),self.item,bundle),[])


class ValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = EvidenceTests
        EvidenceTests.setUpClass()

    def test_registry(self):
        self.assertIn('MOVIMENTO_SEM_REGRA',VALIDATORS)
        self.assertIsNone(validator_for('DECISAO'))
        self.assertEqual(validator_for('MOVIMENTO_SEM_REGRA').classe,'MOVIMENTO_SEM_REGRA')

    def build(self, trecho):
        ref = EvidenceTests.ref
        return proposal(evidencias=[{'arquivo':ref['arquivo'],'ref':ref['ref'],'trecho':trecho}])

    def test_context_without_closing_policy_stops_at_movimento(self):
        for context in ({}, {'versao':1,'classes':{}}):
            outcome = validator_for('MOVIMENTO_SEM_REGRA').validate(self.build(EvidenceTests.entry['description']),EvidenceTests.item,EvidenceTests.bundle,context)
            self.assertFalse(outcome['ok'])
            self.assertEqual([(c['check'],c['status']) for c in outcome['checks']],[('schema','PASS'),('evidencia','PASS'),('movimento','FAIL')])
            self.assertIn('closing_policy',outcome['checks'][-1]['reason'])

    def test_invalid_evidence_stops_before_the_class_check(self):
        outcome = validator_for('MOVIMENTO_SEM_REGRA').validate(self.build('TRECHO QUE NAO EXISTE'),EvidenceTests.item,EvidenceTests.bundle,{})
        self.assertFalse(outcome['ok'])
        self.assertEqual([(c['check'],c['status']) for c in outcome['checks']],[('schema','PASS'),('evidencia','FAIL')])

    def test_invalid_shape_stops_at_schema(self):
        bad = self.build(EvidenceTests.entry['description'])
        bad['excecao_id'] = 'PEN-OUTRO'
        outcome = validator_for('MOVIMENTO_SEM_REGRA').validate(bad,EvidenceTests.item,EvidenceTests.bundle,{})
        self.assertEqual([(c['check'],c['status']) for c in outcome['checks']],[('schema','FAIL')])


CHECKS = ['schema','evidencia','movimento','evidencia_descricao','conta','par_conhecido','nao_provisao','nao_disponibilidade']


class MovimentoSemRegraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
        cls.bundle = read_inputs(ROOT/'Tarvo_Data_Pack_set2026')
        close_month(cls.bundle,cls.policy,'2026-09')
        cls.context = {'closing_policy':cls.policy,'accounts':cls.bundle.accounts}
        cls.validator = validator_for('MOVIMENTO_SEM_REGRA')
        cls.fee = next(e for e in cls.bundle.bank_entries if e['bank']=='AURORA' and e['description'].startswith('TAR PACOTE SERVICOS'))
        cls.credit = next(e for e in cls.bundle.bank_entries if e['bank']=='AURORA' and e['amount']>0)

    def build(self, entry=None, conta='4.2.01', trecho='TAR PACOTE SERVICOS', scope=None, refs=None):
        entry = entry or self.fee
        source = entry['_source']
        ref = {'arquivo':source['arquivo_origem'],'aba':'','ref':source['ref_origem'],'linha':source['linha_origem']}
        item = ClosingException('PEN-X','MOVIMENTO_SEM_REGRA','CONCILIACAO_BANCARIA',scope or f'{entry["bank"]}:{source["ref_origem"]}','Helena','motivo','conta',None,[ref] if refs is None else refs)
        data = proposal(parametros={'conta_codigo':conta},evidencias=[{'arquivo':ref['arquivo'],'ref':ref['ref'],'trecho':trecho}])
        return data, item

    def run_case(self, **kwargs):
        data, item = self.build(**kwargs)
        return self.validator.validate(data,item,self.bundle,self.context)

    def failed(self, outcome):
        self.assertFalse(outcome['ok'],outcome)
        self.assertEqual(outcome['checks'][-1]['status'],'FAIL')
        return outcome['checks'][-1]['check']

    def test_valid_proposal_passes_every_check_in_order(self):
        outcome = self.run_case()
        self.assertTrue(outcome['ok'],outcome)
        self.assertEqual([c['check'] for c in outcome['checks']],CHECKS)
        self.assertTrue(all(c['status']=='PASS' for c in outcome['checks']))

    def test_movimento(self):
        ref = self.build()[1].refs[0]
        self.assertEqual(self.failed(self.run_case(scope='SEM-DOIS-PONTOS')),'movimento')
        self.assertEqual(self.failed(self.run_case(scope='MERIDIANO:'+ref['ref'])),'movimento')
        self.assertEqual(self.failed(self.run_case(scope='AURORA:L99999')),'movimento')
        self.assertEqual(self.failed(self.run_case(refs=[ref,ref])),'movimento')

    def test_evidencia_descricao(self):
        # the amount is in the CSV line (so it passes the generic evidence check) but not in the description
        amount = '389,00'
        self.assertIn(amount,source_line(self.bundle,self.build()[1].refs[0]))
        for snippet in ('TA',amount):
            self.assertEqual(self.failed(self.run_case(trecho=snippet)),'evidencia_descricao',snippet)
        self.assertTrue(self.run_case(trecho='SERVICOS')['ok'])

    def test_conta(self):
        accounts = self.bundle.accounts
        self.assertEqual(accounts['1.1']['TIPO'],'SINTETICA')
        for code in ('9.9.99','1.1'):
            self.assertEqual(self.failed(self.run_case(conta=code)),'conta',code)
        no_posting = next((code for code,a in accounts.items() if a['TIPO']=='ANALITICA' and a['ACEITA_LANCTO']!='S'),None)
        if no_posting:
            self.assertEqual(self.failed(self.run_case(conta=no_posting)),'conta')
        self.assertTrue(self.run_case(conta='4.2.06')['ok'])

    def test_par_conhecido(self):
        self.assertEqual(self.failed(self.run_case(conta='3.2.01')),'par_conhecido')
        credit = self.credit['description']
        self.assertEqual(self.failed(self.run_case(entry=self.credit,conta='4.2.01',trecho=credit)),'par_conhecido')
        self.assertTrue(self.run_case(entry=self.credit,conta='3.2.01',trecho=credit)['ok'])

    def test_nao_provisao(self):
        for code in ('2.1.03.001','2.1.04.001'):
            self.assertEqual(self.failed(self.run_case(conta=code)),'nao_provisao',code)

    def test_nao_disponibilidade(self):
        for code in ('1.1.01.001','1.1.09.001'):
            self.assertEqual(self.failed(self.run_case(conta=code)),'nao_disponibilidade',code)

    def test_known_pairs_of_september(self):
        pairs = known_pairs(self.bundle,self.policy)
        self.assertIn(('-','4'),pairs)
        self.assertIn(('+','1'),pairs)
        self.assertNotIn(('+','4'),pairs)

    def test_known_pairs_follow_the_policy(self):
        policy = {**self.policy,'bank_rules':[r for r in self.policy['bank_rules'] if r['account'].split('.')[0]!='4']}
        self.assertNotIn(('-','4'),known_pairs(self.bundle,policy))

    def test_known_pairs_ignore_movements_outside_the_period(self):
        from datetime import date
        extra = {**self.credit,'date':date(2026,10,5),'description':'TAR PACOTE OUTUBRO','amount':self.credit['amount']}
        extra['_source'] = {**self.credit['_source'],'ref_origem':'L9999'}
        policy = {**self.policy,'bank_rules':[r for r in self.policy['bank_rules'] if r['account'].split('.')[0]!='4' or r['id']=='bank-fees']}
        bundle = SimpleNamespace(bank_entries=[extra])
        self.assertIn(('+','4'),known_pairs(bundle,policy))
        self.assertNotIn(('+','4'),known_pairs(bundle,policy,'2026-09'))
        self.assertIn(('+','4'),known_pairs(bundle,policy,'2026-10'))
        outcome = self.validator.validate(*self.build(entry=self.credit,conta='4.2.01',trecho=self.credit['description']),self.bundle,{**self.context,'period':'2026-09'})
        self.assertEqual(self.failed(outcome),'par_conhecido')

    def test_bank_rule_for_matches_the_versioned_csv(self):
        import csv
        with open(ROOT/'saida/lancamentos_classificados.csv',encoding='utf-8-sig',newline='') as handle:
            rows = {(r['banco'],r['ref_origem']):r['regra_id'] for r in csv.DictReader(handle,delimiter=';')}
        self.assertEqual(len(rows),184)
        for entry in self.bundle.bank_entries:
            rule = bank_rule_for(self.policy,entry)
            self.assertEqual(rule['id'] if rule else '',rows[(entry['bank'],entry['_source']['ref_origem'])])


if __name__ == '__main__':
    unittest.main()
