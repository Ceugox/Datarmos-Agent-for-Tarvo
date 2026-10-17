# API do fechamento

Camada HTTP fina sobre a mesma orquestração da CLI (`src/tarvo_close/runner.py`). Não há regra de negócio na API: ela recebe o pacote do mês, enfileira o fechamento, guarda o resultado e serve as saídas. A CLI continua rodando do zero, sem serviço e sem chave. Decisões de projeto: `docs/adr/0002-camada-de-inferencia.md`.

Stack: FastAPI + uvicorn em `0.0.0.0:$PORT`, Postgres (`DATABASE_URL`), arquivos em `DATA_DIR`. Um worker no mesmo processo consome a tabela `jobs` (`FOR UPDATE SKIP LOCKED`); separar o worker depois é subir `python -m api.worker` com o mesmo código e as mesmas variáveis. As migrações (`api/migrations/`) rodam no start e são idempotentes.

## Autenticação

Toda rota exige `Authorization: Bearer <chave>`, exceto `GET /health`. Chave ausente, malformada ou inexistente devolve `401 {"detail":"chave inválida"}`. Cada cliente só enxerga os próprios fechamentos, exceções, arquivos e auditoria; o id de outro cliente responde `404`, como se não existisse.

**Como a chave é guardada.** A chave tem a forma `tk_` + 256 bits aleatórios (`secrets.token_urlsafe(32)`). O banco guarda só `sha256(API_KEY_PEPPER + chave)` em hex. Por que sha256 e não bcrypt: hash lento protege contra força bruta de entradas de baixa entropia (senha escolhida por pessoa), e uma chave aleatória de 256 bits não é esse caso; sha256 ainda permite buscar o cliente por igualdade no índice, sem varrer a tabela. O `API_KEY_PEPPER` (variável de ambiente, opcional) fica fora do banco, então um dump do banco sozinho não valida nenhuma chave. Trocar o pepper invalida todas as chaves existentes.

### Criar a primeira chave

```bash
DATABASE_URL=postgresql://... API_KEY_PEPPER=... python -m api.keys criar --cliente "Tarvo"
```

O comando roda as migrações, grava o cliente e imprime a chave **uma vez**, em stdout, e mais nada. A Tarvo recebe como versão 1 as políticas `closing-policy` e `inference-policy` de `config/` (seed). A chave não é recuperável: perdeu, cria outra. Nome de cliente repetido devolve erro e código de saída 1. Use o mesmo `API_KEY_PEPPER` do serviço.

### Primeira chave no Railway

O `DATABASE_URL` interno do Railway (`postgres.railway.internal`) só resolve de dentro do container; `railway run` local não o alcança. Rode o comando no serviço:

```bash
railway ssh --service api -- python -m api.keys criar --cliente "Tarvo"
```

A chave aparece uma única vez, na saída do comando; guarde-a na hora.

### Subida e volume

O contêiner inicia como root só para o `docker-entrypoint.sh`: ele cria `$DATA_DIR`, ajusta o dono para o usuário `app` (o volume do Railway monta `/data` como root), confere que `app` consegue escrever e então troca de usuário com `runuser`. Se não conseguir escrever, aborta com mensagem em stderr. O `healthcheckTimeout` de 120 s do `railway.json` cobre o start com as migrações.

## Variáveis de ambiente

Ver `.env.example`.

| Variável | Padrão | Função |
|---|---|---|
| `DATABASE_URL` | (obrigatória) | Postgres |
| `DATA_DIR` | `./data` (`/data` no contêiner) | `<DATA_DIR>/<cliente_id>/<fechamento_id>/entrada/` e `.../saida/` |
| `PORT` | `8000` | porta HTTP |
| `MAX_UPLOAD_MB` | `50` | limite de upload |
| `RATE_LIMIT_PER_MINUTE` | `60` | requisições por minuto por cliente, por processo |
| `API_KEY_PEPPER` | vazio | segredo extra do hash das chaves |
| `WORKER_IN_PROCESS` | `1` | `0` desliga o worker no processo da API |
| `ANTHROPIC_API_KEY` | vazio | só lida com `usar_llm=true`. A API sobe e funciona sem ela com `usar_llm=false`; com `usar_llm=true` e sem chave o fechamento roda sem a camada (saída igual à de `--no-llm`) e registra `aviso` no fechamento |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | modelo do resolvedor |
| `LLM_BUDGET_TOKENS` | `200000` | orçamento de tokens por execução; ao estourar, as exceções restantes vão para humano (`ORCAMENTO_ESGOTADO`) |

