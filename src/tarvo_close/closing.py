from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
import re

from .domain import cnpj, decimal, identifier, normalize, quantize, source

ZERO = Decimal(0)
HUNDRED = Decimal(100)
RATE_KEYS = ('debit','credit','installment_short','installment_long','pix','advance')
AMOUNT_COLUMNS = {
    'comissoes_por_lojista': 'comissao_brl',
    'divergencias_taxa': 'diferenca_brl',
    'notas_a_emitir': 'valor_brl',
    'lancamentos_classificados': 'valor',
    'pendencias': 'valor_brl',
}


@dataclass
class ClosingResult:
    tables: dict = field(default_factory=lambda: {name: [] for name in AMOUNT_COLUMNS})
    traces: list = field(default_factory=list)
    coverage: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    contests: dict = field(default_factory=lambda: {'ORBE': [], 'PONTE': []})

    def emit(self, name, prefix, key, fields, contributions):
        output_id = identifier(prefix, key)
        if any(r['id_saida'] == output_id for rows in self.tables.values() for r in rows):
            raise ValueError(f'Duplicate output identity: {output_id}')
        row = {'id_saida': output_id, **fields}
        self.tables[name].append(row)
        self.traces.extend({'id_saida': output_id, **part} for part in contributions)
        return row

    def pending(self, key, kind, reason, owner, contributions=(), scope=''):
        contributions = list(contributions)
        amount = sum((r['valor'] for r in contributions), ZERO) if contributions else None
        return self.emit('pendencias', 'PEN', key, {
            'tipo':kind, 'ref_origem':';'.join(sorted({r['ref_origem'] for r in contributions})),
            'valor_brl':amount, 'motivo':reason, 'quem_decide':owner, 'status':'PENDENTE', 'escopo':scope,
        }, contributions)

    def cover(self, kind, record, status, reason):
        self.coverage.append({'tipo_origem':kind, **record['_source'], 'status':status, 'motivo':reason})


def iso_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date()


def validate_policy(policy):
    expected = {'schema_version','status','checkout','remittance','ec_overrides','commercial_conditions','unbilled_merchants','decisions','open_questions','bank_rules'}
    if set(policy) != expected or policy['schema_version'] != 2 or policy['status'] != 'REGRAS_DO_FINANCEIRO':
        raise ValueError('This engine requires the version 2 policy schema with the finance team rules')
    checkout = policy['checkout']
    if set(checkout) != {'commission_basis','rounding','vigency_event','evidence'}:
        raise ValueError('Unknown checkout policy fields')
    if checkout['commission_basis'] != 'contracted_rate' or checkout['rounding'] not in {'truncate','half_up'} or checkout['vigency_event'] not in {'movement','original_sale'}:
        raise ValueError('Unknown checkout basis, rounding or date policy')
    remittance = policy['remittance']
    if set(remittance) != {'share','competence_event','negative_spread','rounding','default_spread','divergence_tolerance_pp','evidence'}:
        raise ValueError('Unknown remittance policy fields')
    if remittance['competence_event'] not in {'settled','contracted'} or remittance['negative_spread'] not in {'exclude_and_contest','signed'}:
        raise ValueError('Unknown remittance competence or negative-spread policy')
    if remittance['rounding'] != 'per_operation':
        raise ValueError('Unknown remittance rounding policy')
    if not ZERO < decimal(remittance['share']) <= 1 or not ZERO < decimal(remittance['default_spread']) < 1 or decimal(remittance['divergence_tolerance_pp']) < 0:
        raise ValueError('Invalid remittance participation, default spread or tolerance')
    for ec, override in policy['ec_overrides'].items():
        if set(override) != {'cnpj','evidence'} or not override['evidence'].strip() or not ec.isdigit():
            raise ValueError('EC override requires a numeric EC and supporting evidence')
        cnpj(override['cnpj'])
    for condition in policy['commercial_conditions']:
        if set(condition) != {'id','cnpj','start','end','rates','evidence'} or not condition['evidence'].strip() or set(condition['rates']) - set(RATE_KEYS):
            raise ValueError('Commercial condition requires identity, period, known rates and evidence')
        cnpj(condition['cnpj'])
        if iso_date(condition['start']) > iso_date(condition['end']):
            raise ValueError('Commercial condition period is inverted')
        for value in condition['rates'].values():
            if not ZERO <= decimal(value) < 1:
                raise ValueError('Commercial condition rate must be a fraction')
    for merchant in policy['unbilled_merchants']:
        if set(merchant) != {'ec','reason','evidence'} or not merchant['ec'].isdigit() or not merchant['evidence'].strip():
            raise ValueError('Unbilled merchant requires EC, reason and evidence')
    for decision in policy['decisions']:
        if set(decision) != {'id','rule','approved_by','when'}:
            raise ValueError('Decision requires id, rule, approver and timestamp')
    for question in policy['open_questions']:
        if set(question) != {'id','reason','owner'}:
            raise ValueError('Unknown pending-rule fields')
    for rule in policy['bank_rules']:
        if set(rule) != {'id','bank','pattern','account','confidence','scope'}:
            raise ValueError('Unknown bank rule fields')
        re.compile(rule['pattern'])
        if rule['bank'] not in {'AURORA','MERIDIANO','ANY'} or not ZERO <= decimal(rule['confidence']) <= 1:
            raise ValueError('Invalid bank rule')
    return policy


