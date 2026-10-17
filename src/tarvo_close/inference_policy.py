"""Inference policy: per-class mode and ceiling. The ceiling is enforced in code, so editing the JSON never raises it (ADR 0002)."""
from decimal import Decimal, InvalidOperation
import json

from .exceptions import CLASSES

MODES = ('desligado','sombra','sugerir','automatico')
CODE_CEILINGS = {'DECISAO':'sugerir', 'CONDICAO_COMERCIAL':'sugerir', 'DADO_INVALIDO':'desligado'}
MIN_CLEAN_CASES = 35


def _rank(mode):
    return MODES.index(mode)


def _ceiling(classe):
    return CODE_CEILINGS.get(classe,'automatico')


def effective_mode(policy, classe):
    entry = policy.get('classes',{}).get(classe)
    if entry is None:
        return 'desligado'
    return min(entry.get('modo','desligado'),entry.get('teto','desligado'),_ceiling(classe),key=_rank)


def load_inference_policy(path):
    with open(path,encoding='utf-8') as handle:
        policy = json.load(handle)
    classes = policy.get('classes',{})
    for classe in CLASSES:
        if classe not in classes:
            raise ValueError(f'Inference policy without class: {classe}')
        entry = classes[classe]
        mode, ceiling = entry.get('modo'), entry.get('teto')
        if mode not in MODES or ceiling not in MODES:
            raise ValueError(f'{classe}: modo/teto must be one of {MODES}')
        if _rank(ceiling) > _rank(_ceiling(classe)):
            raise ValueError(f'{classe}: o teto da classe não passa de {_ceiling(classe)}')
        if _rank(mode) > _rank(ceiling):
            raise ValueError(f'{classe}: modo {mode} acima do teto {ceiling}')
        if mode == 'automatico':
            criterion = entry.get('criterio') or {}
            if not entry.get('aprovado_por') or not entry.get('aprovado_em'):
                raise ValueError(f'{classe}: automatico exige aprovado_por e aprovado_em')
            if criterion.get('casos_seguidos_sem_erro',0) < MIN_CLEAN_CASES or criterion.get('erros',0) != 0:
                raise ValueError(f'{classe}: automatico exige {MIN_CLEAN_CASES} casos seguidos sem erro no backtest')
        confidence = entry.get('confianca')
        if confidence is not None:
            try:
                valid = isinstance(confidence,str) and Decimal(0) <= Decimal(confidence) <= Decimal(1)
            except InvalidOperation:
                valid = False
            if not valid:
                raise ValueError(f'{classe}: confianca must be null or a decimal string between 0 and 1')
    return policy
