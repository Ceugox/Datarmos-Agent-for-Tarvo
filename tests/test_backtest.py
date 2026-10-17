from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close import backtest
from tarvo_close.backtest import build_cases, exception_id, gabarito_proposal, main, materialize, perturbations, record_policy, run_backtest, summarize, wilson_lower
from tarvo_close.closing import close_month
from tarvo_close.readers import read_inputs
from tarvo_close.resolver import FakeResolver, TokenBudget
from tarvo_close.validators import source_line

PACK = ROOT/'Tarvo_Data_Pack_set2026'
CLASS = 'MOVIMENTO_SEM_REGRA'


def outcomes(*values):
    return [{'id':str(index), 'classe':CLASS, 'resultado':value} for index, value in enumerate(values)]


class PerturbationTests(unittest.TestCase):
    def test_five_kinds_none_equal_to_the_original(self):
        original = 'PIX ENVIADO CONTABILIDADE EXATA LTDA'
        variants = dict(perturbations(original))
        self.assertEqual(list(variants),['sufixo','prefixo','abreviacao','acentos','ordem'])
        self.assertTrue(all(text != original for text in variants.values()))
        self.assertEqual(variants['sufixo'],original+' REF 0926')
        self.assertEqual(variants['prefixo'],'DEB '+original)
        self.assertEqual(variants['abreviacao'],'PIX ENVI. CONTABILIDADE EXATA LTDA')
        self.assertEqual(variants['acentos'],original.lower())
        self.assertEqual(variants['ordem'],'ENVIADO PIX CONTABILIDADE EXATA LTDA')

    def test_accents_are_removed_and_identical_variants_are_not_generated(self):
        self.assertEqual(dict(perturbations('Repasse Comissão'))['acentos'],'repasse comissao')
        self.assertEqual([kind for kind, _ in perturbations('PIX')],['sufixo','prefixo','acentos'])
        self.assertNotIn('acentos',dict(perturbations('123 456')))

    def test_abbreviation_replaces_the_token_not_an_earlier_substring(self):
        self.assertEqual(dict(perturbations('X-ENVIADO ENVIADO PIX'))['abreviacao'],'X-ENVIADO ENVI. PIX')
        self.assertEqual(dict(perturbations('TAR PACOTE  SERVICOS '))['abreviacao'],'TAR PACO.  SERVICOS ')

    def test_deterministic(self):
        self.assertEqual(perturbations('TAR PACOTE SERVICOS PJ'),perturbations('TAR PACOTE SERVICOS PJ'))


