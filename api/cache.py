"""Response cache in Postgres, same interface as tarvo_close.llm_cache.ResponseCache, scoped by client."""
import hashlib

from psycopg.types.json import Jsonb

from tarvo_close.llm_cache import canonical


class PostgresResponseCache:
    def __init__(self, conn_factory, cliente_id):
        self.conn_factory = conn_factory
        self.cliente_id = cliente_id

    def key(self, prompt_version, model, payload):
        body = canonical({'prompt_version':prompt_version, 'model':model, 'input':payload})
        return hashlib.sha256(body.encode('utf-8')).hexdigest()

    def get(self, key):
        with self.conn_factory() as conn:
            row = conn.execute('SELECT conteudo FROM llm_cache WHERE chave=%s AND cliente_id=%s',(key,self.cliente_id)).fetchone()
        return row['conteudo'] if row else None

    def put(self, key, value):
        # the primary key is (cliente_id, chave): each client has its own row for the same key
        with self.conn_factory() as conn:
            conn.execute('INSERT INTO llm_cache (chave, cliente_id, conteudo) VALUES (%s,%s,%s) ON CONFLICT (cliente_id, chave) DO UPDATE SET conteudo=EXCLUDED.conteudo, criado_em=now()',
                         (key,self.cliente_id,Jsonb(value)))
            conn.commit()
