"""Gera site/data/results.js a partir de saida/ (stdlib). Rodar: python site/build_data.py"""
import csv, json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'saida'


def rows(name):
    with open(OUT / name, encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter=';'))


def money(d):
    return {k: float(v) for k, v in d.items()}


metrics = json.loads((OUT / 'metrics.json').read_text(encoding='utf-8'))

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

data = {
    'metrics': metrics,
    'merchants': [{'name': n, 'checkout': float(v.get('CHECKOUT', 0)), 'remessa': float(v.get('REMESSA', 0))} for n, v in merchants],
    'divergences': [{'name': k, 'count': c, 'brl': float(s)} for k, (c, s) in sorted(div_by_party.items(), key=lambda kv: -abs(kv[1][1]))],
    'pending_by_owner': dict(pend_owner),
    'pending': [{'tipo': r['tipo'], 'valor': float(r['valor_brl'] or 0), 'quem': r['quem_decide']} for r in pend],
    'bank_accounts': [{'name': k, 'count': c, 'brl': float(s)} for k, (c, s) in sorted(bank.items(), key=lambda kv: -kv[1][0])],
    'coverage': dict(cov),
    'late_adjustments': {'commission_before': 207039.73, 'commission_after': 203735.34, 'notes_before': 246588.68, 'notes_after': 243284.29},
    'corrected': {'Casa do Estudante · devolver ao lojista': 15396.77, 'Spreads negativos · recuperar da Ponte': 1834.05, 'Orbe · Rota e Bridge · cobrar': 1576.23, 'Ponte · Mundo Aberto · contestar': 1418.88},
    'runtime_s': [0.53, 0.43, 0.45],
}
(Path(__file__).parent / 'data' / 'results.js').write_text('window.RESULTS = ' + json.dumps(data, ensure_ascii=False, indent=1) + ';\n', encoding='utf-8')
print('ok', len(data['merchants']), 'lojistas', len(data['divergences']), 'grupos de divergência')