Não há CORS aberto. Os logs registram só ids, status e duração: nunca conteúdo de transação nem chave.

## Endpoints

Os exemplos usam `http://localhost:8000` e a chave em `$CHAVE`.

### `GET /health`

Sem autenticação. Executa `SELECT 1` no banco.

```bash
curl http://localhost:8000/health
# {"status":"ok","banco":"ok"}
```

`200` ok; `503` banco inacessível.

### `POST /v1/fechamentos`

Multipart. Campos: `periodo` (`YYYY-MM`), `usar_llm` (`true`/`false`, padrão `false`) e `arquivos` (um ou vários) **ou** um único `.zip` do pacote.

Por arquivos:

```bash
curl -X POST http://localhost:8000/v1/fechamentos \
  -H "Authorization: Bearer $CHAVE" \
  -F periodo=2026-09 -F usar_llm=false \
  -F arquivos=@Tarvo_Data_Pack_set2026/01_orbe_relatorio_comissoes_set2026.csv \
  -F arquivos=@Tarvo_Data_Pack_set2026/02_tabela_taxas_contratadas.xlsx \
  -F arquivos=@Tarvo_Data_Pack_set2026/03_email_ponte_cambio_relatorio_set2026.eml \
  -F arquivos=@Tarvo_Data_Pack_set2026/04_plano_de_contas_fenix_erp.csv \
  -F arquivos=@Tarvo_Data_Pack_set2026/05a_extrato_banco_aurora_cc4471_set2026.csv \
  -F arquivos=@Tarvo_Data_Pack_set2026/05b_extrato_banco_meridiano_cc90233_set2026.ofx \
  -F arquivos=@Tarvo_Data_Pack_set2026/06_orbe_ajustes_tardios_set2026.csv
# {"id":"0b0e...","status":"NA_FILA"}
```

Por zip:

```bash
curl -X POST http://localhost:8000/v1/fechamentos \
  -H "Authorization: Bearer $CHAVE" \
  -F periodo=2026-09 -F arquivos=@pacote-set2026.zip
```

