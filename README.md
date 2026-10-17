# Datarmos Agent for Tarvo: motor de fechamento mensal

Motor local para o case Barte AI. Recebe a pasta (ou o ZIP) com os arquivos do mês, incluindo ajustes tardios da Orbe quando chegam, aplica as regras do financeiro da Tarvo e gera os seis CSVs de `saida/`, um relatório HTML de revisão e rascunhos de contestação para a Orbe e a Ponte. Um único comando, sem limpeza manual dos arquivos.

**O cálculo é determinístico e roda sem chave de API.** Sem chave, ou com `--no-llm`, nenhuma chamada de IA é feita e `saida/` fica byte a byte igual (fora `manifest.json` e `index.html`). Existe uma camada de inferência opcional, desligada por padrão, que só propõe (nunca calcula) e cuja chamada fica registrada em `auditoria.jsonl` ao lado das saídas; ver "Camada de inferência". A IA também foi usada na investigação e no desenvolvimento (ver `PROMPTS/`).

## Rodar do zero

Python 3.12 ou superior (testado em 3.14):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_engine.py --input Tarvo_Data_Pack_set2026 --period 2026-09 --output saida-banca
```

Em Linux/macOS, troque `.\.venv\Scripts\python.exe` por `.venv/bin/python`.

Abra `saida-banca/index.html` no navegador. Os CSVs ficam direto na pasta de saída e devem coincidir com os de `saida/` entregues.

- `--input`: pasta ou `.zip` com os arquivos do mês. Os arquivos são identificados pelos prefixos `01_`, `02_`, `03_`, `04_`, `05a_` e `05b_`; nada é fixo para setembro. Ajustes tardios da Orbe (`06_*.csv`, mesmo layout do `01`) são opcionais: quando existem, entram no checkout do mês; quando não existem, nada é bloqueado.
- `--period`: competência `AAAA-MM`.
- `--output`: pasta nova. Se a pasta já existir com conteúdo diferente, o motor recusa sobrescrever (para não perder um fechamento anterior); com conteúdo idêntico, apenas confirma.
- `--policy`: regras (padrão `config/closing-policy.json`).
- `--no-llm`: não usa a camada de inferência. Sem esta flag e sem `ANTHROPIC_API_KEY` no ambiente, o resultado é o mesmo (aviso em stderr); `auditoria.jsonl` não é gerado.
- `--inference-policy`: modos e critérios da camada por classe de exceção (padrão `config/inference-policy.json`).
- `--cache-dir`: cache das respostas do modelo (padrão `.cache/llm`, ignorado pelo git). Reexecução com cache não chama a rede e dá a mesma saída.
- `--revisao-de <pasta da execução pai>` e `--decisoes decisoes.json`: aplicam decisões humanas numa revisão nova (ver "Decisões e revisões").

Para outubro: `--input <pasta de outubro> --period 2026-10 --output saida-2026-10`.

### Fonte ausente, atrasada ou com layout diferente

O mês não fica parado por causa de uma fonte (regra da Helena, 17/10 12h31). Se um arquivo falta, vem duplicado ou o leitor não reconhece o layout, o motor fecha o que não depende dele, registra uma pendência `FONTE_BLOQUEADA` para a Helena com o motivo e o que ficou bloqueado, marca o fechamento como `PROVISORIO` (em `metrics.json`, `manifest.json` e no topo do HTML) e sai com **código 3**. Código 0 é fechamento completo; 1 é erro de regra ou configuração, que para tudo.

| Fonte indisponível | Fica sem número | Fecha normalmente |
|---|---|---|
| `01_` Orbe ou `06_` ajustes (se presente e ilegível) | Checkout: comissões, notas, divergências da Orbe, devolução, alerta | Remessa e bancos |
| `02_` Taxas | Checkout e remessa | Bancos |
| `03_` Ponte | Remessa e nota da Ponte | Checkout e bancos |
| `04_` Plano de contas | Classificação dos dois extratos | Checkout e remessa |
| `05a_` ou `05b_` | Lançamentos daquele banco | Todo o resto |

Quando a fonte chegar, roda-se de novo numa pasta nova de saída.

## Saídas

| Arquivo | Conteúdo |
|---|---|
| `comissoes_por_lojista.csv` | Comissão por CNPJ e linha de negócio (CHECKOUT, REMESSA). |
| `divergencias_taxa.csv` | Lançamentos com taxa/spread aplicado diferente do contratado, com o valor a contestar e a contraparte (Orbe ou Ponte). |
| `notas_a_emitir.csv` | Uma nota por lojista de checkout com saldo positivo e uma nota para a Ponte Câmbio pela participação nas remessas. Status `A_EMITIR_APOS_REVISAO`. |
| `lancamentos_classificados.csv` | Cada movimento dos dois extratos com a conta contábil da contrapartida. |
| `pendencias.csv` | O que depende de decisão: valor, motivo e quem decide. |
| `rastro.csv` | Para cada `id_saida`, as linhas de origem cuja soma reproduz o valor. |

Também: `auditoria.jsonl` (só quando a camada rodou ou numa revisão), `contestacoes/` (rascunho de e-mail e lista de operações por contraparte), `cobertura.csv` (destino de cada linha de origem), `metrics.json`, `checks.json`, `policy.json`, `manifest.json` (hashes de entradas, regras, motor e saídas) e `anexos/` (anexo do e-mail da Ponte).

### Formato fixo dos CSVs

Sempre: separador `;`, ponto decimal, datas `AAAA-MM-DD` e CNPJ só com 14 dígitos, em texto. Valor de pendência desconhecido fica vazio, não zero; `confianca` fica vazia numa linha `IA` aprovada antes de existir backtest. O CI confere isso nos bytes de `saida/` e da reexecução com `python tests/output_format.py saida /tmp/saida-ci`; os testes da CLI, das revisões e da API usam o mesmo verificador.

## Resultado de setembro/2026

- Comissão de checkout: **R$ 203.735,34** (bruto × taxa contratada, linha a linha), já com os 14 ajustes tardios da Orbe (`06_`): −R$ 3.304,39 em 10 estornos, 3 reversões de antecipação e 1 venda.
- Participação em remessas: **R$ 39.543,45** (50% do spread realizado de 228 operações; 4 spreads negativos fora; operação repetida contada uma vez).
- 21 notas: 20 de checkout e 1 para a Ponte Câmbio, somando R$ 243.284,29. A Casa do Estudante fica sem nota (saldo de −R$ 5,50 por estorno de venda de agosto) e a Atlas não é faturada até o comercial confirmar a taxa.
- 115 divergências: Rota Global (87) e Bridge (5) contra a Orbe, R$ 1.576,23 líquidos; Mundo Aberto (23) contra a Ponte, R$ 1.418,88.
- Devolução à Casa do Estudante pela isenção não informada à Orbe: R$ 15.396,77.
- 184 movimentos bancários classificados; 2.374 linhas de origem com destino registrado.

## Camada de inferência

Decisão de projeto: `docs/adr/0002-camada-de-inferencia.md`. O núcleo continua determinístico; a camada fica por cima e resolve só o que não é decisão da Helena.

- **Exceção tipada.** Cada pendência vem de uma exceção com classe (`LAYOUT_FONTE`, `CADASTRO`, `MOVIMENTO_SEM_REGRA`, `ESPERA_DADO`, `ESPERA_EVIDENCIA`, `CONDICAO_COMERCIAL`, `DECISAO`, `DADO_INVALIDO`); a tabela `tipo` → classe está em `src/tarvo_close/exceptions.py` e `pendencias.csv` não muda.
- **O modelo não calcula.** Nunca valor, arredondamento, comissão, total ou nota (o schema da proposta não tem campo monetário), e nunca decide política. Casamento só por chave rígida (CNPJ, EC, nº de operação, FITID, valor exato), nunca por semelhança de nome.
- **Evidência verificável.** Toda proposta cita arquivo, referência e `trecho`, e o validador relê a fonte: o trecho (3 caracteres ou mais) tem de ser literal na descrição. Sem isso, a proposta é rejeitada e a exceção segue para humano.
- **Modos por classe**, em `config/inference-policy.json`: `desligado | sombra | sugerir | automatico`. `sombra`: a proposta só aparece na auditoria e os CSVs ficam iguais aos de `--no-llm`. `sugerir`: igual até uma decisão humana; aprovada, a linha sai com `metodo=IA`, `status=SUGERIDO` e a pendência vira `RESOLVIDA`. `automatico`: a proposta validada se aplica sem humano.
- **Teto em código.** `DECISAO` e `CONDICAO_COMERCIAL` não passam de `sugerir`, e `DADO_INVALIDO` fica `desligado`; o teto é conferido em `src/tarvo_close/inference_policy.py` (`CODE_CEILINGS`), então editar o JSON não o sobe.
- **Promoção.** Subir de modo exige 35 casos seguidos sem erro no backtest da classe; `automatico` exige ainda `aprovado_por` (Helena), data e `confianca` na política. Estado inicial: `MOVIMENTO_SEM_REGRA` em `sombra`, `DECISAO` e `CONDICAO_COMERCIAL` em `sugerir` (só tipadas, sem pré-preenchimento), o resto `desligado`.
- **Confiança.** Numa linha `IA`, `confianca` é o limite inferior de Wilson (95%) da precisão da classe no backtest, gravado na política. Nunca é autodeclarada pelo modelo; vazia enquanto não houver backtest.
- **Validador de `MOVIMENTO_SEM_REGRA`** (tudo tem de passar, senão humano): evidência citando o movimento; conta existente, analítica e que aceita lançamento; par (sinal do movimento, grupo da conta) já presente nas regras bancárias aplicadas no mês; contas de provisão (`2.1.03.*`, `2.1.04.*`) e de disponibilidade (`1.1.01.*`, `1.1.09.001`) vão para humano.
- **Aprovar não cria regra** em `closing-policy.json`: a decisão vale para aquele movimento.

### Decisões e revisões

Decisão (`aprovar`, `rejeitar` ou `editar`, com `decidido_por` e `motivo`) nunca reescreve uma execução: gera a revisão `rev-N`, com `run_id` próprio e o `run_id` pai no `manifest.json`. A revisão não chama o modelo (roda sem chave) e sempre grava `auditoria.jsonl`, com os eventos `REVISAO` e `DECISAO_APLICADA`.

```powershell
.\.venv\Scripts\python.exe run_engine.py --input Tarvo_Data_Pack_set2026 --period 2026-09 --output saida-banca --no-llm
.\.venv\Scripts\python.exe run_engine.py --input Tarvo_Data_Pack_set2026 --period 2026-09 --output saida-rev --revisao-de saida-banca --decisoes decisoes.json
```

`decisoes.json` é uma lista de `{"excecao_id": "PEN-...", "decisao": "aprovar", "decidido_por": "Helena", "motivo": "...", "parametros": {"conta_codigo": "4.2.01"}}` (`parametros` só em `editar`, que passa pelo mesmo validador). Efeito na pendência: `DECISAO`, `CONDICAO_COMERCIAL` e demais classes sem proposta viram `APROVADA` ou `REJEITADA` e nenhum número muda; `MOVIMENTO_SEM_REGRA` aprovada ou editada vira `RESOLVIDA` (linha `metodo=IA`, com a evidência na `formula` do rastro); `aprovar` sem proposta validada na execução pai é registrado como `RECUSADA` (a revisão existe, nada muda). Funciona também sobre um pai rodado com `--no-llm`: o `manifest.json` traz `camada` (`ligada`, `auditoria`) e é isso que a revisão lê. Pai antigo, sem o marcador e sem `auditoria.jsonl`, é recusado.

### Backtest

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m tarvo_close.backtest --input Tarvo_Data_Pack_set2026 --period 2026-09 --policy config/closing-policy.json --inference-policy config/inference-policy.json --resolver fake
```

