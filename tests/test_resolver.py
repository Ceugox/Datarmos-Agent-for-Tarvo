from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock
import json
import os
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.llm_cache import ResponseCache, canonical
from tarvo_close.resolver import AnthropicResolver, CachedResolver, FakeResolver, Failure, Proposal, TokenBudget, cost_usd

USAGE_KEYS = ('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens')


class APIConnectionError(Exception):
    pass


class APITimeoutError(Exception):
    pass


class APIStatusError(Exception):
    def __init__(self, message='x', status_code=None, request_id=None):
        super().__init__(message)
        self.message, self.status_code, self.request_id = message, status_code, request_id


class RateLimitError(APIStatusError):
    pass


class InternalServerError(APIStatusError):
    pass


class OverloadedError(APIStatusError):
    pass


class BadRequestError(APIStatusError):
    pass


class AuthenticationError(APIStatusError):
    pass


FAKE_KEY = 'sk-ant-TESTE'


class FakeClient:
    def __init__(self, response=None, error=None):
        self.kwargs, self.response, self.error = [], response, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.kwargs.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def tool_response(proposta, stop_reason='tool_use'):
    block = SimpleNamespace(type='tool_use',name='propor_resolucao',input={'proposta':proposta})
    usage = SimpleNamespace(input_tokens=10,output_tokens=20,cache_read_input_tokens=None,cache_creation_input_tokens=5)
    return SimpleNamespace(content=[block],stop_reason=stop_reason,usage=usage)


def exception(**changes):
    base = {'excecao_id':'PEN-1', 'classe':'MOVIMENTO_SEM_REGRA', 'tipo':'CONCILIACAO_BANCARIA', 'motivo':'Pagamento do CPF 123.456.789-09 na Conta: 4471-0',
            'refs':[{'arquivo':'extrato.csv', 'aba':'', 'ref':'L2', 'linha':2}], 'linhas_citadas':[{'arquivo':'extrato.csv', 'ref':'L2', 'texto':'TAR PACOTE'}]}
    return {**base,**changes}


PROPOSAL = {'excecao_id':'PEN-1', 'classe':'MOVIMENTO_SEM_REGRA', 'acao':'ENCAMINHAR_HUMANO', 'parametros':{},
            'evidencias':[{'arquivo':'extrato.csv', 'ref':'L2', 'trecho':'TAR PACOTE'}], 'justificativa':'x', 'requer_humano':True}
CONTEXT = {'accounts':[{'codigo':'4.2.01'}], 'closing_policy':{'a':1,'b':2}}


