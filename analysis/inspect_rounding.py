exec(open('analysis/analyze.py',encoding='utf-8').read().replace("print(json.dumps(summary, ensure_ascii=True, indent=2, default=str))",''))
from decimal import ROUND_DOWN
sales=[r for r in checkout if r['tipo_lancamento']=='VENDA']
print('TRUNC SALES',sum(r['valor_taxa']!=(r['valor_bruto']*r['taxa_aplicada_pct']/100).quantize(Decimal('.01'),rounding=ROUND_DOWN) for r in sales))
for ec in ['1074504011','1075624862']:
 rs=[r for r in comparisons if r['cod_estabelecimento']==ec and r['contract_pct']!=r['taxa_aplicada_pct']]
 print('TRUNC DIFF',ec,sum((r['valor_taxa']-(r['valor_bruto']*r['contract_pct']/100).quantize(Decimal('.01'),rounding=ROUND_DOWN) for r in rs),Decimal(0)))
print('NO SALES',len(checkout)-len(sales))
print('MISSING ORIGINAL',len([r for r in checkout if r['tipo_lancamento']=='ESTORNO' and r['id_referencia'] not in {x['id_transacao'] for x in checkout}]))
print('REVERSAL REFS',[(r['id_transacao'],r['id_referencia']) for r in checkout if r['tipo_lancamento']=='REVERSAO ANTECIPACAO'])
print('FX NEG',total(summary['fx']['negative'],'spread'))
print('FX ELIGIBLE HALF',rounded(total(eligible_fx,'spread')/2))
print('COUNT CONTRACTED MONTH',Counter(r['contracted'].month for r in unique_fx))
