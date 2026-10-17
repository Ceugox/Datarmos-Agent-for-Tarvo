"""Inference pipeline (ADR 0002): queue of typed exceptions, resolver, deterministic validator, audit log.

A validated proposal is applied only in `automatico` mode (run_inference) or by a human decision in a new revision (run_revision).
"""
from pathlib import Path
import hashlib
import json
import sys

from .domain import identifier
from .reporting import encode_json
from .inference_policy import effective_mode
from .privacy import mask_personal_data
from .resolver import USAGE_KEYS, Failure, cost_usd, zero_usage
from .validators import check_shape, source_line, validator_for

DECISIONS = ('aprovar', 'rejeitar', 'editar')


def build_queue(result, inference_policy):
    return [{'excecao':item.as_dict(), 'modo':effective_mode(inference_policy,item.classe)} for item in result.exceptions]


def exception_payload(excecao, bundle):
    payload = excecao.as_dict() if hasattr(excecao,'as_dict') else dict(excecao)
    cited = []
    for ref in payload['refs']:
        try:
            text = mask_personal_data(source_line(bundle,ref))
        except ValueError:
            text = ''  # the evidence check rejects any proposal that cites this row
        cited.append({'arquivo':ref['arquivo'], 'ref':ref['ref'], 'texto':text})
    return {**payload, 'linhas_citadas':cited}


def fixed_context(bundle, policy, period=None):
    return {'closing_policy':policy, 'accounts':bundle.accounts, 'period':period}


def _cost(model, usage):
    value = cost_usd(model,usage)
    return None if value is None else str(value)


def _event(item, resultado, motivo, resolver, proposta=None, checks=None, usage=None, cached=False):
    usage = {**zero_usage(), **(usage or {})}
    excecao = item['excecao']
    return {'evento':'EXCECAO', 'excecao_id':excecao['excecao_id'], 'classe':excecao['classe'], 'tipo':excecao['tipo'], 'modo':item['modo'],
            'resultado':resultado, 'motivo':motivo, 'proposta':proposta, 'verificacoes':checks or [], 'tokens':usage,
            'custo_usd':_cost(resolver.model,usage), 'cache':cached, 'aplicada':False}


def _pending(result, excecao_id):
    return next((row for row in result.tables['pendencias'] if row['id_saida'] == excecao_id),None)


def apply_proposal(result, bundle, inference_policy, excecao, proposal, confianca=None):
    """Applies a validated MOVIMENTO_SEM_REGRA proposal to the bank row and its pending item. Only the account fields change, never the amount."""
    ban_id = identifier('BAN',excecao['escopo'])
    row = next((r for r in result.tables['lancamentos_classificados'] if r['id_saida'] == ban_id),None)
    pending = _pending(result,excecao['excecao_id'])
    trace = next((t for t in result.traces if t['id_saida'] == ban_id),None)
    if row is None or pending is None or trace is None:
        raise ValueError(f'Exception {excecao["excecao_id"]} has no bank row to apply to')
    if pending['status'] != 'PENDENTE' or row['metodo'] == 'IA':
        raise ValueError(f'Exception {excecao["excecao_id"]} was already decided')
    if excecao['classe'] != 'MOVIMENTO_SEM_REGRA' or proposal.get('acao') != 'CLASSIFICAR_CONTA':
        raise ValueError(f'Exception {excecao["excecao_id"]}: only CLASSIFICAR_CONTA on MOVIMENTO_SEM_REGRA can be applied')
    code = proposal['parametros']['conta_codigo']
    if code not in bundle.accounts:
        raise ValueError(f'Account {code} is not in the chart of accounts')
    row.update(conta_codigo=code,conta_descricao=bundle.accounts[code]['DESCRICAO'],metodo='IA',status='SUGERIDO',regra_id='',
               confianca=inference_policy['classes'][excecao['classe']].get('confianca') or '' if confianca is None else confianca)
    trace['formula'] += ''.join(f'; evidência IA: {e["arquivo"]} {e["ref"]} "{e["trecho"]}"' for e in proposal['evidencias'])
    pending['status'] = 'RESOLVIDA'
    return row


