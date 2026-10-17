"""Service settings read from the environment (ADR 0002, Fase 4)."""
from dataclasses import dataclass
import os


@dataclass
class Settings:
    database_url: str = ''
    data_dir: str = './data'
    port: int = 8000
    max_upload_mb: int = 50
    rate_limit_per_minute: int = 60
    llm_budget_tokens: int = 200000
    api_key_pepper: str = ''
    worker_in_process: bool = True

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        return cls(
            database_url=env.get('DATABASE_URL',''),
            data_dir=env.get('DATA_DIR') or './data',
            port=int(env.get('PORT') or 8000),
            max_upload_mb=int(env.get('MAX_UPLOAD_MB') or 50),
            rate_limit_per_minute=int(env.get('RATE_LIMIT_PER_MINUTE') or 60),
            llm_budget_tokens=int(env.get('LLM_BUDGET_TOKENS') or 200000),
            api_key_pepper=env.get('API_KEY_PEPPER',''),
            worker_in_process=env.get('WORKER_IN_PROCESS','1') != '0',
        )
