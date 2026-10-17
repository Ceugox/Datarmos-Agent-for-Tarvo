"""Fixed output format, checked on the bytes the corrector reads: ';' separator, '.' decimal point,
dates as YYYY-MM-DD and CNPJ as 14 digits. Shared by the CLI, revision and API tests."""
import csv
from io import StringIO
from pathlib import Path
import re

DECIMAL = re.compile(r'-?\d+(\.\d+)?')
INTEGER = re.compile(r'\d+')
DATE = re.compile(r'\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])')
CNPJ = re.compile(r'\d{14}')
# Column -> (pattern, empty allowed). Empty means unknown, never zero (README).
COLUMNS = {
    'comissao_brl':(DECIMAL,False), 'diferenca_brl':(DECIMAL,False), 'valor_bruto_brl':(DECIMAL,False), 'valor':(DECIMAL,False),
    'taxa_contratada_pct':(DECIMAL,False), 'taxa_aplicada_pct':(DECIMAL,False),
    'valor_brl':(DECIMAL,True),   # unknown pending amount stays empty
    'confianca':(DECIMAL,True),   # IA line approved before a backtest confidence exists stays empty
    'linha_origem':(INTEGER,False),
    'data':(DATE,False), 'data_movimento':(DATE,False), 'data_vigencia':(DATE,False),
    'cnpj':(CNPJ,False), 'tomador_cnpj':(CNPJ,False),
}


def csv_errors(name, content):
    """Format errors of one CSV given as bytes; empty list when the file follows the fixed format."""
    errors = []
    if content.startswith(b'\xef\xbb\xbf'):
        errors.append(f'{name}: BOM UTF-8 no início')
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError as error:
        return [f'{name}: não é UTF-8 ({error})']
    if '\r' in text:
        errors.append(f'{name}: fim de linha CRLF')
    lines = text.split('\n')
    if not lines or not lines[0]:
        return errors+[f'{name}: sem cabeçalho']
    if ';' not in lines[0] or ',' in lines[0]:
        errors.append(f'{name}: cabeçalho não separado por ";": {lines[0]!r}')
    rows = list(csv.reader(StringIO(text,newline=''),delimiter=';'))
    header = rows[0]
    if len(set(header)) != len(header):
        errors.append(f'{name}: coluna repetida no cabeçalho')
    for number, row in enumerate(rows[1:],start=2):
        if len(row) != len(header):
            errors.append(f'{name}:{number}: {len(row)} campos, cabeçalho tem {len(header)}')
            continue
        for column, value in zip(header,row):
            if column not in COLUMNS:
                continue
            pattern, empty_ok = COLUMNS[column]
            if value == '' and empty_ok:
                continue
            if not pattern.fullmatch(value):
                errors.append(f'{name}:{number}: {column}={value!r} fora do formato')
    return errors


def output_errors(directory):
    """Format errors of every CSV under an output directory (including contestacoes/)."""
    directory = Path(directory)
    paths = sorted(directory.rglob('*.csv'))
    if not paths:
        return [f'{directory}: nenhum CSV']
    return [error for path in paths for error in csv_errors(path.relative_to(directory).as_posix(),path.read_bytes())]


if __name__ == '__main__':
    import sys
    found = [error for directory in sys.argv[1:] for error in output_errors(directory)]
    print('\n'.join(found) if found else f'Formato fixo OK: {", ".join(sys.argv[1:])}')
    raise SystemExit(1 if found or len(sys.argv) < 2 else 0)