def resolve_duplicates(rows, key, kind, result):
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    effective = []
    for identity, records in sorted(groups.items()):
        ordered = sorted(records, key=lambda row: (row['_source']['arquivo_origem'], row['_source']['linha_origem']))
        signatures = [{k: v for k,v in row.items() if k not in {'_source','notes'}} for row in ordered]
        if any(signature != signatures[0] for signature in signatures[1:]):
            result.pending(f'conflict:{kind}:{identity}', 'CONFLITO_DE_VERSAO', f'O identificador {identity} possui versões divergentes. Nenhuma foi escolhida automaticamente.', 'Financeiro / fornecedor da fonte', scope=identity)
            for row in ordered:
                result.cover(kind,row,'CONFLITO','Identificador com versões divergentes')
            continue
        effective.append(ordered[0])
        for duplicate in ordered[1:]:
            result.cover(kind,duplicate,'REPETIDO','Número de operação único: contado uma vez; repetição preservada')
            value_key = 'spread' if kind == 'REMESSA' else 'valor_taxa'
            parts = [source(duplicate,duplicate[value_key],f'{value_key} repetido no relatório')]
            if kind == 'REMESSA':
                result.contests['PONTE'].append({'motivo':'OPERACAO_REPETIDA','ref_origem':identity,'lojista':duplicate['name'],'valor_brl':duplicate[value_key],'detalhe':'Linha repetida (reprocessada) somada no total do relatório; corrigir o relatório.'})
            result.pending(f'duplicate:{kind}:{identity}:{duplicate["_source"]["linha_origem"]}', 'OPERACAO_REPETIDA_CONTESTAR', 'Mesmo identificador repetido no relatório. Contado uma vez; incluir na contestação para a fonte corrigir o relatório.', 'Helena (financeiro)', parts, identity)
    return effective


def condition_for(contract, event, policy):
    matches = [c for c in policy['commercial_conditions'] if cnpj(c['cnpj']) == contract['cnpj'] and iso_date(c['start']) <= event <= iso_date(c['end'])]
    if len(matches) > 1:
        raise ValueError(f'Overlapping commercial conditions for {contract["cnpj"]}')
    return matches[0] if matches else None


def event_date(row, policy):
    if policy['checkout']['vigency_event'] == 'original_sale' and row['data_venda_original']:
        return datetime.strptime(row['data_venda_original'],'%d/%m/%Y').date()
    return row['date']


def select_contract(row, contracts, policy):
    event = event_date(row, policy)
    ec = row['cod_estabelecimento']
    override = policy['ec_overrides'].get(ec)
    return [contract for contract in contracts if contract['start'] <= event <= contract['end'] and (contract['ec'] == ec or (override and contract['cnpj'] == cnpj(override['cnpj'])))]


def rate_key_for(row):
    if row['tipo_lancamento'] in {'ANTECIPACAO','REVERSAO ANTECIPACAO'}:
        return 'advance'
    if row['modalidade'] == 'CREDITO PARCELADO':
        installments = row['qtd_parcelas']
        if installments is None or not 2 <= installments <= 12:
            return None
        return 'installment_short' if installments <= 6 else 'installment_long'
    return {'DEBITO':'debit','PIX':'pix','CREDITO A VISTA':'credit'}.get(row['modalidade'])


