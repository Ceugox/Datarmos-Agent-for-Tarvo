from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from tarvo_close.exceptions import CLASSES
from tarvo_close.inference_policy import effective_mode, load_inference_policy

PATH = ROOT/'config/inference-policy.json'


def edited(**changes):
    policy = json.loads(PATH.read_text(encoding='utf-8'))
    for classe, fields in changes.items():
        policy['classes'][classe].update(fields)
    return policy


class InferencePolicyTests(unittest.TestCase):
    def load(self, policy):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'policy.json'
            path.write_text(json.dumps(policy),encoding='utf-8')
            return load_inference_policy(path)

    def test_repository_policy_loads_with_the_initial_modes(self):
        policy = load_inference_policy(PATH)
        self.assertEqual(policy['prompt_version'],'2026-10-17.1')
        expected = {'MOVIMENTO_SEM_REGRA':'sombra','DECISAO':'sugerir','CONDICAO_COMERCIAL':'sugerir'}
        for classe in CLASSES:
            self.assertEqual(effective_mode(policy,classe),expected.get(classe,'desligado'),classe)

    def test_ceiling_of_decision_classes_cannot_be_raised_in_the_json(self):
        for classe in ('DECISAO','CONDICAO_COMERCIAL'):
            with self.assertRaisesRegex(ValueError,'não passa de sugerir'):
                self.load(edited(**{classe:{'teto':'automatico'}}))
            with self.assertRaisesRegex(ValueError,'não passa de sugerir'):
                self.load(edited(**{classe:{'modo':'automatico','teto':'automatico'}}))
            with self.assertRaisesRegex(ValueError,'acima do teto'):
                self.load(edited(**{classe:{'modo':'automatico'}}))

    def test_effective_mode_enforces_the_code_ceiling_without_load(self):
        self.assertEqual(effective_mode({'classes':{'DECISAO':{'modo':'automatico','teto':'automatico'}}},'DECISAO'),'sugerir')
        self.assertEqual(effective_mode({'classes':{'DADO_INVALIDO':{'modo':'automatico','teto':'automatico'}}},'DADO_INVALIDO'),'desligado')
        self.assertEqual(effective_mode({'classes':{'CADASTRO':{'modo':'sugerir','teto':'sombra'}}},'CADASTRO'),'sombra')

    def test_invalid_data_never_leaves_desligado(self):
        with self.assertRaises(ValueError):
            self.load(edited(DADO_INVALIDO={'modo':'sombra'}))
        with self.assertRaises(ValueError):
            self.load(edited(DADO_INVALIDO={'teto':'sombra'}))

    def test_automatico_needs_approval_and_35_clean_cases(self):
        criterion = {'casos_seguidos_sem_erro':35,'erros':0,'backtest_versao':'1','data':'2026-10-17'}
        approval = {'aprovado_por':'Helena','aprovado_em':'2026-10-17'}
        measured = {'confianca':'0.90'}
        ok = self.load(edited(MOVIMENTO_SEM_REGRA={'modo':'automatico','criterio':criterion,**measured,**approval}))
        self.assertEqual(effective_mode(ok,'MOVIMENTO_SEM_REGRA'),'automatico')
        with self.assertRaisesRegex(ValueError,'aprovado_por'):
            self.load(edited(MOVIMENTO_SEM_REGRA={'modo':'automatico','criterio':criterion,**measured}))
        with self.assertRaisesRegex(ValueError,'35'):
            self.load(edited(MOVIMENTO_SEM_REGRA={'modo':'automatico','criterio':{**criterion,'casos_seguidos_sem_erro':34},**measured,**approval}))
        with self.assertRaisesRegex(ValueError,'35'):
            self.load(edited(MOVIMENTO_SEM_REGRA={'modo':'automatico','criterio':{**criterion,'erros':1},**measured,**approval}))
        with self.assertRaisesRegex(ValueError,'confianca'):
            self.load(edited(MOVIMENTO_SEM_REGRA={'modo':'automatico','criterio':criterion,**approval}))

    def test_missing_class_and_bad_confidence_are_rejected(self):
        policy = edited()
        del policy['classes']['CADASTRO']
        with self.assertRaisesRegex(ValueError,'CADASTRO'):
            self.load(policy)
        for bad in ('1.5',0.9,'abc'):
            with self.assertRaisesRegex(ValueError,'confianca'):
                self.load(edited(MOVIMENTO_SEM_REGRA={'confianca':bad}))
        self.load(edited(MOVIMENTO_SEM_REGRA={'confianca':'0.9'}))


if __name__ == '__main__':
    unittest.main()
