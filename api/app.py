"""HTTP service: a thin layer over the CLI functions (ADR 0002, Fase 4). No closing rule lives here."""
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
import logging
import math
import re
import shutil
import threading
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from psycopg.types.json import Jsonb

from api import db, jobs, keys, policies, storage, worker
from api.settings import Settings

log = logging.getLogger('api')

PERIOD = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')
FILENAME = re.compile(r'^[A-Za-z0-9._-]+$')
EXTENSIONS = {'01_':'.csv', '02_':'.xlsx', '03_':'.eml', '04_':'.csv', '05a_':'.csv', '05b_':'.ofx', '06_':'.csv'}
ARQUIVOS_SAIDA = {'comissoes_por_lojista.csv', 'divergencias_taxa.csv', 'notas_a_emitir.csv', 'lancamentos_classificados.csv', 'pendencias.csv', 'rastro.csv',
                  'cobertura.csv', 'checks.json', 'policy.json', 'metrics.json', 'manifest.json', 'index.html', 'auditoria.jsonl',
                  'contestacoes/operacoes_orbe.csv', 'contestacoes/rascunho_orbe.txt', 'contestacoes/operacoes_ponte.csv', 'contestacoes/rascunho_ponte.txt'}
MEDIA_TYPES = {'.csv':'text/csv; charset=utf-8', '.json':'application/json', '.html':'text/html; charset=utf-8', '.jsonl':'application/x-ndjson', '.txt':'text/plain; charset=utf-8'}
FINAL = ('CONCLUIDO','PROVISORIO')


class RateLimiter:
    """Sliding window per client, in memory: the limit is per process, not shared across instances."""
    def __init__(self, limit, window=60.0):
        self.limit, self.window, self.hits, self.lock = limit, window, {}, threading.Lock()

    def check(self, key):
        now = time.monotonic()
        with self.lock:
            queue = self.hits.setdefault(key,deque())
            while queue and now-queue[0] >= self.window:
                queue.popleft()
            if len(queue) >= self.limit:
                return max(1,math.ceil(self.window-(now-queue[0])))
            queue.append(now)
        return 0