Setembro não tem movimento sem regra, então os casos são perturbados: para cada movimento casado por regra, remove-se a regra e, em variantes, altera-se a descrição (sufixo, prefixo, abreviação, acentos, ordem); o gabarito é a conta da regra original (183 casos `regra_removida` mais as perturbações; `AURORA:L53` fica de fora porque a regra genérica `merchant-payment` ainda o casa). A precisão vale para esse tipo de perturbação, não para fornecedor nunca visto, e por isso a classe começa em `sombra`. `--resolver fake` responde o gabarito (prova o medidor, roda no CI); `--resolver anthropic` usa o modelo (exige `ANTHROPIC_API_KEY`). `--gravar` registra `criterio` e `confianca` na política, só com `--resolver anthropic` e sem `--limit`, e nunca toca `modo`, `teto` nem `aprovado_por`.

### O que sai para a Anthropic

Só com a camada ligada (`usar_llm=true` na API, ou chave no ambiente sem `--no-llm` na CLI) e só para classes fora de `desligado`. Por exceção vão a descrição e a linha citada da fonte, com CPF e número de conta mascarados; o `system` leva a política de fechamento e o plano de contas inteiros. Campo a campo, o que é e o que não é mascarado e a retenção: seção LGPD de `docs/api.md`. Estimativa do ADR (`claude-opus-5-5`, preços de 2026-10): cerca de US$ 0,04 por exceção, setembro abaixo de US$ 0,10, mês ruim com 50 exceções elegíveis perto de US$ 2; `LLM_BUDGET_TOKENS` (padrão 200000) limita a execução e, ao estourar, o restante vai para humano (`ORCAMENTO_ESGOTADO`). Os números reais saem da auditoria; a única chamada real até agora foi recusada pela API (ver Limitações), então ainda não há custo medido.

