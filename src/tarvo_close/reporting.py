from datetime import date
from decimal import Decimal
from html import escape
from io import StringIO
from pathlib import Path
from urllib.parse import quote
import csv
import hashlib
import json
import os
import tempfile

from . import __version__

HEADERS = {
    'comissoes_por_lojista':['id_saida','cnpj','lojista','linha_negocio','comissao_brl'],
    'divergencias_taxa':['id_saida','cnpj','linha_negocio','ref_origem','taxa_contratada_pct','taxa_aplicada_pct','diferenca_brl'],
    'notas_a_emitir':['id_saida','tomador_cnpj','tomador','linha_negocio','valor_brl','discriminacao'],
    'lancamentos_classificados':['id_saida','banco','ref_origem','data','descricao','valor','conta_codigo','metodo','confianca'],
    'pendencias':['id_saida','tipo','ref_origem','valor_brl','motivo','quem_decide'],
    'rastro':['id_saida','arquivo_origem','ref_origem','valor'],
    'cobertura':['tipo_origem','arquivo_origem','ref_origem','linha_origem','aba_origem','status','motivo'],
}


def serialized(value):
    if isinstance(value, Decimal):
        return format(value,'f')
    if isinstance(value,date):
        return value.isoformat()
    if value is None:
        return ''
    raise TypeError(type(value).__name__)


def encode_json(value):
    return json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True,default=serialized)+'\n'


