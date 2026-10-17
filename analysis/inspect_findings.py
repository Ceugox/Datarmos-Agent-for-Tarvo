exec(open('analysis/analyze.py',encoding='utf-8').read().replace("print(json.dumps(summary, ensure_ascii=True, indent=2, default=str))",''))
print('RATE GROUPS')
for ec in sorted(set(r['cod_estabelecimento'] for r in comparisons)):
 rows=[r for r in comparisons if r['cod_estabelecimento']==ec and r['contract_pct']!=r['taxa_aplicada_pct']]
 if rows: print(ec,rows[0]['contract_name'],len(rows),sum(r['difference'] for r in rows), [(r['id_transacao'],str(r['contract_pct']),str(r['taxa_aplicada_pct']),str(r['difference'])) for r in rows[:2]])
print('SAME RATE ROUNDING',Counter(r['difference'] for r in comparisons if r['contract_pct']==r['taxa_aplicada_pct']))
print('RATE ONLY POS',sum((r['difference'] for r in comparisons if r['contract_pct']!=r['taxa_aplicada_pct'] and r['difference']>0),Decimal(0)))
print('REFS AUGUST', len([r for r in checkout if r['data_venda_original'] and '/08/2026' in r['data_venda_original']]))
print('REF SAMPLES',[(r['id_transacao'],r['tipo_lancamento'],r['id_referencia'],r['data_venda_original']) for r in checkout if r['tipo_lancamento']!='VENDA'][:10])
print('AURORA GROUPS')
for prefix in ['TED RECEBIDA','PIX ENVIADO','TRANSF ENTRE','PIX RECEBIDO','DEVOLUCAO']:
 rows=[r for r in aurora if r['description'].startswith(prefix)]
 print(prefix,len(rows),total(rows,'amount'),[r['ref'] for r in rows] if prefix in ['TRANSF ENTRE','PIX RECEBIDO','DEVOLUCAO'] else '')
print('MERIDIANO TRANSFERS', [r for r in meridiano if 'MESMA TITULARIDADE' in r['description']])
print('FX ESTIMATED',total(eligible_fx,'estimated_spread'))
print('FX NOTES',[(r['operation'],r['notes']) for r in unique_fx if r['notes']])
print('FX 50 ROUND UNIQUE',rounded(total(unique_fx,'spread')/2),sum((rounded(r['spread']/2) for r in unique_fx),Decimal(0)))