def advance_alerts(rows, period, result):
    # Without the receivables schedule, only merchants with no earlier activity in the pack can be checked:
    # for them, everything already sold is inside this month.
    month_start = datetime.strptime(period+'-01','%Y-%m-%d').date()
    by_ec = defaultdict(list)
    for row in rows:
        by_ec[row['cod_estabelecimento']].append(row)
    for ec, events in sorted(by_ec.items()):
        earlier = any(r['data_venda_original'] and datetime.strptime(r['data_venda_original'],'%d/%m/%Y').date() < month_start for r in events)
        if earlier or min(r['date'] for r in events) == month_start:
            continue
        sales = advances = ZERO
        flagged = []
        for row in sorted(events, key=lambda r: (r['date'], r['tipo_lancamento'] != 'VENDA', r['id_transacao'])):
            if row['tipo_lancamento'] in {'VENDA','ESTORNO'}:
                sales += row['valor_bruto']
            elif row['tipo_lancamento'] == 'REVERSAO ANTECIPACAO':
                advances += row['valor_bruto']
            elif row['tipo_lancamento'] == 'ANTECIPACAO':
                advances += row['valor_bruto']
                if advances > sales:
                    flagged.append((row, advances, sales))
        if flagged:
            row, advances, sales = max(flagged, key=lambda item: item[1]-item[2])
            first = min(r['date'] for r in events).isoformat()
            result.pending(f'advance-alert:{ec}', 'ALERTA_ANTECIPACAO', f'{row["nome_estabelecimento"]} começou a transacionar em {first} e antecipou {advances} até {row["date"].isoformat()}, com {sales} em vendas até essa data. A antecipação é sobre o que já foi vendido e não há trava. Avisar financeiro e comercial.', 'Helena (financeiro) / Comercial', [source(r,r['valor_bruto'],'antecipação acima das vendas acumuladas') for r, _, _ in flagged], ec)


