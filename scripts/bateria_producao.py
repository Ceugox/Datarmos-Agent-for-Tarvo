"""Bateria de testes contra a API publicada (docs/testes-producao.md).

Uso:
    python scripts/bateria_producao.py --url https://<domínio da API> --chave-a <arquivo> --chave-b <arquivo>

As chaves são lidas de arquivos (a primeira linha que começa com tk_) e nunca impressas. Os dois clientes
precisam ser diferentes: B é usado para provar o isolamento e, no fim, para provocar o rate limit.
A referência de comparação é a CLI rodada agora, neste checkout, que deve ser o commit publicado.
O bloco 10 liga a camada de inferência: na primeira vez chama o modelo (cerca de US$ 0,13); nas seguintes
as respostas vêm do cache do cliente e custam zero. Use --sem-camada para pular.
"""
from collections import Counter
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
import argparse
import http.client
import json
import shutil
import ssl
import subprocess
import sys
import time
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tests'))
from output_format import csv_errors  # noqa: E402

PACK = ROOT/'Tarvo_Data_Pack_set2026'
CSVS = ['comissoes_por_lojista.csv', 'divergencias_taxa.csv', 'notas_a_emitir.csv', 'lancamentos_classificados.csv', 'pendencias.csv', 'rastro.csv',
        'cobertura.csv', 'contestacoes/operacoes_orbe.csv', 'contestacoes/operacoes_ponte.csv']
MONEY = ['comissoes_por_lojista.csv', 'divergencias_taxa.csv', 'notas_a_emitir.csv', 'lancamentos_classificados.csv', 'rastro.csv']
# Descrições novas para as 4 tarifas de setembro: nenhuma regra bancária as reconhece e elas viram MOVIMENTO_SEM_REGRA.
FEE_RENAMES = {
    '05a_': [('TAR PACOTE SERVICOS PJ', 'PACOTE SERVICOS PJ - TARIFA MENSAL'), ('TAR TED/PIX AVULSAS 09/2026', 'COBRANCA TED/PIX AVULSAS 09/2026')],
    '05b_': [('<MEMO>TARIFA MANUTENCAO CONTA PJ', '<MEMO>MANUTENCAO CONTA PJ - TARIFA'), ('<MEMO>TARIFA PACOTE CAMBIO', '<MEMO>PACOTE CAMBIO - TARIFA')],
}


def read_key(path):
    return next(line.strip() for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip().startswith('tk_'))


def pack_files(pack):
    return [p for p in sorted(Path(pack).iterdir()) if p.name[:3] in {'01_', '02_', '03_', '04_', '05a', '05b', '06_'}]


def renamed_fees_pack(target):
    shutil.copytree(PACK, target)
    for prefix, pairs in FEE_RENAMES.items():
        path = next(Path(target).glob(prefix+'*'))
        raw = path.read_bytes()
        try:
            text, encoding = raw.decode('utf-8'), 'utf-8'
        except UnicodeDecodeError:
            text, encoding = raw.decode('latin-1'), 'latin-1'
        for old, new in pairs:
            if text.count(old) != 1:
                raise SystemExit(f'Descrição esperada não encontrada em {path.name}: {old}')
            text = text.replace(old, new)
        path.write_bytes(text.encode(encoding))
    return Path(target)


