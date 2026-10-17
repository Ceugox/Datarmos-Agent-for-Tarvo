from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.audit import AuditLog


class AuditLogTests(unittest.TestCase):
    def test_write_jsonl(self):
        log = AuditLog()
        log.record({'evento':'EXCECAO', 'custo_usd':Decimal('0.048'), 'b':'ção', 'a':1})
        log.record({'evento':'EXECUCAO'})
        with TemporaryDirectory() as directory:
            path = Path(directory)/'auditoria.jsonl'
            log.write(path)
            text = path.read_text(encoding='utf-8')
        lines = text.split('\n')
        self.assertEqual(len(lines),3)
        self.assertEqual(lines[2],'')
        self.assertEqual(lines[0],'{"a": 1, "b": "ção", "custo_usd": "0.048", "evento": "EXCECAO"}')
        self.assertEqual(json.loads(lines[1]),{'evento':'EXECUCAO'})
        self.assertNotIn('timestamp',text)


if __name__ == '__main__':
    unittest.main()