def close_checkout(bundle, policy, period, result):
    rounding = policy['checkout']['rounding']
    unbilled = {m['ec']: m for m in policy['unbilled_merchants']}
    effective = resolve_duplicates(bundle.checkout,'id_transacao','CHECKOUT',result)
    commissions = defaultdict(list)
    identities = {}
    unresolved = defaultdict(list)
    held = defaultdict(list)
    conflicts = defaultdict(list)
    differences = defaultdict(list)
    refunds = defaultdict(list)
    refund_rounded = defaultdict(list)
    tx_ids = {r['id_transacao'] for r in effective}
    in_period = []
    compared = 0
    for row in effective:
        if row['date'].isoformat()[:7] != period:
            result.cover('CHECKOUT',row,'FORA_COMPETENCIA','Data de movimento fora do período')
            continue
        in_period.append(row)
        ec = row['cod_estabelecimento']
        if ec in unbilled:
            held[ec].append(row)
            result.cover('CHECKOUT',row,'NAO_FATURAR','Lojista sem contrato assinado; faturar quando o comercial confirmar a taxa')
            continue
        contracts = select_contract(row,bundle.contracts,policy)
        if not contracts:
            unresolved[ec].append(row)
            result.cover('CHECKOUT',row,'SEM_CONTRATO','Sem EC/CNPJ e contrato vigente resolvidos')
            continue
        if len(contracts) != 1:
            conflicts[ec].append(row)
            result.cover('CHECKOUT',row,'CONTRATO_AMBIGUO','Mais de um contrato vigente')
            continue
        contract = contracts[0]
        cnpj_value = contract['cnpj']
        identities[cnpj_value] = min((c for c in bundle.contracts if c['cnpj'] == cnpj_value), key=lambda c: (c['start'], c['_source']['linha_origem']))['name']
        rate_key = rate_key_for(row)
        if not rate_key or contract[rate_key] is None:
            result.cover('CHECKOUT',row,'TAXA_NAO_RESOLVIDA','Modalidade ou taxa contratada sem regra')
            result.pending(f'rate:{row["id_transacao"]}','TAXA_NAO_RESOLVIDA','Modalidade, parcelas ou taxa contratada sem regra disponível.','Helena (financeiro) / Comercial',[source(row,row['valor_bruto'],'volume afetado')],cnpj_value)
            continue
        event = event_date(row,policy)
        sheet_rate = contract[rate_key]
        condition = condition_for(contract,event,policy)
        rate = decimal(condition['rates'][rate_key]) if condition and rate_key in condition['rates'] else sheet_rate
        fee = quantize(row['valor_bruto']*rate,rounding)
        basis = f'{row["tipo_lancamento"]}: quantize({row["valor_bruto"]}*{rate}); {rounding}; taxa {rate_key} vigente em {event.isoformat()}'
        if condition:
            basis += f'; condição comercial {condition["id"]}'
        commissions[cnpj_value].append(source(row,fee,basis))
        if row['tipo_lancamento'] == 'ESTORNO' and row['id_referencia'] not in tx_ids:
            result.cover('CHECKOUT',row,'INCLUIDO','Estorno de venda anterior ao relatório; taxa da data da venda original')
        else:
            result.cover('CHECKOUT',row,'INCLUIDO','Comissão pela taxa contratada')
        compared += 1
        applied = row['taxa_aplicada_pct']/HUNDRED
        if condition:
            if row['valor_taxa']:
                refunds[cnpj_value].append(source(row,row['valor_taxa'],f'valor_taxa cobrado pela Orbe durante {condition["id"]}; devolver ao lojista'))
                refund_rounded[cnpj_value].append((row['valor_taxa'],quantize(row['valor_bruto']*applied,rounding)))
            continue
        if applied != sheet_rate:
            difference = quantize(row['valor_bruto']*(applied-sheet_rate),rounding)
            terms = [source(row,difference,f'quantize({row["valor_bruto"]}*({applied}-{sheet_rate})); {rounding}; taxa {rate_key} vigente em {event.isoformat()}')]
            divergence = result.emit('divergencias_taxa','DIV',row['id_transacao'],{
                'cnpj':cnpj_value,'linha_negocio':'CHECKOUT','ref_origem':row['id_transacao'],'taxa_contratada_pct':quantize(sheet_rate*HUNDRED),
                'taxa_aplicada_pct':row['taxa_aplicada_pct'],'diferenca_brl':difference,'status':'A_CONTESTAR',
                'lojista':contract['name'],'tipo_lancamento':row['tipo_lancamento'],'data_movimento':row['date'],'data_vigencia':event,
                'valor_bruto_brl':row['valor_bruto'],'ref_contrato':contract['_source']['ref_origem'],'contraparte':'ORBE',
            },terms)
            differences[cnpj_value].extend(terms)
            result.contests['ORBE'].append({'motivo':'TAXA_DIFERENTE_DO_CONTRATO','ref_origem':row['id_transacao'],'lojista':contract['name'],'valor_brl':difference,'detalhe':f'{row["tipo_lancamento"]} de {row["date"].isoformat()}: aplicada {row["taxa_aplicada_pct"]}% x contratada {sheet_rate*HUNDRED}%; bruto {row["valor_bruto"]}','id_saida':divergence['id_saida']})
    advance_alerts(in_period,period,result)
    for ec, rows in sorted(held.items()):
        result.pending(f'unbilled:{ec}','LOJISTA_NAO_FATURAR',unbilled[ec]['reason'],'Comercial / Helena (financeiro)',[source(r,r['valor_bruto'],'valor bruto a faturar quando a taxa for confirmada') for r in rows],ec)
    for kind, groups in [('CADASTRO_OU_CONTRATO_AUSENTE',unresolved),('CONTRATO_AMBIGUO',conflicts)]:
        for ec, rows in sorted(groups.items()):
            result.pending(f'{kind}:{ec}',kind,f'{len(rows)} lançamentos sem contrato único; fora da comissão.','Comercial',[source(r,r['valor_bruto'],'valor bruto afetado') for r in rows],ec)
    for cnpj_value, terms in sorted(differences.items()):
        result.pending(f'difference:{cnpj_value}','DIVERGENCIA_A_CONTESTAR_ORBE',f'Diferença líquida (vendas e estornos se anulam) de {identities[cnpj_value]} a cobrar da Orbe e devolver ao lojista. Decisão caso a caso.','Helena (financeiro)',terms,cnpj_value)
    for cnpj_value, terms in sorted(refunds.items()):
        charged = sum((r['valor'] for r in terms),ZERO)
        rounded = sum((pair[1] for pair in refund_rounded[cnpj_value]),ZERO)
        truncated = sum(1 for pair in refund_rounded[cnpj_value] if pair[0] != pair[1])
        reason = (f'{identities[cnpj_value]}: a Orbe cobrou pela planilha porque não foi avisada da isenção. Não é divergência de contrato nem cobrança à Orbe: devolver ao lojista. '
            f'Valor = valor_taxa efetivamente cobrado pela Orbe ({charged}). '
            f'Alternativa considerada e descartada: valor bruto x taxa aplicada com arredondamento comum = {rounded} ({rounded-charged:+} por truncamento da Orbe em {truncated} de {len(terms)} lançamentos). '
            'Por que o valor cobrado: a Helena separou este caso das divergências ("É diferente de uma divergência comum. [...] é devolução ao lojista", 17/10) e definiu a base ("O que foi cobrado eu devolvo ao lojista", 16/10 20h49). '
            'A fórmula bruto x (aplicada - contratada) e o "a gente não trunca" (16/10 21h13) valem para a divergência a cobrar da Orbe e para a comissão da Tarvo; '
            f'numa devolução, o arredondado devolveria {rounded-charged} que o lojista nunca pagou.')
        result.pending(f'refund:{cnpj_value}','DEVOLUCAO_CONDICAO_COMERCIAL',reason,'Helena (financeiro) / Comercial',terms,cnpj_value)
    for cnpj_value, terms in sorted(commissions.items()):
        result.emit('comissoes_por_lojista','COM',f'CHECKOUT:{cnpj_value}',{
            'cnpj':cnpj_value,'lojista':identities[cnpj_value],'linha_negocio':'CHECKOUT',
            'comissao_brl':sum((r['valor'] for r in terms),ZERO),'status':'CALCULADO','base_calculo':'valor_bruto x taxa contratada por linha; estornos e reversões pela taxa da data original',
        },terms)
    result.metrics.update({
        'checkout_lidos':len(bundle.checkout),'checkout_comparados':compared,
        'checkout_sem_contrato':sum(map(len,unresolved.values())),'checkout_nao_faturado':sum(map(len,held.values())),
        'checkout_bruto_nao_faturado':sum((r['valor_bruto'] for rows in held.values() for r in rows),ZERO),
        'devolucao_condicao_comercial':sum((r['valor'] for rows in refunds.values() for r in rows),ZERO),
    })


