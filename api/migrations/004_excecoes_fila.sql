ALTER TABLE excecoes ADD COLUMN IF NOT EXISTS escopo text;
ALTER TABLE excecoes ADD COLUMN IF NOT EXISTS valor_brl text;
ALTER TABLE excecoes ADD COLUMN IF NOT EXISTS motivo_pendencia text;
ALTER TABLE excecoes ADD COLUMN IF NOT EXISTS quem_decide text;
