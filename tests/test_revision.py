from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import json
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(Path(__file__).resolve().parent))

from tarvo_close.audit import AuditLog
from tarvo_close.closing import close_month
from tarvo_close.domain import identifier
from tarvo_close.inference import apply_proposal, run_inference
from tarvo_close.inference_policy import effective_mode, load_inference_policy
from tarvo_close.readers import read_inputs
from tarvo_close.resolver import FakeResolver, TokenBudget
from test_cli_inference import PACK, VOLATILE, files, run, same_bytes
from test_exceptions import copy_pack

CLOSING_POLICY = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
NO_FEES = deepcopy(CLOSING_POLICY)
NO_FEES['bank_rules'] = [rule for rule in NO_FEES['bank_rules'] if rule['id'] != 'bank-fees']
MSR = 'MOVIMENTO_SEM_REGRA'
AUTOMATIC = {'modo':'automatico', 'teto':'automatico', 'aprovado_por':'Helena', 'aprovado_em':'2026-10-17', 'criterio':{'casos_seguidos_sem_erro':35, 'erros':0, 'backtest_versao':'t', 'data':'2026-10-17'}, 'confianca':'0.90'}


def inference_policy(mode, confidence=None):
    data = json.loads((ROOT/'config/inference-policy.json').read_text(encoding='utf-8'))
    entry = data['classes'][MSR]
    if mode == 'automatico':
        entry.update(deepcopy(AUTOMATIC))
        entry['confianca'] = confidence
    else:
        entry.update(modo=mode, confianca=confidence)
    return data


def read_csv(directory, name):
    with open(Path(directory)/f'{name}.csv',encoding='utf-8',newline='') as handle:
        return list(csv.DictReader(handle,delimiter=';'))


def read_audit(directory):
    return [json.loads(line) for line in (Path(directory)/'auditoria.jsonl').read_text(encoding='utf-8').splitlines()]


class RevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.policy_path = cls.root/'closing-policy.json'
        cls.policy_path.write_text(json.dumps(NO_FEES),encoding='utf-8')
        cls.bundle = read_inputs(PACK)
        result = close_month(cls.bundle,NO_FEES,'2026-09')
        cls.movements = [e.as_dict() for e in result.exceptions if e.classe == MSR]
        cls.others = [e.as_dict() for e in result.exceptions if e.classe == 'DECISAO']
        entries = {f'{e["bank"]}:{e["_source"]["ref_origem"]}':e for e in cls.bundle.bank_entries}
        cls.responses = {m['excecao_id']:cls.proposal(m,entries[m['escopo']]['description']) for m in cls.movements}
        cls.base = cls.root/'base'
        code, _, _ = run(cls.base,'--policy',str(cls.policy_path),'--no-llm')
        assert code == 0
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def proposal(movement, trecho, conta='4.2.01'):
        ref = movement['refs'][0]
        return {'excecao_id':movement['excecao_id'], 'classe':MSR, 'acao':'CLASSIFICAR_CONTA', 'parametros':{'conta_codigo':conta},
                'evidencias':[{'arquivo':ref['arquivo'], 'ref':ref['ref'], 'trecho':trecho}], 'justificativa':'tarifa bancária', 'requer_humano':False}

    def path(self, name):
        return self.root/name

    def policy_file(self, mode, confidence=None):
        type(self).counter += 1
        path = self.root/f'inference-{self.counter}.json'
        path.write_text(json.dumps(inference_policy(mode,confidence)),encoding='utf-8')
        return path

    def layer(self, name, mode, confidence=None, resolver=None, *extra):
        resolver = resolver or FakeResolver(self.responses)
        code, out, err = run(self.path(name),'--policy',str(self.policy_path),'--inference-policy',str(self.policy_file(mode,confidence)),
                             '--cache-dir',str(self.path('cache-'+name)),*extra,resolver=resolver)
        self.assertEqual(code,0,err)
        return resolver, out, err

    def decisions(self, name, *items):
        path = self.path(name+'.json')
        path.write_text(json.dumps(list(items)),encoding='utf-8')
        return str(path)

    def decision(self, movement, decision='aprovar', **extra):
        return {'excecao_id':movement['excecao_id'], 'decisao':decision, 'decidido_por':'Helena', 'motivo':'confere com o extrato', **extra}

    def revise(self, name, parent, mode, confidence, *items, expected=0):
        code, out, err = run(self.path(name),'--policy',str(self.policy_path),'--inference-policy',str(self.policy_file(mode,confidence)),
                             '--decisoes',self.decisions(name,*items),'--revisao-de',str(self.path(parent)))
        self.assertEqual(code,expected,err)
        return out, err

    def row(self, directory, table, id_saida):
        return next(r for r in read_csv(directory,table) if r['id_saida'] == id_saida)

    def assert_numbers_unchanged(self, directory):
        for name in ('comissoes_por_lojista','divergencias_taxa','notas_a_emitir','cobertura'):
            self.assertEqual((self.base/f'{name}.csv').read_bytes(),(self.path(directory)/f'{name}.csv').read_bytes(),name)
        before = {r['id_saida']:r['valor'] for r in read_csv(self.base,'lancamentos_classificados')}
        after = {r['id_saida']:r['valor'] for r in read_csv(self.path(directory),'lancamentos_classificados')}
        self.assertEqual(before,after)

    def test_setup_has_four_movements_without_rule(self):
        self.assertEqual(len(self.movements),4)
        self.assertTrue(self.others)

    def test_sombra_validates_and_applies_nothing(self):
        self.layer('sombra','sombra')
        same_bytes(self,self.base,self.path('sombra'),VOLATILE|{'auditoria.jsonl'})
        events = [e for e in read_audit(self.path('sombra')) if e['evento'] == 'EXCECAO' and e['classe'] == MSR]
        self.assertEqual(len(events),4)
        for event in events:
            self.assertEqual((event['resultado'],event['modo'],event['aplicada']),('VALIDADA','sombra',False))
        self.assertFalse(any(r['metodo'] == 'IA' for r in read_csv(self.path('sombra'),'lancamentos_classificados')))

    def approve(self, name, confidence):
        self.layer(name+'-parent','sugerir',confidence)
        same_bytes(self,self.base,self.path(name+'-parent'),VOLATILE|{'auditoria.jsonl'})
        movement = self.movements[0]
        out, _ = self.revise(name,name+'-parent','sugerir',confidence,self.decision(movement))
        return movement, out

    def test_sugerir_then_aprovar_applies_the_line(self):
        for confidence, expected in ((None,''), ('0.90','0.90')):
            with self.subTest(confidence=confidence):
                name = f'sug-{expected or "null"}'
                movement, out = self.approve(name,confidence)
                ban = identifier('BAN',movement['escopo'])
                line = self.row(self.path(name),'lancamentos_classificados',ban)
                before = self.row(self.base,'lancamentos_classificados',ban)
                self.assertEqual((line['metodo'],line['conta_codigo'],line['confianca'],line['status'],line['regra_id']),('IA','4.2.01',expected,'SUGERIDO',''))
                self.assertEqual(line['conta_descricao'],self.bundle.accounts['4.2.01']['DESCRICAO'])
                self.assertEqual(line['valor'],before['valor'])
                pending = self.row(self.path(name),'pendencias',movement['excecao_id'])
                self.assertEqual(pending['status'],'RESOLVIDA')
                self.assertEqual(self.row(self.base,'pendencias',movement['excecao_id'])['status'],'PENDENTE')
                trace = self.row(self.path(name),'rastro',ban)
                self.assertIn('; evidência IA: ',trace['formula'])
                self.assertEqual(trace['valor'],before['valor'])
                parent_run = json.loads((self.path(name+'-parent')/'manifest.json').read_text(encoding='utf-8'))['run_id']
                manifest = json.loads((self.path(name)/'manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['revisao']['run_id_pai'],parent_run)
                self.assertIn('-rev1-',manifest['run_id'])
                self.assertNotIn('revisao',json.loads((self.path(name+'-parent')/'manifest.json').read_text(encoding='utf-8')))
                self.assertIn(f'Revision rev-1 of {parent_run}: 1 applied, 0 recorded, 0 refused',out)
                events = read_audit(self.path(name))
                self.assertEqual(events[0]['evento'],'REVISAO')
                self.assertEqual((events[0]['run_id_pai'],events[0]['numero']),(parent_run,1))
                own = [e for e in events if e['evento'] == 'DECISAO_APLICADA' and not e.get('herdado')]
                self.assertEqual([(e['decidido_por'],e['motivo'],e['resultado']) for e in own],[('Helena','confere com o extrato','APLICADA')])
                self.assertEqual(events[1],own[0])
                self.assert_numbers_unchanged(name)
                self.assert_ia_rows_have_evidence_and_event(name)

    def assert_ia_rows_have_evidence_and_event(self, name):
        directory = self.path(name)
        events = read_audit(directory)
        backed = {e['excecao_id'] for e in events if e['evento'] == 'DECISAO_APLICADA' and e['resultado'] == 'APLICADA'}
        backed |= {e['excecao_id'] for e in events if e['evento'] == 'EXCECAO' and e['resultado'] == 'VALIDADA' and e['aplicada']}
        pending_by_ban = {identifier('BAN',m['escopo']):m['excecao_id'] for m in self.movements}
        ia = [r for r in read_csv(directory,'lancamentos_classificados') if r['metodo'] == 'IA']
        self.assertTrue(ia)
        for row in ia:
            self.assertIn('evidência IA',self.row(directory,'rastro',row['id_saida'])['formula'])
            self.assertIn(pending_by_ban[row['id_saida']],backed)

    def test_automatico_applies_without_a_decision(self):
        with self.assertRaises(ValueError):  # no measured confidence: the loader refuses
            path = self.path('no-confidence.json')
            path.write_text(json.dumps(inference_policy('automatico')),encoding='utf-8')
            load_inference_policy(path)
        resolver, out, _ = self.layer('auto','automatico','0.90')
        events = [e for e in read_audit(self.path('auto')) if e['evento'] == 'EXCECAO' and e['classe'] == MSR]
        self.assertEqual([(e['resultado'],e['aplicada']) for e in events],[('VALIDADA',True)]*4)
        rows = [r for r in read_csv(self.path('auto'),'lancamentos_classificados') if r['metodo'] == 'IA']
        self.assertEqual({(r['conta_codigo'],r['confianca'],r['status']) for r in rows},{('4.2.01','0.90','SUGERIDO')})
        self.assertEqual({r['status'] for r in read_csv(self.path('auto'),'pendencias') if r['id_saida'] in self.responses},{'RESOLVIDA'})
        self.assertIn('4 applied',out)
        self.assert_numbers_unchanged('auto')
        self.assert_ia_rows_have_evidence_and_event('auto')

    def test_automatico_without_confidence_fails_in_the_cli(self):
        code, _, err = run(self.path('auto-fail'),'--policy',str(self.policy_path),'--inference-policy',str(self.policy_file('automatico')),
                           '--cache-dir',str(self.path('c')),resolver=FakeResolver(self.responses))
        self.assertEqual(code,1)
        self.assertIn('Closing failed',err)

    def test_editar(self):
        self.layer('edit-parent','sugerir')
        movement = self.movements[1]
        ban = identifier('BAN',movement['escopo'])
        self.revise('edit-ok','edit-parent','sugerir',None,self.decision(movement,'editar',parametros={'conta_codigo':'4.2.06'}))
        line = self.row(self.path('edit-ok'),'lancamentos_classificados',ban)
        self.assertEqual((line['metodo'],line['conta_codigo'],line['conta_descricao']),('IA','4.2.06',self.bundle.accounts['4.2.06']['DESCRICAO']))
        self.assertIn('4.2.06',[e for e in read_audit(self.path('edit-ok')) if e['evento'] == 'DECISAO_APLICADA'][0]['proposta']['parametros']['conta_codigo'])
        self.assert_ia_rows_have_evidence_and_event('edit-ok')
        _, err = self.revise('edit-bad','edit-parent','sugerir',None,self.decision(movement,'editar',parametros={'conta_codigo':'2.1.03.001'}))
        self.assertIn('nao_provisao',err)
        self.assertEqual(self.row(self.path('edit-bad'),'lancamentos_classificados',ban)['metodo'],'REGRA')
        self.assertEqual(self.row(self.path('edit-bad'),'pendencias',movement['excecao_id'])['status'],'PENDENTE')
        event = [e for e in read_audit(self.path('edit-bad')) if e['evento'] == 'DECISAO_APLICADA'][0]
        self.assertEqual(event['resultado'],'RECUSADA')
        self.assertEqual(next(c for c in event['verificacoes'] if c['status'] == 'FAIL')['check'],'nao_provisao')
        self.assert_numbers_unchanged('edit-bad')
        self.revise('edit-none','edit-parent','sugerir',None,self.decision(movement,'editar'),expected=1)

    def test_rejeitar(self):
        self.layer('rej-parent','sugerir')
        movement = self.movements[2]
        self.revise('rej','rej-parent','sugerir',None,self.decision(movement,'rejeitar'))
        self.assertEqual(self.row(self.path('rej'),'pendencias',movement['excecao_id'])['status'],'REJEITADA')
        line = self.row(self.path('rej'),'lancamentos_classificados',identifier('BAN',movement['escopo']))
        self.assertEqual((line['metodo'],line['conta_codigo']),('REGRA',''))
        self.assertEqual([e['resultado'] for e in read_audit(self.path('rej')) if e['evento'] == 'DECISAO_APLICADA'],['REGISTRADA'])
        self.assert_numbers_unchanged('rej')

    def test_classes_without_proposal_are_only_recorded(self):
        self.layer('dec-parent','sugerir')
        target = self.others[0]
        out, _ = self.revise('dec-ok','dec-parent','sugerir',None,self.decision(target))
        self.assertEqual(self.row(self.path('dec-ok'),'pendencias',target['excecao_id'])['status'],'APROVADA')
        self.assertIn('0 applied, 1 recorded, 0 refused',out)
        self.assertEqual((self.base/'lancamentos_classificados.csv').read_bytes(),(self.path('dec-ok')/'lancamentos_classificados.csv').read_bytes())
        self.assert_numbers_unchanged('dec-ok')
        self.revise('dec-edit','dec-parent','sugerir',None,self.decision(target,'editar',parametros={'conta_codigo':'4.2.01'}),expected=1)
        self.revise('dec-rej','dec-parent','sugerir',None,self.decision(target,'rejeitar'))
        self.assertEqual(self.row(self.path('dec-rej'),'pendencias',target['excecao_id'])['status'],'REJEITADA')

    def test_forced_automatic_mode_never_applies_decision_classes(self):
        result = close_month(self.bundle,NO_FEES,'2026-09')
        data = inference_policy('sugerir')
        for classe in ('DECISAO','CONDICAO_COMERCIAL'):
            data['classes'][classe].update(modo='automatico',teto='automatico')
            self.assertEqual(effective_mode(data,classe),'sugerir')
        classes = ('DECISAO','CONDICAO_COMERCIAL')
        planted = {e.excecao_id:{'excecao_id':e.excecao_id, 'classe':e.classe, 'acao':'CLASSIFICAR_CONTA', 'parametros':{'conta_codigo':'4.2.01'},
                                 'evidencias':[{'arquivo':e.refs[0]['arquivo'] if e.refs else 'x', 'ref':'L1', 'trecho':'x'}], 'justificativa':'x', 'requer_humano':False}
                   for e in result.exceptions if e.classe in classes}
        self.assertEqual({result_class for result_class in (e.classe for e in result.exceptions if e.excecao_id in planted)},set(classes))
        before = deepcopy(result.tables)
        resolver = FakeResolver(planted)
        events = run_inference(self.bundle,result,NO_FEES,data,resolver,AuditLog(),TokenBudget(200000))
        self.assertFalse(set(resolver.calls) & set(planted))
        ours = [e for e in events if e['classe'] in classes]
        self.assertEqual({e['classe'] for e in ours},set(classes))
        self.assertEqual({(e['motivo'],e['aplicada'],e['modo']) for e in ours},{('SEM_VALIDADOR',False,'sugerir')})
        self.assertFalse(any(e['aplicada'] for e in events if e['classe'] in classes))
        self.assertEqual(result.tables,before)

    def test_apply_twice_raises(self):
        result = close_month(self.bundle,NO_FEES,'2026-09')
        movement = self.movements[0]
        data = inference_policy('sugerir')
        apply_proposal(result,self.bundle,data,movement,self.responses[movement['excecao_id']])
        with self.assertRaises(ValueError):
            apply_proposal(result,self.bundle,data,movement,self.responses[movement['excecao_id']])

    def test_decisions_need_a_parent_revision(self):
        self.layer('p-parent','sugerir')
        decisions = self.decisions('orphan',self.decision(self.movements[0]))
        code, _, err = run(self.path('no-parent'),'--policy',str(self.policy_path),'--decisoes',decisions)
        self.assertEqual(code,1)
        self.assertIn('Closing failed',err)
        self.assertFalse(self.path('no-parent').exists())
        code, _, err = run(self.path('no-decisions'),'--policy',str(self.policy_path),'--revisao-de',str(self.path('p-parent')))
        self.assertEqual((code,'Closing failed' in err),(1,True))

    def test_parent_without_audit_fails(self):
        code, _, err = run(self.path('rev-no-audit'),'--policy',str(self.policy_path),'--decisoes',self.decisions('na',self.decision(self.movements[0])),'--revisao-de',str(self.base))
        self.assertEqual(code,1)
        self.assertIn('Closing failed',err)
        self.assertIn('auditoria',err)

    def test_revision_on_other_sources_fails(self):
        self.layer('src-parent','sugerir')
        with TemporaryDirectory() as directory:
            pack = copy_pack(directory)
            late = next(pack.glob('06_*.csv'))
            late.write_bytes(late.read_bytes()+b'\n')
            code, _, err = run(self.path('src-rev'),'--policy',str(self.policy_path),'--inference-policy',str(self.policy_file('sugerir')),'--input',str(pack),
                               '--decisoes',self.decisions('src',self.decision(self.movements[0])),'--revisao-de',str(self.path('src-parent')))
        self.assertEqual(code,1)
        self.assertIn('Closing failed',err)
        self.assertRegex(err,'sources|fontes')

    def test_revision_with_other_closing_policy_fails(self):
        self.layer('pol-parent','sugerir')
        other = self.root/'other-policy.json'
        other.write_text(json.dumps(CLOSING_POLICY),encoding='utf-8')
        code, _, err = run(self.path('pol-rev'),'--policy',str(other),'--inference-policy',str(self.policy_file('sugerir')),
                           '--decisoes',self.decisions('pol',self.decision(self.others[0])),'--revisao-de',str(self.path('pol-parent')))
        self.assertEqual(code,1)
        self.assertIn('Closing failed',err)
        self.assertIn('outra closing-policy',err)

    def test_revision_with_other_period_fails(self):
        self.layer('per-parent','sugerir')
        code, _, err = run(self.path('per-rev'),'--policy',str(self.policy_path),'--inference-policy',str(self.policy_file('sugerir')),'--period','2026-10',
                           '--decisoes',self.decisions('per',self.decision(self.others[0])),'--revisao-de',str(self.path('per-parent')))
        self.assertEqual(code,1)
        self.assertIn('Closing failed',err)

    def test_later_revision_keeps_the_confidence_the_parent_applied(self):
        self.layer('conf-parent','sugerir','0.90')
        first, second = self.movements[0], self.movements[1]
        self.revise('conf-1','conf-parent','sugerir','0.90',self.decision(first))
        self.revise('conf-2','conf-1','sugerir','0.50',self.decision(second))
        lines = {r['id_saida']:r for r in read_csv(self.path('conf-2'),'lancamentos_classificados')}
        self.assertEqual((lines[identifier('BAN',first['escopo'])]['confianca'],lines[identifier('BAN',second['escopo'])]['confianca']),('0.90','0.50'))
        applied = [e for e in read_audit(self.path('conf-2')) if e['evento'] == 'DECISAO_APLICADA' and e['resultado'] == 'APLICADA']
        self.assertEqual(sorted(e['confianca'] for e in applied),['0.50','0.90'])

    def test_automatic_parent_confidence_is_recorded_and_replayed(self):
        self.layer('auto-conf','automatico','0.90')
        events = [e for e in read_audit(self.path('auto-conf')) if e['evento'] == 'EXCECAO' and e['aplicada']]
        self.assertEqual({e['confianca'] for e in events},{'0.90'})
        self.revise('auto-conf-rev','auto-conf','sugerir','0.10',self.decision(self.others[0]))
        lines = [r for r in read_csv(self.path('auto-conf-rev'),'lancamentos_classificados') if r['metodo'] == 'IA']
        self.assertEqual(({r['confianca'] for r in lines},len(lines)),({'0.90'},4))

    def test_shadow_proposal_cannot_be_approved(self):
        self.layer('shadow-parent','sombra')
        out, err = self.revise('shadow-rev','shadow-parent','sugerir',None,self.decision(self.movements[0]),expected=1)
        self.assertIn('Closing failed',err)
        self.assertIn('sombra',err)

    def test_approve_without_a_validated_proposal_fails(self):
        self.layer('empty-parent','sugerir',None,FakeResolver({}))
        out, err = self.revise('empty-rev','empty-parent','sugerir',None,self.decision(self.movements[0]),expected=1)
        self.assertIn('Closing failed',err)

    def test_malformed_parent_manifest_fails_cleanly(self):
        self.layer('bad-parent','sugerir')
        broken = self.path('broken-parent')
        shutil.copytree(self.path('bad-parent'),broken)
        (broken/'manifest.json').write_text('[]',encoding='utf-8')
        out, err = self.revise('bad-rev','broken-parent','sugerir',None,self.decision(self.movements[0]),expected=1)
        self.assertIn('Closing failed',err)
        (broken/'manifest.json').write_text('{}',encoding='utf-8')
        self.revise('bad-rev2','broken-parent','sugerir',None,self.decision(self.movements[0]),expected=1)

    def test_revision_works_with_no_llm_flag_and_chains(self):
        self.layer('chain-parent','sugerir')
        first, second = self.movements[0], self.movements[3]
        self.revise('chain-1','chain-parent','sugerir',None,self.decision(first))
        code, out, err = run(self.path('chain-2'),'--policy',str(self.policy_path),'--inference-policy',str(self.policy_file('sugerir')),'--no-llm',
                             '--decisoes',self.decisions('chain-2',self.decision(second)),'--revisao-de',str(self.path('chain-1')))
        self.assertEqual(code,0,err)
        manifest = json.loads((self.path('chain-2')/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['revisao']['numero'],2)
        self.assertIn('-rev2-',manifest['run_id'])
        lines = {r['id_saida']:r for r in read_csv(self.path('chain-2'),'lancamentos_classificados')}
        self.assertEqual([lines[identifier('BAN',m['escopo'])]['metodo'] for m in (first,second,self.movements[1])],['IA','IA','REGRA'])
        self.assert_ia_rows_have_evidence_and_event('chain-2')
        again = self.path('again')
        code, _, err = run(again,'--policy',str(self.policy_path),'--inference-policy',str(self.policy_file('sugerir')),
                           '--decisoes',self.decisions('again',self.decision(first,'rejeitar')),'--revisao-de',str(self.path('chain-2')))
        self.assertEqual(code,1)  # already decided in an earlier revision
        self.assertIn('already decided',err)

    def test_cache_makes_the_second_run_identical_without_calls(self):
        inner = FakeResolver(self.responses)
        policy = str(self.policy_file('sombra'))
        results = []
        for name in ('cache-a','cache-b'):
            code, _, err = run(self.path(name),'--policy',str(self.policy_path),'--inference-policy',policy,'--cache-dir',str(self.path('shared-cache')),resolver=inner)
            self.assertEqual(code,0,err)
            results.append(len(inner.calls))
        self.assertEqual(results[0],results[1])
        self.assertGreaterEqual(results[0],4)
        same_bytes(self,self.path('cache-a'),self.path('cache-b'),VOLATILE|{'auditoria.jsonl'})
        first, second = (read_audit(self.path(n)) for n in ('cache-a','cache-b'))
        strip = lambda events: [{k:v for k,v in e.items() if k != 'cache'} for e in events]
        self.assertEqual(strip(first),strip(second))
        self.assertTrue(all(e['cache'] for e in second if e['evento'] == 'EXCECAO' and e['proposta']))


if __name__ == '__main__':
    unittest.main()
