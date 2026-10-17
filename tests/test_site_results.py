"""The public dashboard preserves unknown amounts and derives figures from a closing."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import sys
import unittest

from test_cli_inference import run

ROOT = Path(__file__).resolve().parents[1]


class SiteResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = TemporaryDirectory()
        cls.closing = Path(cls.workspace.name) / 'closing'
        code, _, error = run(cls.closing, '--no-llm')
        if code:
            raise AssertionError(error)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.workspace = TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.folder = Path(self.workspace.name)
        self.source = self.folder / 'closing'
        shutil.copytree(self.closing, self.source)
        self.output = self.folder / 'results.js'

    def generate(self, *args):
        return subprocess.run(
            [sys.executable, '-X', 'utf8', str(ROOT / 'site/build_data.py'), '--input', str(self.source),
             '--output', str(self.output), *map(str, args)],
            capture_output=True, text=True, encoding='utf-8',
        )

    def results(self):
        return json.loads(self.output.read_text(encoding='utf-8').removeprefix('window.RESULTS = ').strip().removesuffix(';'))

    def test_unknown_pending_amounts_stay_unknown_and_the_snapshot_identifies_its_run(self):
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = self.results()
        pending = next(row for row in snapshot['pending'] if row['tipo'] == 'DECISAO_DO_FINANCEIRO')
        self.assertIsNone(pending['valor'])
        manifest = json.loads((self.source / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(snapshot['source']['run_id'], manifest['run_id'])
        self.assertIsNone(snapshot['late_adjustments'])
        self.assertNotIn('runtime_s', snapshot)

    def test_review_amounts_follow_the_source_instead_of_september_constants(self):
        metrics_path = self.source / 'metrics.json'
        metrics = json.loads(metrics_path.read_text(encoding='utf-8'))
        metrics.update(devolucao_condicao_comercial='12.34', diferenca_checkout_brl='56.78', diferenca_remessa_brl='9.10')
        metrics_path.write_text(json.dumps(metrics), encoding='utf-8')
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stderr)
        amounts = self.results()['amounts_to_review']
        self.assertEqual(amounts['Casa do Estudante · devolução a revisar'], 12.34)
        self.assertEqual(amounts['Orbe · divergências a contestar'], 56.78)
        self.assertEqual(amounts['Ponte · divergências a contestar'], 9.10)
        self.assertEqual(amounts['Spreads negativos · contestação a revisar'], 1834.05)

    def test_before_and_after_figures_use_the_supplied_baseline(self):
        baseline = self.folder / 'baseline'
        baseline.mkdir()
        (baseline / 'metrics.json').write_text(json.dumps({
            'periodo': '2026-09', 'comissao_checkout': '500.01', 'valor_notas': '600.02',
        }), encoding='utf-8')
        result = self.generate('--baseline', baseline)
        self.assertEqual(result.returncode, 0, result.stderr)
        comparison = self.results()['late_adjustments']
        self.assertEqual(comparison['commission_before'], 500.01)
        self.assertEqual(comparison['notes_before'], 600.02)
        self.assertEqual(comparison['commission_after'], 203735.34)

    def test_a_baseline_from_another_period_is_rejected_without_publishing(self):
        baseline = self.folder / 'baseline'
        baseline.mkdir()
        (baseline / 'metrics.json').write_text(json.dumps({'periodo': '2026-08'}), encoding='utf-8')
        result = self.generate('--baseline', baseline)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('same period', result.stderr)
        self.assertFalse(self.output.exists())