class AnthropicResolverTests(unittest.TestCase):
    def test_import_is_lazy(self):
        code = "import sys; sys.path.insert(0,sys.argv[1]); import tarvo_close.resolver; print('anthropic' in sys.modules)"
        out = subprocess.run([sys.executable,'-c',code,str(ROOT/'src')],capture_output=True,text=True,check=True)
        self.assertEqual(out.stdout.strip(),'False')

    def test_call_parameters(self):
        client = FakeClient(tool_response(PROPOSAL))
        with mock.patch.dict(os.environ,{},clear=False):
            os.environ.pop('ANTHROPIC_MODEL',None)
            resolver = AnthropicResolver(client=client)
        result = resolver.propose(exception(),CONTEXT)
        call = client.kwargs[0]
        self.assertEqual(call['model'],'claude-opus-5-5')
        self.assertIs(call['tools'][0]['strict'],True)
        self.assertEqual(call['tools'][0]['name'],'propor_resolucao')
        self.assertEqual(call['tool_choice'],{'type':'auto'})
        self.assertEqual(call['output_config'],{'effort':'medium'})
        self.assertEqual(call['max_tokens'],16000)
        self.assertEqual(call['betas'],['server-side-fallback-2026-07-01'])
        self.assertEqual(call['fallbacks'],'default')
        self.assertEqual(call['system'][0]['cache_control'],{'type':'ephemeral'})
        self.assertNotIn('thinking',call)
        schema = call['tools'][0]['input_schema']
        self.assertEqual(schema['required'],['proposta'])
        self.assertIs(schema['additionalProperties'],False)
        self.assertIsInstance(result,Proposal)
        self.assertEqual(result.data,PROPOSAL)
        self.assertEqual(result.usage,{'input_tokens':10, 'output_tokens':20, 'cache_read_input_tokens':0, 'cache_creation_input_tokens':5})

    def test_model_comes_from_environment(self):
        with mock.patch.dict(os.environ,{'ANTHROPIC_MODEL':'outro-modelo'}):
            self.assertEqual(AnthropicResolver(client=FakeClient()).model,'outro-modelo')

    def test_system_is_deterministic(self):
        client = FakeClient(tool_response(PROPOSAL))
        resolver = AnthropicResolver(client=client)
        resolver.propose(exception(),CONTEXT)
        resolver.propose(exception(),{'closing_policy':{'b':2,'a':1}, 'accounts':[{'codigo':'4.2.01'}]})
        self.assertEqual(client.kwargs[0]['system'],client.kwargs[1]['system'])
        self.assertIn(canonical(CONTEXT),client.kwargs[0]['system'][0]['text'])

    def test_personal_data_is_masked_in_messages(self):
        client = FakeClient(tool_response(PROPOSAL))
        AnthropicResolver(client=client).propose(exception(),CONTEXT)
        sent = str(client.kwargs[0]['messages'])
        self.assertNotIn('123.456.789-09',sent)
        self.assertNotIn('4471-0',sent)
        self.assertIn('TAR PACOTE',sent)

    def test_refusal(self):
        result = AnthropicResolver(client=FakeClient(tool_response(PROPOSAL,'refusal'))).propose(exception(),CONTEXT)
        self.assertEqual(result.reason,'RECUSA')

    def test_no_tool_call(self):
        response = SimpleNamespace(content=[SimpleNamespace(type='text',text='oi')],stop_reason='end_turn',usage=None)
        result = AnthropicResolver(client=FakeClient(response)).propose(exception(),CONTEXT)
        self.assertEqual(result.reason,'SEM_TOOL_CALL')

    def classify(self, error):
        client = FakeClient(error=error)
        client.api_key = FAKE_KEY  # like the SDK client: the key lives on the client and must never reach the failure
        with self.assertLogs('tarvo_close.resolver') as logs:
            result = AnthropicResolver(client=client).propose(exception(),CONTEXT)
        self.assertIsInstance(result,Failure)
        self.assertNotIn(FAKE_KEY,str(result))
        self.assertNotIn(FAKE_KEY,'\n'.join(logs.output))
        return result, logs

    def test_api_errors_are_configuration_failures(self):
        for error_class, status in ((BadRequestError,400), (AuthenticationError,401), (APIStatusError,403), (APIStatusError,404), (APIStatusError,413), (APIStatusError,422)):
            error = error_class("tools.0.custom: For 'anyOf', 'type' is not supported "+'z'*600,status_code=status,request_id='req_123')
            result, logs = self.classify(error)
            self.assertEqual((result.reason,result.detail),('ERRO_API',error_class.__name__))
            self.assertEqual(set(result.detalhe),{'tipo','status','mensagem','request_id'})
            self.assertEqual((result.detalhe['tipo'],result.detalhe['status'],result.detalhe['request_id']),(error_class.__name__,status,'req_123'))
            self.assertTrue(result.detalhe['mensagem'].startswith("tools.0.custom: For 'anyOf'"))
            self.assertEqual(len(result.detalhe['mensagem']),500)
            self.assertEqual([r.levelname for r in logs.records],['ERROR'])
            self.assertEqual(logs.records[0].getMessage(),f'ERRO_API {error_class.__name__} status={status} request_id=req_123')

    def test_transient_errors_are_network_failures(self):
        errors = (RateLimitError('x',status_code=429,request_id='r1'), InternalServerError('x',status_code=500), OverloadedError('x',status_code=529,request_id='r3'),
                  APIStatusError('x',status_code=503), APIConnectionError('x'), APITimeoutError('x'))
        for error in errors:
            result, logs = self.classify(error)
            self.assertEqual((result.reason,result.detail),('ERRO_REDE',type(error).__name__))
            self.assertEqual(result.detalhe['tipo'],type(error).__name__)
            self.assertEqual(result.detalhe['status'],getattr(error,'status_code',None))
            self.assertEqual(result.detalhe['request_id'],getattr(error,'request_id',None))
            self.assertEqual([r.levelname for r in logs.records],['WARNING'])

    def test_status_error_without_status_is_not_transient(self):
        result, _ = self.classify(APIStatusError('x'))
        self.assertEqual(result.reason,'ERRO_API')
        self.assertIsNone(result.detalhe['status'])

    def test_other_errors_are_not_swallowed(self):
        with self.assertRaises(RuntimeError):
            AnthropicResolver(client=FakeClient(error=RuntimeError('x'))).propose(exception(),CONTEXT)

    def test_proposal_not_a_dict(self):
        for value in ('texto',None,[1]):
            result = AnthropicResolver(client=FakeClient(tool_response(value))).propose(exception(),CONTEXT)
            self.assertEqual(result.reason,'FORA_DO_SCHEMA')

    def test_prompt_version_default_matches_the_policy(self):
        policy = json.loads((ROOT/'config'/'inference-policy.json').read_text(encoding='utf-8'))
        from tarvo_close.resolver import RESOLVER_VERSION
        self.assertEqual(AnthropicResolver(client=FakeClient()).prompt_version,f"{policy['prompt_version']}+{RESOLVER_VERSION}")
        self.assertEqual(policy['prompt_version'],'2026-10-17.2')

    def test_source_never_reads_the_api_key(self):
        self.assertNotIn('ANTHROPIC_API_KEY',(ROOT/'src'/'tarvo_close'/'resolver.py').read_text(encoding='utf-8'))


