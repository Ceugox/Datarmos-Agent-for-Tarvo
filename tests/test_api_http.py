from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from zipfile import ZipFile
import json
import os
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))

from output_format import csv_errors
from test_cli_inference import PACK, files, run
from tarvo_close.resolver import FakeResolver

try:  # the engine CI job installs only requirements.txt
    from fastapi.testclient import TestClient
    from api import db, jobs, keys, policies, worker
    from api.app import ARQUIVOS_SAIDA, create_app
    from api.settings import Settings
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

TEST_DATABASE_URL = os.environ.get('TEST_DATABASE_URL')
TABLES = ('llm_cache','auditoria','decisoes','excecoes','jobs','fechamentos','politicas','clientes','schema_migrations')
CSV_TYPE = 'text/csv; charset=utf-8'
PACK_FILES = sorted(p for p in PACK.iterdir() if p.name[:2] in ('01','02','03','04','05','06'))


def pack_uploads():
    return [('arquivos',(p.name,p.read_bytes(),'application/octet-stream')) for p in PACK_FILES]


@unittest.skipUnless(TEST_DATABASE_URL and HAS_DEPS,'TEST_DATABASE_URL não definido ou dependências da API ausentes: testes da API pulados')
class ApiHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.cli = Path(cls.tmp.name)/'cli'
        code, _, _ = run(cls.cli,'--no-llm')
        assert code == 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

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
        self.id_a, self.key_a = keys.create_client(self.conn,'A')
        self.id_b, self.key_b = keys.create_client(self.conn,'B')
        self.open()

    def open(self, **overrides):
        values = dict(database_url=TEST_DATABASE_URL,data_dir=self.data.name,worker_in_process=False,rate_limit_per_minute=1000)
        self.settings = Settings(**{**values,**overrides})
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)

    def factory(self):
        return db.connect(TEST_DATABASE_URL)

    def auth(self, key=None):
        return {'Authorization':f'Bearer {key or self.key_a}'}

    def post(self, uploads=None, key=None, **data):
        return self.client.post('/v1/fechamentos',headers=self.auth(key),data={'periodo':'2026-09',**data},files=pack_uploads() if uploads is None else uploads)

    def work(self, resolver=None):
        self.assertTrue(worker.run_once(self.factory,self.settings,resolver))

    def closing(self, key=None, resolver=None, **data):
        response = self.post(key=key,**data)
        self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(response.json()['status'],'NA_FILA')
        self.work(resolver)
        fid = response.json()['id']
        info = self.client.get(f'/v1/fechamentos/{fid}',headers=self.auth(key)).json()
        return fid, info

    def get_file(self, fid, name, key=None):
        return self.client.get(f'/v1/fechamentos/{fid}/arquivos/{name}',headers=self.auth(key))

    def check_csvs(self, fid, reference=None):
        for name in sorted(ARQUIVOS_SAIDA):
            if not name.endswith('.csv'):
                continue
            response = self.get_file(fid,name)
            self.assertEqual(response.status_code,200,name)
            self.assertEqual(response.headers['content-type'],CSV_TYPE,name)
            self.assertEqual(csv_errors(name,response.content),[],name)
            if reference:
                self.assertEqual(response.content,(reference/name).read_bytes(),name)

    def test_health(self):
        response = self.client.get('/health')
        self.assertEqual((response.status_code,response.json()),(200,{'status':'ok','banco':'ok'}))

    def test_no_cors_middleware(self):
        response = self.client.get('/health',headers={'Origin':'https://x.test'})
        self.assertNotIn('access-control-allow-origin',response.headers)

    def test_routes_require_a_valid_key(self):
        fid = '00000000-0000-4000-8000-000000000000'
        calls = [('post','/v1/fechamentos'),('get',f'/v1/fechamentos/{fid}'),('get',f'/v1/fechamentos/{fid}/arquivos/pendencias.csv'),
                 ('get',f'/v1/fechamentos/{fid}/excecoes'),('get',f'/v1/fechamentos/{fid}/auditoria'),('post','/v1/excecoes/1/decisao')]
        for headers in ({},{'Authorization':'Bearer tk_errada'},{'Authorization':'Basic abc'},{'Authorization':'Bearer'}):
            for method, path in calls:
                response = getattr(self.client,method)(path,headers=headers)
                self.assertEqual((response.status_code,response.json()),(401,{'detail':'chave inválida'}),(method,path,headers))

    def test_closing_from_files_matches_the_cli_bytes(self):
        fid, info = self.closing()
        self.assertEqual(info['status'],'PROVISORIO' if info['metrics']['status'] == 'PROVISORIO' else 'CONCLUIDO')
        self.assertEqual((info['periodo'],info['usar_llm'],info['numero_revisao'],info['pai_id'],info['revisoes'],info['aviso'],info['erro']),('2026-09',False,0,None,[],None,None))
        self.assertTrue(info['run_id'].startswith('2026-09-'))
        self.assertEqual(info['excecoes']['por_classe'],{'DECISAO':8,'ESPERA_EVIDENCIA':2,'CONDICAO_COMERCIAL':2,'ESPERA_DADO':1})  # the queue exists without the layer
        self.assertEqual(self.get_file(fid,'auditoria.jsonl').status_code,404)
        self.check_csvs(fid,self.cli)
        for name in ('checks.json','metrics.json','policy.json'):
            self.assertEqual(self.get_file(fid,name).content,(self.cli/name).read_bytes(),name)
        self.assertEqual(self.get_file(fid,'metrics.json').headers['content-type'],'application/json')
        self.assertEqual(self.get_file(fid,'index.html').headers['content-type'],'text/html; charset=utf-8')
        self.assertEqual(self.get_file(fid,'contestacoes/rascunho_orbe.txt').headers['content-type'],'text/plain; charset=utf-8')
        self.assertEqual(self.get_file(fid,'index.html').headers['x-content-type-options'],'nosniff')

    def test_closing_from_zip(self):
        buffer = BytesIO()
        with ZipFile(buffer,'w') as archive:
            for path in PACK_FILES:
                archive.writestr(path.name,path.read_bytes())
        response = self.post(uploads=[('arquivos',('pacote-set2026.zip',buffer.getvalue(),'application/zip'))])
        self.assertEqual(response.status_code,202,response.text)
        self.work()
        fid = response.json()['id']
        self.assertIn(self.client.get(f'/v1/fechamentos/{fid}',headers=self.auth()).json()['status'],('CONCLUIDO','PROVISORIO'))
        self.check_csvs(fid,self.cli)

    def test_use_llm_without_key_warns_and_matches_no_llm(self):
        fid, info = self.closing(usar_llm='true')
        self.assertIn(info['status'],('CONCLUIDO','PROVISORIO'))
        self.assertTrue(info['usar_llm'])
        self.assertIn('ANTHROPIC_API_KEY',info['aviso'])
        self.assertEqual(self.get_file(fid,'auditoria.jsonl').status_code,404)
        self.check_csvs(fid,self.cli)

    def test_other_client_gets_404_everywhere(self):
        fid, _ = self.closing(resolver=FakeResolver(),usar_llm='true')
        row = self.conn.execute('SELECT id FROM excecoes LIMIT 1').fetchone()
        paths = [f'/v1/fechamentos/{fid}',f'/v1/fechamentos/{fid}/arquivos/pendencias.csv',f'/v1/fechamentos/{fid}/excecoes',f'/v1/fechamentos/{fid}/auditoria']
        for path in paths:
            self.assertEqual(self.client.get(path,headers=self.auth()).status_code,200,path)
            self.assertEqual(self.client.get(path,headers=self.auth(self.key_b)).status_code,404,path)
        body = {'decisao':'aprovar','decidido_por':'Helena','motivo':'ok'}
        self.assertEqual(self.client.post(f'/v1/excecoes/{row["id"]}/decisao',headers=self.auth(self.key_b),json=body).status_code,404)
        self.assertEqual(self.client.get('/v1/fechamentos/nao-e-uuid',headers=self.auth()).status_code,404)

    def test_download_outside_the_list_is_404(self):
        fid, _ = self.closing()
        for name in ('anexos/01_orbe_relatorio_comissoes_set2026.csv','../../clientes','..%2F..%2Fetc%2Fpasswd','nao_existe.csv','pendencias.csv/../manifest.json2','%2e%2e/saida/pendencias.csv'):
            self.assertEqual(self.get_file(fid,name).status_code,404,name)

    def test_download_before_done_is_409(self):
        response = self.post()
        fid = response.json()['id']
        self.assertEqual(self.get_file(fid,'pendencias.csv').status_code,409)
        self.assertEqual(self.client.get(f'/v1/fechamentos/{fid}',headers=self.auth()).json()['status'],'NA_FILA')

    def entrada_dirs(self):
        return list(Path(self.data.name).rglob('entrada'))

    def test_oversize_upload_is_413_before_writing(self):
        self.open(max_upload_mb=1)
        big = b'x;y\n'+b'a;b\n'*(300*1024)
        response = self.post(uploads=[('arquivos',('01_orbe.csv',big,'text/csv'))])
        self.assertEqual(response.status_code,413)
        self.assertEqual(self.entrada_dirs(),[])
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM fechamentos').fetchone()['n'],0)

    def test_invalid_uploads_are_rejected_before_writing(self):
        ok = ('01_orbe.csv',b'a;b\n','text/csv')
        cases = [([('arquivos',('../01_orbe.csv',b'x','text/csv'))],'nome com ..'),
                 ([('arquivos',('a/01_orbe.csv',b'x','text/csv'))],'nome com barra'),
                 ([('arquivos',('01 orbe.csv',b'x','text/csv'))],'nome com espaço'),
                 ([('arquivos',('segredo.csv',b'x','text/csv'))],'prefixo desconhecido'),
                 ([('arquivos',('01_orbe.xlsx',b'x','text/csv'))],'extensão errada'),
                 ([('arquivos',ok),('arquivos',('pacote.zip',b'PK','application/zip'))],'zip misturado'),
                 ([('arquivos',ok),('arquivos',ok)],'nome repetido'),
                 ([],'sem arquivos')]
        for uploads, label in cases:
            if uploads:
                response = self.post(uploads=uploads)
            else:
                response = self.client.post('/v1/fechamentos',headers=self.auth(),data={'periodo':'2026-09'},files={'x':('y','z')})
            self.assertEqual(response.status_code,422,label)
        for data in ({'periodo':'2026-13'},{'periodo':'setembro'},{'usar_llm':'talvez'}):
            self.assertEqual(self.post(**data).status_code,422,data)
        self.assertEqual(self.entrada_dirs(),[])
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM fechamentos').fetchone()['n'],0)

    def test_chunked_upload_without_content_length_is_411(self):
        def body():
            yield b'--x--'
        response = self.client.post('/v1/fechamentos',headers={**self.auth(),'Content-Type':'multipart/form-data; boundary=x'},content=body())
        self.assertEqual((response.status_code,response.json()),(411,{'detail':'Content-Length obrigatório'}))
        self.assertEqual(self.entrada_dirs(),[])

    def test_non_ascii_digit_exception_id_is_404(self):
        body = {'decisao':'aprovar','decidido_por':'H','motivo':'m'}
        for eid in ('%C2%B2','99999999999','abc'):
            self.assertEqual(self.client.post(f'/v1/excecoes/{eid}/decisao',headers=self.auth(),json=body).status_code,404,eid)

    def test_rate_limit_is_429_with_retry_after(self):
        self.open(rate_limit_per_minute=3)
        codes = [self.client.get('/v1/fechamentos/nao-e-uuid',headers=self.auth()).status_code for _ in range(3)]
        self.assertEqual(codes,[404,404,404])
        response = self.client.get('/v1/fechamentos/nao-e-uuid',headers=self.auth())
        self.assertEqual(response.status_code,429)
        self.assertGreaterEqual(int(response.headers['retry-after']),1)
        self.assertEqual(self.client.get('/v1/fechamentos/nao-e-uuid',headers=self.auth(self.key_b)).status_code,404)  # per client
        self.assertEqual(self.client.get('/health').status_code,200)

    def exception_of(self, fid, classe='DECISAO'):
        rows = self.client.get(f'/v1/fechamentos/{fid}/excecoes',headers=self.auth()).json()
        return next(r for r in rows if r['classe'] == classe)

    def test_decision_creates_a_revision_with_audit(self):
        fid, info = self.closing(resolver=FakeResolver(),usar_llm='true')
        self.assertIsNone(info['aviso'])
        self.assertEqual(self.get_file(fid,'auditoria.jsonl').status_code,200)
        self.assertGreater(sum(info['excecoes']['por_classe'].values()),0)
        self.assertIn('DECISAO',info['excecoes']['por_classe'])
        audit = self.client.get(f'/v1/fechamentos/{fid}/auditoria',headers=self.auth()).json()['eventos']
        self.assertEqual(audit[-1]['evento'],'EXECUCAO')
        exc = self.exception_of(fid)
        self.assertEqual(exc['pendencia_status'],'PENDENTE')
        self.assertFalse(exc['aplicada'])
        self.assertEqual(self.client.post(f'/v1/excecoes/{exc["id"]}/decisao',headers=self.auth(),json={'decisao':'talvez','decidido_por':'H','motivo':'m'}).status_code,422)
        self.assertEqual(self.client.post(f'/v1/excecoes/{exc["id"]}/decisao',headers=self.auth(),json={'decisao':'aprovar','decidido_por':' ','motivo':'m'}).status_code,422)
        body = {'decisao':'aprovar','decidido_por':'Helena','motivo':'Conferido com o comercial'}
        response = self.client.post(f'/v1/excecoes/{exc["id"]}/decisao',headers=self.auth(),json=body)
        self.assertEqual(response.status_code,202,response.text)
        rev = response.json()['revisao_id']
        self.assertEqual(response.json()['status'],'NA_FILA')
        saved = self.conn.execute('SELECT * FROM decisoes').fetchall()
        self.assertEqual([(d['excecao_id'],d['decisao'],d['decidido_por'],str(d['revisao_id'])) for d in saved],[(exc['excecao_id'],'aprovar','Helena',rev)])
        self.assertEqual(self.client.post(f'/v1/excecoes/{exc["id"]}/decisao',headers=self.auth(),json=body).status_code,409)  # revision still queued
        self.work()
        revision = self.client.get(f'/v1/fechamentos/{rev}',headers=self.auth()).json()
        self.assertIn(revision['status'],('CONCLUIDO','PROVISORIO'))
        self.assertEqual((revision['numero_revisao'],revision['pai_id']),(1,fid))
        self.assertTrue(revision['run_id'].startswith('2026-09-rev1-'))
        self.assertEqual(self.client.get(f'/v1/fechamentos/{fid}',headers=self.auth()).json()['revisoes'],[rev])
        applied = self.exception_of(rev)
        self.assertEqual((applied['excecao_id'],applied['pendencia_status']),(exc['excecao_id'],'APROVADA'))
        csv_text = self.get_file(rev,'pendencias.csv').content.decode('utf-8')
        self.assertIn('APROVADA',csv_text)
        self.check_csvs(rev)
        events = self.client.get(f'/v1/fechamentos/{rev}/auditoria',headers=self.auth()).json()['eventos']
        decided = [e for e in events if e['evento'] == 'DECISAO_APLICADA' and not e.get('herdado')]
        self.assertEqual([(e['excecao_id'],e['decisao'],e['decidido_por'],e['resultado']) for e in decided],[(exc['excecao_id'],'aprovar','Helena','REGISTRADA')])
        self.assertEqual(events[0]['evento'],'REVISAO')
        self.assertEqual(self.get_file(fid,'pendencias.csv').content.decode('utf-8').count('APROVADA'),0)  # the parent run is untouched
        # deciding again on the same exception fails inside the revision job, not in the request
        again = self.client.post(f'/v1/excecoes/{exc["id"]}/decisao',headers=self.auth(),json={**body,'decisao':'rejeitar'})
        self.assertEqual(again.status_code,202)
        self.work()
        failed = self.client.get(f'/v1/fechamentos/{again.json()["revisao_id"]}',headers=self.auth()).json()
        self.assertEqual(failed['status'],'ERRO')
        self.assertIn('already decided',failed['erro'])
        self.assertNotIn('Traceback',failed['erro'])

    def test_queue_exists_without_the_layer(self):
        fid, _ = self.closing()
        rows = self.client.get(f'/v1/fechamentos/{fid}/excecoes',headers=self.auth()).json()
        self.assertEqual(len(rows),13)
        for row in rows:
            self.assertEqual((row['resultado'],row['pendencia_status'],row['motivo'],row['proposta'],row['verificacoes'],row['aplicada']),('SEM_CAMADA','PENDENTE',None,None,[],False),row)
            self.assertTrue(all(row[k] for k in ('classe','tipo','modo','quem_decide','motivo_pendencia')),row)
            self.assertIsInstance(row['escopo'],str)  # may be empty for a class without scope
            self.assertTrue(row['valor_brl'] is None or isinstance(row['valor_brl'],str),row)
        self.assertEqual({r['modo'] for r in rows if r['classe'] in ('DECISAO','CONDICAO_COMERCIAL')},{'sugerir'})
        self.assertEqual(self.client.get(f'/v1/fechamentos/{fid}/auditoria',headers=self.auth()).json()['eventos'],[])

    def test_decision_on_a_closing_without_the_layer_creates_a_revision(self):
        fid, _ = self.closing()
        exc = self.exception_of(fid)
        body = {'decisao':'aprovar','decidido_por':'Helena','motivo':'Conferido com o comercial'}
        response = self.client.post(f'/v1/excecoes/{exc["id"]}/decisao',headers=self.auth(),json=body)
        self.assertEqual(response.status_code,202,response.text)
        rev = response.json()['revisao_id']
        self.work()
        revision = self.client.get(f'/v1/fechamentos/{rev}',headers=self.auth()).json()
        self.assertIn(revision['status'],('CONCLUIDO','PROVISORIO'),revision['erro'])
        self.assertEqual(sum(revision['excecoes']['por_classe'].values()),13)
        rows = self.client.get(f'/v1/fechamentos/{rev}/excecoes',headers=self.auth()).json()
        self.assertEqual([r['pendencia_status'] for r in rows if r['excecao_id'] == exc['excecao_id']],['APROVADA'])
        self.assertEqual(sum(r['pendencia_status'] == 'PENDENTE' for r in rows),12)
        self.assertIn('APROVADA',self.get_file(rev,'pendencias.csv').content.decode('utf-8'))
        events = self.client.get(f'/v1/fechamentos/{rev}/auditoria',headers=self.auth()).json()['eventos']
        decided = [e for e in events if e['evento'] == 'DECISAO_APLICADA' and not e.get('herdado')]
        self.assertEqual([(e['excecao_id'],e['decidido_por'],e['motivo'],e['resultado']) for e in decided],[(exc['excecao_id'],'Helena','Conferido com o comercial','REGISTRADA')])
        for name in ('lancamentos_classificados.csv','comissoes_por_lojista.csv'):
            self.assertEqual(self.get_file(rev,name).content,self.get_file(fid,name).content,name)
        self.check_csvs(rev)

    def test_approve_without_proposal_is_refused_and_recorded(self):
        policy = json.loads((ROOT/'config'/'closing-policy.json').read_text(encoding='utf-8'))
        policy['bank_rules'] = [r for r in policy['bank_rules'] if r['id'] != 'bank-fees']
        policies.seed_tarvo(self.conn,self.id_a)
        self.conn.execute("INSERT INTO politicas (cliente_id, tipo, versao, conteudo) VALUES (%s,'closing',2,%s)",(self.id_a,json.dumps(policy)))
        self.conn.commit()
        fid, _ = self.closing()
        rows = self.client.get(f'/v1/fechamentos/{fid}/excecoes',headers=self.auth()).json()
        movements = [r for r in rows if r['classe'] == 'MOVIMENTO_SEM_REGRA']
        self.assertEqual((len(movements),{r['tipo'] for r in movements}),(4,{'CONCILIACAO_BANCARIA'}))
        exc = movements[0]
        response = self.client.post(f'/v1/excecoes/{exc["id"]}/decisao',headers=self.auth(),json={'decisao':'aprovar','decidido_por':'Helena','motivo':'Conferido'})
        self.assertEqual(response.status_code,202,response.text)
        rev = response.json()['revisao_id']
        self.work()
        revision = self.client.get(f'/v1/fechamentos/{rev}',headers=self.auth()).json()
        self.assertIn(revision['status'],('CONCLUIDO','PROVISORIO'),revision['erro'])
        events = self.client.get(f'/v1/fechamentos/{rev}/auditoria',headers=self.auth()).json()['eventos']
        decided = [e for e in events if e['evento'] == 'DECISAO_APLICADA' and not e.get('herdado')]
        self.assertEqual([(e['excecao_id'],e['resultado']) for e in decided],[(exc['excecao_id'],'RECUSADA')])
        self.assertTrue(decided[0].get('motivo_recusa'))
        mine = [r for r in self.client.get(f'/v1/fechamentos/{rev}/excecoes',headers=self.auth()).json() if r['excecao_id'] == exc['excecao_id']]
        self.assertEqual([r['pendencia_status'] for r in mine],['PENDENTE'])
        for name in ('lancamentos_classificados.csv','comissoes_por_lojista.csv'):
            self.assertEqual(self.get_file(rev,name).content,self.get_file(fid,name).content,name)
        self.check_csvs(rev)

    def test_decision_on_a_parent_without_marker_is_409(self):
        fid, _ = self.closing()
        exc = self.exception_of(fid)
        manifest = worker.result_dir(self.settings,self.id_a,fid,0)/'manifest.json'
        data = json.loads(manifest.read_text(encoding='utf-8'))
        del data['camada']  # an old run: no marker and no auditoria.jsonl
        manifest.write_text(json.dumps(data),encoding='utf-8')
        response = self.client.post(f'/v1/excecoes/{exc["id"]}/decisao',headers=self.auth(),json={'decisao':'aprovar','decidido_por':'H','motivo':'m'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM decisoes').fetchone()['n'],0)

    def test_worker_error_marks_the_closing_as_error(self):
        response = self.post(uploads=[('arquivos',('pacote.zip',b'isto nao e um zip','application/zip'))])
        self.work()
        info = self.client.get(f'/v1/fechamentos/{response.json()["id"]}',headers=self.auth()).json()
        self.assertEqual(info['status'],'ERRO')
        self.assertTrue(info['erro'])
        self.assertNotIn('Traceback',info['erro'])
        self.assertEqual(self.conn.execute('SELECT status FROM jobs').fetchone()['status'],'ERRO')
        self.assertFalse(worker.run_once(self.factory,self.settings))

    def test_in_process_worker_runs_from_the_lifespan(self):
        self.open(worker_in_process=True)
        response = self.post()
        fid = response.json()['id']
        for _ in range(300):
            status = self.client.get(f'/v1/fechamentos/{fid}',headers=self.auth()).json()['status']
            if status in ('CONCLUIDO','PROVISORIO','ERRO'):
                break
            time.sleep(0.1)
        self.assertIn(status,('CONCLUIDO','PROVISORIO'))


if __name__ == '__main__':
    unittest.main()