class WilsonTests(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(wilson_lower(9,10),'0.5958')
        self.assertEqual(wilson_lower(35,35),'0.9011')
        self.assertIsNone(wilson_lower(0,0))

    def test_summarize_counts_without_the_pipeline(self):
        summary = summarize(outcomes('ACERTO','ERRO','HUMANO','ACERTO','HUMANO','ACERTO'))[CLASS]
        self.assertEqual(summary,{'total':6, 'decididos':4, 'acertos':3, 'erros':1, 'humanos':2, 'precisao':'0.7500', 'cobertura':'0.6667',
                                  'seguidos_sem_erro':2, 'wilson_95':wilson_lower(3,4)})

    def test_streak_ignores_human_cases_and_breaks_on_errors(self):
        self.assertEqual(summarize(outcomes('ACERTO','HUMANO','ACERTO','HUMANO'))[CLASS]['seguidos_sem_erro'],2)
        self.assertEqual(summarize(outcomes('ACERTO','ACERTO','ERRO'))[CLASS]['seguidos_sem_erro'],0)

    def test_no_decided_case_has_no_precision(self):
        summary = summarize(outcomes('HUMANO','HUMANO'))[CLASS]
        self.assertEqual((summary['precisao'],summary['wilson_95'],summary['cobertura'],summary['seguidos_sem_erro']),(None,None,'0.0000',0))


class CaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
        cls.cases = build_cases(PACK,cls.policy,'2026-09')

    def test_september_cases(self):
        kinds = [case['tipo'] for case in self.cases]
        # 184 movements are matched by a rule; one (a PIX to the accountant) stays matched by the generic payment rule once its own rule is gone
        self.assertEqual(kinds.count('regra_removida'),183)
        self.assertEqual(len({case['id'] for case in self.cases}),len(self.cases))
        self.assertEqual(set(kinds),{'regra_removida','sufixo','prefixo','abreviacao','acentos','ordem'})
        self.assertNotIn('AURORA:L53:regra_removida',{case['id'] for case in self.cases})
        first = self.cases[0]
        self.assertEqual((first['id'],first['tipo'],first['regra_id'],first['gabarito'],first['descricao'],first['descricao_original']),
                         ('AURORA:L10:regra_removida','regra_removida','bank-fees','4.2.01','TAR PACOTE SERVICOS PJ','TAR PACOTE SERVICOS PJ'))

    def test_order_is_stable(self):
        again = build_cases(PACK,self.policy,'2026-09')
        self.assertEqual([c['id'] for c in again],[c['id'] for c in self.cases])

    def check_materialized(self, case):
        with TemporaryDirectory() as directory:
            pack, reduced = materialize(case,PACK,directory)
            self.assertIsNone(reduced)
            pack, reduced = materialize(case,PACK,Path(directory)/'again',self.policy)
            self.assertNotIn(case['regra_id'],[rule['id'] for rule in reduced['bank_rules']])
            self.assertEqual(len(reduced['bank_rules']),len(self.policy['bank_rules'])-1)
            bundle = read_inputs(pack)
            line = source_line(bundle,{'arquivo':case['arquivo'], 'aba':'', 'ref':case['ref'], 'linha':case['linha']})
            self.assertIn(case['descricao'],line)
            entry = next(e for e in bundle.bank_entries if e['bank'] == case['banco'] and e['_source']['ref_origem'] == case['ref'])
            self.assertEqual(entry['description'],case['descricao'])
            result = close_month(bundle,reduced,'2026-09')
            found = [e for e in result.exceptions if e.escopo == f'{case["banco"]}:{case["ref"]}']
            self.assertEqual([(e.classe,e.tipo) for e in found],[(CLASS,'CONCILIACAO_BANCARIA')])
            self.assertEqual(found[0].excecao_id,exception_id(case))
        # the real pack is never touched
        self.assertEqual(entry['description'],case['descricao'])
        original = next(e for e in read_inputs(PACK).bank_entries if e['bank'] == case['banco'] and e['_source']['ref_origem'] == case['ref'])
        self.assertEqual(original['description'],case['descricao_original'])

    def test_materialize_csv_case(self):
        case = next(c for c in self.cases if c['banco'] == 'AURORA' and c['tipo'] == 'sufixo')
        self.assertEqual(case['descricao'],case['descricao_original']+' REF 0926')
        self.check_materialized(case)

    def test_materialize_ofx_case(self):
        case = next(c for c in self.cases if c['banco'] == 'MERIDIANO' and c['tipo'] == 'prefixo')
        self.assertTrue(case['descricao'].startswith('DEB '))
        self.check_materialized(case)
        self.check_materialized(next(c for c in self.cases if c['banco'] == 'MERIDIANO' and c['tipo'] == 'regra_removida'))

    def test_materialize_rejects_a_description_that_is_not_in_the_source(self):
        case = dict(next(c for c in self.cases if c['banco'] == 'AURORA'),descricao_original='OUTRA COISA')
        with TemporaryDirectory() as directory, self.assertRaises(ValueError):
            materialize(case,PACK,directory)


class RunBacktestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
        cls.inference_policy = json.loads((ROOT/'config/inference-policy.json').read_text(encoding='utf-8'))
        cls.cases = build_cases(PACK,cls.policy,'2026-09')[:6]  # the six variants of the first movement

    def test_counts_hits_errors_and_human_cases_exactly(self):
        plan = ['certa','errada','ausente','certa','certa','ausente']
        wrong = {'4.2.04'}

        def factory(case):
            kind = plan[self.cases.index(case)]
            if kind == 'ausente':
                return FakeResolver()
            data = gabarito_proposal(case)
            if kind == 'errada':
                data['parametros'] = {'conta_codigo':next(iter(wrong))}
            return FakeResolver({exception_id(case):data})

        outcome = run_backtest(self.cases,PACK,self.policy,self.inference_policy,'2026-09',factory)
        self.assertEqual([c['resultado'] for c in outcome['casos']],['ACERTO','ERRO','HUMANO','ACERTO','ACERTO','HUMANO'])
        self.assertEqual(outcome['casos'][5]['motivo'],'SEM_TOOL_CALL')
        self.assertEqual(outcome['por_classe'][CLASS],{'total':6, 'decididos':4, 'acertos':3, 'erros':1, 'humanos':2, 'precisao':'0.7500',
                                                       'cobertura':'0.6667', 'seguidos_sem_erro':2, 'wilson_95':wilson_lower(3,4)})

    def test_one_resolver_call_per_case_and_only_for_the_target_exception(self):
        resolvers = []

        def factory(case):
            resolvers.append(FakeResolver({exception_id(case):gabarito_proposal(case)}))
            return resolvers[-1]

        run_backtest(self.cases[:3],PACK,self.policy,self.inference_policy,'2026-09',factory)
        self.assertEqual([r.calls for r in resolvers],[[exception_id(c)] for c in self.cases[:3]])

    def test_budget_is_shared_and_exhaustion_makes_the_rest_human_without_calls(self):
        shared = FakeResolver({exception_id(self.cases[0]):{**gabarito_proposal(self.cases[0]),'_usage':{'input_tokens':100}}})
        outcome = run_backtest(self.cases[:3],PACK,self.policy,self.inference_policy,'2026-09',shared,budget=TokenBudget(100))
        self.assertEqual([(c['resultado'],c['motivo']) for c in outcome['casos']],[('ACERTO',None),('HUMANO','ORCAMENTO_ESGOTADO'),('HUMANO','ORCAMENTO_ESGOTADO')])
        self.assertEqual(len(shared.calls),1)

    def test_limit_and_shared_resolver(self):
        outcome = run_backtest(self.cases,PACK,self.policy,self.inference_policy,'2026-09',FakeResolver(),limit=2)
        self.assertEqual(len(outcome['casos']),2)
        self.assertEqual(outcome['por_classe'][CLASS]['humanos'],2)


class RecordPolicyTests(unittest.TestCase):
    def test_gravar_changes_only_criterion_and_confidence_of_the_class(self):
        original = (ROOT/'config/inference-policy.json').read_text(encoding='utf-8')
        summary = {CLASS:{'seguidos_sem_erro':35, 'erros':0, 'wilson_95':'0.9011'}}
        with TemporaryDirectory() as directory:
            path = Path(directory)/'inference-policy.json'
            path.write_bytes(original.encode('utf-8'))
            record_policy(path,summary,'abc123def456')
            text = path.read_bytes().decode('utf-8')
        self.assertNotIn('\r',text)
        before, after = json.loads(original), json.loads(text)
        entry = after['classes'][CLASS]
        self.assertEqual((entry['modo'],entry['teto'],entry['aprovado_por'],entry['aprovado_em']),('sombra','automatico',None,None))
        self.assertEqual(entry['criterio']['casos_seguidos_sem_erro'],35)
        self.assertEqual((entry['criterio']['erros'],entry['criterio']['backtest_versao'],entry['confianca']),(0,'abc123def456','0.9011'))
        self.assertRegex(entry['criterio']['data'],r'^\d{4}-\d{2}-\d{2}$')
        for key in ('criterio','confianca'):
            before['classes'][CLASS].pop(key)
            after['classes'][CLASS].pop(key)
        self.assertEqual(before,after)
        changed = [line for line in text.splitlines() if line not in original.splitlines()]
        self.assertLessEqual(len(changed),5)  # same key order: the diff is only the recorded fields

    def test_gravar_is_refused_with_the_fake_or_a_limit_and_leaves_the_policy_intact(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'inference-policy.json'
            path.write_bytes((ROOT/'config/inference-policy.json').read_bytes())
            before = path.read_bytes()
            base = ['--input',str(PACK),'--period','2026-09','--policy',str(ROOT/'config/closing-policy.json'),'--inference-policy',str(path),'--gravar']
            for extra in (['--resolver','fake'],['--resolver','anthropic','--limit','2']):
                with StringIO() as err, redirect_stderr(err):
                    self.assertEqual(main(base+extra),1)
                    self.assertIn('--gravar',err.getvalue())
            self.assertEqual(path.read_bytes(),before)

    def test_anthropic_resolver_requires_a_key_and_never_runs_here(self):
        with mock.patch.dict(os.environ,{},clear=False) as env, StringIO() as err, redirect_stderr(err):
            env.pop('ANTHROPIC_API_KEY',None)
            code = main(['--input',str(PACK),'--period','2026-09','--policy',str(ROOT/'config/closing-policy.json'),
                         '--inference-policy',str(ROOT/'config/inference-policy.json'),'--resolver','anthropic','--limit','1'])
            message = err.getvalue()
        self.assertEqual(code,1)
        self.assertIn('ANTHROPIC_API_KEY',message)


if __name__ == '__main__':
    unittest.main()
