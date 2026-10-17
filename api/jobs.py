"""Job queue in Postgres. claim uses FOR UPDATE SKIP LOCKED so several workers never take the same job."""
from psycopg.types.json import Jsonb


def enqueue(conn, fechamento_id, tipo, payload=None):
    row = conn.execute("INSERT INTO jobs (fechamento_id, tipo, status, payload) VALUES (%s,%s,'NA_FILA',%s) RETURNING id",
                       (fechamento_id,tipo,Jsonb(payload or {}))).fetchone()
    conn.commit()
    return row['id']


def claim(conn):
    """Take the oldest queued job, or None. The caller commits (the lock lasts until then)."""
    return conn.execute("UPDATE jobs SET status='PROCESSANDO', iniciado_em=now(), tentativas=tentativas+1 "
                        "WHERE id = (SELECT id FROM jobs WHERE status='NA_FILA' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *").fetchone()


def finish(conn, job_id):
    conn.execute("UPDATE jobs SET status='CONCLUIDO', concluido_em=now() WHERE id=%s",(job_id,))
    conn.commit()


def fail(conn, job_id, erro):
    conn.execute("UPDATE jobs SET status='ERRO', erro=%s, concluido_em=now() WHERE id=%s",(erro,job_id))
    conn.commit()