class Battery:
    def __init__(self, base, key_a, key_b, reference):
        self.base, self.reference = base.rstrip('/'), Path(reference)
        self.A, self.B = {'Authorization': f'Bearer {key_a}'}, {'Authorization': f'Bearer {key_b}'}
        self.http = httpx.Client(timeout=180)
        self.results = []

    def check(self, block, name, ok, detail=''):
        self.results.append((block, name, bool(ok)))
        print(f'[{"OK " if ok else "FALHA"}] {block} | {name}' + (f' | {detail}' if detail and not ok else ''), flush=True)

    def request(self, method, url, **kw):
        """Respeita o Retry-After: o limite por cliente é testado só no bloco 11 e não pode virar falha falsa nos outros."""
        response = self.http.request(method, url, **kw)
        for _ in range(14):
            if response.status_code != 429:
                break
            time.sleep(int(response.headers.get('retry-after', '5')) + 1)
            response = self.http.request(method, url, **kw)
        return response

    def get(self, path, headers):
        return self.request('GET', self.base+path, headers=headers)

    def post(self, path, headers, **kw):
        return self.request('POST', self.base+path, headers=headers, **kw)

    def raw_get(self, path, headers):
        """GET sem normalizar o caminho: o httpx resolve '..' antes de enviar e o teste de travessia não chegaria ao servidor."""
        status = None
        for _ in range(15):
            conn = http.client.HTTPSConnection(urlsplit(self.base).hostname or '', context=ssl.create_default_context(), timeout=60)
            conn.putrequest('GET', path, skip_accept_encoding=True)
            for name, value in headers.items():
                conn.putheader(name, value)
            conn.endheaders()
            response = conn.getresponse()
            status, retry = response.status, response.getheader('Retry-After')
            response.read()
            conn.close()
            if status != 429:
                return status
            time.sleep(int(retry or 5) + 1)
        return status

    def close_month(self, headers, pack, use_llm=False):
        files = [('arquivos', (p.name, p.read_bytes())) for p in pack_files(pack)]
        return self.post('/v1/fechamentos', headers, data={'periodo': '2026-09', 'usar_llm': str(use_llm).lower()}, files=files)

    def wait(self, headers, fid):
        state = {}
        for _ in range(300):
            state = self.get(f'/v1/fechamentos/{fid}', headers).json()
            if state['status'] not in {'NA_FILA', 'PROCESSANDO'}:
                return state
            time.sleep(2)
        return state

    def download(self, headers, fid, name):
        return self.get(f'/v1/fechamentos/{fid}/arquivos/{name}', headers)

    def queue(self, headers, fid):
        data = self.get(f'/v1/fechamentos/{fid}/excecoes', headers).json()
        return data if isinstance(data, list) else data.get('excecoes', [])

    def decide(self, headers, exc_id, decisao, **extra):
        body = {'decisao': decisao, 'decidido_por': 'Helena (bateria de testes)', 'motivo': 'Bateria de testes em produção', **extra}
        return self.post(f'/v1/excecoes/{exc_id}/decisao', headers, json=body)

    def ref(self, name):
        return (self.reference/name).read_bytes()

    def run(self, fees_pack, with_layer=True):
        A, B, check = self.A, self.B, self.check

        # 1. Infra
        r = self.http.get(f'{self.base}/health')
        check('1 infra', '/health 200 com banco ok', r.status_code == 200 and r.json() == {'status': 'ok', 'banco': 'ok'}, r.text[:100])
        r = self.http.get(f'{self.base}/health', headers={'Origin': 'https://exemplo-externo.com'})
        check('1 infra', 'sem CORS aberto', 'access-control-allow-origin' not in r.headers)
        check('1 infra', 'X-Content-Type-Options: nosniff', self.get('/v1/fechamentos/x', A).headers.get('x-content-type-options') == 'nosniff')

        # 2. Autenticação
        ghost = '/v1/fechamentos/00000000-0000-0000-0000-000000000000'
        for label, headers in [('sem Authorization', {}), ('esquema Basic', {'Authorization': 'Basic abc'}),
                               ('chave inválida', {'Authorization': 'Bearer tk_invalida_000000000000000000000000'})]:
            r = self.http.get(self.base+ghost, headers=headers)
            check('2 auth', f'{label} -> 401', r.status_code == 401 and r.headers.get('www-authenticate') == 'Bearer', str(r.status_code))
        r = self.get(ghost, {'Authorization': A['Authorization'].replace('Bearer', 'bearer')})
        check('2 auth', '"bearer" minúsculo aceito', r.status_code == 404, str(r.status_code))
        for route in ['/v1/fechamentos/x/excecoes', '/v1/fechamentos/x/auditoria', '/v1/fechamentos/x/arquivos/pendencias.csv']:
            check('2 auth', f'{route} sem chave -> 401', self.http.get(self.base+route).status_code == 401)
        check('2 auth', 'POST decisão sem chave -> 401', self.http.post(f'{self.base}/v1/excecoes/1/decisao', json={}).status_code == 401)
        check('2 auth', 'POST fechamento sem chave -> 401', self.http.post(f'{self.base}/v1/fechamentos', data={'periodo': '2026-09'}).status_code == 401)

        # 3. Validação do upload
        files = [('arquivos', (p.name, p.read_bytes())) for p in pack_files(PACK)]
        cases = [('periodo 2026-9', {'periodo': '2026-9', 'usar_llm': 'false'}, files),
                 ('usar_llm=talvez', {'periodo': '2026-09', 'usar_llm': 'talvez'}, files),
                 ('arquivo fora do padrão do pacote', {'periodo': '2026-09', 'usar_llm': 'false'}, [('arquivos', ('planilha.csv', b'a;b\n'))]),
                 ('nome com ../', {'periodo': '2026-09', 'usar_llm': 'false'}, [('arquivos', ('../01_x.csv', b'a'))]),
                 ('nomes repetidos', {'periodo': '2026-09', 'usar_llm': 'false'}, [files[0], files[0]])]
        for label, data, payload in cases:
            r = self.post('/v1/fechamentos', A, data=data, files=payload)
            check('3 upload', f'{label} -> 422', r.status_code == 422, str(r.status_code))
        r = self.post('/v1/fechamentos', A, json={'periodo': '2026-09'})
        check('3 upload', 'corpo JSON em vez de multipart -> 422', r.status_code == 422, str(r.status_code))
        conn = http.client.HTTPSConnection(urlsplit(self.base).hostname or '', context=ssl.create_default_context(), timeout=60)
        conn.putrequest('POST', '/v1/fechamentos')
        conn.putheader('Authorization', A['Authorization'])
        conn.putheader('Content-Type', 'multipart/form-data; boundary=x')
        conn.putheader('Content-Length', str(60*1024*1024))
        conn.endheaders()
        conn.send(b'--x\r\n')
        status = conn.getresponse().status
        conn.close()
        check('3 upload', 'Content-Length de 60 MB -> 413 antes de ler o corpo', status == 413, str(status))

        # 4. Fechamento sem a camada, comparado com a CLI
        r = self.close_month(A, PACK)
        check('4 fechamento', 'POST -> 202 NA_FILA', r.status_code == 202 and r.json().get('status') == 'NA_FILA', r.text[:120])
        base_id = r.json()['id']
        state = self.wait(A, base_id)
        check('4 fechamento', 'status CONCLUIDO', state['status'] == 'CONCLUIDO', state['status'])
        for name in CSVS:
            got = self.download(A, base_id, name)
            same = got.content == self.ref(name)
            check('4 fechamento', f'{name} igual à CLI e no formato fixo',
                  got.status_code == 200 and same and csv_errors(name, got.content) == [] and got.headers['content-type'] == 'text/csv; charset=utf-8',
                  f'{got.status_code} igual={same}')
        for name in ['metrics.json', 'checks.json', 'policy.json']:
            check('4 fechamento', f'{name} igual à CLI', self.download(A, base_id, name).content == self.ref(name))
        manifest = self.download(A, base_id, 'manifest.json').json()
        reference = json.loads(self.ref('manifest.json'))
        check('4 fechamento', 'run_id igual ao da CLI', manifest['run_id'] == reference['run_id'], f"{manifest['run_id']} x {reference['run_id']}")
        check('4 fechamento', 'manifest registra a execução e as linhas lidas',
              manifest.get('execucao', {}).get('linhas_lidas_total') == reference.get('execucao', {}).get('linhas_lidas_total')
              and manifest.get('camada') == {'ligada': False, 'auditoria': False})
        check('4 fechamento', 'sem camada não há auditoria.jsonl (404)', self.download(A, base_id, 'auditoria.jsonl').status_code == 404)

        # 5. ZIP
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for p in pack_files(PACK):
                archive.write(p, p.name)
        r = self.post('/v1/fechamentos', A, data={'periodo': '2026-09', 'usar_llm': 'false'}, files=[('arquivos', ('pacote.zip', buffer.getvalue()))])
        zip_id = r.json().get('id')
        zstate = self.wait(A, zip_id) if zip_id else {'status': str(r.status_code)}
        check('5 zip', 'upload .zip concluído', zstate['status'] == 'CONCLUIDO', zstate['status'])
        if zip_id:
            check('5 zip', 'CSVs do .zip iguais à CLI', all(self.download(A, zip_id, n).content == self.ref(n) for n in MONEY+['pendencias.csv']))

        # 6. Download por lista fechada
        for name in ['../manifest.json', '..%2Fmanifest.json', '%2e%2e/%2e%2e/etc/passwd', 'contestacoes/../manifest.json', 'inexistente.csv',
                     'saida/pendencias.csv', 'PENDENCIAS.CSV']:
            code = self.raw_get(f'/v1/fechamentos/{base_id}/arquivos/{name}', A)
            check('6 download', f'"{name}" (caminho cru) -> 404', code == 404, str(code))
        for name, expected in {'index.html': 'text/html; charset=utf-8', 'metrics.json': 'application/json',
                               'contestacoes/rascunho_orbe.txt': 'text/plain; charset=utf-8'}.items():
            got = self.download(A, base_id, name).headers.get('content-type')
            check('6 download', f'{name} com Content-Type {expected}', got == expected, str(got))

        # 7. Fila sem a camada
        items = self.queue(A, base_id)
        by_class = Counter(i['classe'] for i in items)
        check('7 fila', '13 exceções sem a camada', len(items) == 13, str(len(items)))
        check('7 fila', 'por classe = setembro', by_class == {'DECISAO': 8, 'ESPERA_EVIDENCIA': 2, 'CONDICAO_COMERCIAL': 2, 'ESPERA_DADO': 1}, str(dict(by_class)))
        check('7 fila', 'todas SEM_CAMADA e PENDENTE', all(i.get('resultado') == 'SEM_CAMADA' and i.get('pendencia_status') == 'PENDENTE' for i in items))
        summary = self.get(f'/v1/fechamentos/{base_id}', A).json()
        check('7 fila', 'GET do fechamento traz contagem por classe e modo', bool(summary.get('excecoes') or summary.get('contagem_excecoes')))

        # 8. Decisões e revisões encadeadas
        by_type = {i['tipo']: i for i in items}
        alert = by_type['ALERTA_ANTECIPACAO']['id']
        check('8 decisao', 'id não numérico -> 404', self.decide(A, 'abc', 'aprovar').status_code == 404)
        check('8 decisao', 'decisao=talvez -> 422', self.decide(A, alert, 'talvez').status_code == 422)
        check('8 decisao', 'campo extra -> 422', self.decide(A, alert, 'aprovar', campo_extra=1).status_code == 422)
        r = self.post(f'/v1/excecoes/{alert}/decisao', A, json={'decisao': 'aprovar', 'decidido_por': '  ', 'motivo': 'x'})
        check('8 decisao', 'decidido_por em branco -> 422', r.status_code == 422, str(r.status_code))
        r = self.decide(A, by_type['LOJISTA_NAO_FATURAR']['id'], 'rejeitar')
        rev1 = r.json().get('revisao_id')
        s1 = self.wait(A, rev1) if rev1 else {'status': str(r.status_code)}
        check('8 decisao', 'rejeitar CONDICAO_COMERCIAL -> revisão 1 concluída', s1['status'] == 'CONCLUIDO', s1['status'])
        r = self.decide(A, by_type['DIVERGENCIA_A_CONTESTAR_PONTE']['id'], 'aprovar')
        rev2 = r.json().get('revisao_id')
        s2 = self.wait(A, rev2) if rev2 else {'status': str(r.status_code)}
        check('8 decisao', 'aprovar DECISAO na mesma linhagem -> revisão 2 concluída', s2['status'] == 'CONCLUIDO', s2['status'])
        if rev2:
            pend = self.download(A, rev2, 'pendencias.csv')
            status_by_id = {line.split(';')[0]: line.rsplit(';', 1)[-1] for line in pend.text.splitlines()[1:]}
            check('8 decisao', 'revisão 2 mantém a REJEITADA da 1 e traz a APROVADA nova',
                  status_by_id.get(by_type['LOJISTA_NAO_FATURAR']['excecao_id']) == 'REJEITADA'
                  and status_by_id.get(by_type['DIVERGENCIA_A_CONTESTAR_PONTE']['excecao_id']) == 'APROVADA')
            check('8 decisao', 'nenhum valor muda (CSVs monetários iguais à CLI)', all(self.download(A, rev2, n).content == self.ref(n) for n in MONEY))
            check('8 decisao', 'pendencias.csv da revisão no formato fixo', csv_errors('pendencias.csv', pend.content) == [])
            revisao = self.download(A, rev2, 'manifest.json').json().get('revisao', {})
            check('8 decisao', 'manifest da revisão 2 com número e pai', revisao.get('numero') == 2 and bool(revisao.get('run_id_pai')))
            events = self.get(f'/v1/fechamentos/{rev2}/auditoria', A).json()['eventos']
            applied = [e for e in events if e['evento'] == 'DECISAO_APLICADA']
            check('8 decisao', 'auditoria da revisão 2 tem as duas decisões com quem decidiu', len(applied) >= 2 and all(e.get('decidido_por') for e in applied))
            r = self.decide(A, by_type['DIVERGENCIA_A_CONTESTAR_PONTE']['id'], 'rejeitar')
            rid = r.json().get('revisao_id')
            s3 = self.wait(A, rid) if rid else {'status': str(r.status_code)}
            check('8 decisao', 'decidir de novo a mesma exceção não aplica', r.status_code == 409 or s3['status'] == 'ERRO', f'{r.status_code} {s3["status"]}')

        # 9. Isolamento entre clientes
        for label, path in [('fechamento', f'/v1/fechamentos/{base_id}'), ('fila', f'/v1/fechamentos/{base_id}/excecoes'),
                            ('auditoria', f'/v1/fechamentos/{rev2 or base_id}/auditoria'), ('arquivo', f'/v1/fechamentos/{base_id}/arquivos/pendencias.csv')]:
            code = self.get(path, B).status_code
            check('9 isolamento', f'cliente B não vê {label} de A (404)', code == 404, str(code))
        check('9 isolamento', 'cliente B não decide exceção de A (404)', self.decide(B, alert, 'aprovar').status_code == 404)
        r = self.close_month(B, PACK)
        b_id = r.json().get('id')
        bstate = self.wait(B, b_id) if b_id else {'status': str(r.status_code)}
        check('9 isolamento', 'cliente B fecha o próprio mês', bstate['status'] == 'CONCLUIDO', bstate['status'])
        check('9 isolamento', 'cliente A não vê fechamento de B (404)', self.get(f'/v1/fechamentos/{b_id}', A).status_code == 404)

        # 10. Camada de inferência (4 tarifas sem regra, modo sombra)
        if with_layer:
            r = self.close_month(A, fees_pack, use_llm=True)
            lid = r.json()['id']
            lstate = self.wait(A, lid)
            events = self.get(f'/v1/fechamentos/{lid}/auditoria', A).json()['eventos']
            msr = [e for e in events if e['evento'] == 'EXCECAO' and e.get('classe') == 'MOVIMENTO_SEM_REGRA']
            execution = next((e for e in events if e['evento'] == 'EXECUCAO'), {})
            check('10 camada', 'fechamento com camada concluído', lstate['status'] == 'CONCLUIDO', lstate['status'])
            check('10 camada', '4 movimentos sem regra avaliados', len(msr) == 4, str(len(msr)))
            check('10 camada', 'nenhuma falha de API ou de rede', not any(e.get('motivo') in {'ERRO_API', 'ERRO_REDE'} for e in msr),
                  str([e.get('motivo') for e in msr]))
            check('10 camada', 'toda proposta validada passou em todas as verificações',
                  all(v.get('status') == 'PASS' for e in msr if e['resultado'] == 'VALIDADA' for v in e['verificacoes']))
            check('10 camada', 'sombra: nenhuma linha metodo=IA no CSV', ';IA;' not in self.download(A, lid, 'lancamentos_classificados.csv').text)
            print(f"      resultados: {dict(Counter(e['resultado'] for e in msr))} | tokens {execution.get('tokens_total')} | US$ {execution.get('custo_usd_total')}")
            validated = next((i for i in self.queue(A, lid) if i.get('resultado') == 'VALIDADA'), None)
            if validated:
                r = self.decide(A, validated['id'], 'aprovar')
                rv = r.json().get('revisao_id')
                sv = self.wait(A, rv) if rv else {'status': str(r.status_code)}
                text = self.download(A, rv, 'lancamentos_classificados.csv').text if sv['status'] == 'CONCLUIDO' else ''
                check('10 camada', 'aprovar proposta vista em sombra não aplica', ';IA;' not in text, sv['status'])

        # 11. Rate limit (cliente B, por último)
        responses = [self.http.get(f'{self.base}/v1/fechamentos/{b_id}', headers=B) for _ in range(70)]
        limited = [x for x in responses if x.status_code == 429]
        check('11 rate limit', '70 requisições em sequência -> 429 com Retry-After', bool(limited) and all(x.headers.get('retry-after') for x in limited),
              f'{len(limited)} respostas 429')

        passed = sum(1 for result in self.results if result[2])
        print(f'\nTOTAL: {passed}/{len(self.results)} OK')
        for block in dict.fromkeys(result[0] for result in self.results):
            block_results = [result for result in self.results if result[0] == block]
            print(f'  {block}: {sum(1 for result in block_results if result[2])}/{len(block_results)}')
        return passed == len(self.results)


def main():
    parser = argparse.ArgumentParser(description='Bateria de testes contra a API publicada.')
    parser.add_argument('--url', required=True, help='URL base da API (https://...)')
    parser.add_argument('--chave-a', required=True, help='arquivo com a chave do cliente A')
    parser.add_argument('--chave-b', required=True, help='arquivo com a chave do cliente B (outro cliente)')
    parser.add_argument('--sem-camada', action='store_true', help='pula o bloco 10, que pode chamar o modelo')
    args = parser.parse_args()
    key_a, key_b = read_key(args.chave_a), read_key(args.chave_b)
    if key_a == key_b:
        raise SystemExit('As duas chaves precisam ser de clientes diferentes.')
    with TemporaryDirectory() as directory:
        reference = Path(directory)/'referencia'
        subprocess.run([sys.executable, str(ROOT/'run_engine.py'), '--input', str(PACK), '--period', '2026-09', '--output', str(reference), '--no-llm'],
                       cwd=ROOT, check=True, capture_output=True)
        fees = renamed_fees_pack(Path(directory)/'tarifas-renomeadas')
        ok = Battery(args.url, key_a, key_b, reference).run(fees, with_layer=not args.sem_camada)
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
