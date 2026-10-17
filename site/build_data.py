"""Build the static case dashboard from a closing and an optional earlier closing."""
import argparse
import csv
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--input', type=Path, default=ROOT / 'saida')
parser.add_argument('--baseline', type=Path)
parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'data' / 'results.js')
args = parser.parse_args()
OUT = args.input


def rows(name):
    with open(OUT / name, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


metrics = json.loads((OUT / 'metrics.json').read_text(encoding='utf-8'))
manifest = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))

by_merchant = defaultdict(lambda: defaultdict(Decimal))
for r in rows('comissoes_por_lojista.csv'):
    by_merchant[r['lojista']][r['linha_negocio']] += Decimal(r['comissao_brl'])
merchants = sorted(by_merchant.items(), key=lambda kv: -sum(kv[1].values()))

div_by_party = defaultdict(lambda: [0, Decimal()])
for r in rows('divergencias_taxa.csv'):
    key = f"{r['contraparte']} · {r['lojista']}"
    div_by_party[key][0] += 1
    div_by_party[key][1] += Decimal(r['diferenca_brl'])

pend = rows('pendencias.csv')
pend_owner = defaultdict(int)
for r in pend:
    pend_owner[r['quem_decide']] += 1

bank = defaultdict(lambda: [0, Decimal()])
for r in rows('lancamentos_classificados.csv'):
    bank[r['conta_descricao']][0] += 1
    bank[r['conta_descricao']][1] += abs(Decimal(r['valor']))

cov = defaultdict(int)
for r in rows('cobertura.csv'):
    cov[r['status']] += 1

negative_spreads = sum((abs(Decimal(r['valor_brl'])) for r in pend
                        if r['tipo'] == 'SPREAD_NEGATIVO_CONTESTAR' and r['valor_brl']), Decimal())
late_adjustments = None
if args.baseline:
    before = json.loads((args.baseline / 'metrics.json').read_text(encoding='utf-8'))
    if before['periodo'] != metrics['periodo']:
        raise ValueError('Baseline and closing must cover the same period')
    late_adjustments = {
        'commission_before': float(before['comissao_checkout']),
        'commission_after': float(metrics['comissao_checkout']),
        'notes_before': float(before['valor_notas']),
        'notes_after': float(metrics['valor_notas']),
    }

data = {
    'source': {'run_id': manifest['run_id'], 'engine_sha256': manifest['engine_sha256'],
               'period': manifest['period'], 'kind': 'static_case_snapshot'},
    'metrics': metrics,
    'merchants': [{'name': n, 'checkout': float(v.get('CHECKOUT', 0)), 'remessa': float(v.get('REMESSA', 0))} for n, v in merchants],
    'divergences': [{'name': k, 'count': c, 'brl': float(s)} for k, (c, s) in sorted(div_by_party.items(), key=lambda kv: -abs(kv[1][1]))],
    'pending_by_owner': dict(pend_owner),
    'pending': [{'tipo': r['tipo'], 'valor': float(r['valor_brl']) if r['valor_brl'] else None, 'quem': r['quem_decide']} for r in pend],
    'bank_accounts': [{'name': k, 'count': c, 'brl': float(s)} for k, (c, s) in sorted(bank.items(), key=lambda kv: -kv[1][0])],
    'coverage': dict(cov),
    'late_adjustments': late_adjustments,
    'amounts_to_review': {
        'Casa do Estudante · devolução a revisar': float(metrics['devolucao_condicao_comercial']),
        'Spreads negativos · contestação a revisar': float(negative_spreads),
        'Orbe · divergências a contestar': float(metrics['diferenca_checkout_brl']),
        'Ponte · divergências a contestar': float(metrics['diferenca_remessa_brl']),
    },
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text('window.RESULTS = ' + json.dumps(data, ensure_ascii=False, indent=1) + ';\n', encoding='utf-8')
print(f"Built {len(data['merchants'])} merchants and {len(data['divergences'])} divergence groups")
