"""Backtest of MOVIMENTO_SEM_REGRA (ADR 0002): September has no movement without a rule, so the cases are made by
removing one bank rule and, optionally, perturbing the description. The ground truth is the account of the removed rule."""
from dataclasses import replace
from datetime import date
from math import sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata

from .audit import AuditLog
from .closing import bank_rule_for, close_month
from .domain import identifier
from .inference import run_inference
from .inference_policy import MIN_CLEAN_CASES, effective_mode
from .llm_cache import ResponseCache, canonical
from .readers import read_inputs
from .resolver import AnthropicResolver, CachedResolver, FakeResolver, TokenBudget

CLASS = 'MOVIMENTO_SEM_REGRA'
WILSON_Z = 1.96


def _ascii_lower(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c)).lower()


def perturbations(description):
    words = description.split()
    parts = re.split(r'(\s+)',description)
    variants = [('sufixo',description+' REF 0926'), ('prefixo','DEB '+description)]
    index = next((i for i, part in enumerate(parts) if len(part) >= 6 and part.isalpha()),None)
    if index is not None:
        short = parts[:index]+[parts[index][:4]+'.']+parts[index+1:]
        variants.append(('abreviacao',''.join(short)))
    variants.append(('acentos',_ascii_lower(description)))
    if len(words) >= 2:
        variants.append(('ordem',' '.join([words[1],words[0]]+words[2:])))
    return [(kind,text) for kind, text in variants if text != description]


def exception_id(case):
    return identifier('PEN',f'bank:{(case["banco"],case["ref"])}')


def without_rule(policy, rule_id):
    result = copy.deepcopy(policy)
    result['bank_rules'] = [rule for rule in result['bank_rules'] if rule['id'] != rule_id]
    return result


def build_cases(input_dir, policy, period):
    bundle = read_inputs(input_dir)
    entries = [e for e in bundle.bank_entries if e['date'].isoformat()[:7] == period]
    cases = []
    for entry in sorted(entries,key=lambda e:(e['bank'],e['date'],e['_source']['ref_origem'])):
        rule = bank_rule_for(policy,entry)
        if rule is None:
            continue
        reduced = without_rule(policy,rule['id'])
        variants = [('regra_removida',entry['description'])]+perturbations(entry['description'])
        for kind, text in variants:
            # another remaining rule that still matches would make the ground truth ambiguous: drop the case
            if bank_rule_for(reduced,{'bank':entry['bank'], 'description':text}) is not None:
                continue
            source = entry['_source']
            cases.append({'id':f'{entry["bank"]}:{source["ref_origem"]}:{kind}', 'banco':entry['bank'], 'ref':source['ref_origem'], 'tipo':kind,
                          'descricao':text, 'descricao_original':entry['description'], 'regra_id':rule['id'], 'gabarito':rule['account'],
                          'arquivo':source['arquivo_origem'], 'linha':source['linha_origem']})
    return cases


def _split_lines(text):
    parts = re.split(r'(\r\n|\r|\n)',text)  # same line breaks the readers count: text, separator, text, ...
    return parts


def _rewrite(raw, case):
    try:
        text, encoding = raw.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        text, encoding = raw.decode('cp1252'), 'cp1252'
    parts = _split_lines(text)
    first = 2*(case['linha']-1)
    if first >= len(parts):
        raise ValueError(f'Line not found: {case["arquivo"]} line {case["linha"]}')
    old, new = case['descricao_original'], case['descricao']
    if case['arquivo'].lower().endswith('.ofx'):
        for index in range(first,len(parts),2):
            if '<MEMO>' in parts[index]:
                if f'<MEMO>{old}' not in parts[index]:
                    raise ValueError(f'MEMO does not match the original description: {case["id"]}')
                parts[index] = parts[index].replace(f'<MEMO>{old}',f'<MEMO>{new}',1)
                break
            if '</STMTTRN>' in parts[index]:
                raise ValueError(f'MEMO not found in block: {case["id"]}')
        else:
            raise ValueError(f'MEMO not found in block: {case["id"]}')
    else:
        cells = parts[first].split(';')
        if len(cells) != 5 or cells[1] != old:
            raise ValueError(f'Description does not match the source line: {case["id"]}')
        cells[1] = new
        parts[first] = ';'.join(cells)
    return ''.join(parts).encode(encoding)


