from collections import Counter
import argparse
import json
import os
from pathlib import Path
import sys

from .inference_policy import load_inference_policy
from .llm_cache import ResponseCache
from .runner import run_closing, run_revision_closing


def main(argv=None, resolver=None):
    parser = argparse.ArgumentParser(description='Generate a traceable monthly closing from the source files, using the finance team rules.')
    parser.add_argument('--input',type=Path,default=Path('Tarvo_Data_Pack_set2026'))
    parser.add_argument('--policy',type=Path,default=Path('config/closing-policy.json'))
    parser.add_argument('--period',required=True)
    parser.add_argument('--output',type=Path,default=Path('saida'))
    parser.add_argument('--no-llm',action='store_true',help='Skip the inference layer; output is identical to a run without an API key.')
    parser.add_argument('--decisoes',type=Path,help='JSON list of human decisions on exceptions; requires --revisao-de.')
    parser.add_argument('--revisao-de',type=Path,help='Output folder of the parent run (with manifest.json and auditoria.jsonl) that --decisoes revises. Creates revision rev-N in --output.')
    parser.add_argument('--cache-dir',type=Path,default=Path('.cache/llm'))
    parser.add_argument('--inference-policy',type=Path,default=Path('config/inference-policy.json'))
    args = parser.parse_args(argv)
    revising = bool(args.decisoes or args.revisao_de)
    if revising and not (args.decisoes and args.revisao_de):
        print('Closing failed: --decisoes and --revisao-de must be used together',file=sys.stderr)
        return 1
    audit = revision = None
    events = []
    try:
        policy = json.loads(args.policy.read_text(encoding='utf-8'))
        if revising:
            # a revision never calls the resolver: it works without a key and with --no-llm
            with open(args.decisoes,encoding='utf-8') as handle:
                decisions = json.load(handle)
            done = run_revision_closing(args.input,policy,load_inference_policy(args.inference_policy),args.period,args.output,args.revisao_de,decisions)
            revision = done['revision']
        else:
            layer = not args.no_llm and (resolver is not None or bool(os.environ.get('ANTHROPIC_API_KEY')))
            inference_policy = load_inference_policy(args.inference_policy) if layer else None
            done = run_closing(args.input,policy,inference_policy,args.period,args.output,resolver=resolver,cache=ResponseCache(args.cache_dir),use_llm=not args.no_llm)
            events = done['events']
            if done['aviso']:
                print(done['aviso'],file=sys.stderr)
        result, manifest, audit = done['result'], done['manifest'], done['audit']
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
    if revision:
        counts = Counter(decision['resultado'] for decision in revision['decisoes'])
        print(f'Revision rev-{revision["numero"]} of {revision["run_id_pai"]}: {counts["APLICADA"]} applied, {counts["REGISTRADA"]} recorded, {counts["RECUSADA"]} refused')
    elif audit:
        summary = audit.events[len(events)]
        cost = 'unknown' if summary['custo_usd_total'] is None else summary['custo_usd_total']
        humans = sum(1 for event in events if event['resultado'] == 'HUMANO')
        proposals = sum(1 for event in events if event['proposta'] is not None)
        applied = sum(1 for event in events if event['aplicada'])
        print(f'Inference: {len(events)} exceptions queued, {proposals} proposals, {humans} to humans, {summary["tokens_total"]} tokens, USD {cost}, {applied} applied, audit {args.output / "auditoria.jsonl"}')
    if metrics['status'] == 'PROVISORIO':
        for block in metrics['fontes_bloqueadas'].values():
            print(f'BLOCKED SOURCE {block["arquivo"]}: {block["motivo"]}',file=sys.stderr)
        print(f'PROVISIONAL closing: blocked stages {", ".join(metrics["etapas_bloqueadas"]) or "none in full"}; release decided by Helena.',file=sys.stderr)
        return 3
    return 0
