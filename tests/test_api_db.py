from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT))

try:
    from api import cache, db, jobs, keys, policies, storage
    from api.settings import Settings
    from tarvo_close.llm_cache import ResponseCache
    HAS_DEPS = True
except ImportError:  # job `tests` of the CI installs only requirements.txt
    HAS_DEPS = False

TEST_DATABASE_URL = os.environ.get('TEST_DATABASE_URL')
TABLES = ('llm_cache','auditoria','decisoes','excecoes','jobs','fechamentos','politicas','clientes','schema_migrations')


@unittest.skipUnless(TEST_DATABASE_URL and HAS_DEPS,'TEST_DATABASE_URL não definido ou dependências da API ausentes: testes da API pulados')
class ApiDbTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(TEST_DATABASE_URL)
        self.addCleanup(self.conn.close)
        db.migrate(self.conn)
        self.conn.execute('TRUNCATE '+', '.join(TABLES)+' CASCADE')
        self.conn.commit()
        db.migrate(self.conn)

    def factory(self):
        return db.connect(TEST_DATABASE_URL)

    def new_fechamento(self, cliente_id):
        fid = uuid.uuid4()
        self.conn.execute("INSERT INTO fechamentos (id, cliente_id, periodo, status) VALUES (%s,%s,'2026-09','NA_FILA')",(fid,cliente_id))
        self.conn.commit()
        return fid

    def test_migrate_twice_does_not_rerun(self):
        expected = sorted(path.name for path in (ROOT/'api'/'migrations').glob('*.sql'))
        self.assertEqual(db.migrate(self.conn),[])  # setUp already applied everything
        applied = sorted(row['nome'] for row in self.conn.execute('SELECT nome FROM schema_migrations'))
        self.assertEqual(applied,expected)
        self.conn.execute('TRUNCATE schema_migrations')
        self.conn.commit()
        self.assertEqual(db.migrate(self.conn),expected)  # IF NOT EXISTS: reapplying is harmless, in order
        self.assertEqual(db.migrate(self.conn),[])

    def test_keys_hash_and_lookup(self):
        cid, key = keys.create_client(self.conn,'Tarvo',pepper='p')
        self.assertTrue(key.startswith('tk_'))
        stored = self.conn.execute('SELECT chave_hash FROM clientes WHERE id=%s',(cid,)).fetchone()['chave_hash']
        self.assertNotIn(key,stored)
        self.assertEqual(keys.find_client(self.conn,key,'p')['id'],cid)
        self.assertIsNone(keys.find_client(self.conn,key+'x','p'))
        self.assertIsNone(keys.find_client(self.conn,key,'outro'))
        self.assertIsNone(keys.find_client(self.conn,'','p'))

    def test_cache_isolated_per_client(self):
        a, _ = keys.create_client(self.conn,'A')
        b, _ = keys.create_client(self.conn,'B')
        cache_a, cache_b = cache.PostgresResponseCache(self.factory,a), cache.PostgresResponseCache(self.factory,b)
        payload = {'linha':'L1','valor':'1.00'}
        key = cache_a.key('v1','modelo',payload)
        self.assertEqual(key,ResponseCache('x').key('v1','modelo',payload))
        self.assertIsNone(cache_a.get(key))
        cache_a.put(key,{'acao':'X','n':1})
        self.assertEqual(cache_a.get(key),{'acao':'X','n':1})
        self.assertIsNone(cache_b.get(key))
        cache_b.put(key,{'acao':'Y'})  # same key, own row: neither overwrites the other
        self.assertEqual(cache_a.get(key),{'acao':'X','n':1})
        self.assertEqual(cache_b.get(key),{'acao':'Y'})
        cache_a.put(key,{'acao':'Z'})
        self.assertEqual(cache_a.get(key),{'acao':'Z'})
        self.assertEqual(cache_b.get(key),{'acao':'Y'})

    def test_seed_and_current(self):
        cid, _ = keys.create_client(self.conn,'Tarvo')
        with self.assertRaises(ValueError):
            policies.current(self.conn,cid,'closing')
        self.assertEqual(policies.seed_tarvo(self.conn,cid),['closing','inference'])
        self.assertEqual(policies.seed_tarvo(self.conn,cid),[])
        _, closing = policies.current(self.conn,cid,'closing')
        _, inference = policies.current(self.conn,cid,'inference')
        self.assertIn('MOVIMENTO_SEM_REGRA',inference['classes'])
        self.assertEqual(inference['classes']['MOVIMENTO_SEM_REGRA']['modo'],'sombra')
        self.assertTrue(closing)
        self.conn.execute("INSERT INTO politicas (cliente_id, tipo, versao, conteudo) VALUES (%s,'closing',2,'{\"v\":2}')",(cid,))
        self.conn.commit()
        self.assertEqual(policies.current(self.conn,cid,'closing')[1],{'v':2})

    def test_claim_skips_locked_job(self):
        cid, _ = keys.create_client(self.conn,'Tarvo')
        fid = self.new_fechamento(cid)
        first = jobs.enqueue(self.conn,fid,'FECHAMENTO',{'x':1})
        second = jobs.enqueue(self.conn,fid,'REVISAO',{})
        other = self.factory()
        self.addCleanup(other.close)
        mine = jobs.claim(self.conn)  # not committed: the row stays locked
        self.assertEqual(mine['id'],first)
        self.assertEqual(mine['status'],'PROCESSANDO')
        self.assertEqual(mine['tentativas'],1)
        theirs = jobs.claim(other)
        self.assertEqual(theirs['id'],second)
        self.assertNotEqual(theirs['id'],mine['id'])
        self.assertIsNone(jobs.claim(other))
        other.rollback()
        self.conn.commit()
        jobs.finish(self.conn,first)
        jobs.fail(self.conn,second,'falhou')
        rows = {row['id']:row for row in self.conn.execute('SELECT * FROM jobs')}
        self.assertEqual(rows[first]['status'],'CONCLUIDO')
        self.assertEqual((rows[second]['status'],rows[second]['erro']),('ERRO','falhou'))

    def test_storage_refuses_escape(self):
        with TemporaryDirectory() as tmp:
            settings = Settings(data_dir=tmp)
            root = Path(tmp).resolve()
            self.assertEqual(storage.input_dir(settings,1,'abc'),root/'1'/'abc'/'entrada')
            self.assertEqual(storage.output_dir(settings,1,'abc'),root/'1'/'abc'/'saida')
            self.assertEqual(storage.revision_dir(settings,1,'abc',2),root/'1'/'abc'/'saida-rev-2')
            self.assertEqual(storage.closing_dir(settings,1,'abc'),root/'1'/'abc')
            for bad in ('..','../x','a/b','a\\b','',  '.'):
                with self.assertRaises(ValueError):
                    storage.closing_dir(settings,1,bad)
            with self.assertRaises(ValueError):
                storage.input_dir(settings,'..','abc')

    def test_connect_accepts_postgres_scheme(self):
        url = 'postgres://'+TEST_DATABASE_URL.split('://',1)[1]
        with db.connect(url) as conn:
            self.assertEqual(conn.execute('SELECT 1 AS um').fetchone()['um'],1)

    def test_settings_from_env(self):
        defaults = Settings.from_env({})
        self.assertEqual((defaults.port,defaults.max_upload_mb,defaults.rate_limit_per_minute,defaults.llm_budget_tokens),(8000,50,60,200000))
        self.assertTrue(defaults.worker_in_process)
        custom = Settings.from_env({'DATABASE_URL':'u','MAX_UPLOAD_MB':'1','WORKER_IN_PROCESS':'0','API_KEY_PEPPER':'p'})
        self.assertEqual((custom.database_url,custom.max_upload_mb,custom.worker_in_process,custom.api_key_pepper),('u',1,False,'p'))


if __name__ == '__main__':
    unittest.main()
