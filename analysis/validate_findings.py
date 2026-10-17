from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote
import analyze as a

assert len(a.checkout) == len({r['id_transacao'] for r in a.checkout}) == 1943
assert all(r['valor_bruto'] - r['valor_taxa'] == r['valor_liquido'] for r in a.checkout)
assert sum(v['count'] for v in a.summary['checkout']['types'].values()) == len(a.checkout)
assert sum(v['fee'] for v in a.summary['checkout']['types'].values()) == Decimal('231880.36')
assert all(r['valor_taxa'] == (r['valor_bruto'] * r['taxa_aplicada_pct'] / 100).quantize(Decimal('.01'), rounding=ROUND_DOWN) for r in a.checkout if r['tipo_lancamento'] == 'VENDA')
differences = [r for r in a.comparisons if r['contract_pct'] != r['taxa_aplicada_pct']]
assert len(differences) == 88
assert a.total(differences, 'difference') == Decimal('1674.67')
assert len(a.comparisons) == 1574
assert len(a.unmapped) == 290
assert a.total(a.unmapped, 'valor_taxa') == Decimal('35368.67')
assert len(a.unique_fx) == 232 and len(a.fx) == 233
duplicate = a.duplicates['PC-0926-0162']
assert len(duplicate) == 2
for field in ['cnpj', 'brl', 'spread', 'currency', 'foreign_amount', 'contracted', 'settled', 'status']:
    assert duplicate[0][field] == duplicate[1][field]
assert sum(Decimal(str(row[3])) for row in list(a.fx_wb['Resumo'].values)[1:]) == a.total(a.fx, 'spread')
assert sum(row[1] for row in list(a.fx_wb['Resumo'].values)[1:]) == len(a.fx)
assert a.total(a.unique_fx,'spread') == Decimal('77251.71')
assert a.total(a.eligible_fx,'spread') == Decimal('75173.00')
assert a.total(a.summary['fx']['not_settled_september'],'spread') == Decimal('2078.71')
balance = Decimal('612334.81')
for entry in a.aurora:
    balance += entry['amount']
    assert balance == entry['balance'], entry['ref']
assert balance == Decimal('-1920088.60')
assert len(a.meridiano) == len({r['ref'] for r in a.meridiano}) == 100
assert a.summary['banks']['meridiano_closing'] - a.total(a.meridiano,'amount') == Decimal('204118.03')
assert a.summary['banks']['aurora_closing'] + a.summary['banks']['meridiano_closing'] == Decimal('-599635.34')

class LinkParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href','')
        if href and not href.startswith(('#','https:','http:')):
            assert (a.ROOT / unquote(href)).is_file(), href

LinkParser().feed((a.ROOT / 'tarvo-economic-analysis.html').read_text(encoding='utf-8'))
print('PASS: source counts, signs, rounding, 88 comparisons, contracts coverage, duplicate financial fields, FX summaries, cutoff, every Aurora balance, unique FITIDs, closing balances and local source links.')