## Serviço HTTP

Camada fina (FastAPI + uvicorn) sobre a mesma orquestração da CLI, com Postgres, arquivos em `DATA_DIR` e um worker no mesmo processo. Endpoints, autenticação, códigos de erro e LGPD: `docs/api.md`.

Rodar local:

```powershell
docker run -d --name tarvo-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16.4
docker build -t tarvo-api .
docker run --rm -p 8000:8000 -e DATABASE_URL=postgresql://postgres:test@host.docker.internal:55432/postgres -v tarvo-data:/data tarvo-api
```

Primeira chave (aparece uma vez; use o mesmo `API_KEY_PEPPER` do serviço, se houver):

```powershell
$env:PYTHONPATH='src'; $env:DATABASE_URL='postgresql://postgres:test@localhost:55432/postgres'
.\.venv\Scripts\python.exe -m api.keys criar --cliente "Tarvo"
```

Resumo: `GET /health`; `POST /v1/fechamentos` (pacote por arquivos ou `.zip`, `usar_llm` padrão `false`); `GET /v1/fechamentos/{id}` (estado e métricas); `GET /v1/fechamentos/{id}/arquivos/{nome}` (saídas); `GET /v1/fechamentos/{id}/excecoes`; `POST /v1/excecoes/{id}/decisao`; `GET /v1/fechamentos/{id}/auditoria`. Chave em `Authorization: Bearer`, guardada só como `sha256(pepper + chave)`; cada cliente tem as próprias políticas versionadas (a Tarvo entra como seed) e só vê o que é seu.

