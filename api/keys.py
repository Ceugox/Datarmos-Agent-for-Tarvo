"""API keys. The key is 256 random bits, not a human password: a slow hash (bcrypt) guards low-entropy
inputs against brute force, which does not apply here; sha256 allows an equality lookup on the unique
index; the optional API_KEY_PEPPER keeps a database dump alone from validating keys."""
import argparse
import hashlib
import os
import secrets
import sys

import psycopg

from api import db


def new_key():
    return 'tk_'+secrets.token_urlsafe(32)


def hash_key(key, pepper=''):
    return hashlib.sha256((pepper+key).encode()).hexdigest()


def create_client(conn, nome, pepper='', demo=False):
    key = new_key()
    row = conn.execute('INSERT INTO clientes (nome, chave_hash, demo) VALUES (%s,%s,%s) RETURNING id',(nome,hash_key(key,pepper),demo)).fetchone()
    conn.commit()
    return row['id'], key


def find_client(conn, key, pepper=''):
    return conn.execute('SELECT * FROM clientes WHERE chave_hash = %s',(hash_key(key or '',pepper),)).fetchone()


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m api.keys')
    sub = parser.add_subparsers(dest='comando',required=True)
    create = sub.add_parser('criar',help='cria um cliente e imprime a chave uma única vez')
    create.add_argument('--cliente',required=True)
    args = parser.parse_args(argv)
    try:
        with db.connect(os.environ.get('DATABASE_URL','')) as conn:
            db.migrate(conn)
            _, key = create_client(conn,args.cliente,os.environ.get('API_KEY_PEPPER',''))
    except psycopg.errors.UniqueViolation:
        print(f'Cliente já existe: {args.cliente}',file=sys.stderr)
        return 1
    except (RuntimeError, psycopg.OperationalError) as error:
        print(f'Erro: {error}',file=sys.stderr)
        return 1
    print(key)
    return 0


if __name__ == '__main__':
    sys.exit(main())
