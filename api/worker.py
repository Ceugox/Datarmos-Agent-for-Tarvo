"""Job worker: runs closings and revisions with the same runner functions the CLI uses (ADR 0002, Fase 4)."""
from pathlib import Path
import csv
import json
import logging
import shutil
import tempfile
import threading
import time

from psycopg.types.json import Jsonb

from api import jobs, storage
from api.cache import PostgresResponseCache
from api.db import connect, migrate
from api.settings import Settings
from tarvo_close import runner
from tarvo_close.inference_policy import load_inference_policy
from tarvo_close.resolver import TokenBudget

log = logging.getLogger('api')
USER_ERRORS = (ValueError, KeyError, TypeError, OSError, ImportError)


def lineage_root(conn, fechamento_id):
    """The original closing of a lineage (revisions have no upload of their own)."""
    current = fechamento_id
    while True:
        row = conn.execute('SELECT pai_id FROM fechamentos WHERE id=%s',(current,)).fetchone()
        if row is None or row['pai_id'] is None:
            return current
        current = row['pai_id']


def input_path(settings, cliente_id, root_id):
    folder = storage.input_dir(settings,cliente_id,root_id)
    zips = sorted(folder.glob('*.zip'))
    return zips[0] if len(zips) == 1 else folder


def result_dir(settings, cliente_id, root_id, numero):
    return storage.output_dir(settings,cliente_id,root_id) if not numero else storage.revision_dir(settings,cliente_id,root_id,numero)


def _policy(conn, policy_id):
    return conn.execute('SELECT conteudo FROM politicas WHERE id=%s',(policy_id,)).fetchone()['conteudo']


def _validated_inference(content):
    with tempfile.TemporaryDirectory(prefix='inference-policy-') as folder:  # reuse the file validator the CLI uses
        path = Path(folder)/'inference-policy.json'
        path.write_text(json.dumps(content),encoding='utf-8')
        return load_inference_policy(path)


def _read_jsonl(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def _store(conn, fech, out, done, revision):
    metrics = json.loads((out/'metrics.json').read_text(encoding='utf-8'))
    checks = json.loads((out/'checks.json').read_text(encoding='utf-8'))
    status = 'PROVISORIO' if metrics.get('status') == 'PROVISORIO' else 'CONCLUIDO'
    conn.execute('UPDATE fechamentos SET status=%s, run_id=%s, metrics=%s, checks=%s, erro=NULL, concluido_em=now() WHERE id=%s',
                 (status,done['manifest']['run_id'],Jsonb(metrics),Jsonb(checks),fech['id']))
    events = _read_jsonl(out/'auditoria.jsonl')
    conn.execute('DELETE FROM auditoria WHERE fechamento_id=%s',(fech['id'],))
    conn.execute('DELETE FROM excecoes WHERE fechamento_id=%s',(fech['id'],))
    for seq, event in enumerate(events):
        conn.execute('INSERT INTO auditoria (fechamento_id, seq, evento) VALUES (%s,%s,%s)',(fech['id'],seq,Jsonb(event)))
    with open(out/'pendencias.csv',encoding='utf-8',newline='') as handle:
        pending = {row['id_saida']:row['status'] for row in csv.DictReader(handle,delimiter=';')}
    decided = {e['excecao_id'] for e in events if e.get('evento') == 'DECISAO_APLICADA' and e.get('resultado') == 'APLICADA'}
    seen = set()
    for event in events:
        # an original run stores its own events; a revision stores the inherited ones too, so its rows carry the new pendencia_status
        if event.get('evento') != 'EXCECAO' or (event.get('herdado') and not revision) or event['excecao_id'] in seen:
            continue
        seen.add(event['excecao_id'])
        conn.execute('INSERT INTO excecoes (fechamento_id, excecao_id, classe, tipo, modo, resultado, motivo, proposta, verificacoes, aplicada, pendencia_status) '
                     'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                     (fech['id'],event['excecao_id'],event['classe'],event['tipo'],event['modo'],event['resultado'],event.get('motivo'),
                      Jsonb(event['proposta']) if event.get('proposta') is not None else None,Jsonb(event.get('verificacoes') or []),
                      bool(event.get('aplicada')) or event['excecao_id'] in decided,pending.get(event['excecao_id'])))
    return status


def process(job, conn, settings, resolver=None):
    started = time.monotonic()
    fech = conn.execute('SELECT * FROM fechamentos WHERE id=%s',(job['fechamento_id'],)).fetchone()
    conn.execute("UPDATE fechamentos SET status='PROCESSANDO' WHERE id=%s",(fech['id'],))
    conn.commit()
    status = 'ERRO'
    try:
        closing = _policy(conn,fech['politica_closing_id'])
        inference = _validated_inference(_policy(conn,fech['politica_inference_id']))
        cliente, root = fech['cliente_id'], lineage_root(conn,fech['id'])
        source = input_path(settings,cliente,root)
        out = result_dir(settings,cliente,root,fech['numero_revisao'])
        shutil.rmtree(out,ignore_errors=True)
        warning = None
        if job['tipo'] == 'REVISAO':
            payload = job['payload']
            parent = conn.execute('SELECT numero_revisao FROM fechamentos WHERE id=%s',(payload['pai_id'],)).fetchone()
            done = runner.run_revision_closing(source,closing,inference,fech['periodo'],out,result_dir(settings,cliente,root,parent['numero_revisao']),payload['decisoes'])
        else:
            done = runner.run_closing(source,closing,inference,fech['periodo'],out,resolver=resolver,cache=PostgresResponseCache(lambda: connect(settings.database_url),cliente),
                                      budget=TokenBudget(settings.llm_budget_tokens),use_llm=fech['usar_llm'])
            warning = done['aviso']
        status = _store(conn,fech,out,done,job['tipo'] == 'REVISAO')
        conn.execute('UPDATE fechamentos SET aviso=%s WHERE id=%s',(warning,fech['id']))
        jobs.finish(conn,job['id'])
    except Exception as error:  # the job must always end in a final state; the message never carries a traceback
        conn.rollback()
        message = f'{type(error).__name__}: {error}'[:500] if isinstance(error,USER_ERRORS) and not isinstance(error,OSError) else f'Erro interno ao processar ({type(error).__name__})'
        conn.execute("UPDATE fechamentos SET status='ERRO', erro=%s, concluido_em=now() WHERE id=%s",(message,fech['id']))
        jobs.fail(conn,job['id'],message)
    log.info('job id=%s fechamento=%s tipo=%s status=%s duracao_s=%.2f',job['id'],fech['id'],job['tipo'],status,time.monotonic()-started)
    return status


def run_once(conn_factory, settings, resolver=None):
    """Process one queued job. False when the queue is empty."""
    with conn_factory() as conn:
        job = jobs.claim(conn)
        conn.commit()
        if job is None:
            return False
        process(job,conn,settings,resolver)
    return True


def run_forever(conn_factory, settings, interval=1.0, stop=None, resolver=None):
    stop = stop or threading.Event()
    while not stop.is_set():
        try:
            worked = run_once(conn_factory,settings,resolver)
        except Exception as error:  # database down: keep the loop alive
            log.error('worker erro=%s',type(error).__name__)
            worked = False
        if not worked:
            stop.wait(interval)


def main():
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    with connect(settings.database_url) as conn:
        migrate(conn)
    run_forever(lambda: connect(settings.database_url),settings)


if __name__ == '__main__':
    main()
