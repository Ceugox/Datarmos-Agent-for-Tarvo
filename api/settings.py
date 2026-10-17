"""Service settings read from the environment (ADR 0002, Fase 4)."""
from dataclasses import dataclass
from datetime import datetime, timezone
import os


def parse_deadline(value):
    """DEMO_ATE in ISO 8601 with an explicit offset (2026-10-18T23:59:00-03:00); empty means no demo mode."""
    if not value:
        return None
    deadline = datetime.fromisoformat(value)
    if deadline.tzinfo is None:
        raise ValueError('DEMO_ATE precisa de fuso horário explícito, por exemplo 2026-10-18T23:59:00-03:00')
    return deadline


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
    demo_ate: datetime | None = None
    demo_keys_per_ip_hour: int = 5
    demo_llm_closings_per_ip_hour: int = 20

    def demo_active(self, now=None):
        """Open demo mode: self-service keys and the inference layer on by default, until DEMO_ATE."""
        return self.demo_ate is not None and (now or datetime.now(timezone.utc)) < self.demo_ate

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
            demo_ate=parse_deadline(env.get('DEMO_ATE','')),
            demo_keys_per_ip_hour=int(env.get('DEMO_CHAVES_POR_IP_HORA') or 5),
            demo_llm_closings_per_ip_hour=int(env.get('DEMO_FECHAMENTOS_IA_POR_IP_HORA') or 20),
        )
