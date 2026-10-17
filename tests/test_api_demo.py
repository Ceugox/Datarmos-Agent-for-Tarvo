"""Modo demonstração (17/10): chave por autoatendimento, IA ligada por padrão, limites por IP e validade até DEMO_ATE."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))

from test_cli_inference import PACK

try:  # the engine CI job installs only requirements.txt
    from fastapi.testclient import TestClient
    from api import db, keys
    from api.app import create_app
    from api.settings import Settings, parse_deadline
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

TEST_DATABASE_URL = os.environ.get('TEST_DATABASE_URL')
TABLES = ('llm_cache','auditoria','decisoes','excecoes','jobs','fechamentos','politicas','clientes','schema_migrations')
PACK_FILES = sorted(p for p in PACK.iterdir() if p.name[:2] in ('01','02','03','04','05','06'))


def uploads():
    return [('arquivos',(p.name,p.read_bytes(),'application/octet-stream')) for p in PACK_FILES]


@unittest.skipUnless(HAS_DEPS,'dependências da API ausentes')
class DemoSettingsTest(unittest.TestCase):
    def test_deadline_needs_an_explicit_timezone(self):
        self.assertEqual(parse_deadline('2026-10-18T23:59:00-03:00').utcoffset(),timedelta(hours=-3))
        self.assertIsNone(parse_deadline(''))
        with self.assertRaisesRegex(ValueError,'fuso'):
            parse_deadline('2026-10-18T23:59:00')

    def test_demo_is_active_only_before_the_deadline(self):
        deadline = datetime(2026,10,18,23,59,tzinfo=timezone(timedelta(hours=-3)))
        settings = Settings(demo_ate=deadline)
        self.assertTrue(settings.demo_active(deadline-timedelta(seconds=1)))
        self.assertFalse(settings.demo_active(deadline))
        self.assertFalse(Settings().demo_active())


@unittest.skipUnless(TEST_DATABASE_URL and HAS_DEPS,'TEST_DATABASE_URL não definido ou dependências da API ausentes: testes da API pulados')
class DemoModeTest(unittest.TestCase):
    def setUp(self):
        env = {k:v for k,v in os.environ.items() if k != 'ANTHROPIC_API_KEY'}
        patch = mock.patch.dict(os.environ,env,clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        self.data = TemporaryDirectory()
        self.addCleanup(self.data.cleanup)
        self.conn = db.connect(TEST_DATABASE_URL)
        self.addCleanup(self.conn.close)
        db.migrate(self.conn)
        self.conn.execute('TRUNCATE '+', '.join(TABLES)+' CASCADE')
        self.conn.commit()
        db.migrate(self.conn)
        self.regular_id, self.regular_key = keys.create_client(self.conn,'regular')

    def open(self, active=True, **overrides):
        deadline = datetime.now(timezone.utc)+(timedelta(hours=1) if active else -timedelta(minutes=1))
        values = dict(database_url=TEST_DATABASE_URL,data_dir=self.data.name,worker_in_process=False,rate_limit_per_minute=1000,demo_ate=deadline)
        client = TestClient(create_app(Settings(**{**values,**overrides})))
        client.__enter__()
        self.addCleanup(client.__exit__,None,None,None)
        return client

    def new_key(self, client, ip='203.0.113.1'):
        return client.post('/v1/demo/chave',headers={'X-Real-IP':ip})

    def close(self, client, key, ip='203.0.113.1', **data):
        return client.post('/v1/fechamentos',headers={'Authorization':f'Bearer {key}','X-Real-IP':ip},data={'periodo':'2026-09',**data},files=uploads())

    def stored_use_llm(self, closing_id):
        return self.conn.execute('SELECT usar_llm FROM fechamentos WHERE id=%s',(closing_id,)).fetchone()['usar_llm']

    def test_self_service_key_works_and_is_returned_once_with_the_notice(self):
        client = self.open()
        r = self.new_key(client)
        self.assertEqual(r.status_code,201,r.text)
        body = r.json()
        self.assertTrue(body['chave'].startswith('tk_'))
        self.assertTrue(body['usar_llm_padrao'])
        self.assertIn('Anthropic',body['aviso'])
        row = self.conn.execute('SELECT demo, chave_hash FROM clientes WHERE chave_hash=%s',(keys.hash_key(body['chave']),)).fetchone()
        self.assertTrue(row['demo'])
        self.assertNotEqual(row['chave_hash'],body['chave'])
        self.assertEqual(client.get('/v1/fechamentos/00000000-0000-0000-0000-000000000000',headers={'Authorization':f'Bearer {body["chave"]}'}).status_code,404)

    def test_demo_client_gets_suggestion_mode_for_movements_and_ceilings_stay(self):
        client = self.open()
        key = self.new_key(client).json()['chave']
        row = self.conn.execute("SELECT p.conteudo FROM politicas p JOIN clientes c ON c.id=p.cliente_id WHERE c.chave_hash=%s AND p.tipo='inference'",
                                (keys.hash_key(key),)).fetchone()
        classes = row['conteudo']['classes']
        self.assertEqual(classes['MOVIMENTO_SEM_REGRA']['modo'],'sugerir')
        self.assertEqual((classes['DECISAO']['teto'],classes['CONDICAO_COMERCIAL']['teto'],classes['DADO_INVALIDO']['teto']),('sugerir','sugerir','desligado'))

    def test_layer_is_on_by_default_while_the_demo_lasts_and_can_be_turned_off(self):
        client = self.open()
        key = self.new_key(client).json()['chave']
        on = self.close(client,key)
        self.assertEqual(on.status_code,202,on.text)
        self.assertTrue(self.stored_use_llm(on.json()['id']))
        off = self.close(client,key,usar_llm='false')
        self.assertFalse(self.stored_use_llm(off.json()['id']))
        regular = self.close(client,self.regular_key)
        self.assertTrue(self.stored_use_llm(regular.json()['id']))

    def test_after_the_deadline_keys_stop_and_the_layer_is_off_by_default(self):
        key = self.new_key(self.open()).json()['chave']
        client = self.open(active=False)
        self.assertEqual(self.new_key(client).status_code,410)
        r = client.get('/v1/fechamentos/00000000-0000-0000-0000-000000000000',headers={'Authorization':f'Bearer {key}'})
        self.assertEqual((r.status_code,r.json()['detail']),(401,'chave de demonstração expirada'))
        regular = self.close(client,self.regular_key)
        self.assertEqual(regular.status_code,202,regular.text)
        self.assertFalse(self.stored_use_llm(regular.json()['id']))

    def test_no_demo_configured_means_no_self_service(self):
        client = self.open(demo_ate=None)
        self.assertEqual(self.new_key(client).status_code,410)

    def test_keys_per_ip_are_limited(self):
        client = self.open(demo_keys_per_ip_hour=2)
        self.assertEqual([self.new_key(client).status_code for _ in range(2)],[201,201])
        limited = self.new_key(client)
        self.assertEqual(limited.status_code,429)
        self.assertTrue(limited.headers.get('retry-after'))
        self.assertEqual(self.new_key(client,ip='198.51.100.7').status_code,201)

    def test_closings_with_the_layer_are_limited_per_ip_and_without_it_are_not(self):
        client = self.open(demo_llm_closings_per_ip_hour=1)
        key = self.new_key(client).json()['chave']
        self.assertEqual(self.close(client,key).status_code,202)
        limited = self.close(client,key)
        self.assertEqual(limited.status_code,429,limited.text)
        self.assertEqual(self.close(client,key,usar_llm='false').status_code,202)
        self.assertEqual(self.close(client,key,ip='198.51.100.7').status_code,202)

    def test_demo_users_are_isolated_from_each_other(self):
        client = self.open()
        key_a, key_b = self.new_key(client).json()['chave'], self.new_key(client,ip='198.51.100.7').json()['chave']
        closing = self.close(client,key_a,usar_llm='false').json()['id']
        self.assertEqual(client.get(f'/v1/fechamentos/{closing}',headers={'Authorization':f'Bearer {key_a}'}).status_code,200)
        self.assertEqual(client.get(f'/v1/fechamentos/{closing}',headers={'Authorization':f'Bearer {key_b}'}).status_code,404)


if __name__ == '__main__':
    unittest.main()