def materialize(case, input_dir, tmp_dir, policy=None):
    pack = Path(tmp_dir)/'pack'
    shutil.copytree(input_dir,pack)
    target = pack/case['arquivo']
    target.write_bytes(_rewrite(target.read_bytes(),case))
    return pack, (without_rule(policy,case['regra_id']) if policy is not None else None)


def gabarito_proposal(case):
    return {'excecao_id':exception_id(case), 'classe':CLASS, 'acao':'CLASSIFICAR_CONTA', 'parametros':{'conta_codigo':case['gabarito']},
            'evidencias':[{'arquivo':case['arquivo'], 'ref':case['ref'], 'trecho':case['descricao']}],
            'justificativa':'Backtest: resposta igual ao gabarito.', 'requer_humano':False}


def wilson_lower(successes, n):
    if n == 0:
        return None
    p = successes/n
    z2 = WILSON_Z**2
    value = (p+z2/(2*n)-WILSON_Z*sqrt(p*(1-p)/n+z2/(4*n*n)))/(1+z2/n)
    return f'{value+1e-12:.4f}'


def summarize(results):
    por_classe = {}
    for item in results:
        por_classe.setdefault(item.get('classe',CLASS),[]).append(item['resultado'])
    summary = {}
    for classe, outcomes in sorted(por_classe.items()):
        decided = [o for o in outcomes if o != 'HUMANO']
        hits = decided.count('ACERTO')
        streak = 0
        for outcome in reversed(decided):
            if outcome != 'ACERTO':
                break
            streak += 1
        summary[classe] = {'total':len(outcomes), 'decididos':len(decided), 'acertos':hits, 'erros':len(decided)-hits, 'humanos':len(outcomes)-len(decided),
                           'precisao':None if not decided else f'{hits/len(decided):.4f}', 'cobertura':f'{len(decided)/len(outcomes):.4f}' if outcomes else None,
                           'seguidos_sem_erro':streak, 'wilson_95':wilson_lower(hits,len(decided))}
    return summary


def _sombra(inference_policy):
    policy = copy.deepcopy(inference_policy)
    if effective_mode(policy,CLASS) == 'desligado':
        policy['classes'][CLASS]['modo'] = 'sombra'  # the backtest measures proposals, so the class must be asked
        if policy['classes'][CLASS]['teto'] == 'desligado':
            policy['classes'][CLASS]['teto'] = 'sombra'
    return policy


def run_case(case, input_dir, policy, inference_policy, period, resolver, budget):
    with TemporaryDirectory(prefix='backtest-') as tmp:
        pack, reduced = materialize(case,input_dir,tmp,policy)
        bundle = read_inputs(pack)
        result = close_month(bundle,reduced,period)
        target = next((e for e in result.exceptions if e.classe == CLASS and e.escopo == f'{case["banco"]}:{case["ref"]}'),None)
        if target is None:
            raise ValueError(f'Case {case["id"]} did not produce a bank reconciliation exception')
        # only the target exception goes to the resolver: sibling exceptions of the reduced pack are not part of the case
        events = run_inference(bundle,replace(result,exceptions=[target]),reduced,inference_policy,resolver,AuditLog(),budget)
    event = next(e for e in events if e['evento'] == 'EXCECAO' and e['excecao_id'] == target.excecao_id)
    if event['resultado'] != 'VALIDADA':
        return {'id':case['id'], 'classe':CLASS, 'resultado':'HUMANO', 'motivo':event['motivo'], 'conta':None}
    account = event['proposta']['parametros']['conta_codigo']
    return {'id':case['id'], 'classe':CLASS, 'resultado':'ACERTO' if account == case['gabarito'] else 'ERRO', 'motivo':None, 'conta':account}


def run_backtest(cases, input_dir, policy, inference_policy, period, resolver, limit=None, budget=None):
    """`resolver` is a Resolver, or a function case -> Resolver (the fake needs the perturbed text as evidence)."""
    selected = cases[:limit] if limit else list(cases)
    inference_policy = _sombra(inference_policy)
    budget = budget or TokenBudget(int(os.environ.get('LLM_BUDGET_TOKENS',200000)))  # one budget for the whole backtest
    results = [run_case(case,input_dir,policy,inference_policy,period,resolver(case) if callable(resolver) else resolver,budget) for case in selected]
    return {'casos':results, 'por_classe':summarize(results)}


