from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.audit import AuditLog
from tarvo_close.closing import ClosingResult, close_month
from tarvo_close.exceptions import ClosingException
from tarvo_close.inference import build_queue, exception_payload, run_inference
from tarvo_close.inference_policy import load_inference_policy
from tarvo_close.llm_cache import ResponseCache
from tarvo_close.readers import read_inputs
from tarvo_close.resolver import CachedResolver, FakeResolver, Failure, TokenBudget


class InferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
        cls.inference_policy = load_inference_policy(ROOT/'config/inference-policy.json')
        cls.bundle = read_inputs(ROOT/'Tarvo_Data_Pack_set2026')
        cls.september = close_month(cls.bundle,cls.policy,'2026-09')
        cls.entries = [e for e in cls.bundle.bank_entries if e['bank'] == 'AURORA' and e['description'].strip() and e['amount'] < 0][:3]
        cls.synthetic = ClosingResult()
        for index, entry in enumerate(cls.entries):
            source = entry['_source']
            ref = {'arquivo':source['arquivo_origem'], 'aba':'', 'ref':source['ref_origem'], 'linha':source['linha_origem']}
            cls.synthetic.exceptions.append(ClosingException(f'PEN-SINT{index}','MOVIMENTO_SEM_REGRA','CONCILIACAO_BANCARIA',f'AURORA:{source["ref_origem"]}','Helena','sem regra','conta',None,[ref]))

    def run_layer(self, result, responses=None, budget=None, resolver=None):
        resolver = resolver or FakeResolver(responses)
        audit = AuditLog()
        events = run_inference(self.bundle,result,self.policy,self.inference_policy,resolver,audit,budget or TokenBudget(200000))
        return resolver, audit, events

    def proposal(self, index, **changes):
        item = self.synthetic.exceptions[index]
        ref = item.refs[0]
        data = {'excecao_id':item.excecao_id, 'classe':'MOVIMENTO_SEM_REGRA', 'acao':'CLASSIFICAR_CONTA', 'parametros':{'conta_codigo':'4.2.01'},
                'evidencias':[{'arquivo':ref['arquivo'], 'ref':ref['ref'], 'trecho':self.entries[index]['description']}], 'justificativa':'teste', 'requer_humano':False}
        data.update(changes)
        return data

    def test_september_queue(self):
        queue = build_queue(self.september,self.inference_policy)
        self.assertEqual(len(queue),13)
        self.assertEqual([i['excecao']['excecao_id'] for i in queue],[e.excecao_id for e in self.september.exceptions])
        for item in queue:
            expected = 'sugerir' if item['excecao']['classe'] in ('DECISAO','CONDICAO_COMERCIAL') else 'desligado'
            self.assertEqual(item['modo'],expected,item['excecao']['classe'])
        classes = {i['excecao']['classe'] for i in queue}
        self.assertTrue({'DECISAO','CONDICAO_COMERCIAL','ESPERA_EVIDENCIA','ESPERA_DADO'} <= classes)

    def test_september_never_calls_the_resolver(self):
        resolver, audit, events = self.run_layer(self.september)
        self.assertEqual(resolver.calls,[])
        self.assertEqual(len(events),13)
        for event in events:
            self.assertEqual(event['resultado'],'HUMANO')
            self.assertEqual(event['motivo'],'SEM_VALIDADOR' if event['modo'] == 'sugerir' else 'MODO_DESLIGADO')
            self.assertIsNone(event['proposta'])
            self.assertFalse(event['aplicada'])
        self.assertEqual(audit.events[-1]['evento'],'EXECUCAO')
        self.assertEqual(len(audit.events),14)

    def test_payload_cites_source_lines(self):
        payload = exception_payload(self.synthetic.exceptions[0],self.bundle)
        self.assertIn(self.entries[0]['description'],payload['linhas_citadas'][0]['texto'])
        broken = ClosingException('PEN-X','MOVIMENTO_SEM_REGRA','CONCILIACAO_BANCARIA','x','H','m','f',None,[{'arquivo':'nao_existe.csv','aba':'','ref':'L1','linha':1}])
        self.assertEqual(exception_payload(broken,self.bundle)['linhas_citadas'][0]['texto'],'')

    def test_valid_proposal_in_shadow_is_validated_and_not_applied(self):
        resolver, audit, events = self.run_layer(self.synthetic,{'PEN-SINT0':self.proposal(0)})
        self.assertEqual(resolver.calls,['PEN-SINT0','PEN-SINT1','PEN-SINT2'])
        first = events[0]
        self.assertEqual((first['modo'],first['resultado'],first['motivo']),('sombra','VALIDADA',None))
        self.assertEqual([(c['check'],c['status']) for c in first['verificacoes']],
                         [(name,'PASS') for name in ('schema','evidencia','movimento','evidencia_descricao','conta','par_conhecido','nao_provisao','nao_disponibilidade')])
        self.assertFalse(first['aplicada'])
        self.assertEqual(first['proposta'],self.proposal(0))
        self.assertEqual([e['motivo'] for e in events[1:]],['SEM_TOOL_CALL','SEM_TOOL_CALL'])

    def test_invalid_evidence(self):
        bad = self.proposal(0,evidencias=[{**self.proposal(0)['evidencias'][0], 'trecho':'TRECHO QUE NAO EXISTE'}])
        _, _, events = self.run_layer(self.synthetic,{'PEN-SINT0':bad})
        self.assertEqual(events[0]['motivo'],'EVIDENCIA_INVALIDA')
        self.assertEqual(events[0]['verificacoes'][-1]['check'],'evidencia')

    def test_out_of_schema_responses(self):
        extra = {**self.proposal(1), 'valor_brl':'10.00'}
        _, _, events = self.run_layer(self.synthetic,{'PEN-SINT0':self.proposal(0,acao='PAGAR'), 'PEN-SINT1':extra})
        self.assertEqual([e['motivo'] for e in events[:2]],['FORA_DO_SCHEMA','FORA_DO_SCHEMA'])
        self.assertEqual(events[0]['verificacoes'][0]['check'],'schema')

    def test_human_requests(self):
        asked = self.proposal(0,requer_humano=True)
        forward = self.proposal(1,acao='ENCAMINHAR_HUMANO',parametros={})
        _, _, events = self.run_layer(self.synthetic,{'PEN-SINT0':asked, 'PEN-SINT1':forward})
        self.assertEqual([e['motivo'] for e in events[:2]],['REQUER_HUMANO','REQUER_HUMANO'])

    def test_refusal(self):
        _, _, events = self.run_layer(self.synthetic,{'PEN-SINT0':Failure('RECUSA')})
        self.assertEqual((events[0]['resultado'],events[0]['motivo']),('HUMANO','RECUSA'))

    def test_failure_usage_is_charged(self):
        usage = {'input_tokens':3000, 'output_tokens':2000}
        resolver = FakeResolver({'PEN-SINT0':Failure('RECUSA',usage=usage)},model='claude-opus-5-5')
        budget = TokenBudget(200000)
        _, audit, events = self.run_layer(self.synthetic,budget=budget,resolver=resolver)
        self.assertEqual(budget.used,5000)
        self.assertEqual(audit.events[-1]['tokens_total'],5000)
        self.assertEqual(events[0]['motivo'],'RECUSA')
        self.assertEqual(events[0]['tokens']['input_tokens'],3000)
        self.assertEqual(events[0]['custo_usd'],'0.052')

    def test_budget_exhausted_skips_the_resolver(self):
        usage = {'input_tokens':3000, 'output_tokens':2000}
        resolver, audit, events = self.run_layer(self.synthetic,{'PEN-SINT0':{**self.proposal(0), '_usage':usage}},budget=TokenBudget(1000))
        self.assertEqual(resolver.calls,['PEN-SINT0'])
        self.assertEqual((events[0]['resultado'],events[0]['motivo']),('VALIDADA',None))
        self.assertEqual([e['motivo'] for e in events[1:]],['ORCAMENTO_ESGOTADO','ORCAMENTO_ESGOTADO'])
        summary = audit.events[-1]
        self.assertEqual(summary['tokens_total'],5000)
        self.assertEqual(summary['orcamento'],{'limite':1000, 'usado':5000, 'esgotado':True})

    def test_cached_second_run_matches_without_calling_the_resolver(self):
        responses = {'PEN-SINT0':self.proposal(0), 'PEN-SINT1':self.proposal(1,requer_humano=True), 'PEN-SINT2':self.proposal(2)}
        with TemporaryDirectory() as directory:
            inner = FakeResolver(responses)
            resolver = CachedResolver(inner,ResponseCache(directory))
            _, _, first = self.run_layer(self.synthetic,resolver=resolver)
            calls = list(inner.calls)
            _, _, second = self.run_layer(self.synthetic,resolver=resolver)
        self.assertEqual(len(calls),3)
        self.assertEqual(inner.calls,calls)
        strip = lambda events: [{k:v for k,v in e.items() if k != 'cache'} for e in events]
        self.assertEqual(strip(first),strip(second))
        self.assertEqual([e['cache'] for e in first],[False,False,False])
        self.assertEqual([e['cache'] for e in second],[True,True,True])


if __name__ == '__main__':
    unittest.main()
