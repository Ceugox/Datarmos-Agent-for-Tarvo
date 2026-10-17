from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import json
import os
import shutil
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.cli import main
from tarvo_close.resolver import FakeResolver

PACK = ROOT/'Tarvo_Data_Pack_set2026'
VOLATILE = {'index.html','manifest.json'}


def run(output, *extra, resolver=None):
    env = {k:v for k,v in os.environ.items() if k != 'ANTHROPIC_API_KEY'}
    out, err = StringIO(), StringIO()
    with mock.patch.dict(os.environ,env,clear=True), redirect_stdout(out), redirect_stderr(err):
        code = main(['--input',str(PACK),'--period','2026-09','--output',str(output),*extra],resolver=resolver)
    return code, out.getvalue(), err.getvalue()


def files(directory):
    return {p.relative_to(directory).as_posix() for p in Path(directory).rglob('*') if p.is_file()}


def same_bytes(test, left, right, ignore=VOLATILE):
    left, right = Path(left), Path(right)
    names = {n for n in files(left)|files(right) if n not in ignore}
    test.assertEqual({n for n in files(left) if n not in ignore},{n for n in files(right) if n not in ignore})
    for name in names:
        test.assertEqual((left/name).read_bytes(),(right/name).read_bytes(),name)


class CliInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.base = Path(cls.tmp.name)/'no-llm'
        cls.code, cls.out, cls.err = run(cls.base,'--no-llm')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_llm_has_no_audit_and_matches_versioned_output(self):
        self.assertEqual(self.code,0)
        self.assertNotIn('auditoria.jsonl',files(self.base))
        self.assertNotIn('Inference:',self.out)
        same_bytes(self,ROOT/'saida',self.base)

    def test_without_key_is_the_same_as_no_llm(self):
        with TemporaryDirectory() as directory:
            code, out, err = run(Path(directory)/'out')
            self.assertEqual(code,0)
            self.assertIn('ANTHROPIC_API_KEY not set',err)
            self.assertNotIn('auditoria.jsonl',files(Path(directory)/'out'))
            same_bytes(self,self.base,Path(directory)/'out')

    def test_layer_on_writes_audit_and_changes_nothing_else(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)/'out'
            code, out, err = run(output,'--cache-dir',str(Path(directory)/'cache'),resolver=FakeResolver())
            self.assertEqual(code,0)
            events = [json.loads(line) for line in (output/'auditoria.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([e['evento'] for e in events],['EXCECAO']*13+['EXECUCAO'])
            same_bytes(self,self.base,output,VOLATILE|{'auditoria.jsonl'})
            self.assertEqual(files(output)-files(self.base),{'auditoria.jsonl'})
            line = next(l for l in out.splitlines() if l.startswith('Inference:'))
            self.assertIn('13 exceptions queued, 0 proposals, 13 to humans, 0 tokens, USD unknown',line)

    def test_decisions(self):
        from tarvo_close.closing import close_month
        from tarvo_close.readers import read_inputs
        policy = json.loads((ROOT/'config/closing-policy.json').read_text(encoding='utf-8'))
        known = close_month(read_inputs(PACK),policy,'2026-09').exceptions[0].excecao_id
        with TemporaryDirectory() as directory:
            root = Path(directory)
            good = root/'good.json'
            good.write_text(json.dumps([{'excecao_id':known, 'decisao':'aprovar', 'decidido_por':'Helena', 'motivo':'ok'}]),encoding='utf-8')
            fake = FakeResolver()
            code, _, err = run(root/'a','--decisoes',str(good),'--cache-dir',str(root/'c'),resolver=fake)
            self.assertEqual(code,1)  # decisions only make sense as a revision of a parent run
            self.assertIn('Closing failed',err)
            self.assertFalse((root/'a').exists())
            self.assertEqual(fake.calls,[])
            for index, bad in enumerate(({'excecao_id':known, 'decisao':'aprovar', 'motivo':'ok'},
                                         {'excecao_id':known, 'decisao':'talvez', 'decidido_por':'Helena', 'motivo':'ok'})):
                path = root/f'bad{index}.json'
                path.write_text(json.dumps([bad]),encoding='utf-8')
                fake = FakeResolver()
                code, _, err = run(root/f'b{index}','--decisoes',str(path),'--revisao-de',str(self.base),'--cache-dir',str(root/'c'),resolver=fake)
                self.assertEqual(fake.calls,[])
                self.assertEqual(code,1)
                self.assertIn('Closing failed',err)
                self.assertFalse((root/f'b{index}').exists())

    def test_inference_policy_above_the_ceiling_fails(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = json.loads((ROOT/'config/inference-policy.json').read_text(encoding='utf-8'))
            data['classes']['DECISAO']['teto'] = 'automatico'
            path = root/'policy.json'
            path.write_text(json.dumps(data),encoding='utf-8')
            code, _, err = run(root/'out','--inference-policy',str(path),'--cache-dir',str(root/'c'),resolver=FakeResolver())
            self.assertEqual(code,1)
            self.assertIn('Closing failed',err)


if __name__ == '__main__':
    unittest.main()
