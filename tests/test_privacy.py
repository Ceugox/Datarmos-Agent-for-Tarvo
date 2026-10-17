from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.privacy import mask_personal_data as mask


class PrivacyTests(unittest.TestCase):
    def test_cpf_is_masked_with_and_without_punctuation(self):
        self.assertEqual(mask('PIX 123.456.789-09 JOAO'),'PIX ***.***.***-** JOAO')
        self.assertEqual(mask('PIX 12345678909 JOAO'),'PIX ***.***.***-** JOAO')

    def test_cpf_glued_to_separators_is_masked(self):
        self.assertEqual(mask('PIX-12345678901'),'PIX-***.***.***-**')
        self.assertEqual(mask('TED/123.456.789-01 x'),'TED/***.***.***-** x')
        self.assertEqual(mask('cpf 123.456.789-01/x'),'cpf ***.***.***-**/x')

    def test_account_and_branch_are_masked_keeping_the_keyword(self):
        self.assertEqual(mask('Conta: 4471-0'),'Conta: ****-*')
        self.assertEqual(mask('C/C 90233-1'),'C/C *****-*')
        self.assertEqual(mask('AG 0318'),'AG ****')
        self.assertEqual(mask('agência: 0318 conta 12.345-6'),'agência: **** conta **.***-*')

    def test_cnpj_stays_intact(self):
        for text in ('84.626.315/0001-39','84626315000139','CNPJ 84.626.315/0001-39 PIX','CNPJ 84626315000139 PIX'):
            self.assertEqual(mask(text),text)

    def test_masking_is_idempotent(self):
        text = 'TED CPF 123.456.789-09 Conta: 4471-0 AG 0318 CNPJ 84626315000139'
        self.assertEqual(mask(mask(text)),mask(text))

    def test_text_without_personal_data_is_unchanged(self):
        text = 'TAR PACOTE SERVICOS 09/2026 REF 2026-09-30 R$ 1.234,56'
        self.assertEqual(mask(text),text)


if __name__ == '__main__':
    unittest.main()
