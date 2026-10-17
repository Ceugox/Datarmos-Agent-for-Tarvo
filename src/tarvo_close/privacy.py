"""Personal data masking applied before any text leaves for the inference layer (ADR 0002, LGPD).

CPF and bank account/branch numbers are masked. CNPJ is a company key and stays intact.
"""
import re

CPF = re.compile(r'(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)')
ACCOUNT = re.compile(r'(?<!\w)(conta|c/c|cc|ag[eê]ncia|ag)(\s*:?\s*)(\d[\d.\-]*)',re.IGNORECASE)


def _mask_digits(match):
    return match.group(1)+match.group(2)+re.sub(r'\d','*',match.group(3))


def mask_personal_data(text):
    return ACCOUNT.sub(_mask_digits,CPF.sub('***.***.***-**',text))