def close_remittances(bundle,policy,period,result):
    config = policy['remittance']
    share = decimal(config['share'])
    default_spread = decimal(config['default_spread'])
    tolerance = decimal(config['divergence_tolerance_pp'])/HUNDRED
    evidence = re.search(r'PARTICIPACAO DE\s+(\d+(?:[.,]\d+)?)%',normalize(bundle.email_body))
    if not evidence or decimal(evidence[1].replace(',','.'))/100 != share:
        raise ValueError('Configured remittance share does not match the source email')
    effective = resolve_duplicates(bundle.remittances,'operation','REMESSA',result)
    eligible = []
    contested = []
    unregistered = defaultdict(list)
    groups = defaultdict(list)
    names = {}
    for row in effective:
        event = row[config['competence_event']]
        if row['status'] not in {'APROVADO','APROVADO C/ RESSALVA'}:
            result.cover('REMESSA',row,'STATUS_PENDENTE','Status sem regra aprovada')
            result.pending(f'fxstatus:{row["operation"]}','STATUS_DESCONHECIDO','Status sem tratamento nesta versão.','Helena (financeiro)',[source(row,row['spread'],'spread afetado')],row['operation'])
            continue
        if event is None:
            result.cover('REMESSA',row,'DATA_PENDENTE','Sem evento de competência')
            result.pending(f'fxdate:{row["operation"]}','DATA_AUSENTE','Sem data para aplicar o corte de competência.','Helena (financeiro)',[source(row,row['spread'],'spread afetado')],row['operation'])
            continue
        if event.isoformat()[:7] != period:
            result.cover('REMESSA',row,'FORA_COMPETENCIA','Data de contratação fora do mês')
            continue
        if row['spread'] < 0 and config['negative_spread'] == 'exclude_and_contest':
            contested.append(row)
            result.cover('REMESSA',row,'CONTESTAR','Spread negativo: trava vencida; fora da comissão e da nota')
            result.contests['PONTE'].append({'motivo':'SPREAD_NEGATIVO','ref_origem':row['operation'],'lojista':row['name'],'valor_brl':row['spread'],'detalhe':f'Spread realizado {row["spread"]} ({row["notes"] or "sem observação"}); trava de 2 horas vencida, não aceito pela Tarvo.'})
            continue
        eligible.append(row)
        result.cover('REMESSA',row,'INCLUIDO','50% do spread realizado; competência pela contratação')
        amount = quantize(row['spread']*share)
        groups[row['cnpj']].append(source(row,amount,f'quantize({row["spread"]}*{share}); half_up por operação'))
        names[row['cnpj']] = row['name']
        contracts = [c for c in bundle.contracts if c['cnpj'] == row['cnpj'] and c['start'] <= row['contracted'] <= c['end']]
        if not contracts:
            unregistered[row['cnpj']].append(row)
            contracted, contract_ref = default_spread, ''
        else:
            contracted = contracts[0]['spread'] if contracts[0]['spread'] is not None else default_spread
            contract_ref = contracts[0]['_source']['ref_origem']
        base = row['foreign_amount']*row['reference_rate']
        if base <= 0:
            result.pending(f'fx-base:{row["operation"]}','BASE_REMESSA_INVALIDA','Valor em moeda ou PTAX zerado: spread aplicado não calculável; comparação com o contrato não feita.','Helena (financeiro)',[source(row,row['spread'],'spread realizado')],row['operation'])
            continue
        applied = row['spread']/base
        if abs(applied-contracted) > tolerance:
            difference = quantize(row['spread']-base*contracted)
            divergence = result.emit('divergencias_taxa','DIV',f'REMESSA:{row["operation"]}',{
                'cnpj':row['cnpj'],'linha_negocio':'REMESSA','ref_origem':row['operation'],'taxa_contratada_pct':quantize(contracted*HUNDRED),
                'taxa_aplicada_pct':quantize(applied*HUNDRED*HUNDRED)/HUNDRED,'diferenca_brl':difference,'status':'A_CONTESTAR',
                'lojista':row['name'],'tipo_lancamento':'REMESSA','data_movimento':row['contracted'],'data_vigencia':row['contracted'],
                'valor_bruto_brl':base,'ref_contrato':contract_ref,'contraparte':'PONTE',
            },[source(row,difference,f'quantize({row["spread"]}-{row["foreign_amount"]}*{row["reference_rate"]}*{contracted}); valor cheio pago a mais pelo lojista')])
            result.contests['PONTE'].append({'motivo':'SPREAD_ACIMA_DO_CONTRATO' if difference > 0 else 'SPREAD_ABAIXO_DO_CONTRATO','ref_origem':row['operation'],'lojista':row['name'],'valor_brl':difference,'detalhe':f'Spread aplicado {quantize(applied*HUNDRED*HUNDRED)/HUNDRED}% x contratado {contracted*HUNDRED}%','id_saida':divergence['id_saida']})
    excess = [r for r in result.tables['divergencias_taxa'] if r['linha_negocio'] == 'REMESSA']
    if excess:
        parts = [part for part in result.traces if part['id_saida'] in {r['id_saida'] for r in excess}]
        result.pending('fx:excess','DIVERGENCIA_A_CONTESTAR_PONTE','Spread diferente do contratado, valor cheio (positivo: lojista pagou a mais). A nota de setembro sai pelo realizado; se a Ponte devolver, a participação é ajustada no mês do ajuste.','Helena (financeiro)',[{k:v for k,v in p.items() if k != 'id_saida'} for p in parts],'REMESSA')
    if contested:
        result.pending('fx:negative','SPREAD_NEGATIVO_CONTESTAR','Spread negativo com trava vencida: fora da comissão e da nota; contestar com a Ponte. Não presumir desconto no repasse.','Helena (financeiro)',[source(r,r['spread'],'spread negativo realizado') for r in contested],'REMESSA')
    for cnpj_value, rows in sorted(unregistered.items()):
        result.pending(f'fx-register:{cnpj_value}','CADASTRO_REMESSA_AUSENTE','Operação de CNPJ fora da planilha: participação calculada mesmo assim (a Ponte paga) e spread padrão usado na comparação.','Comercial',[source(r,r['spread'],'spread realizado') for r in rows],cnpj_value)
    for cnpj_value, terms in sorted(groups.items()):
        result.emit('comissoes_por_lojista','COM',f'REMESSA:{cnpj_value}',{
            'cnpj':cnpj_value,'lojista':names[cnpj_value],'linha_negocio':'REMESSA','comissao_brl':sum((r['valor'] for r in terms),ZERO),
            'status':'CALCULADO','base_calculo':'50% do spread realizado por operação; competência pela contratação; spreads negativos excluídos',
        },terms)
    result.metrics.update({
        'remessas_lidas':len(bundle.remittances),'remessas_distintas_sem_conflito':len(effective),'remessas_elegiveis':len(eligible),
        'remessas_contestadas':len(contested),'spread_elegivel':sum((r['spread'] for r in eligible),ZERO),
        'participacao_remessas':sum((r['valor'] for terms in groups.values() for r in terms),ZERO),
        'diferenca_remessa_brl':sum((r['diferenca_brl'] for r in excess),ZERO),
    })


