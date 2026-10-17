import argparse
import json
import os
from pathlib import Path
import sys

from .audit import AuditLog
from .closing import close_month
from .inference import load_decisions, record_decisions, run_inference
from .inference_policy import load_inference_policy
from .llm_cache import ResponseCache
from .readers import read_inputs
from .reporting import publish_result
from .resolver import AnthropicResolver, CachedResolver, TokenBudget


def main(argv=None, resolver=None):
    parser = argparse.ArgumentParser(description='Generate a traceable monthly closing from the source files, using the finance team rules.')
    parser.add_argument('--input',type=Path,default=Path('Tarvo_Data_Pack_set2026'))
    parser.add_argument('--policy',type=Path,default=Path('config/closing-policy.json'))
    parser.add_argument('--period',required=True)
    parser.add_argument('--output',type=Path,default=Path('saida'))
    parser.add_argument('--no-llm',action='store_true',help='Skip the inference layer; output is identical to a run without an API key.')
    parser.add_argument('--decisoes',type=Path,help='JSON list of human decisions on exceptions (recorded in the audit log).')
    parser.add_argument('--cache-dir',type=Path,default=Path('.cache/llm'))
    parser.add_argument('--inference-policy',type=Path,default=Path('config/inference-policy.json'))
    args = parser.parse_args(argv)
    layer = not args.no_llm
    if layer and resolver is None and not os.environ.get('ANTHROPIC_API_KEY'):
        print('ANTHROPIC_API_KEY not set: inference layer off, same as --no-llm',file=sys.stderr)
        layer = False
    if not layer and args.decisoes:
        print('--decisoes ignored: inference layer off',file=sys.stderr)
    audit = None
    try:
        policy = json.loads(args.policy.read_text(encoding='utf-8'))
        bundle = read_inputs(args.input)
        result = close_month(bundle,policy,args.period)
        if layer:
            inference_policy = load_inference_policy(args.inference_policy)
            decisions = load_decisions(args.decisoes,result) if args.decisoes else []
            audit = AuditLog()
            inner = resolver or AnthropicResolver(prompt_version=inference_policy['prompt_version'])
            budget = TokenBudget(int(os.environ.get('LLM_BUDGET_TOKENS',200000)))
            events = run_inference(bundle,result,policy,inference_policy,CachedResolver(inner,ResponseCache(args.cache_dir)),audit,budget)
            if args.decisoes:
                record_decisions(audit,decisions)
                print('Decisions recorded in the audit log only: the revision (rev-N) that applies them arrives in phase 3.',file=sys.stderr)
        manifest = publish_result(bundle,result,policy,args.period,args.output)
        if audit:
            audit.write(args.output/'auditoria.jsonl')
    except (OSError,ValueError,KeyError,TypeError,ImportError) as error:
        print(f'Closing failed: {error}',file=sys.stderr)
        return 1
    metrics = {key:('BLOCKED' if value is None else value) for key, value in result.metrics.items()}
    print(f'Closing saved: {args.output.resolve()}')
    print(f'Run: {manifest["run_id"]}')
    print(f'Checkout commission: BRL {metrics["comissao_checkout"]}')
    print(f'Remittance participation: BRL {metrics["participacao_remessas"]}')
    partial = ' (PARTIAL: blocked '+', '.join(metrics['totais_parciais'])+')' if metrics.get('totais_parciais') else ''
    print(f'Invoices to issue after review: {metrics["notas"]}; BRL {metrics["valor_notas"]}{partial}')
    print(f'Rate divergences: {metrics["divergencias"]}; Orbe BRL {metrics["diferenca_checkout_brl"]}; Ponte BRL {metrics["diferenca_remessa_brl"]}{partial}')
    print(f'Pending items: {metrics["pendencias"]}. Open {args.output / "index.html"} to review.')
    if audit:
        summary = audit.events[len(events)]
        cost = 'unknown' if summary['custo_usd_total'] is None else summary['custo_usd_total']
        humans = sum(1 for event in events if event['resultado'] == 'HUMANO')
        proposals = sum(1 for event in events if event['proposta'] is not None)
        print(f'Inference: {len(events)} exceptions queued, {proposals} proposals, {humans} to humans, {summary["tokens_total"]} tokens, USD {cost}, audit {args.output / "auditoria.jsonl"}')
    if metrics['status'] == 'PROVISORIO':
        for block in metrics['fontes_bloqueadas'].values():
            print(f'BLOCKED SOURCE {block["arquivo"]}: {block["motivo"]}',file=sys.stderr)
        print(f'PROVISIONAL closing: blocked stages {", ".join(metrics["etapas_bloqueadas"]) or "none in full"}; release decided by Helena.',file=sys.stderr)
        return 3
    return 0