def run_inference(bundle, result, closing_policy, inference_policy, resolver, audit, budget):
    context = fixed_context(bundle,closing_policy,result.metrics.get('periodo'))
    by_id = {item.excecao_id:item for item in result.exceptions}
    events, total = [], zero_usage()
    for item in build_queue(result,inference_policy):
        excecao = item['excecao']
        validator = validator_for(excecao['classe'])
        if item['modo'] == 'desligado':
            event = _event(item,'HUMANO','MODO_DESLIGADO',resolver)
        elif validator is None:
            event = _event(item,'HUMANO','SEM_VALIDADOR',resolver)
        elif budget.exhausted:
            event = _event(item,'HUMANO','ORCAMENTO_ESGOTADO',resolver)
        else:
            payload = exception_payload(by_id[excecao['excecao_id']],bundle)
            answer = resolver.propose(payload,context)
            budget.charge(answer.usage)
            for key in USAGE_KEYS:
                total[key] += int(answer.usage.get(key,0) or 0)
            if isinstance(answer,Failure):
                event = _event(item,'HUMANO',answer.reason,resolver,usage=answer.usage)
            else:
                data, cached = answer.data, answer.cached
                shape = check_shape(data,excecao)
                if shape:
                    checks = [{'check':'schema', 'status':'FAIL', 'reason':'; '.join(shape)}]
                    event = _event(item,'HUMANO','FORA_DO_SCHEMA',resolver,proposta=data,checks=checks,usage=answer.usage,cached=cached)
                elif data['acao'] == 'ENCAMINHAR_HUMANO' or data['requer_humano']:
                    event = _event(item,'HUMANO','REQUER_HUMANO',resolver,proposta=data,usage=answer.usage,cached=cached)
                else:
                    verdict = validator.validate(data,excecao,bundle,context)
                    failed = next((c for c in verdict['checks'] if c['status'] == 'FAIL'),None)
                    if verdict['ok']:
                        resultado, motivo = 'VALIDADA', None
                    else:
                        resultado, motivo = 'HUMANO', 'EVIDENCIA_INVALIDA' if failed and failed['check'] == 'evidencia' else 'VALIDADOR_REJEITOU'
                    event = _event(item,resultado,motivo,resolver,proposta=data,checks=verdict['checks'],usage=answer.usage,cached=cached)
                    if resultado == 'VALIDADA' and item['modo'] == 'automatico':
                        event['confianca'] = apply_proposal(result,bundle,inference_policy,excecao,data)['confianca']
                        event['aplicada'] = True
        audit.record(event)
        events.append(event)
    audit.record({'evento':'EXECUCAO', 'modelo':resolver.model, 'prompt_version':resolver.prompt_version, 'tokens_total':budget.used,
                  'custo_usd_total':_cost(resolver.model,total), 'orcamento':{'limite':budget.limit, 'usado':budget.used, 'esgotado':budget.exhausted}})
    return events


def load_decisions(path, result):
    with open(path,encoding='utf-8') as handle:
        decisions = json.load(handle)
    if not isinstance(decisions,list):
        raise ValueError('Decisions file must be a JSON list')
    known = {item.excecao_id for item in result.exceptions}
    for index, decision in enumerate(decisions):
        if not isinstance(decision,dict):
            raise ValueError(f'Decision {index}: must be an object')
        for key in ('excecao_id','decisao','decidido_por','motivo'):
            if not isinstance(decision.get(key),str) or not decision[key].strip():
                raise ValueError(f'Decision {index}: missing or empty {key}')
        if decision['decisao'] not in DECISIONS:
            raise ValueError(f'Decision {index}: decisao must be one of {DECISIONS}')
        if sum(1 for other in decisions if isinstance(other,dict) and other.get('excecao_id') == decision['excecao_id']) > 1:
            raise ValueError(f'Decision {index}: more than one decision for {decision["excecao_id"]}')
        if decision['excecao_id'] not in known:
            raise ValueError(f'Decision {index}: unknown excecao_id {decision["excecao_id"]}')
        if 'parametros' in decision and not isinstance(decision['parametros'],dict):
            raise ValueError(f'Decision {index}: parametros must be an object')
        extra = set(decision)-{'excecao_id','decisao','decidido_por','motivo','parametros'}
        if extra:
            raise ValueError(f'Decision {index}: unexpected fields {sorted(extra)}')
    return decisions