class Decisao(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decisao: str = Field(pattern='^(aprovar|rejeitar|editar)$')
    decidido_por: str = Field(max_length=200)
    motivo: str = Field(max_length=2000)
    parametros: dict | None = None

    @field_validator('decidido_por','motivo')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('não pode ser vazio')
        return value.strip()


def parse_uuid(value):
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(404,'não encontrado')


def parse_bool(value):
    text = (value or 'false').strip().lower()
    if text in ('true','1','on','yes','sim'):
        return True
    if text in ('false','0','off','no','nao','não',''):
        return False
    raise HTTPException(422,'usar_llm deve ser true ou false')


def validate_names(uploads):
    names = []
    for upload in uploads:
        name = upload.filename or ''
        if not FILENAME.fullmatch(name) or set(name) == {'.'}:
            raise HTTPException(422,'nome de arquivo inválido: use só letras, números, ponto, hífen e sublinhado')
        names.append(name)
    if not names:
        raise HTTPException(422,'envie os arquivos do pacote ou um único .zip')
    if len(set(names)) != len(names):
        raise HTTPException(422,'nomes de arquivo repetidos')
    if len(names) == 1 and names[0].lower().endswith('.zip'):
        return
    for name in names:
        prefix = next((p for p in EXTENSIONS if name.startswith(p)),None)
        if prefix is None or not name.lower().endswith(EXTENSIONS[prefix]):
            raise HTTPException(422,f'arquivo fora do padrão do pacote: {name}')


def create_app(settings=None):
    settings = settings or Settings.from_env()
    limiter = RateLimiter(settings.rate_limit_per_minute)
    max_bytes = settings.max_upload_mb*1024*1024

    def factory():
        return db.connect(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        with factory() as conn:
            db.migrate(conn)
        stop, thread = threading.Event(), None
        if settings.worker_in_process:
            thread = threading.Thread(target=worker.run_forever,args=(factory,settings),kwargs={'stop':stop},name='tarvo-worker',daemon=True)
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(timeout=10)

    app = FastAPI(title='Tarvo Close API',lifespan=lifespan)
    app.state.settings, app.state.limiter = settings, limiter

    @app.middleware('http')
    async def no_sniff(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def get_conn():
        conn = factory()
        try:
            yield conn
        finally:
            conn.close()

    def current_client(request: Request, conn=Depends(get_conn)):
        match = re.fullmatch(r'Bearer\s+(\S+)',request.headers.get('authorization',''),re.IGNORECASE)
        client = keys.find_client(conn,match.group(1),settings.api_key_pepper) if match else None
        if client is None:
            raise HTTPException(401,'chave inválida',headers={'WWW-Authenticate':'Bearer'})
        wait = limiter.check(client['id'])
        if wait:
            log.info('rate limit cliente=%s',client['id'])
            raise HTTPException(429,'limite de requisições excedido',headers={'Retry-After':str(wait)})
        return client

    def own_fechamento(conn, client, raw_id):
        row = conn.execute('SELECT * FROM fechamentos WHERE id=%s AND cliente_id=%s',(parse_uuid(raw_id),client['id'])).fetchone()
        if row is None:
            raise HTTPException(404,'fechamento não encontrado')
        return row

    @app.get('/health')
    def health():
        try:
            with factory() as conn:
                conn.execute('SELECT 1')
        except Exception as error:
            log.error('health erro=%s',type(error).__name__)
            return JSONResponse({'status':'erro','banco':'indisponível'},status_code=503)
        return {'status':'ok','banco':'ok'}

    def save_upload(client, form):
        uploads = [item for item in form.getlist('arquivos') if hasattr(item,'filename')]
        period = form.get('periodo')
        if not isinstance(period,str) or not PERIOD.fullmatch(period):
            raise HTTPException(422,'periodo deve estar no formato AAAA-MM')
        use_llm = parse_bool(form.get('usar_llm') if isinstance(form.get('usar_llm'),str) else None)
        validate_names(uploads)
        if sum(item.size or 0 for item in uploads) > max_bytes:
            raise HTTPException(413,f'upload acima de {settings.max_upload_mb} MB')
        with factory() as conn:
            try:
                closing_id, closing = policies.current(conn,client['id'],'closing')
            except ValueError:
                policies.seed_tarvo(conn,client['id'])  # a new client starts from the Tarvo policies, versioned in its own rows
                closing_id, closing = policies.current(conn,client['id'],'closing')
            inference_id, _ = policies.current(conn,client['id'],'inference')
            fid = uuid.uuid4()
            folder = storage.input_dir(settings,client['id'],fid)
            folder.mkdir(parents=True)
            total = 0
            try:
                for upload in uploads:
                    target = folder/upload.filename
                    with open(target,'wb') as handle:
                        while chunk := upload.file.read(1024*1024):
                            total += len(chunk)
                            if total > max_bytes:
                                raise HTTPException(413,f'upload acima de {settings.max_upload_mb} MB')
                            handle.write(chunk)
                conn.execute("INSERT INTO fechamentos (id, cliente_id, periodo, status, usar_llm, politica_closing_id, politica_inference_id) VALUES (%s,%s,%s,'NA_FILA',%s,%s,%s)",
                             (fid,client['id'],period,use_llm,closing_id,inference_id))
                jobs.enqueue(conn,fid,'FECHAMENTO',{})
            except BaseException:
                conn.rollback()
                shutil.rmtree(storage.closing_dir(settings,client['id'],fid),ignore_errors=True)
                raise
        log.info('fechamento criado id=%s cliente=%s arquivos=%s bytes=%s',fid,client['id'],len(uploads),total)
        return fid

    @app.post('/v1/fechamentos',status_code=202)
    async def create_fechamento(request: Request, client=Depends(current_client)):
        length = request.headers.get('content-length')
        if length is None:  # chunked bodies would be parsed to disk whole before any count
            raise HTTPException(411,'Content-Length obrigatório')
        if not re.fullmatch(r'[0-9]{1,15}',length):
            raise HTTPException(400,'Content-Length inválido')
        if int(length) > max_bytes:
            raise HTTPException(413,f'upload acima de {settings.max_upload_mb} MB')
        if not request.headers.get('content-type','').lower().startswith('multipart/form-data'):
            raise HTTPException(422,'envie multipart/form-data')
        form = await request.form(max_files=50)
        try:
            fid = await run_in_threadpool(save_upload,client,form)
        finally:
            await form.close()
        return {'id':str(fid),'status':'NA_FILA'}

    @app.get('/v1/fechamentos/{fid}')
    def get_fechamento(fid: str, client=Depends(current_client), conn=Depends(get_conn)):
        row = own_fechamento(conn,client,fid)
        children = [r['id'] for r in conn.execute('SELECT id FROM fechamentos WHERE pai_id=%s ORDER BY numero_revisao, criado_em',(row['id'],))]
        counts = {'por_classe':{}, 'por_modo':{}}
        for item in conn.execute('SELECT classe, modo FROM excecoes WHERE fechamento_id=%s',(row['id'],)):
            for key, value in (('por_classe',item['classe']),('por_modo',item['modo'])):
                counts[key][value] = counts[key].get(value,0)+1
        return {'id':row['id'], 'periodo':row['periodo'], 'status':row['status'], 'usar_llm':row['usar_llm'], 'run_id':row['run_id'],
                'numero_revisao':row['numero_revisao'], 'pai_id':row['pai_id'], 'revisoes':children, 'metrics':row['metrics'], 'checks':row['checks'],
                'excecoes':counts, 'aviso':row['aviso'], 'erro':row['erro'],
                'criado_em':row['criado_em'], 'concluido_em':row['concluido_em']}

    @app.get('/v1/fechamentos/{fid}/arquivos/{nome:path}')
    def download(fid: str, nome: str, client=Depends(current_client), conn=Depends(get_conn)):
        row = own_fechamento(conn,client,fid)
        if nome not in ARQUIVOS_SAIDA:
            raise HTTPException(404,'arquivo não encontrado')
        if row['status'] not in FINAL:
            raise HTTPException(409,'fechamento ainda não concluído')
        folder = worker.result_dir(settings,client['id'],worker.lineage_root(conn,row['id']),row['numero_revisao'])
        path = (folder/nome).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise HTTPException(404,'arquivo não encontrado')
        return FileResponse(path,media_type=MEDIA_TYPES.get(path.suffix,'application/octet-stream'))

    @app.get('/v1/fechamentos/{fid}/excecoes')
    def list_excecoes(fid: str, client=Depends(current_client), conn=Depends(get_conn)):
        row = own_fechamento(conn,client,fid)
        return conn.execute('SELECT id, excecao_id, classe, tipo, modo, resultado, motivo, proposta, verificacoes, aplicada, pendencia_status FROM excecoes WHERE fechamento_id=%s ORDER BY id',(row['id'],)).fetchall()

    @app.get('/v1/fechamentos/{fid}/auditoria')
    def get_auditoria(fid: str, client=Depends(current_client), conn=Depends(get_conn)):
        row = own_fechamento(conn,client,fid)
        return {'eventos':[r['evento'] for r in conn.execute('SELECT evento FROM auditoria WHERE fechamento_id=%s ORDER BY seq',(row['id'],))]}

    @app.post('/v1/excecoes/{eid}/decisao',status_code=202)
    def decide(eid: str, body: Decisao, client=Depends(current_client), conn=Depends(get_conn)):
        if not re.fullmatch(r'[0-9]{1,10}',eid) or int(eid) > 2**31-1:
            raise HTTPException(404,'exceção não encontrada')
        exc = conn.execute('SELECT e.* FROM excecoes e JOIN fechamentos f ON f.id=e.fechamento_id WHERE e.id=%s AND f.cliente_id=%s',(int(eid),client['id'])).fetchone()
        if exc is None:
            raise HTTPException(404,'exceção não encontrada')
        root = worker.lineage_root(conn,exc['fechamento_id'])
        conn.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',(str(root),))  # one revision at a time per lineage
        lineage = conn.execute('WITH RECURSIVE l AS (SELECT * FROM fechamentos WHERE id=%s UNION ALL SELECT f.* FROM fechamentos f JOIN l ON f.pai_id=l.id) SELECT * FROM l ORDER BY numero_revisao DESC, criado_em DESC',(root,)).fetchall()
        ids = [r['id'] for r in lineage]
        if conn.execute("SELECT 1 FROM jobs WHERE fechamento_id = ANY(%s) AND status IN ('NA_FILA','PROCESSANDO')",(ids,)).fetchone():
            conn.rollback()
            raise HTTPException(409,'há um processamento em andamento nesta linhagem de fechamento')
        parent = next((r for r in lineage if r['status'] in FINAL),None)
        if parent is None:
            conn.rollback()
            raise HTTPException(409,'fechamento ainda não concluído')
        if not (worker.result_dir(settings,client['id'],root,parent['numero_revisao'])/'auditoria.jsonl').is_file():
            conn.rollback()
            raise HTTPException(409,'a execução não tem auditoria: decisões exigem uma execução com a camada de inferência (usar_llm)')
        child = uuid.uuid4()
        conn.execute("INSERT INTO fechamentos (id, cliente_id, periodo, status, usar_llm, numero_revisao, pai_id, politica_closing_id, politica_inference_id) VALUES (%s,%s,%s,'NA_FILA',%s,%s,%s,%s,%s)",
                     (child,client['id'],parent['periodo'],parent['usar_llm'],parent['numero_revisao']+1,parent['id'],parent['politica_closing_id'],parent['politica_inference_id']))
        conn.execute('INSERT INTO decisoes (fechamento_id, excecao_id, decisao, decidido_por, motivo, parametros, revisao_id) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                     (exc['fechamento_id'],exc['excecao_id'],body.decisao,body.decidido_por,body.motivo,Jsonb(body.parametros) if body.parametros is not None else None,child))
        decision = {'excecao_id':exc['excecao_id'], 'decisao':body.decisao, 'decidido_por':body.decidido_por, 'motivo':body.motivo}
        if body.parametros is not None:
            decision['parametros'] = body.parametros
        jobs.enqueue(conn,child,'REVISAO',{'decisoes':[decision], 'pai_id':str(parent['id']), 'original_id':str(root)})
        log.info('decisao excecao=%s fechamento=%s revisao=%s decisao=%s',exc['id'],exc['fechamento_id'],child,body.decisao)
        return {'revisao_id':str(child),'status':'NA_FILA'}

    return app


app = create_app()