A fila de exceções existe sempre: com `usar_llm=false`, `/excecoes` lista todas as exceções do fechamento com `resultado=SEM_CAMADA` (setembro: 13). Decidir sobre elas é permitido: `DECISAO` e `CONDICAO_COMERCIAL` viram `APROVADA` ou `REJEITADA`; `aprovar` em `MOVIMENTO_SEM_REGRA` sem proposta vira `RECUSADA`. O `409` fica para revisão em andamento ou execução antiga sem o marcador `camada`.

## Deploy no Railway

Projeto `tarvo-fechamento`: serviços `api` e `Postgres`, mais o volume `/data` no `api`. URL: https://api-production-0e0e3.up.railway.app (`GET /health`).

- `DATABASE_URL=${{Postgres.DATABASE_URL}}` no serviço `api`; demais variáveis abaixo, conforme `.env.example`.
- Deploy com `railway up` a partir de uma cópia limpa (`git archive HEAD` para uma pasta nova), porque o diretório local tem pastas ignoradas sem permissão de leitura que quebram o upload.
- Primeira chave, no terminal de quem vai guardá-la (ela aparece uma vez): `railway ssh --service api -- python -m api.keys criar --cliente "Tarvo"`. O `DATABASE_URL` interno só resolve dentro do contêiner; `railway run` local não o alcança.
- `railway.json` (Dockerfile, health check em `/health`, 120 s) é Config as Code que o CLI marca como deprecated; funciona até 2026-12-01.

