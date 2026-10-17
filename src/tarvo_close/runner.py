"""Closing orchestration shared by the CLI and the HTTP API: read, close, optional inference layer or revision, publish."""
from pathlib import Path
import os

from .audit import AuditLog
from .closing import close_month
from .inference import run_inference, run_revision, validate_decisions
from .llm_cache import ResponseCache
from .readers import read_inputs
from .reporting import now, publish_result
from .resolver import AnthropicResolver, CachedResolver, TokenBudget

NO_KEY_WARNING = 'ANTHROPIC_API_KEY not set: inference layer off, same as --no-llm'


def run_closing(input_path, closing_policy, inference_policy, period, output, resolver=None, cache=None, budget=None, use_llm=True):
    """Closes the period and publishes it. The layer runs only with use_llm and a resolver or ANTHROPIC_API_KEY; otherwise the output equals --no-llm."""
    warning, started_at = None, now()
    if use_llm and resolver is None and not os.environ.get('ANTHROPIC_API_KEY'):
        use_llm, warning = False, NO_KEY_WARNING
    bundle = read_inputs(input_path)
    result = close_month(bundle,closing_policy,period)
    audit, events = None, []
    if use_llm:
        audit = AuditLog()
        inner = resolver or AnthropicResolver(prompt_version=inference_policy['prompt_version'])
        budget = budget or TokenBudget(int(os.environ.get('LLM_BUDGET_TOKENS',200000)))
        events = run_inference(bundle,result,closing_policy,inference_policy,CachedResolver(inner,cache or ResponseCache('.cache/llm')),audit,budget)
    manifest = publish_result(bundle,result,closing_policy,period,output,started_at=started_at)
    if audit:
        audit.write(Path(output)/'auditoria.jsonl')
    return {'result':result, 'manifest':manifest, 'events':events, 'audit':audit, 'aviso':warning}


def run_revision_closing(input_path, closing_policy, inference_policy, period, output, parent_dir, decisions):
    """Applies human decisions on top of the parent run in a new revision; never calls the resolver."""
    started_at = now()
    bundle = read_inputs(input_path)
    result = close_month(bundle,closing_policy,period)
    decisions = validate_decisions(decisions,result)
    audit = AuditLog()
    revision = run_revision(bundle,result,closing_policy,inference_policy,parent_dir,decisions,audit)
    manifest = publish_result(bundle,result,closing_policy,period,output,revision=revision,started_at=started_at)
    audit.write(Path(output)/'auditoria.jsonl')
    return {'result':result, 'manifest':manifest, 'revision':revision, 'audit':audit}