class CostAndBudgetTests(unittest.TestCase):
    def test_cost(self):
        usage = {'input_tokens':1000, 'output_tokens':100, 'cache_read_input_tokens':10000, 'cache_creation_input_tokens':8000}
        self.assertEqual(cost_usd('claude-opus-5-5',usage),Decimal('0.048'))

    def test_unknown_model_has_no_cost(self):
        self.assertIsNone(cost_usd('modelo-sem-preco',{'input_tokens':1}))

    def test_budget(self):
        budget = TokenBudget(100)
        self.assertFalse(budget.exhausted)
        budget.charge({'input_tokens':40, 'output_tokens':30, 'cache_read_input_tokens':20, 'cache_creation_input_tokens':9})
        self.assertEqual(budget.used,99)
        self.assertFalse(budget.exhausted)
        budget.charge({'input_tokens':1})
        self.assertTrue(budget.exhausted)


class FakeAndCachedTests(unittest.TestCase):
    def test_fake_resolver(self):
        usage = {'input_tokens':7}
        fake = FakeResolver({'A':{'k':1,'_usage':usage}, 'B':Failure('RECUSA')})
        self.assertEqual(fake.propose({'excecao_id':'ZZ'},{}).reason,'SEM_TOOL_CALL')
        proposal = fake.propose({'excecao_id':'A'},{})
        self.assertEqual(proposal.data,{'k':1})
        self.assertEqual(proposal.usage,{'input_tokens':7, 'output_tokens':0, 'cache_read_input_tokens':0, 'cache_creation_input_tokens':0})
        self.assertEqual(fake.propose({'excecao_id':'B'},{}).reason,'RECUSA')
        self.assertEqual(fake.calls,['ZZ','A','B'])

    def test_cached_resolver(self):
        with TemporaryDirectory() as directory:
            inner = FakeResolver({'PEN-1':{**PROPOSAL,'_usage':{'input_tokens':9}}})
            cached = CachedResolver(inner,ResponseCache(directory))
            first = cached.propose(exception(),CONTEXT)
            second = cached.propose(exception(),CONTEXT)
            self.assertEqual(inner.calls,['PEN-1'])
            self.assertFalse(first.cached)
            self.assertTrue(second.cached)
            self.assertEqual(second.data,first.data)
            self.assertEqual(set(second.usage),set(USAGE_KEYS))
            self.assertEqual(sum(second.usage.values()),0)
            cached.propose(exception(motivo='outro'),CONTEXT)
            self.assertEqual(len(inner.calls),2)

    def test_cache_file_without_data_is_a_miss(self):
        for bad in ([],{}):
            with TemporaryDirectory() as directory:
                inner = FakeResolver({'PEN-1':dict(PROPOSAL)})
                cache = ResponseCache(directory)
                cache.put(cache.key(inner.prompt_version,inner.model,{'excecao':exception(),'context':CONTEXT}),bad)
                result = CachedResolver(inner,cache).propose(exception(),CONTEXT)
                self.assertEqual(inner.calls,['PEN-1'])
                self.assertFalse(result.cached)
                self.assertTrue(CachedResolver(inner,cache).propose(exception(),CONTEXT).cached)

    def test_failure_is_not_cached(self):
        with TemporaryDirectory() as directory:
            inner = FakeResolver()
            cached = CachedResolver(inner,ResponseCache(directory))
            cached.propose(exception(),CONTEXT)
            cached.propose(exception(),CONTEXT)
            self.assertEqual(len(inner.calls),2)


if __name__ == '__main__':
    unittest.main()
