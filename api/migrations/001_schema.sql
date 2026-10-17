CREATE TABLE IF NOT EXISTS schema_migrations (nome text PRIMARY KEY, aplicado_em timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS clientes (
  id serial PRIMARY KEY,
  nome text NOT NULL UNIQUE,
  chave_hash text NOT NULL UNIQUE,
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS politicas (
  id serial PRIMARY KEY,
  cliente_id int NOT NULL REFERENCES clientes(id),
  tipo text NOT NULL CHECK (tipo IN ('closing','inference')),
  versao int NOT NULL,
  conteudo jsonb NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (cliente_id, tipo, versao)
);

CREATE TABLE IF NOT EXISTS fechamentos (
  id uuid PRIMARY KEY,
  cliente_id int NOT NULL REFERENCES clientes(id),
  periodo text NOT NULL,
  status text NOT NULL CHECK (status IN ('NA_FILA','PROCESSANDO','CONCLUIDO','PROVISORIO','ERRO')),
  usar_llm boolean NOT NULL DEFAULT false,
  run_id text,
  numero_revisao int NOT NULL DEFAULT 0,
  pai_id uuid REFERENCES fechamentos(id),
  politica_closing_id int REFERENCES politicas(id),
  politica_inference_id int REFERENCES politicas(id),
  metrics jsonb,
  checks jsonb,
  erro text,
  criado_em timestamptz NOT NULL DEFAULT now(),
  concluido_em timestamptz
);

CREATE TABLE IF NOT EXISTS jobs (
  id serial PRIMARY KEY,
  fechamento_id uuid NOT NULL REFERENCES fechamentos(id),
  tipo text NOT NULL CHECK (tipo IN ('FECHAMENTO','REVISAO')),
  status text NOT NULL CHECK (status IN ('NA_FILA','PROCESSANDO','CONCLUIDO','ERRO')),
  tentativas int NOT NULL DEFAULT 0,
  payload jsonb NOT NULL DEFAULT '{}',
  erro text,
  criado_em timestamptz NOT NULL DEFAULT now(),
  iniciado_em timestamptz,
  concluido_em timestamptz
);

CREATE TABLE IF NOT EXISTS excecoes (
  id serial PRIMARY KEY,
  fechamento_id uuid NOT NULL REFERENCES fechamentos(id),
  excecao_id text NOT NULL,
  classe text NOT NULL,
  tipo text NOT NULL,
  modo text NOT NULL,
  resultado text NOT NULL,
  motivo text,
  proposta jsonb,
  verificacoes jsonb NOT NULL DEFAULT '[]',
  aplicada boolean NOT NULL DEFAULT false,
  pendencia_status text,
  UNIQUE (fechamento_id, excecao_id)
);

CREATE TABLE IF NOT EXISTS decisoes (
  id serial PRIMARY KEY,
  fechamento_id uuid NOT NULL REFERENCES fechamentos(id),
  excecao_id text NOT NULL,
  decisao text NOT NULL CHECK (decisao IN ('aprovar','rejeitar','editar')),
  decidido_por text NOT NULL,
  motivo text NOT NULL,
  parametros jsonb,
  revisao_id uuid REFERENCES fechamentos(id),
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auditoria (
  id serial PRIMARY KEY,
  fechamento_id uuid NOT NULL REFERENCES fechamentos(id),
  seq int NOT NULL,
  evento jsonb NOT NULL,
  UNIQUE (fechamento_id, seq)
);

CREATE TABLE IF NOT EXISTS llm_cache (
  chave text PRIMARY KEY,
  cliente_id int NOT NULL REFERENCES clientes(id),
  conteudo jsonb NOT NULL,
  criado_em timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS jobs_status_id_idx ON jobs (status, id);
CREATE INDEX IF NOT EXISTS fechamentos_cliente_criado_idx ON fechamentos (cliente_id, criado_em);
CREATE INDEX IF NOT EXISTS excecoes_fechamento_idx ON excecoes (fechamento_id);
CREATE INDEX IF NOT EXISTS auditoria_fechamento_seq_idx ON auditoria (fechamento_id, seq);