def classify_banks(bundle,policy,period,result):
    entries = []
    own_transfers = []
    seen = set()
    for entry in sorted(bundle.bank_entries,key=lambda row:(row['bank'],row['date'],row['_source']['ref_origem'])):
        key = (entry['bank'],entry['_source']['ref_origem'])
        if key in seen:
            raise ValueError(f'Duplicate bank transaction identity: {key}')
        seen.add(key)
        if entry['date'].isoformat()[:7] != period:
            result.cover('BANCO',entry,'FORA_COMPETENCIA','Movimento fora do período')
            continue
        description = normalize(entry['description'])
        rule = next((r for r in policy['bank_rules'] if r['bank'] in {'ANY',entry['bank']} and re.search(r['pattern'],description)),None)
        account = rule['account'] if rule else ''
        if account and (account not in bundle.accounts or bundle.accounts[account]['ACEITA_LANCTO'] != 'S' or bundle.accounts[account]['TIPO'] != 'ANALITICA'):
            raise ValueError(f'Invalid posting account in bank rule: {account}')
        result.emit('lancamentos_classificados','BAN',':'.join(key),{
            'banco':entry['bank'],'ref_origem':entry['_source']['ref_origem'],'data':entry['date'].isoformat(),
            'descricao':entry['description'],'valor':entry['amount'],'conta_codigo':account,'metodo':'REGRA',
            'confianca':rule['confidence'] if rule else '0','status':'SUGERIDO' if rule else 'PENDENTE','regra_id':rule['id'] if rule else '',
            'conta_descricao':bundle.accounts[account]['DESCRICAO'] if account else '',
        },[source(entry,entry['amount'],'valor do movimento bancário')])
        result.cover('BANCO',entry,'CLASSIFICADO' if rule else 'SEM_CLASSIFICACAO','Contrapartida do movimento por regra configurada')
        entries.append(entry)
        if not rule:
            result.pending(f'bank:{key}','CONCILIACAO_BANCARIA','Movimento sem regra de classificação.','Helena (financeiro)',[source(entry,entry['amount'],'movimento bancário afetado')],':'.join(key))
        elif rule['scope'] == 'unknown_credit':
            result.pending(f'bank:{key}','CREDITO_NAO_IDENTIFICADO','Crédito sem pagador identificado: mantido em créditos não identificados, não é receita até alguém identificar.','Helena (financeiro) / Tesouraria',[source(entry,entry['amount'],'crédito não identificado')],':'.join(key))
        elif rule['scope'] == 'returned_payment':
            result.pending(f'bank:{key}','REPASSE_DEVOLVIDO','PIX de repasse devolvido: o repasse volta a ser devido ao lojista (mesma conta do pagamento original). Motivo da devolução ainda desconhecido.','Helena (financeiro)',[source(entry,entry['amount'],'repasse devolvido')],':'.join(key))
        if rule and rule['scope'] == 'own_transfer':
            own_transfers.append(entry)
    for entry in own_transfers:
        pairs = [r for r in own_transfers if r['bank'] != entry['bank'] and r['date'] == entry['date'] and r['amount'] == -entry['amount']]
        reverse_count = len([r for r in own_transfers if r['bank'] == entry['bank'] and r['date'] == entry['date'] and r['amount'] == entry['amount']])
        if len(pairs) != 1 or reverse_count != 1:
            result.pending(f'transfer:{entry["bank"]}:{entry["_source"]["ref_origem"]}','TRANSFERENCIA_EM_TRANSITO','Transferência própria sem contrapartida na outra conta no mesmo dia. Fica em transferências entre contas próprias até conferir o extrato da outra conta (em 09/2026, o financeiro informou que a saída de 30/09 cai no Meridiano em 01/10).','Tesouraria',[source(entry,entry['amount'],'transferência em trânsito')])
    result.metrics.update({'movimentos_bancarios_lidos':len(bundle.bank_entries),'movimentos_bancarios_exportados':len(entries),'saldos_bancarios':bundle.bank_balances})