def encode_csv(name,rows):
    columns = HEADERS[name] + sorted({key for row in rows for key in row}-set(HEADERS[name]))
    stream = StringIO(newline='')
    writer = csv.DictWriter(stream,fieldnames=columns,delimiter=';',lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({key:(serialized(value) if isinstance(value,(Decimal,date)) else '' if value is None else value) for key,value in row.items()})
    return stream.getvalue()


def encode_rows(rows):
    columns = ['motivo','ref_origem','lojista','valor_brl','detalhe','id_saida']
    stream = StringIO(newline='')
    writer = csv.DictWriter(stream,fieldnames=columns,delimiter=';',lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({key:serialized(row[key]) if isinstance(row.get(key),Decimal) else row.get(key,'') for key in columns})
    return stream.getvalue()


CONTEST_TEXT = {
    'ORBE': ('Orbe Adquirência', 'cobranças de taxa diferentes do contrato vigente da Tarvo com cada lojista. O valor é valor bruto x (taxa aplicada - taxa contratada), linha a linha; vendas e estornos da mesma operação se anulam'),
    'PONTE': ('Ponte Câmbio', 'operações em que o spread aplicado difere do contratado, spreads negativos com trava vencida (não aceitos pela Tarvo) e linhas repetidas que precisam ser corrigidas no relatório'),
}


def contest_draft(counterpart,items,period):
    name, scope = CONTEST_TEXT[counterpart]
    totals = {}
    for item in items:
        totals[item['motivo']] = totals.get(item['motivo'],Decimal(0))+item['valor_brl']
    competence = f'{period[5:]}/{period[:4]}'
    lines = ['RASCUNHO - revisar antes de enviar. Nada foi enviado pelo motor.', '', f'Para: {name}', f'Assunto: Contestação - competência {competence} - Tarvo', '',
             'Prezados,', '', f'No fechamento de {competence} identificamos {scope}.', '']
    if not items:
        lines.append('Não há itens a contestar nesta competência.')
    for reason, total in sorted(totals.items()):
        count = sum(1 for item in items if item['motivo'] == reason)
        lines.append(f'- {reason}: {count} operações, {format_brl(total)}')
    lines += ['', f'A lista com cada operação segue no anexo operacoes_{counterpart.lower()}.csv.', 'Pedimos a análise e a correção ou a devolução dos valores aos lojistas, conforme o caso.', '', 'Atenciosamente,', 'Helena - Financeiro Tarvo', '']
    return '\n'.join(lines)


def count(value):
    return 'bloqueado' if value is None else str(value)


def format_brl(value):
    if value is None:
        return 'bloqueado'
    return 'R$ '+f'{Decimal(value):,.2f}'.replace(',','_').replace('.',',').replace('_','.')


def render_report(result,bundle,policy,run_id,output):
    datasets = {**result.tables,'rastro':result.traces,'cobertura':result.coverage}
    statistics = result.metrics
    partial = f' (parcial: sem as etapas bloqueadas {", ".join(statistics["totais_parciais"])})' if statistics.get('totais_parciais') else ''
    cards = [
        ('Comissão de checkout',format_brl(statistics['comissao_checkout']),'Valor bruto x taxa contratada, linha a linha; estornos pela taxa da venda original.'),
        ('Participação em remessas',format_brl(statistics['participacao_remessas']),'50% do spread realizado por operação, pela data de contratação; spreads negativos fora.'),
        ('Divergências a contestar',format_brl(None if None in (statistics['diferenca_checkout_brl'],statistics['diferenca_remessa_brl']) else statistics['diferenca_checkout_brl']+statistics['diferenca_remessa_brl']),f'{statistics["divergencias"]} lançamentos{partial}: Orbe {format_brl(statistics["diferenca_checkout_brl"])}; Ponte {format_brl(statistics["diferenca_remessa_brl"])}.'),
    ]
    summary_cards = ''.join(f'<article><h2>{escape(title)}</h2><strong>{escape(value)}</strong><p>{escape(detail)}</p></article>' for title,value,detail in cards)
    checks = ''.join(f'<li><b>{escape(check["status"])}</b> {escape(check["check"])} {escape(check.get("reason",""))}</li>' for check in result.checks)
    download_links = ' '.join(f'<a href="{name}.csv">{name}.csv</a>' for name in HEADERS)
    source_links = []
    for name, metadata in sorted(bundle.sources.items()):
        target = Path(metadata['path']) if 'path' in metadata else output/'anexos'/name
        href = quote(os.path.relpath(target,output).replace('\\','/'),safe='/')
        source_links.append(f'<li><a href="{escape(href)}">{escape(name)}</a><small> SHA-256 {metadata["sha256"]}</small></li>')
    payload = encode_json(datasets).replace('</','<\\/')
    policy_text = escape(encode_json(policy))
    provisional = statistics['status'] == 'PROVISORIO'
    title = 'Fechamento provisório: há fontes bloqueadas.' if provisional else 'Fechamento calculado com as regras do financeiro.'
    blocked_notice = ''
    if provisional:
        items = ''.join(f'<li><b>{escape(block["arquivo"])}</b>: {escape(block["motivo"])}</li>' for block in statistics['fontes_bloqueadas'].values())
        blocked_notice = '<div class="warning"><strong>Resultado provisório.</strong> O que não depende das fontes abaixo foi fechado normalmente; o que depende delas não tem números nesta execução (aparece como bloqueado) e está em pendencias.csv como FONTE_BLOQUEADA. Quem libera é a Helena.<ul>'+items+'</ul></div>'
    return '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tarvo — Fechamento mensal</title><style>
*{box-sizing:border-box}body{margin:0;font:16px/1.6 'Segoe UI',Arial,sans-serif;background:#f2f5fa;color:#19324f}header{background:#173451;color:white;padding:32px max(24px,calc((100vw - 1200px)/2))}header h1{font-size:38px;line-height:1.2;max-width:900px;margin:10px 0 20px}main{max-width:1250px;padding:30px 24px 70px;margin:auto}p{max-width:880px}.warning{background:#fff0d7;color:#714100;border-left:4px solid #b77b19;padding:18px 22px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:25px 0}.cards article{padding:22px;background:white;border:1px solid #c9d7e7;border-radius:7px}.cards h2{font-size:16px;margin:0 0 8px}.cards strong{font-size:27px}.cards p{font-size:13px}h2{margin-top:32px}a{color:#225f9f}header a{color:#bde8ff}.downloads{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0}.downloads a{background:white;padding:8px 12px;border:1px solid #bdccde;border-radius:4px;font-size:13px}.controls{display:flex;flex-wrap:wrap;gap:14px}.controls label{display:flex;flex-direction:column;flex:1;min-width:230px}input,select,button{font:inherit;padding:9px 12px;border:1px solid #9fb2ca;border-radius:4px;background:white;color:#19324f}button{cursor:pointer}button:disabled{opacity:.4}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #078b95;outline-offset:3px}.scroll{overflow:auto;background:white;margin:15px 0;border:1px solid #ccd9e8;border-radius:5px}table{border-collapse:collapse;min-width:100%;font-size:13px}th,td{padding:11px 14px;text-align:left;border-bottom:1px solid #e1e8f2;vertical-align:top;max-width:340px;min-width:120px;overflow-wrap:anywhere}th{background:#e5edf7;white-space:nowrap}tr:last-child td{border:0}.pager{display:flex;justify-content:space-between;gap:10px}.pager div{display:flex;gap:8px}small{font-size:12px;color:#536b83;overflow-wrap:anywhere}li{margin:9px 0}details{margin:20px 0;padding:18px;background:white;border:1px solid #cbd7e5;border-radius:5px}summary{cursor:pointer;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}footer{margin-top:35px;border-top:1px solid #cad7e7;padding-top:20px}code{font-size:13px}.policy{max-height:500px;overflow:auto}@media(max-width:800px){.cards{grid-template-columns:1fr}header h1{font-size:30px}header{padding:25px 22px}.pager{flex-wrap:wrap}}@media print{header{background:white;color:#19324f;padding:0}main{padding:0}.controls,.scroll,.pager,.downloads,button{display:none}.cards{grid-template-columns:repeat(3,1fr)}.cards article{padding:10px}.cards strong{font-size:18px}body{background:white}a{color:inherit;text-decoration:none}details{break-inside:avoid}@page{size:A4;margin:15mm}}
</style></head><body><header><p>Tarvo / Motor local '''+escape(__version__)+''' / '''+escape(statistics['periodo'])+'''</p><h1>'''+escape(title)+'''</h1><p>Execução <code>'''+escape(run_id)+'''</code>. Cálculos e rastros verificados; notas e contestações aguardam revisão da Helena.</p></header><main>'''+blocked_notice+'''<div class="warning"><strong>Regras aplicadas:</strong> respostas da Helena (financeiro) no canal #duvidas-hackathon-ai, 16 e 17/10. Nada é emitido, pago ou contestado automaticamente: o motor entrega notas a emitir, pendências e rascunhos de contestação para revisão.</div><div class="cards">'''+summary_cards+'''</div><p>'''+count(statistics['checkout_lidos'])+''' lançamentos de checkout; '''+count(statistics['remessas_lidas'])+''' linhas de remessa; '''+count(statistics['movimentos_bancarios_exportados'])+''' movimentos bancários exportados; '''+count(statistics['pendencias'])+''' pendências.</p><p><strong>Fora da comissão de checkout:</strong> '''+count(statistics['checkout_nao_faturado'])+''' lançamentos de lojista sem contrato assinado ('''+escape(format_brl(statistics['checkout_bruto_nao_faturado']))+''' brutos), a faturar quando o comercial confirmar a taxa, e '''+count(statistics['checkout_sem_contrato'])+''' sem cadastro resolvido. Devolução por condição comercial não informada à Orbe: '''+escape(format_brl(statistics['devolucao_condicao_comercial']))+'''. '''+count(statistics['notas'])+''' notas a emitir somam '''+escape(format_brl(statistics['valor_notas']))+escape(partial)+'''.</p><h2>Verificações</h2><ul>'''+checks+'''</ul><p>PASS significa consistência e cobertura do cálculo: cada valor é recomposto pelo rastro e cada linha de origem tem destino. O motor não executa emissões, repasses, contestações ou lançamentos no ERP.</p><h2>Consultar e rastrear resultados</h2><p>Selecione uma saída e pesquise um ID, CNPJ ou referência. Copie um id_saida e escolha rastro para conferir suas contribuições. A soma de valor em rastro reproduz o valor monetário dessa saída.</p><div class="controls"><label>Saída<select id="dataset"></select></label><label>Pesquisa<input id="search" type="search" placeholder="ID, CNPJ, histórico ou referência"></label></div><p id="count" aria-live="polite"></p><div id="table" class="scroll"></div><div class="pager"><span id="page"></span><div><button id="previous">Anterior</button><button id="next">Próxima</button></div></div><noscript><p>A pesquisa requer JavaScript. Os CSVs e o resumo permanecem disponíveis sem ele.</p></noscript><h2>Arquivos para revisão</h2><div class="downloads">'''+download_links+''' <a href="contestacoes/rascunho_orbe.txt">contestação Orbe</a> <a href="contestacoes/rascunho_ponte.txt">contestação Ponte</a> <a href="manifest.json">manifest.json</a> <a href="policy.json">policy.json</a> <a href="checks.json">checks.json</a></div><p>CSV com ponto e vírgula, ponto decimal, datas ISO e CNPJ textual. Campos extras registram status, regra e memória de cálculo. Valor de pendência desconhecido fica vazio; não é convertido em zero. Valores de pendências sobrepostas não devem ser somados como exposição total.</p><details><summary>Regras e decisões desta execução</summary><pre class="policy">'''+policy_text+'''</pre></details><details><summary>Fontes preservadas e integridade</summary><ul>'''+''.join(source_links)+'''</ul></details><footer><p><button onclick="window.print()">Imprimir / salvar PDF</button></p><p>O motor lê os arquivos locais e usa regras determinísticas. A IA foi usada no desenvolvimento e na investigação; não há chamadas de IA em execução e nenhuma chave de API é necessária.</p></footer></main><script type="application/json" id="records">'''+payload+'''</script><script>
const records=JSON.parse(document.getElementById('records').textContent);const selector=document.getElementById('dataset');const search=document.getElementById('search');let page=0;for(const key of Object.keys(records)){const option=document.createElement('option');option.value=key;option.textContent=key;selector.append(option)}function render(){const all=records[selector.value];const term=search.value.trim().toLocaleLowerCase('pt-BR');const rows=all.filter(row=>Object.values(row).some(v=>String(v??'').toLocaleLowerCase('pt-BR').includes(term)));const pages=Math.max(1,Math.ceil(rows.length/25));page=Math.min(page,pages-1);const columns=[...new Set(all.flatMap(row=>Object.keys(row)))];const table=document.createElement('table');const head=table.createTHead().insertRow();for(const title of columns){const cell=document.createElement('th');cell.scope='col';cell.textContent=title;head.append(cell)}const body=table.createTBody();for(const row of rows.slice(page*25,page*25+25)){const line=body.insertRow();for(const key of columns){const cell=line.insertCell();cell.textContent=row[key]??'';if(['cnpj','tomador_cnpj','id_saida','ref_origem','data','comissao_brl','diferenca_brl','valor_brl','valor'].includes(key)){cell.style.whiteSpace='nowrap'}}}document.getElementById('table').replaceChildren(table);document.getElementById('count').textContent=`${rows.length} registros encontrados de ${all.length}`;document.getElementById('page').textContent=`Página ${page+1} de ${pages}`;document.getElementById('previous').disabled=page===0;document.getElementById('next').disabled=page===pages-1}selector.onchange=()=>{page=0;search.value='';render()};search.oninput=()=>{page=0;render()};document.getElementById('previous').onclick=()=>{page--;render()};document.getElementById('next').onclick=()=>{page++;render()};render();
</script><script>selector.value='comissoes_por_lojista';render();</script></body></html>'''


def publish_result(bundle,result,policy,period,output,revision=None):
    output = Path(output).resolve()
    engine_digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        engine_digest.update(path.name.encode())
        engine_digest.update(path.read_bytes())
    source_hashes = {key:value['sha256'] for key,value in bundle.sources.items()}
    identity = {'period':period,'sources':source_hashes,'policy':policy,'engine':engine_digest.hexdigest()}
    if revision:
        identity['revision'] = revision
    fingerprint = hashlib.sha256(encode_json(identity).encode()).hexdigest()
    run_id = f'{period}-rev{revision["numero"]}-{fingerprint[:16]}' if revision else f'{period}-{fingerprint[:16]}'
    contents = {name+'.csv':encode_csv(name,rows).encode('utf-8') for name,rows in {**result.tables,'rastro':result.traces,'cobertura':result.coverage}.items()}
    contents['checks.json'] = encode_json(result.checks).encode()
    contents['policy.json'] = encode_json(policy).encode()
    contents['metrics.json'] = encode_json(result.metrics).encode()
    contents['index.html'] = render_report(result,bundle,policy,run_id,output).encode('utf-8')
    for counterpart, items in result.contests.items():
        slug = counterpart.lower()
        contents[f'contestacoes/operacoes_{slug}.csv'] = encode_rows(items).encode('utf-8')
        contents[f'contestacoes/rascunho_{slug}.txt'] = contest_draft(counterpart,items,period).encode('utf-8')
    for name,content in bundle.attachments.items():
        contents['anexos/'+name] = content
    manifest = {'run_id':run_id,'period':period,'status':result.metrics['status'],'engine_version':__version__,'engine_sha256':engine_digest.hexdigest(),'sources':{name:{k:v for k,v in meta.items() if k != 'path'} for name,meta in bundle.sources.items()},'output_sha256':{key:hashlib.sha256(content).hexdigest() for key,content in contents.items()},'rules':policy['status'],'slack_read':True}
    if revision:
        manifest['revisao'] = revision
    contents['manifest.json'] = encode_json(manifest).encode()
    if output.exists():
        for name,content in contents.items():
            destination = output/name
            if not destination.is_file() or destination.read_bytes() != content:
                raise ValueError('Output directory differs from this execution; choose a new --output directory. No files were overwritten.')
        return manifest
    output.parent.mkdir(parents=True,exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.closing-stage-',dir=output.parent)).resolve()
    if staging.parent != output.parent or staging == output:
        raise ValueError('Invalid staging path')
    for name,content in contents.items():
        target = staging/name
        if not target.resolve().is_relative_to(staging):
            raise ValueError('Artifact path escapes staging directory')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content)
    for name,expected in manifest['output_sha256'].items():
        if hashlib.sha256((staging/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Saved artifact checksum mismatch')
    staging.rename(output)
    return manifest