## Variáveis de ambiente

Modelo em `.env.example`. Nenhuma é necessária para a CLI sem a camada.

| Variável | Padrão | Função |
|---|---|---|
| `ANTHROPIC_API_KEY` | vazio | liga a camada (CLI sem `--no-llm`; API com `usar_llm=true`). Só do ambiente, nunca gravada |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | modelo do resolvedor |
| `LLM_BUDGET_TOKENS` | `200000` | tokens por execução; ao estourar, o restante vai para humano |
| `DATABASE_URL` | obrigatória na API | Postgres |
| `DATA_DIR` | `./data` (`/data` no contêiner) | entradas e saídas dos fechamentos da API |
| `PORT` | `8000` | porta HTTP |
| `MAX_UPLOAD_MB` | `50` | limite de upload |
| `RATE_LIMIT_PER_MINUTE` | `60` | requisições por minuto por cliente, por processo |
| `API_KEY_PEPPER` | vazio | segredo extra do hash das chaves; trocar invalida as chaves |
| `WORKER_IN_PROCESS` | `1` | `0` desliga o worker no processo da API |

## Limitações conhecidas

- Notas, contestações e lançamentos são propostas para revisão: o motor não emite nota, não envia e-mail e não lança no ERP.
- Atlas Idiomas fica sem faturamento até o comercial confirmar a taxa; o motor ainda não fatura num mês as linhas de meses anteriores (fica manual, com valor e linhas na pendência).
- Sem conciliação da Orbe contra o banco parcela por parcela (depende da agenda de recebíveis, fora do pacote).
- O alerta de antecipação só avalia lojistas sem histórico anterior no pacote.
- O bloqueio é por fonte inteira: com `02_` indisponível, a remessa também para, embora a participação de 50% não dependa da planilha (a divergência de spread depende). Erro na regra ou na configuração continua parando o fechamento inteiro, com mensagem.
- A confiança da classificação bancária por regra é um escore, não probabilidade calibrada. Só a das linhas `IA` é medida (Wilson no backtest), e o backtest real ainda não foi rodado: a política não tem `criterio` nem `confianca` preenchidos.
- Camada e API: job preso em `PROCESSANDO` se o processo morrer no meio (não há retomada); não há revogação de chave (perdeu, cria outra; trocar o pepper invalida todas); o rate limit é por processo; a primeira chamada real à Anthropic falhou com `400 invalid_request_error: "tools.0.custom: For 'anyOf', 'type' is not supported"` (o schema da proposta tinha `type` junto do `anyOf` na raiz); a correção tira o `type: object` da raiz, mantém o dos 8 ramos e sobe `prompt_version` para `2026-10-17.2`, para não reaproveitar o cache antigo. Erros da API agora são separados na auditoria: `ERRO_REDE` só para conexão, timeout, 429 e status 500 ou mais; `ERRO_API` para os demais 4xx (400, 401, 403, 404, 413, 422), com `detalhe` (tipo, status, mensagem, `request_id`).
- `railway.json` é Config as Code deprecated; funciona até 2026-12-01.
- Detalhes e decisões do time em `HIPOTESES.md`.

## Regras

As regras vêm das respostas do financeiro no Slack e estão em `config/closing-policy.json`, cada uma com evidência e data. O resumo, as decisões que o financeiro deixou para o time e as limitações estão em `HIPOTESES.md`; a transcrição das perguntas e respostas, em `docs/slack-financeiro.md`.

## Conferir um valor

No HTML, escolha uma saída, copie o `id_saida`, mude para `rastro` e pesquise o ID. A soma da coluna `valor` é o valor da saída. Cada linha do rastro diz o que foi aplicado:

- `formula`: a conta em texto (por exemplo `VENDA: quantize(<bruto>*<taxa>); half_up; taxa debit vigente em <data>; taxa contratada da planilha`; estorno pela taxa da data da venda original; isenção da Casa; 50% do spread pela data de contratação).
- `regra`: o caminho da regra em `config/closing-policy.json` (`decisions/checkout-basis`, `commercial_conditions/<id>`, `remittance`, `bank_rules/<id>`); com mais de uma, separadas por ` + `. Uma regra citada que não existe na política para o fechamento derruba a execução.
- `ref_contrato`: arquivo e linha da planilha de taxas de onde veio a taxa (`02_tabela_taxas_contratadas.xlsx!<ref>`).
- `arquivo_origem`, `aba_origem`, `ref_origem`, `linha_origem`: a linha da fonte.