def propose_invoices(bundle,period,result):
    partner = re.search(r'Backoffice Parceiros\s*-\s*(.*?)\s*-\s*CNPJ\s*([\d./-]+)',bundle.email_body,re.I)
    fx_partner = (cnpj(partner[2]),partner[1].strip()) if partner else None
    groups = defaultdict(list)
    for commission in result.tables['comissoes_por_lojista']:
        if commission['linha_negocio'] == 'CHECKOUT':
            recipient = (commission['cnpj'],commission['lojista'])
        elif fx_partner:
            recipient = fx_partner
        else:
            if not any(r['tipo'] == 'TOMADOR_NAO_IDENTIFICADO' for r in result.tables['pendencias']):
                result.pending('invoice:partner','TOMADOR_NAO_IDENTIFICADO','Não foi possível obter o parceiro no e-mail. Nota de remessa não proposta.','Fiscal / Helena (financeiro)')
            continue
        groups[(recipient[0],recipient[1],commission['linha_negocio'])].append(commission)
    commission_traces = defaultdict(list)
    for part in result.traces:
        commission_traces[part['id_saida']].append({k:v for k,v in part.items() if k != 'id_saida'})
    competence = f'{period[5:]}/{period[:4]}'
    for (recipient_cnpj,name,line), commissions in sorted(groups.items()):
        amount = sum((r['comissao_brl'] for r in commissions),ZERO)
        terms = [part for commission in commissions for part in commission_traces[commission['id_saida']]]
        if amount <= 0:
            result.pending(f'invoice:{recipient_cnpj}:{line}','SALDO_NAO_POSITIVO_SEM_NOTA',f'Comissão do mês de {name} é {amount}: não emite nota e o saldo não é carregado automaticamente. Tratar com o lojista.','Helena (financeiro)',terms,recipient_cnpj)
            continue
        service = 'Comissão de intermediação de pagamentos (checkout)' if line == 'CHECKOUT' else 'Intermediação de câmbio - participação de 50% no spread das remessas'
        result.emit('notas_a_emitir','NFC',f'{recipient_cnpj}:{line}',{
            'tomador_cnpj':recipient_cnpj,'tomador':name,'linha_negocio':line,'valor_brl':amount,
            'discriminacao':f'{service} - competência {competence}',
            'status':'A_EMITIR_APOS_REVISAO','comissoes_origem':';'.join(r['id_saida'] for r in commissions),
        },terms)


