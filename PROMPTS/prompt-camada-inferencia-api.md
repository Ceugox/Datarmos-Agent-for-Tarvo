# Tarefa: camada de inferência (LLM) sobre o motor determinístico de fechamento da Tarvo, exposta como API no Railway

> Prompt montado na sessão Cowork de 17/10/2026 (`sessao-cowork-2026-10-17.md`) para a próxima etapa do motor. Ainda não executado.

## Contexto
Este repositório (`src/tarvo_close/`) fecha o mês da Tarvo de forma determinística: lê o data pack
(`Tarvo_Data_Pack_set2026/`), aplica as regras do financeiro (`config/closing-policy.json`) e gera os CSVs
de `saida/` com rastro até a linha de origem. Antes de propor qualquer coisa, leia `README.md`,
`HIPOTESES.md`, `docs/adr/`, `config/closing-policy.json`, `src/tarvo_close/closing.py`, `readers.py`,
`domain.py` e `tests/test_closing.py`.

Hoje toda exceção vira pendência para uma pessoa. Muitas delas têm solução sem decisão humana: falta só
um dado do mês seguinte ou uma evidência que está em e-mail, Slack ou na própria fonte. O objetivo é uma
camada que resolva essas exceções e deixe para a Helena (financeiro) e para o comercial só o que é
decisão de verdade. Depois, expor o motor como API no Railway para que clientes enviem o pacote do mês,
acompanhem o fechamento, baixem as saídas e decidam as exceções.

## Princípios invioláveis
1. O LLM nunca calcula valor monetário, arredondamento, comissão, total ou nota. Todo número continua
   saindo do núcleo determinístico.
2. O LLM nunca decide política: taxa e condição comercial são do comercial; regra de fechamento, cobrar a
   Orbe e contestar a Ponte são da Helena. Para essas, o LLM só prepara a decisão.
3. Toda proposta do LLM cita a evidência (arquivo + ref_origem/linha, ou mensagem) e passa por um
   validador determinístico antes de ser aplicada. Proposta sem evidência verificável é rejeitada.
4. Nada de casamento aproximado aceito por semelhança de nome: só aceitar se uma chave rígida confirmar
   (CNPJ, EC, nº de operação, FITID, valor exato).
5. Sem chave de API, ou com `--no-llm`, o motor roda como hoje e os arquivos de `saida/` ficam
   byte a byte iguais (fora `manifest.json`/`run_id`). Isso precisa de teste.
6. Reprodutibilidade: as respostas do LLM ficam em cache por hash de (prompt, modelo, entrada). Rodar de
   novo com o cache dá a mesma saída.
7. O formato obrigatório dos CSVs não muda. Linha resolvida pela camada sai com `metodo=IA` e
   `confianca` medida no backtest, nunca autodeclarada pelo modelo.
8. A CLI continua rodando do zero, sem o serviço HTTP e sem chave.

## Arquitetura alvo
- **Núcleo determinístico** (existente): calcula e emite exceções tipadas em vez de só pendências de texto.
- **Fila de exceções**: cada exceção tem classe, escopo, refs de origem e o que falta para resolver.
- **Resolvedor (LLM)**: recebe uma exceção e ferramentas de leitura (fontes do mês, mês anterior, pasta
  de evidências com e-mails e Slack exportados, a política) e devolve uma proposta estruturada (JSON
  validado por schema).
- **Validadores determinísticos**, um por classe: somas, chaves, sinal e tipo de conta, vigência,
  restrições da política.
- **Política de promoção** (em `config/inference-policy.json`): para cada classe, `modo` = `desligado` |
  `sombra` | `sugerir` | `automatico`, com o critério que a levou até ali. Só `automatico` aplica sem humano.
- **Log de auditoria**: proposta, evidência, resultado do validador, modo, quem aprovou, tokens e custo.
- **Serviço HTTP**: camada fina sobre o mesmo núcleo usado pela CLI; não duplica regra de negócio.

Contrato mínimo da proposta (ajuste se precisar e justifique):
```json
{"excecao_id": "...", "classe": "...", "acao": "...", "parametros": {},
 "evidencias": [{"arquivo": "...", "ref": "...", "trecho": "..."}],
 "justificativa": "...", "requer_humano": false}
```

