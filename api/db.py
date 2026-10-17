"""Postgres connection and idempotent migrations."""
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS_DIR = Path(__file__).resolve().parent/'migrations'


def connect(url):
    if not url:
        raise RuntimeError('DATABASE_URL não definido')
    if url.startswith('postgres://'):  # Railway may hand out either scheme
        url = 'postgresql://'+url[len('postgres://'):]
    return psycopg.connect(url,row_factory=dict_row)


def migrate(conn):
    """Apply api/migrations/*.sql in order, once each. Returns the names applied now."""
    applied = []
    with conn.transaction():
        conn.execute('SELECT pg_advisory_xact_lock(7461001)')  # two processes starting together
        conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (nome text PRIMARY KEY, aplicado_em timestamptz NOT NULL DEFAULT now())')
        done = {row['nome'] for row in conn.execute('SELECT nome FROM schema_migrations')}
        for path in sorted(MIGRATIONS_DIR.glob('*.sql')):
            if path.name in done:
                continue
            conn.execute(path.read_text(encoding='utf-8'))
            conn.execute('INSERT INTO schema_migrations (nome) VALUES (%s)',(path.name,))
            applied.append(path.name)
    return applied