def backtest_version(cases, prompt_version, resolver_name):
    payload = canonical({'prompt_version':prompt_version, 'casos':[[c['id'],c['descricao'],c['gabarito']] for c in cases]})
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:8]+'@'+resolver_name


def record_policy(path, summary, version):
    """Writes only criterio and confianca of the measured class; modo, teto and aprovado_* are never touched."""
    with open(path,encoding='utf-8') as handle:
        policy = json.load(handle)
    for classe, stats in summary.items():
        entry = policy['classes'][classe]
        entry['criterio'] = {**entry['criterio'], 'casos_seguidos_sem_erro':stats['seguidos_sem_erro'], 'erros':stats['erros'], 'backtest_versao':version, 'data':date.today().isoformat()}
        entry['confianca'] = stats['wilson_95']
    # same key order as the file: rewriting it must not produce a diff beyond the recorded fields
    with open(path,'w',encoding='utf-8',newline='\n') as handle:
        handle.write(json.dumps(policy,ensure_ascii=False,indent=2)+'\n')


def format_table(summary):
    header = ('classe','total','decididos','acertos','erros','humanos','precisao','cobertura','seguidos','wilson_95')
    rows = [header]+[(c,s['total'],s['decididos'],s['acertos'],s['erros'],s['humanos'],s['precisao'] or '-',s['cobertura'] or '-',s['seguidos_sem_erro'],s['wilson_95'] or '-') for c, s in summary.items()]
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(header))]
    lines = ['  '.join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)) for row in rows]
    for classe, stats in summary.items():
        met = stats['seguidos_sem_erro'] >= MIN_CLEAN_CASES and stats['erros'] == 0
        lines.append(f'{classe}: critério de {MIN_CLEAN_CASES} casos seguidos sem erro {"ATINGIDO" if met else "NÃO atingido"} ({stats["seguidos_sem_erro"]} seguidos, {stats["erros"]} erros)')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Backtest of the MOVIMENTO_SEM_REGRA inference class on perturbed September movements.')
    parser.add_argument('--input',required=True)
    parser.add_argument('--period',required=True)
    parser.add_argument('--policy',required=True)
    parser.add_argument('--inference-policy',required=True)
    parser.add_argument('--resolver',choices=('fake','anthropic'),default='fake')
    parser.add_argument('--limit',type=int)
    parser.add_argument('--gravar',action='store_true')
    parser.add_argument('--cache-dir',default='.cache/llm')
    args = parser.parse_args(argv)
    if args.gravar and (args.resolver != 'anthropic' or args.limit):
        print('Backtest failed: --gravar requires --resolver anthropic and no --limit (the fake answers the ground truth and a partial run does not measure the class).',file=sys.stderr)
        return 1
    try:
        policy = json.loads(Path(args.policy).read_text(encoding='utf-8'))
        inference_policy = json.loads(Path(args.inference_policy).read_text(encoding='utf-8'))
        if args.resolver == 'anthropic':
            if not os.environ.get('ANTHROPIC_API_KEY'):
                print('Backtest failed: --resolver anthropic requires ANTHROPIC_API_KEY in the environment.',file=sys.stderr)
                return 1
            resolver = CachedResolver(AnthropicResolver(prompt_version=inference_policy['prompt_version']),ResponseCache(args.cache_dir))
        else:
            resolver = lambda case: FakeResolver({exception_id(case):gabarito_proposal(case)},prompt_version=inference_policy['prompt_version'])
        cases = build_cases(args.input,policy,args.period)
        outcome = run_backtest(cases,args.input,policy,inference_policy,args.period,resolver,args.limit)
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        print(f'Backtest failed: {error}',file=sys.stderr)
        return 1
    print(f'Cases: {len(outcome["casos"])} of {len(cases)} (resolver {args.resolver})')
    print(format_table(outcome['por_classe']))
    if args.gravar:
        executed = cases[:args.limit] if args.limit else cases
        record_policy(args.inference_policy,outcome['por_classe'],backtest_version(executed,inference_policy['prompt_version'],resolver.model))
        print(f'Criterion recorded in {args.inference_policy}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