## Resolvedor: Anthropic
- SDK oficial `anthropic` (Python), versão fixada em `requirements.txt`.
- Modelo via `ANTHROPIC_MODEL` (padrão `claude-opus-5-5`), chave via `ANTHROPIC_API_KEY`, nunca no
  repositório.
- Tool use com schema JSON para a proposta; resposta fora do schema é rejeitada e vira humano.
- Timeout e retry com backoff; `max_tokens` definido; orçamento de tokens por execução
  (`LLM_BUDGET_TOKENS`). Ao estourar, as exceções restantes caem para humano.
- Prompt caching para o contexto fixo (política, plano de contas, regras de `HIPOTESES.md`).
- Para o modelo vai só o contexto da exceção (linhas citadas, campos necessários), nunca o arquivo inteiro.
- Registrar tokens de entrada/saída e custo por exceção e por execução.
- Nos testes e no CI, o cliente é substituído por um falso: sem chave e sem rede.

## Classes de exceção (partir das pendências reais de setembro em `saida/pendencias.csv`)
| Classe | Exemplo real | Quem resolve | Modo inicial |
|---|---|---|---|
| Layout de fonte mudou | Colunas da Ponte renomeadas | LLM mapeia; validador confere o rodapé "Total de operações"/"Spread total R$" e a cobertura | sugerir |
| Cadastro/entidade | EC sem cadastro, nome truncado | LLM propõe; validador exige CNPJ/EC | sugerir |
| Movimento bancário sem regra | Descrição nova de fornecedor/tarifa | LLM classifica pelo critério da contrapartida; validador confere sinal, tipo de conta e obrigação conhecida | sombra |
| Pendência que espera dado | Transferência de R$ 300 mil, TED da Ponte | Regra determinística sobre o mês seguinte (sem LLM) | automatico |
| Pendência que espera evidência | Devolução de R$ 12.400, PIX de R$ 7.350 | LLM busca evidência; aplica só se ela citar a operação/valor | sugerir |
| Condição comercial nova | Isenção da Casa, Bridge 15/09, Mundo Aberto 1,20% | LLM extrai e propõe entrada na política + rascunho de aviso à Orbe/Ponte; comercial aprova | sugerir (nunca automatico) |
| Decisão | Cobrar a Orbe, devolver à Casa, taxa da Atlas, spread negativo | Humano; LLM pré-preenche resumo da causa e rascunho | sugerir (nunca automatico) |

## Avaliação
- Gabarito = setembro, com as regras confirmadas pela Helena em `HIPOTESES.md`.
- Para cada classe, montar casos a partir de setembro (inclusive casos perturbados: descrição bancária
  alterada, coluna renomeada, nome truncado), com a resposta esperada.
- Medir precisão e cobertura por classe. Promover de modo só com N casos sem erro, registrando o critério
  na política de promoção.

## Serviço HTTP

### Stack
- FastAPI + uvicorn, ouvindo em `0.0.0.0:$PORT`.
- Postgres (`DATABASE_URL`): execuções, jobs, fila de exceções, decisões, log de auditoria, cache das
  respostas do LLM, chaves de API dos clientes (só o hash).
- Arquivos enviados e saídas em `DATA_DIR` (volume em `/data` no Railway). O disco do container é
  efêmero: nada importante fora de `DATA_DIR` ou do Postgres.
- O fechamento roda em segundo plano (pode levar minutos com o LLM): a requisição devolve um `id` na
  hora. Comece com um worker no mesmo processo lendo uma tabela de jobs no Postgres; deixe a interface
  pronta para separar um serviço worker depois.
- Migrações do banco rodam no start, de forma idempotente.