def validate_result(bundle,result):
    by_output = defaultdict(list)
    for trace in result.traces:
        if trace['arquivo_origem'] not in bundle.sources or not trace['ref_origem'] or trace['linha_origem'] < 1:
            raise ValueError('Trace contains an unknown source reference')
        if not trace['valor'].is_finite():
            raise ValueError('Trace contains an invalid monetary amount')
        by_output[trace['id_saida']].append(trace)
    ids = set()
    for name, rows in result.tables.items():
        for row in rows:
            output_id = row['id_saida']
            if output_id in ids:
                raise ValueError('Output IDs must be unique across all outputs')
            ids.add(output_id)
            amount = row[AMOUNT_COLUMNS[name]]
            if amount is not None and (not by_output[output_id] or sum((r['valor'] for r in by_output[output_id]),ZERO) != amount):
                raise ValueError(f'Trace does not reproduce {name}/{output_id}')
            if amount is None and by_output[output_id]:
                raise ValueError('Unknown pending amount must not have monetary contributions')
            for key in ['cnpj','tomador_cnpj']:
                if key in row:
                    cnpj(row[key])
    if set(by_output)-ids:
        raise ValueError('Orphan trace')
    expected = len(bundle.checkout)+len(bundle.remittances)+len(bundle.bank_entries)
    coverage_keys = [(r['arquivo_origem'],r['aba_origem'],r['linha_origem']) for r in result.coverage]
    if len(coverage_keys) != expected or len(set(coverage_keys)) != expected:
        raise ValueError('Input coverage is missing or duplicates source rows')
    result.checks.extend([
        {'check':'monetary_trace_reconciliation','status':'PASS','outputs':len(ids)},
        {'check':'source_row_coverage','status':'PASS','rows':expected},
        {'check':'unique_output_ids_and_cnpjs','status':'PASS'},
        {'check':'finance_rules_applied','status':'PASS','reason':'Regras respondidas pela Helena no Slack aplicadas; premissas residuais em HIPOTESES.md.'},
    ])


def close_month(bundle,policy,period):
    validate_policy(policy)
    if not re.fullmatch(r'\d{4}-\d{2}',period):
        raise ValueError('Period must use YYYY-MM')
    datetime.strptime(period+'-01','%Y-%m-%d')
    result = ClosingResult()
    for question in policy['open_questions']:
        result.pending('rule:'+question['id'],'DECISAO_DO_FINANCEIRO',question['reason'],question['owner'])
    close_checkout(bundle,policy,period,result)
    close_remittances(bundle,policy,period,result)
    classify_banks(bundle,policy,period,result)
    propose_invoices(bundle,period,result)
    validate_result(bundle,result)
    checkout_divergences = [r for r in result.tables['divergencias_taxa'] if r['linha_negocio'] == 'CHECKOUT']
    result.metrics.update({
        'periodo':period,'status':'CALCULADO','regras':'REGRAS_DO_FINANCEIRO',
        'divergencias':len(result.tables['divergencias_taxa']),'divergencias_checkout':len(checkout_divergences),
        'diferenca_checkout_brl':sum((r['diferenca_brl'] for r in checkout_divergences),ZERO),
        'comissao_checkout':sum((r['comissao_brl'] for r in result.tables['comissoes_por_lojista'] if r['linha_negocio']=='CHECKOUT'),ZERO),
        'notas':len(result.tables['notas_a_emitir']),'valor_notas':sum((r['valor_brl'] for r in result.tables['notas_a_emitir']),ZERO),
        'pendencias':len(result.tables['pendencias']),
    })
    for rows in result.tables.values():
        rows.sort(key=lambda row:row['id_saida'])
    for items in result.contests.values():
        items.sort(key=lambda row:(row['motivo'],row['lojista'],row['ref_origem']))
    result.traces.sort(key=lambda row:(row['id_saida'],row['arquivo_origem'],row['aba_origem'],row['linha_origem'],str(row['valor'])))
    result.coverage.sort(key=lambda row:(row['arquivo_origem'],row['aba_origem'],row['linha_origem']))
    return result
