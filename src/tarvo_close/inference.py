"""Inference pipeline (ADR 0002): queue of typed exceptions, resolver, deterministic validator, audit log.

Phase 2 applies nothing: every proposal ends in the audit log only (`aplicada` is always false).
"""
import json

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


def fixed_context(bundle, policy):
    return {'closing_policy':policy, 'accounts':bundle.accounts}


def _cost(model, usage):
    value = cost_usd(model,usage)
    return None if value is None else str(value)


def _event(item, resultado, motivo, resolver, proposta=None, checks=None, usage=None, cached=False):
    usage = {**zero_usage(), **(usage or {})}
    excecao = item['excecao']
    return {'evento':'EXCECAO', 'excecao_id':excecao['excecao_id'], 'classe':excecao['classe'], 'tipo':excecao['tipo'], 'modo':item['modo'],
            'resultado':resultado, 'motivo':motivo, 'proposta':proposta, 'verificacoes':checks or [], 'tokens':usage,
            'custo_usd':_cost(resolver.model,usage), 'cache':cached, 'aplicada':False}


def run_inference(bundle, result, closing_policy, inference_policy, resolver, audit, budget):
    context = fixed_context(bundle,closing_policy)
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
                    verdict = validator.validate(data,excecao,bundle,inference_policy)
                    failed = next((c for c in verdict['checks'] if c['status'] == 'FAIL'),None)
                    if verdict['ok']:
                        resultado, motivo = 'VALIDADA', None
                    else:
                        resultado, motivo = 'HUMANO', 'EVIDENCIA_INVALIDA' if failed and failed['check'] == 'evidencia' else 'VALIDADOR_REJEITOU'
                    event = _event(item,resultado,motivo,resolver,proposta=data,checks=verdict['checks'],usage=answer.usage,cached=cached)
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
        if decision['excecao_id'] not in known:
            raise ValueError(f'Decision {index}: unknown excecao_id {decision["excecao_id"]}')
        if 'parametros' in decision and not isinstance(decision['parametros'],dict):
            raise ValueError(f'Decision {index}: parametros must be an object')
        extra = set(decision)-{'excecao_id','decisao','decidido_por','motivo','parametros'}
        if extra:
            raise ValueError(f'Decision {index}: unexpected fields {sorted(extra)}')
    return decisions


def record_decisions(audit, decisions):
    for decision in decisions:
        audit.record({'evento':'DECISAO_RECEBIDA', **decision, 'aplicada':False})
