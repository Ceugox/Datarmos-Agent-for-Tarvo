"""Per-client closing and inference policies, versioned in the database. Tarvo is the seed."""
from pathlib import Path
import json

from psycopg.types.json import Jsonb

from tarvo_close.inference_policy import load_inference_policy

CONFIG_DIR = Path(__file__).resolve().parents[1]/'config'
TIPOS = ('closing','inference')


def _seed_content(tipo):
    if tipo == 'inference':
        return load_inference_policy(CONFIG_DIR/'inference-policy.json')  # same validation as the CLI
    return json.loads((CONFIG_DIR/'closing-policy.json').read_text(encoding='utf-8'))


def seed_tarvo(conn, cliente_id):
    """Write version 1 of each policy type the client does not have yet. Returns the types written."""
    written = []
    for tipo in TIPOS:
        if conn.execute('SELECT 1 FROM politicas WHERE cliente_id=%s AND tipo=%s',(cliente_id,tipo)).fetchone():
            continue
        conn.execute('INSERT INTO politicas (cliente_id, tipo, versao, conteudo) VALUES (%s,%s,1,%s)',(cliente_id,tipo,Jsonb(_seed_content(tipo))))
        written.append(tipo)
    conn.commit()
    return written


def current(conn, cliente_id, tipo):
    row = conn.execute('SELECT id, conteudo FROM politicas WHERE cliente_id=%s AND tipo=%s ORDER BY versao DESC LIMIT 1',(cliente_id,tipo)).fetchone()
    if row is None:
        raise ValueError(f'Cliente {cliente_id} sem política {tipo}')
    return row['id'], row['conteudo']