STATUS_BY_DECISION = {'aprovar':'APROVADA', 'rejeitar':'REJEITADA'}


def _read_parent(parent_dir, bundle, period, closing_policy):
    parent = Path(parent_dir)
    if not (parent/'manifest.json').is_file():
        raise ValueError(f'Parent run has no manifest.json: {parent}')
    if not (parent/'auditoria.jsonl').is_file():
        raise ValueError('a execução pai não tem auditoria (auditoria.jsonl): rode-a com a camada ligada antes de decidir')
    manifest = json.loads((parent/'manifest.json').read_text(encoding='utf-8'))
    if not isinstance(manifest,dict) or not all(key in manifest for key in ('run_id','period','sources','output_sha256')) \
            or not isinstance(manifest['sources'],dict) or not isinstance(manifest['output_sha256'],dict):
        raise ValueError('Parent manifest.json is malformed')
    if manifest.get('period') != period:
        raise ValueError(f'Parent run is from period {manifest.get("period")}, not {period}')
    if {k:v.get('sha256') for k,v in manifest.get('sources',{}).items()} != {k:v['sha256'] for k,v in bundle.sources.items()}:
        raise ValueError('Parent run used other source files (sources sha256 differ, fontes diferentes): the decisions were taken on different data')
    if manifest['output_sha256'].get('policy.json') != hashlib.sha256(encode_json(closing_policy).encode()).hexdigest():
        raise ValueError('decisões tomadas com outra closing-policy')
    events = [json.loads(line) for line in (parent/'auditoria.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    if not all(isinstance(event,dict) for event in events):
        raise ValueError('Parent auditoria.jsonl is malformed')
    return manifest, events


def _movement(bundle, excecao):
    bank, _, ref = excecao['escopo'].partition(':')
    entry = next((e for e in bundle.bank_entries if e['bank'] == bank and e['_source']['ref_origem'] == ref),None)
    if entry is None:
        raise ValueError(f'Movement {excecao["escopo"]} not found in the statements')
    return entry


def run_revision(bundle, result, closing_policy, inference_policy, parent_dir, decisions, audit):
    """Applies human decisions on top of the parent run (rebuilt without the resolver) and records them in the audit log."""
    manifest, parent_events = _read_parent(parent_dir,bundle,result.metrics['periodo'],closing_policy)
    context = fixed_context(bundle,closing_policy,result.metrics['periodo'])
    by_id = {item.excecao_id:item.as_dict() for item in result.exceptions}

    def validate_and_apply(excecao, proposal, confianca=None):
        verdict = validator_for(excecao['classe']).validate(proposal,excecao,bundle,context)
        row = apply_proposal(result,bundle,inference_policy,excecao,proposal,confianca) if verdict['ok'] else None
        return verdict, row

    def open_pending(excecao_id):
        pending = _pending(result,excecao_id)
        if pending is None or pending['status'] != 'PENDENTE':
            raise ValueError(f'Exception {excecao_id} was already decided')
        return pending

    for event in parent_events:  # replay what the parent applied: deterministic, no resolver
        kind = event.get('evento')
        if kind == 'EXCECAO' and event.get('aplicada') or kind == 'DECISAO_APLICADA' and event.get('resultado') == 'APLICADA':
            if event['excecao_id'] not in by_id:
                raise ValueError(f'Parent run state not reproducible: unknown exception {event["excecao_id"]}')
            verdict, _ = validate_and_apply(by_id[event['excecao_id']],event['proposta'],event.get('confianca'))  # the confidence the parent applied
            if not verdict['ok']:
                failed = next(c for c in verdict['checks'] if c['status'] == 'FAIL')
                raise ValueError(f'Parent run state not reproducible: {event["excecao_id"]} fails {failed["check"]}: {failed["reason"]}')
        elif kind == 'DECISAO_APLICADA' and event.get('resultado') == 'REGISTRADA':
            open_pending(event['excecao_id'])['status'] = STATUS_BY_DECISION[event['decisao']]
    validated = {e['excecao_id']:e for e in parent_events if e.get('evento') == 'EXCECAO' and e.get('resultado') == 'VALIDADA'}
    proposed = {e['excecao_id']:e['proposta'] for e in parent_events if e.get('evento') == 'EXCECAO' and e.get('proposta')}
    own, summary = [], []
    for decision in decisions:
        excecao = by_id[decision['excecao_id']]
        base = {'excecao_id':excecao['excecao_id'], 'classe':excecao['classe'], 'decisao':decision['decisao'], 'decidido_por':decision['decidido_por'], 'motivo':decision['motivo']}
        pending = open_pending(excecao['excecao_id'])
        proposal, checks, outcome = None, [], 'REGISTRADA'
        if decision['decisao'] == 'rejeitar' or validator_for(excecao['classe']) is None:
            if decision['decisao'] == 'editar':
                raise ValueError(f'Exception {excecao["excecao_id"]}: class {excecao["classe"]} has no proposal to edit')
            pending['status'] = STATUS_BY_DECISION[decision['decisao']]
        else:
            if decision['decisao'] == 'aprovar':
                if excecao['excecao_id'] not in validated:
                    raise ValueError(f'Exception {excecao["excecao_id"]}: the parent run has no validated proposal to approve')
                if validated[excecao['excecao_id']].get('modo') not in ('sugerir','automatico'):
                    raise ValueError(f'Exception {excecao["excecao_id"]}: proposta em modo sombra não pode ser aprovada')
                proposal = validated[excecao['excecao_id']]['proposta']
            else:
                code = (decision.get('parametros') or {}).get('conta_codigo')
                if not isinstance(code,str) or not code.strip():
                    raise ValueError(f'Exception {excecao["excecao_id"]}: editar requires parametros.conta_codigo')
                evidence = (proposed.get(excecao['excecao_id']) or {}).get('evidencias')
                if not evidence:
                    ref = excecao['refs'][0]
                    evidence = [{'arquivo':ref['arquivo'], 'ref':ref['ref'], 'trecho':_movement(bundle,excecao)['description']}]
                proposal = {'excecao_id':excecao['excecao_id'], 'classe':excecao['classe'], 'acao':'CLASSIFICAR_CONTA', 'parametros':{'conta_codigo':code.strip()},
                            'evidencias':evidence, 'justificativa':f'Conta editada por {decision["decidido_por"]}: {decision["motivo"]}', 'requer_humano':False}
            verdict, row = validate_and_apply(excecao,proposal)
            checks = verdict['checks']
            outcome = 'APLICADA' if row else 'RECUSADA'
            if outcome == 'RECUSADA':
                failed = next(c for c in checks if c['status'] == 'FAIL')
                print(f'Decision refused for {excecao["excecao_id"]}: {failed["check"]}: {failed["reason"]}',file=sys.stderr)
        own.append({'evento':'DECISAO_APLICADA', **base, 'resultado':outcome, 'verificacoes':checks, 'proposta':proposal, **({'confianca':row['confianca']} if outcome == 'APLICADA' else {})})
        summary.append({**base, 'resultado':outcome})
    number = manifest.get('revisao',{}).get('numero',0)+1
    audit.record({'evento':'REVISAO', 'run_id_pai':manifest['run_id'], 'numero':number})
    for event in own:
        audit.record(event)
    for event in parent_events:  # the parent chain stays readable and lets a later revision decide what is still open
        if event.get('evento') in ('EXCECAO','DECISAO_APLICADA'):
            audit.record({**event, 'herdado':True})
    return {'numero':number, 'run_id_pai':manifest['run_id'], 'decisoes':summary}
