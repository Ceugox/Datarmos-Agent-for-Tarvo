-- the cache key is per client: the same key from two clients must not collide
DO $$
BEGIN
  IF (SELECT array_length(conkey,1) FROM pg_constraint WHERE conrelid='llm_cache'::regclass AND contype='p') = 1 THEN
    ALTER TABLE llm_cache DROP CONSTRAINT llm_cache_pkey;
    ALTER TABLE llm_cache ADD PRIMARY KEY (cliente_id, chave);
  END IF;
END $$;
