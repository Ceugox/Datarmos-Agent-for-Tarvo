from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
import hashlib
import re
import unicodedata

CENT = Decimal('0.01')


def normalize(value):
    decomposed = unicodedata.normalize('NFKD', str(value or ''))
    return ''.join(c for c in decomposed if not unicodedata.combining(c)).upper().strip()


def decimal(value):
    if value is None or str(value).strip() == '':
        raise ValueError('Missing numeric value')
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f'Invalid numeric value: {value!r}') from error
    if not result.is_finite():
        raise ValueError('Non-finite numeric value')
    return result


def brazilian_decimal(value):
    return decimal(str(value).strip().replace('.', '').replace(',', '.'))


def parse_rate(value):
    if value is None or value == '':
        return None
    if normalize(value) == 'PADRAO':
        return None
    if isinstance(value, str) and value.endswith('%'):
        result = brazilian_decimal(value[:-1]) / 100
    else:
        result = decimal(value)
    if not Decimal(0) <= result < Decimal(1):
        raise ValueError(f'Contract rate must be a fraction: {value!r}')
    return result


def cnpj(value):
    if isinstance(value, (int, float, Decimal)):
        numeric = decimal(value)
        if numeric != numeric.to_integral_value():
            raise ValueError('CNPJ must be an integer or formatted text')
        digits = str(int(numeric)).zfill(14)
    else:
        text = str(value or '').strip()
        if not re.fullmatch(r'[\d./-]+', text):
            raise ValueError(f'Invalid CNPJ representation: {value!r}')
        digits = re.sub(r'\D', '', text)
    if len(digits) != 14:
        raise ValueError(f'CNPJ must contain 14 digits: {value!r}')
    return digits


def quantize(value, policy='half_up'):
    rounding = {'half_up': ROUND_HALF_UP, 'truncate': ROUND_DOWN}[policy]
    return value.quantize(CENT, rounding=rounding)


def identifier(prefix, *parts):
    digest = hashlib.sha256('|'.join(str(p) for p in parts).encode()).hexdigest()[:18]
    return f'{prefix}-{digest}'


def parse_validity(value):
    text = normalize(value)
    matches = re.findall(r'\d{2}/\d{2}/\d{4}', text)
    if len(matches) != 1:
        raise ValueError(f'Unsupported contract validity: {value!r}')
    day, month, year = map(int, matches[0].split('/'))
    boundary = date(year, month, day)
    if text.startswith('ATE '):
        return date.min, boundary
    if text == matches[0] or text.startswith('A PARTIR DE '):
        return boundary, date.max
    raise ValueError(f'Unsupported contract validity: {value!r}')


def allocate_shares(amounts, mode):
    if mode == 'per_operation':
        return {key: quantize(value) for key, value in amounts.items()}
    if mode != 'aggregate':
        raise ValueError(f'Unknown allocation policy: {mode}')
    allocated = {key: quantize(value, 'truncate') for key, value in amounts.items()}
    residual = quantize(sum(amounts.values(), Decimal(0))) - sum(allocated.values(), Decimal(0))
    count = int(abs(residual / CENT))
    direction = CENT if residual > 0 else -CENT
    candidates = sorted(amounts, key=lambda key: (-(amounts[key] - allocated[key]) if residual > 0 else amounts[key] - allocated[key], key))
    if count > len(candidates):
        raise ValueError('Allocation residual exceeds source coverage')
    for key in candidates[:count]:
        allocated[key] += direction
    assert sum(allocated.values(), Decimal(0)) == quantize(sum(amounts.values(), Decimal(0)))
    return allocated


@dataclass
class ClosingInputs:
    checkout: list = field(default_factory=list)
    contracts: list = field(default_factory=list)
    remittances: list = field(default_factory=list)
    bank_entries: list = field(default_factory=list)
    accounts: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
    attachments: dict = field(default_factory=dict)
    bank_balances: dict = field(default_factory=dict)
    email_body: str = ''


def source(record, amount, formula):
    return {**record['_source'], 'valor': amount, 'formula': formula}
