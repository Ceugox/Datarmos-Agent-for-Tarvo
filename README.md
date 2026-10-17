# Datarmos Agent for Tarvo: motor de fechamento mensal

> ### [Abrir o site da Datarmos ↗](https://datarmos.up.railway.app)
>
> **Vídeo de abertura, pitch, resultados do case e guia para usar a API.**
>
> [datarmos.up.railway.app](https://datarmos.up.railway.app) · [Pitch de 13 slides](https://datarmos.up.railway.app/pitch/) · [Relatório do fechamento](https://datarmos.up.railway.app/relatorio/)

Motor de fechamento mensal para o case Barte AI. **Você pode rodar localmente com Python ou enviar os arquivos por HTTP para a API.** Os dois caminhos usam o mesmo motor: recebem os arquivos do mês, aplicam as regras do financeiro e geram seis CSVs principais, relatório HTML e rascunhos de contestação, sem limpeza manual dos arquivos.

O repositório também implementa API autenticada por cliente, fila de exceções, decisões humanas e revisões preservando o original. O site e o pitch são uma apresentação estática do case, sem conexão com a API. Descrição do produto em [docs/product-description.md](docs/product-description.md); inventário, evidências e limites da auditoria em [docs/repository-audit.md](docs/repository-audit.md).

O pedido central é um **motor determinístico com inferência via LLM para reduzir a fricção da análise das exceções que exigem intervenção humana**. Cálculo, proposta e aprovação têm papéis separados. A conferência das entregas e dos critérios oficiais está em [docs/submission-review.md](docs/submission-review.md), com as pendências de comprovação.

**O cálculo é determinístico e roda sem chave de API.** Sem chave, ou com `--no-llm`, nenhuma chamada de IA é feita e as saídas financeiras são iguais. A CLI com chave no ambiente habilita a inferência, salvo `--no-llm`; a API exige `usar_llm=true`, exceto durante a demonstração temporária. A inferência propõe classificação, nunca calcula valores, e registra a execução em `auditoria.jsonl`; ver "Camada de inferência". A IA também foi usada na investigação e no desenvolvimento (ver `PROMPTS/`).

## Usar o motor

| Caminho | O que você precisa | Onde recebe o resultado |
|---|---|---|
| **Local** | Python 3.12+ e o pacote do mês; sem servidor ou chave | Pasta de saída no seu computador |
| **HTTP** | Pacote do mês e chave da API; sem instalar Python | Consulta e download pela API |

### Opção 1 — Rodar localmente

Python 3.12 ou superior (testado em 3.14):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_engine.py --input Tarvo_Data_Pack_set2026 --period 2026-09 --output saida-banca --no-llm
```

Em Linux/macOS, troque `.\.venv\Scripts\python.exe` por `.venv/bin/python`.

Abra `saida-banca/index.html` no navegador. Os CSVs ficam na mesma pasta. Para outro mês, troque `--input`, `--period` e `--output`. O parâmetro `--input` também aceita um `.zip`.

Na auditoria de 17/10, `saida/` estava inacessível neste diretório de trabalho. O comando acima funciona em uma pasta nova; não precisa sobrescrever nem restaurar a entrega. A comparação com os arquivos versionados foi feita em uma cópia isolada do `HEAD`.

### Opção 2 — Enviar por HTTP

API: `https://api-production-0e0e3.up.railway.app`. Use uma chave fornecida pelo operador do serviço. Durante a demonstração temporária, também é possível obter uma chave por `POST /v1/demo/chave`; fora desse período, essa rota responde `410`. Detalhes em [docs/api.md](docs/api.md#modo-demonstração).

Exemplo em PowerShell, na raiz do repositório, com `curl.exe`:

```powershell
# 1. Compacte os arquivos do case e informe sua chave.
Compress-Archive -Path .\Tarvo_Data_Pack_set2026\* -DestinationPath .\tarvo-set2026.zip
$api = 'https://api-production-0e0e3.up.railway.app'
$chave = '<sua-chave-da-api>'

# 2. Envie o ZIP. A resposta contém o ID do fechamento.
$fechamento = curl.exe --fail-with-body --silent --show-error "$api/v1/fechamentos" `
  -H "Authorization: Bearer $chave" `
  -F 'periodo=2026-09' -F 'usar_llm=false' `
  -F 'arquivos=@tarvo-set2026.zip' | ConvertFrom-Json
$id = $fechamento.id

# 3. Consulte o processamento; repita até CONCLUIDO, PROVISORIO ou ERRO.
curl.exe --fail-with-body --silent --show-error "$api/v1/fechamentos/$id" `
  -H "Authorization: Bearer $chave"

# 4. Quando CONCLUIDO ou PROVISORIO, baixe o relatório e um CSV.
curl.exe --fail-with-body --silent --show-error "$api/v1/fechamentos/$id/arquivos/index.html" `
  -H "Authorization: Bearer $chave" -o relatorio-api.html
curl.exe --fail-with-body --silent --show-error "$api/v1/fechamentos/$id/arquivos/comissoes_por_lojista.csv" `
  -H "Authorization: Bearer $chave" -o comissoes-api.csv
```

O envio retorna **HTTP 202** e `NA_FILA`: o resultado ainda está sendo processado. `PROVISORIO` permite baixar as partes calculadas e revisar o que ficou bloqueado; `ERRO` traz o motivo em `erro`. Download antes de concluir responde `409`. Abra `relatorio-api.html` no navegador depois do download.

`usar_llm=false` reproduz o caminho local com `--no-llm`, inclusive durante a demonstração. Para experimentar a inferência opcional, use `usar_llm=true`; ela depende da chave Anthropic no servidor e das classes habilitadas na política. O pacote original de setembro não tem movimento sem regra elegível para o modelo.

Também é possível enviar vários arquivos no mesmo POST, repetindo o campo `arquivos` para cada arquivo, em vez de enviar um ZIP. Em Linux/macOS, use `curl` no lugar de `curl.exe` e adapte as variáveis ao seu shell. A referência completa de endpoints, autenticação e decisões está em [docs/api.md](docs/api.md).

### Opções da execução local

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

**R$ 20.225,93 identificados para revisão:** R$ 15.396,77 de devolução comercial + R$ 1.834,05 de spreads negativos a contestar + R$ 1.576,23 de divergências Orbe + R$ 1.418,88 de divergências Ponte. A soma reúne obrigações de devolução e contestações, sem comprovar pagamento, recuperação ou economia realizada. As 13 pendências têm responsáveis distintos (financeiro, comercial e tesouraria), não são todas decisões exclusivas da Helena. Os 8 dias úteis descritos no case são o prazo manual; tempo de execução do motor não comprova redução desse prazo.

A soma checkout + remessa é R$ 243.278,79; as notas somam R$ 243.284,29 porque o saldo negativo de R$ 5,50 da Casa não gera nota.

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

Só com a camada ligada (`usar_llm=true` na API, ou chave no ambiente sem `--no-llm` na CLI) e só para classes elegíveis fora de `desligado`. Durante `DEMO_ATE`, a API habilita IA por padrão; `usar_llm=false` desliga explicitamente. Por exceção vão a descrição e a linha citada da fonte, com CPF e número de conta mascarados; o `system` leva a política de fechamento e o plano de contas inteiros. Campo a campo, o que é e o que não é mascarado e a retenção: seção LGPD de `docs/api.md`. `LLM_BUDGET_TOKENS` (padrão 200000) limita a execução e, ao estourar, o restante vai para humano (`ORCAMENTO_ESGOTADO`). Estimativas do ADR são históricas; tokens e custos registrados devem ser consultados na auditoria de cada execução. O registro de produção em `docs/testes-producao.md` relata respostas válidas e uma reexecução em cache com 0 tokens; não é uma medição atual de custo por fechamento.

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
- `railway.json` registra a configuração legada da API. A ferramenta de gestão consultada marca Config as Code como deprecated; confira a configuração efetiva do serviço no Railway antes de publicar.

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
| `DEMO_ATE` | vazio | fim do modo demonstração (ISO 8601 com fuso). Até lá: chave por autoatendimento em `POST /v1/demo/chave` e camada de IA ligada por padrão na API; depois, tudo volta ao normal sem deploy. Ver `docs/api.md` |
| `DEMO_CHAVES_POR_IP_HORA` / `DEMO_FECHAMENTOS_IA_POR_IP_HORA` | `5` / `20` | limites por IP no modo demonstração |

## Limitações conhecidas

- Notas, contestações e lançamentos são propostas para revisão: o motor não emite nota, não envia e-mail e não lança no ERP.
- Atlas Idiomas fica sem faturamento até o comercial confirmar a taxa; o motor ainda não fatura num mês as linhas de meses anteriores (fica manual, com valor e linhas na pendência).
- Sem conciliação da Orbe contra o banco parcela por parcela (depende da agenda de recebíveis, fora do pacote).
- O alerta de antecipação só avalia lojistas sem histórico anterior no pacote.
- O bloqueio é por fonte inteira: com `02_` indisponível, a remessa também para, embora a participação de 50% não dependa da planilha (a divergência de spread depende). Erro na regra ou na configuração continua parando o fechamento inteiro, com mensagem.
- A confiança da classificação bancária por regra é um escore, não probabilidade calibrada. Só a das linhas `IA` é medida (Wilson no backtest), e o backtest real ainda não foi rodado: a política não tem `criterio` nem `confianca` preenchidos.
- Camada e API: job preso em `PROCESSANDO` se o processo morrer no meio (não há retomada); não há revogação individual de chave; o rate limit é por processo. Os erros iniciais de schema da Anthropic foram corrigidos: cada chamada leva apenas a variante da classe da exceção, e a versão do resolvedor entra na chave do cache. O histórico e o registro de 78/78 verificações em produção estão em `docs/testes-producao.md`; essa bateria não foi repetida nesta auditoria. Erros são separados entre `ERRO_REDE` (conexão, timeout, 429, 5xx) e `ERRO_API` (demais 4xx), com detalhe na auditoria.
- `railway.json` é configuração legada; a ferramenta de gestão consultada não aceita novas alterações no campo Config as Code. Os campos do serviço podem ser conferidos diretamente no Railway.
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

### Site e pitch

O site é HTML/CSS/JavaScript estático, com o pitch em `site/pitch/index.html`. Ambos apresentam o pacote de setembro; não enviam arquivos nem decisões para a API. A seção “Usar a API” explica envio, consulta e download, e o topo tem atalho para o GitHub. O painel usa Chart.js e fontes de CDNs externas.

O vídeo de 44 segundos fornecido pelo autor está em `site/media/abertura.mp4`. Na abertura, `site/intro.js` tenta reproduzi-lo com som habilitado e mantém “Pular” disponível. Se a política do navegador bloquear autoplay com áudio, exibe “Iniciar com som”, sem silenciar o vídeo. Ao terminar, a logo Datarmos aparece com um raio no laranja da marca (`--ember`, `#ff6a2b`), e o site é liberado automaticamente. O mesmo vídeo está disponível na seção de apresentação. A animação é feita no player, sem alterar o conteúdo do vídeo original; movimento reduzido elimina as transições.

Para atualizar os gráficos a partir de uma execução:

```powershell
.\.venv\Scripts\python.exe site/build_data.py --input saida-banca
.\.venv\Scripts\python.exe -m http.server 8765 --directory site
```

Abra `http://localhost:8765`. `--baseline <execução sem ajustes tardios>` habilita a comparação antes/depois da mesma competência; sem baseline, o gráfico informa a ausência. O gerador deriva os valores das saídas e grava o `run_id` e o hash do motor em `results.js`. O texto do site e do pitch é editorial: ao trocar competência, revise também os números e exemplos nesses HTMLs.

O retrato publicado do case está em `site/relatorio/`, para que o build do site pelo GitHub também sirva o relatório e seus CSVs. Ao trocar o pacote do painel, atualize esse diretório junto de `results.js`. `site/deploy.sh [pasta-do-relatório]` monta um pacote limpo com o relatório informado (padrão: `saida/`). No Railway, o serviço `site` precisa de **Root Directory `/site`**, Dockerfile `Dockerfile`, porta 8080 e healthcheck `/health`: a raiz do repositório contém o Dockerfile da API e não deve ser usada como raiz do site. O serviço foi recuperado e republicado em 17/10; o registro da investigação está em `docs/repository-audit.md`.

### Diretórios

- `run_engine.py`, `src/tarvo_close/`: leitura das fontes, cálculo, validação e publicação; camada de inferência (`inference.py`, `resolver.py`, `validators.py`, `backtest.py`).
- `api/`, `Dockerfile`, `railway.json`: serviço HTTP.
- `site/`: site estático, dados dos gráficos e pitch de 13 slides.
- `config/closing-policy.json`: regras e decisões. `config/inference-policy.json`: modos da camada.
- `Tarvo_Data_Pack_set2026/`: arquivos do case.
- `saida/`: execução entregue de setembro.
- `PROMPTS/`, `HIPOTESES.md`, `docs/`: histórico de IA, premissas e respostas do financeiro.
- `LICENSE`: licença MIT do código.

## Licença

O código do Datarmos Agent for Tarvo (`src/`, `run_engine.py`, `config/`, `tests/`) é MIT, ver `LICENSE`. O data pack `Tarvo_Data_Pack_set2026/`, as saídas derivadas em `saida/` e as transcrições em `docs/` e `PROMPTS/` são material do case Barte AI e não estão cobertos pela licença.