Para refazer um número: some `valor` das linhas do `id_saida`; para cada linha, aplique a `formula` com a taxa que a `ref_contrato` mostra na planilha. `tests/test_rastro.py` faz isso para todas as linhas de comissão e divergência de checkout e remessa e para a nota da Ponte, só com o rastro e a planilha. O `manifest.json` registra hashes das entradas, das regras e do motor, o horário da execução em UTC (`execucao.iniciada_em`, `execucao.concluida_em`; reexecução idêntica na mesma pasta devolve o manifest salvo, sem horário novo), as linhas lidas de cada arquivo e aba (`sources[*].linhas_lidas`, `execucao.linhas_lidas_total`) e `camada` (`ligada`, `auditoria`).

## Verificação

O CI (`.github/workflows/ci.yml`) roda estes comandos em `push` na `main` e em `pull_request`, com a versão de Python de `.python-version` (a mesma do `Dockerfile`). Dois jobs, em paralelo.

Job `tests` (motor, sem rede e sem chave):

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
python run_engine.py --input Tarvo_Data_Pack_set2026 --period 2026-09 --output /tmp/saida-ci
diff -r -x index.html -x manifest.json saida /tmp/saida-ci
python tests/output_format.py saida /tmp/saida-ci
```

Job `api` (Postgres 16.4 como service container, sem chave e sem rede externa):

```bash
grep -q "^FROM python:$(cat .python-version)-slim" Dockerfile
pip install -r requirements-api.txt
TEST_DATABASE_URL=postgresql://postgres:test@localhost:5432/postgres python -m unittest discover -s tests -p "test_api_*.py" -v
```

Local: no Windows, troque `python` por `.\.venv\Scripts\python.exe`. Sem `TEST_DATABASE_URL` os testes da API são pulados com o motivo; para rodá-los, suba o Postgres da seção "Serviço HTTP" e use `postgresql://postgres:test@localhost:55432/postgres`. Nenhum teste chama a Anthropic: usam cliente falso.

Os testes cobrem os números de setembro, as regras do financeiro (estorno de agosto, isenção da Casa, spreads negativos, duplicata, nota única da Ponte, alerta de antecipação), a reconciliação dos CSVs com o rastro, ZIP de entrada, reexecução sem sobrescrita, reordenação, conflito de versões, período seguinte simulado, rejeição de dados corrompidos, `--no-llm` byte a byte, validadores, revisões, backtest e a API (autenticação, isolamento entre clientes, limites e a mesma saída pela CLI e pela API).

Contra o serviço publicado há uma bateria à parte, fora do CI porque precisa da API no ar e de duas chaves de cliente: `scripts/bateria_producao.py`. O que ela cobre, como rodar, o último resultado (78/78 em 17/10/2026) e os defeitos que só apareceram em produção estão em `docs/testes-producao.md`.

## Estrutura

- `run_engine.py`, `src/tarvo_close/`: leitura das fontes, cálculo, validação e publicação; camada de inferência (`inference.py`, `resolver.py`, `validators.py`, `backtest.py`).
- `api/`, `Dockerfile`, `railway.json`: serviço HTTP.
- `config/closing-policy.json`: regras e decisões. `config/inference-policy.json`: modos da camada.
- `Tarvo_Data_Pack_set2026/`: arquivos do case.
- `saida/`: execução entregue de setembro.
- `PROMPTS/`, `HIPOTESES.md`, `docs/`: histórico de IA, premissas e respostas do financeiro.
- `LICENSE`: licença MIT do código.

## Licença

O código do Datarmos Agent for Tarvo (`src/`, `run_engine.py`, `config/`, `tests/`) é MIT, ver `LICENSE`. O data pack `Tarvo_Data_Pack_set2026/`, as saídas derivadas em `saida/` e as transcrições em `docs/` e `PROMPTS/` são material do case Barte AI e não estão cobertos pela licença.
