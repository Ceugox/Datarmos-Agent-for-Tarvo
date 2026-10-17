-- Modo demonstração (17/10): clientes criados por autoatendimento; a chave deixa de valer depois de DEMO_ATE.
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS demo boolean NOT NULL DEFAULT false;