### Endpoints
| Método e rota | Faz |
|---|---|
| `GET /health` | Saúde do serviço (sem autenticação; usado pelo healthcheck) |
| `POST /v1/fechamentos` | Recebe `periodo` + arquivos do data pack (multipart ou .zip) e `usar_llm` (bool). Valida nomes, tipos e tamanho antes de aceitar. Devolve `id` e `status=NA_FILA` |
| `GET /v1/fechamentos/{id}` | Status, `metrics.json`, `checks.json`, contagem de exceções por classe e modo |
| `GET /v1/fechamentos/{id}/arquivos/{nome}` | Baixa um CSV de `saida/` (lista fechada de nomes, sem caminho livre) |
| `GET /v1/fechamentos/{id}/excecoes` | Fila de exceções, com proposta do LLM, evidência e resultado do validador |
| `POST /v1/excecoes/{id}/decisao` | `aprovar` / `rejeitar` / `editar` com `decidido_por` e motivo. Grava na auditoria e reprocessa o que depender da decisão. Classes de decisão e condição comercial só fecham por aqui |
| `GET /v1/fechamentos/{id}/auditoria` | Log completo: propostas, validações, decisões, tokens e custo |

### Segurança e dados
- Autenticação por `Authorization: Bearer <chave>`, uma chave por cliente, guardada como hash. Toda
  consulta filtra pelo cliente da chave. Comando para criar a primeira chave.
- Documentar em `docs/api.md` quais dados saem para a Anthropic, porque são dados financeiros de
  terceiros (LGPD).
- Limite de tamanho de upload (`MAX_UPLOAD_MB`) e de requisições por cliente. Sem CORS aberto.
- Logs sem conteúdo de transação nem chave.

## Deploy no Railway
- `Dockerfile` (Python 3.12 slim, dependências fixadas em `requirements.txt`) e `railway.json` com
  healthcheck em `/health` e política de restart.
- Serviços no projeto: a API, um Postgres e um Volume montado em `/data`.
- Variáveis: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL=claude-opus-5-5`, `DATABASE_URL`,
  `LLM_BUDGET_TOKENS`, `MAX_UPLOAD_MB`, `DATA_DIR=/data`. Tudo listado em `.env.example`, sem valores.
- `README.md`: como rodar o serviço localmente (Docker), como subir no Railway (CLI `railway`), como
  criar a primeira chave de cliente.
- Não faça o deploy nem crie recursos na conta: entregue tudo pronto para o time rodar.

## Como trabalhar
1. Primeiro, sem escrever código: escreva `docs/adr/0002-camada-de-inferencia.md` (decisão, alternativas,
   riscos, incluindo custo por fechamento e envio de dados à Anthropic) e um plano em fases. Liste o que
   você está assumindo. Se uma regra de negócio não estiver em `HIPOTESES.md`, pergunte; não invente.
2. Fase 1: tipar as exceções no núcleo, sem mudar nenhum número de saída. Testes atuais continuam passando.
3. Fase 2: fila, contrato da proposta, validadores, cache, log de auditoria, política de promoção e o
   resolvedor Anthropic atrás de uma interface.
4. Fase 3: uma classe ponta a ponta — movimento bancário sem regra — com testes do validador, teste de
   `--no-llm` idêntico e backtest em setembro com descrições perturbadas.
5. Fase 4 (só com a Fase 3 verde): serviço HTTP, Postgres, worker, autenticação, Dockerfile e
   `railway.json`.
6. Ao fim de cada fase: rodar os testes, regenerar `saida/` e mostrar o diff dos arquivos de saída.

## Entregáveis
- `docs/adr/0002-camada-de-inferencia.md`
- Código novo em `src/tarvo_close/` (por exemplo `exceptions.py`, `resolver.py`, `validators.py`)
- `config/inference-policy.json` (modos por classe)
- `api/` (serviço HTTP), `Dockerfile`, `railway.json`, `.env.example`
- `docs/api.md` (endpoints, autenticação, dados enviados ao LLM, exemplos com curl)
- Testes novos em `tests/`
- `README.md` atualizado (CLI, camada de inferência, serviço, deploy, variáveis, limitações)
- `HIPOTESES.md` atualizado com as premissas novas

## Critérios de aceite
- Sem LLM, a saída é idêntica à atual, pela CLI e pela API.
- Nenhum valor monetário vem do LLM.
- Toda linha `metodo=IA` tem evidência no rastro e passou pelo validador.
- Classes de decisão e de condição comercial nunca aplicam sozinhas.
- Nenhuma rota responde sem autenticação, exceto `/health`; um cliente nunca acessa execuções de outro.
- Download recusa nomes fora da lista.
- Decisão humana gravada aparece na auditoria e altera a pendência correspondente.
- CI roda sem chave e sem rede; todos os testes passam.