Validação antes de gravar qualquer byte: o nome do arquivo só pode ter `[A-Za-z0-9._-]` (sem `/` nem `\`); o prefixo tem de ser `01_`, `02_`, `03_`, `04_`, `05a_`, `05b_` ou `06_`, com a extensão da fonte (`01_`, `04_`, `05a_`, `06_`: `.csv`; `02_`: `.xlsx`; `03_`: `.eml`; `05b_`: `.ofx`); ou um único `.zip`.

| Código | Quando |
|---|---|
| `202` | aceito; devolve `{"id", "status":"NA_FILA"}` |
| `401` | chave inválida |
| `411` | requisição sem `Content-Length` (o cabeçalho é exigido) |
| `413` | `Content-Length` acima de `MAX_UPLOAD_MB` (recusado antes de ler) ou excedido durante a gravação (o parcial é apagado) |
| `422` | `periodo` fora de `YYYY-MM`, nome ou prefixo de arquivo inválido, mistura de zip com arquivos |
| `429` | limite de requisições (traz `Retry-After`) |

### `GET /v1/fechamentos/{id}`

Estado e métricas. Use como poll até `status` sair de `NA_FILA`/`PROCESSANDO`.

```bash
curl -H "Authorization: Bearer $CHAVE" http://localhost:8000/v1/fechamentos/$ID
```

Campos: `id`, `periodo`, `status`, `usar_llm`, `run_id`, `numero_revisao`, `pai_id`, `revisoes` (ids das revisões filhas), `metrics` (conteúdo de `metrics.json`), `checks` (conteúdo de `checks.json`), `excecoes` (`{"por_classe": {...}, "por_modo": {...}}`), `erro`, `aviso` (string ou `null`; preenchido quando `usar_llm=true` e não há `ANTHROPIC_API_KEY`), `criado_em`, `concluido_em`. `404` para id inexistente ou de outro cliente.

### `GET /v1/fechamentos/{id}/arquivos/{nome}`

Baixa uma saída. A lista é fechada; qualquer outro nome (inclusive `../` e `anexos/`) devolve `404`.

```bash
curl -H "Authorization: Bearer $CHAVE" -o pendencias.csv \
  http://localhost:8000/v1/fechamentos/$ID/arquivos/pendencias.csv
```

Arquivos servidos: `comissoes_por_lojista.csv`, `divergencias_taxa.csv`, `notas_a_emitir.csv`, `lancamentos_classificados.csv`, `pendencias.csv`, `rastro.csv`, `cobertura.csv`, `checks.json`, `policy.json`, `metrics.json`, `manifest.json`, `index.html`, `auditoria.jsonl`, `contestacoes/operacoes_orbe.csv`, `contestacoes/rascunho_orbe.txt`, `contestacoes/operacoes_ponte.csv`, `contestacoes/rascunho_ponte.txt`.

`409` se o fechamento ainda não terminou; `404` se o arquivo não existe na execução (por exemplo `auditoria.jsonl` quando a camada não rodou).

### Formato dos CSVs

Os CSVs seguem sempre as mesmas quatro regras: separador `;`, ponto decimal, datas `AAAA-MM-DD` e CNPJ só com 14 dígitos. A API devolve os bytes exatos do arquivo gerado (`Content-Type: text/csv; charset=utf-8`), sem reformatar. O CI verifica isso em toda execução (`tests/output_format.py`, também contra CRLF, BOM, campo faltando e arquivo fora de UTF-8).

### `GET /v1/fechamentos/{id}/excecoes`

```bash
curl -H "Authorization: Bearer $CHAVE" http://localhost:8000/v1/fechamentos/$ID/excecoes
```

Lista a fila de exceções do fechamento, sempre, com ou sem a camada: `id` (usado na decisão), `excecao_id`, `classe`, `tipo`, `escopo`, `valor_brl` (string decimal ou `null`), `quem_decide`, `motivo_pendencia`, `modo` (modo efetivo da classe na política de inferência), `resultado`, `motivo`, `proposta`, `verificacoes`, `aplicada`, `pendencia_status` (de `pendencias.csv`). Sem a camada (`usar_llm=false` ou sem chave) `resultado` é `SEM_CAMADA`, `motivo` e `proposta` são `null` e `verificacoes` é `[]`; com a camada (e nas revisões), os eventos da auditoria preenchem `resultado`, `motivo`, `proposta`, `verificacoes` e `aplicada`.

### `POST /v1/excecoes/{id}/decisao`

`{id}` é o `id` da exceção em `/excecoes`. Corpo JSON: `decisao` (`aprovar` | `rejeitar` | `editar`), `decidido_por`, `motivo`, e `parametros` (em `editar`: `{"conta_codigo": "..."}`).

```bash
curl -X POST http://localhost:8000/v1/excecoes/$EXC_ID/decisao \
  -H "Authorization: Bearer $CHAVE" -H "Content-Type: application/json" \
  -d '{"decisao":"aprovar","decidido_por":"Helena","motivo":"Conferi o extrato"}'
# {"revisao_id":"7c1d...","status":"NA_FILA"}
```

A decisão nunca reescreve a execução: cria uma revisão nova (fechamento filho com `pai_id`, `numero_revisao + 1`, `run_id` próprio e o `run_id` pai no `manifest.json`), sobre a mesma entrada. Aprovar não cria `bank_rule`; a decisão vale para aquele movimento. `editar` passa pelo mesmo validador da proposta.

| Código | Quando |
|---|---|
| `202` | revisão enfileirada |
| `404` | exceção inexistente ou de outro cliente |
| `409` | já há revisão em andamento (job `NA_FILA` ou `PROCESSANDO`) na linhagem do fechamento, ou a execução pai é antiga: sem `auditoria.jsonl` e sem o marcador `camada` no `manifest.json` (refaça o fechamento) |
| `422` | corpo fora da forma (campo ausente, `decisao` desconhecida) |

Decidir sobre fechamento feito com `usar_llm=false` é permitido (o `manifest.json` do pai traz `camada.auditoria = false`): `DECISAO` e `CONDICAO_COMERCIAL` viram `APROVADA` ou `REJEITADA` sem mudar nenhum número; `aprovar` em `MOVIMENTO_SEM_REGRA` sem proposta validada vira `RECUSADA` (registrada na auditoria da revisão).

Erros de regra (por exemplo aprovar proposta em modo `sombra`, ou exceção já decidida) aparecem na revisão: ela termina em `ERRO` com a mensagem em `erro`.

### `GET /v1/fechamentos/{id}/auditoria`

```bash
curl -H "Authorization: Bearer $CHAVE" http://localhost:8000/v1/fechamentos/$ID/auditoria
# {"eventos":[ ... ]}
```

Eventos em ordem (`seq`): proposta, verificações, modo, tokens e custo, decisão e quem decidiu.

Os eventos `EXCECAO` com `motivo` `ERRO_API` ou `ERRO_REDE` trazem o campo `detalhe` com `tipo`, `status`, `mensagem` (até 500 caracteres) e `request_id`; nunca a chave nem o conteúdo enviado. `ERRO_REDE`: falha de conexão, timeout, `429` ou status 500 e acima (vale tentar de novo). `ERRO_API`: os demais 4xx.

## Estados

Fechamento (e revisão, que é um fechamento filho): `NA_FILA`, `PROCESSANDO`, depois `CONCLUIDO`, `PROVISORIO` (`metrics.status` igual a `PROVISORIO`: saída provisória) ou `ERRO` (mensagem em `erro`, sem traceback nem conteúdo de arquivo). Job: `NA_FILA`, `PROCESSANDO`, `CONCLUIDO`, `ERRO`. Decisão: `aprovar`, `rejeitar`, `editar`; a pendência vira `APROVADA` ou `REJEITADA` (decisão registrada) ou `RESOLVIDA` (proposta aplicada, linha com `metodo=IA`).

## Limites

- Upload: `MAX_UPLOAD_MB` (50), conferido por `Content-Length` e, de novo, na gravação em streaming.
- Requisições: `RATE_LIMIT_PER_MINUTE` (60) por cliente, janela deslizante, `429` com `Retry-After`. **O contador vive na memória do processo**: com mais de uma instância, o limite efetivo é por instância (N instâncias deixam passar até N vezes o valor). Se o serviço escalar na horizontal, o limite tem de ir para o Postgres ou para a borda.
- Tokens do LLM por execução: `LLM_BUDGET_TOKENS` (200000).

## LGPD: o que sai para a Anthropic, campo a campo

**Por padrão nada sai.** `usar_llm` é `false`; só com `usar_llm=true` **e** `ANTHROPIC_API_KEY` configurada a camada roda. Sem uma das duas, a saída é idêntica à de `--no-llm`. Só as classes com modo diferente de `desligado` na `inference-policy` chamam o modelo; no estado inicial é só `MOVIMENTO_SEM_REGRA` (modo `sombra`).

A chamada é `AnthropicResolver.propose` (`src/tarvo_close/resolver.py`) e leva três partes.

**1. `system` (contexto fixo, igual para todas as exceções do fechamento).** O texto de `SYSTEM_INSTRUCTIONS` (regras do resolvedor) seguido de `fixed_context` (`src/tarvo_close/inference.py`) em JSON:

| Campo | Conteúdo |
|---|---|
| `closing_policy` | a `closing-policy` do cliente **inteira**: `schema_version`, `status`, `checkout`, `remittance`, `ec_overrides`, `commercial_conditions`, `unbilled_merchants`, `decisions`, `open_questions`, `bank_rules`. Inclui regras, taxas, nomes e identificadores de lojista e EC que a política cita |
| `accounts` | o plano de contas inteiro (`COD_CONTA`, `DESCRICAO`, `TIPO`, `NATUREZA`, `ACEITA_LANCTO`, `COD_SUPERIOR`, `DT_CRIACAO`) |
| `period` | `YYYY-MM` |

O `system` **não passa por `mask_personal_data`**: não deve haver CPF nem número de conta bancária na política ou no plano de contas. Quem cadastra a política de um cliente é responsável por isso.

**2. Mensagem do usuário.** `USER_INSTRUCTIONS` e, entre `<excecao>` e `</excecao>`, a exceção montada por `exception_payload`, com `mask_personal_data` aplicado ao JSON inteiro antes do envio:

| Campo | Conteúdo |
|---|---|
| `excecao_id`, `classe`, `tipo`, `escopo` | identificadores da exceção (o `escopo` de um movimento bancário é `BANCO:REF`) |
| `quem_decide`, `motivo`, `falta` | textos da regra do núcleo: quem decide, por que parou, o que resolve |
| `valor_brl` | valor que o **núcleo** calculou para a pendência; o modelo não propõe valor (a proposta não tem campo monetário) |
| `refs` | por linha de origem: `arquivo`, `aba`, `ref`, `linha` |
| `linhas_citadas` | por ref: `arquivo`, `ref` e `texto`, a **linha de origem relida da fonte** e mascarada |

O que é a linha citada (`validators.source_line`) depende do arquivo: em CSV, a linha inteira como está no arquivo; em `.xlsx`, as células da linha unidas por `;`; em `.ofx`, o bloco `<STMTTRN>` inteiro da transação; em outros textos (como o `.eml`), a linha do arquivo. Para um movimento bancário isso inclui data, descrição, valor e as demais colunas da linha.

**3. Resposta.** A proposta volta como chamada da ferramenta `propor_resolucao`, validada por schema e relida contra a fonte. O `system` vai com cache de prompt (`cache_control`); reexecuções com resposta já em cache não chamam a rede.

**O que é mascarado antes do envio** (`privacy.mask_personal_data`, só sobre a exceção e as linhas citadas):

- CPF (`000.000.000-00` ou 11 dígitos) vira `***.***.***-**`;
- o número depois de `conta`, `c/c`, `cc`, `agência` ou `ag` tem os dígitos trocados por `*`.

**O que NÃO é mascarado e sai**: CNPJ (chave de empresa), descrição do movimento (texto livre do banco, que pode conter nome de pessoa ou empresa), valores, datas, nomes de lojista, EC, número de operação, FITID, e tudo o que está na política e no plano de contas. A máscara é por padrão de texto: CPF fora dos formatos acima, ou conta sem a palavra-chave antes do número, passam. Não envie pacotes cujo conteúdo o cliente não possa compartilhar com um subprocessador.

**O que não sai**: arquivos inteiros (só a linha citada de cada ref), as outras linhas dos extratos, os CSVs de saída, anexos, a chave de API do cliente, o `DATABASE_URL`.

**Retenção.** Zero Data Retention com a Anthropic é decisão contratual da Tarvo; este serviço não a configura nem a garante. Até ela existir, trate `usar_llm=true` como envio a um subprocessador sem retenção zero.

**Auditoria.** Cada proposta, a evidência, o resultado de cada verificação, tokens e custo ficam em `auditoria.jsonl` e na tabela `auditoria`.
