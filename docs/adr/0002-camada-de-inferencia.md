# 0002 — Camada de inferência (LLM) sobre o motor determinístico, exposta como API

Status: proposta em 2026-10-17, aguardando aprovação. Complementa o ADR 0001 sem revogá-lo: o núcleo continua determinístico, local e sem rede; o que muda é que ele passa a ter uma camada opcional por cima e um serviço HTTP fino em volta.

## Contexto

Hoje toda exceção do fechamento vira linha de `pendencias.csv` para uma pessoa. Parte delas não pede decisão: falta um dado do mês seguinte, uma evidência ou só o mapeamento de uma descrição nova. A Helena quer receber só o que é decisão. Também precisamos que clientes enviem o pacote do mês, acompanhem o fechamento, baixem as saídas e decidam as exceções sem rodar a CLI.

Fatos levantados no repositório antes desta decisão:

- Setembro não tem nenhum movimento bancário sem regra: os 184 movimentos casam com `bank_rules`. A classe da Fase 3 não tem caso real; o backtest depende de casos perturbados.
- Não há pasta de evidências (e-mail, Slack exportado) no pacote. Só o `.eml` da Ponte. `docs/slack-financeiro.md` é transcrição do case, não fonte do mês.
- "Layout mudou" e "cadastro" não aparecem nas pendências de setembro; os três ECs foram resolvidos em `ec_overrides`.
- As pendências que esperam dado (R$ 300 mil em trânsito, TED da Ponte) dependem do extrato de outubro, que não está no repositório.
- O plano de contas tem `TIPO`, `NATUREZA` (D/C) e `ACEITA_LANCTO`; `lancamentos_classificados.csv` já tem `metodo`, `confianca`, `regra_id` e `status`.

## Decisão

### Princípios (do pedido, não reabrir)

1. O LLM não calcula valor, arredondamento, comissão, total ou nota.
2. O LLM não decide política. Taxa e condição comercial são do comercial; regra de fechamento, cobrar a Orbe e contestar a Ponte são da Helena.
3. Toda proposta cita evidência verificável e passa por validador determinístico. Sem evidência verificável, rejeitada.
4. Só chave rígida confirma casamento (CNPJ, EC, nº de operação, FITID, valor exato). Semelhança de nome nunca basta.
5. Sem chave ou com `--no-llm`, `saida/` fica byte a byte igual (fora `manifest.json`/`run_id`), com teste.
6. Respostas do LLM em cache por hash de (prompt, modelo, entrada); reexecução com cache dá a mesma saída.
7. O formato dos CSVs não muda. Linha resolvida pela camada sai com `metodo=IA` e `confianca` medida no backtest.
8. A CLI roda do zero, sem serviço HTTP e sem chave.

### Arquitetura

```
fontes ─► núcleo determinístico ─► exceções tipadas ─► fila
                                                         │
               ┌─────────────────────────────────────────┤
               ▼                                         ▼
     regra determinística                     resolvedor (interface)
     (classes "espera dado")          FakeResolver (testes/CI) │ AnthropicResolver
                                                         │
                                                proposta JSON (schema)
                                                         ▼
                                          validador determinístico da classe
                                                         ▼
                              política de promoção (desligado│sombra│sugerir│automatico)
                                                         ▼
                         aplica (automatico, ou decisão humana aprovada) ─► nova revisão
                                                         ▼
                                                  log de auditoria
```

- **Exceção tipada** (`src/tarvo_close/exceptions.py`): `id` estável (mesmo hash do `id_saida` da pendência), `classe`, `tipo` (o `tipo` atual da pendência, sem mudar), `escopo`, `refs` (arquivo + `ref_origem` + linha), `falta` (o que resolve) e `quem_decide`. O núcleo emite a exceção junto com a pendência; `pendencias.csv` continua sendo gerado a partir dela, com o mesmo conteúdo.
- **Classes** (mapeamento dos 25 `tipo` atuais; a tabela vive em `exceptions.py` e um `tipo` sem classe para o fechamento):

  | Classe | `tipo` atuais | Modo inicial |
  |---|---|---|
  | `LAYOUT_FONTE` | `FONTE_BLOQUEADA` (arquivo ilegível ou layout não reconhecido) | `desligado` nesta entrega |
  | `CADASTRO` | `TAXA_NAO_RESOLVIDA`, `CADASTRO_REMESSA_AUSENTE`, `CADASTRO_OU_CONTRATO_AUSENTE`, `CONTRATO_AMBIGUO`, `TOMADOR_NAO_IDENTIFICADO` | `desligado` nesta entrega |
  | `MOVIMENTO_SEM_REGRA` | `CONCILIACAO_BANCARIA` | `sombra` |
  | `ESPERA_DADO` | `TRANSFERENCIA_EM_TRANSITO` | `desligado` nesta entrega |
  | `ESPERA_EVIDENCIA` | `REPASSE_DEVOLVIDO`, `CREDITO_NAO_IDENTIFICADO` | `desligado` nesta entrega |
  | `CONDICAO_COMERCIAL` | `DEVOLUCAO_CONDICAO_COMERCIAL`, `LOJISTA_NAO_FATURAR` | `sugerir`, teto `sugerir` |
  | `DECISAO` | `DIVERGENCIA_A_CONTESTAR_*`, `SPREAD_NEGATIVO_CONTESTAR`, `OPERACAO_REPETIDA_CONTESTAR`, `SALDO_NAO_POSITIVO_SEM_NOTA`, `ALERTA_ANTECIPACAO`, `REVERSAO_SEM_ANTECIPACAO`, `REVERSAO_IRREGULAR`, `DECISAO_DO_FINANCEIRO` | `sugerir`, teto `sugerir` |
  | `DADO_INVALIDO` | `FONTE_BLOQUEADA` (ausente/duplicada), `CONFLITO_DE_VERSAO`, `DATA_AUSENTE`, `STATUS_DESCONHECIDO`, `BASE_REMESSA_INVALIDA` | `desligado`, teto `desligado` |

  `DECISAO_DO_FINANCEIRO` vem de `open_questions` da política e pode ser qualquer pergunta em aberto; por isso fica em `DECISAO`, mesmo quando é a conferência do TED da Ponte (que é espera de dado). Quando a pergunta trouxer a classe na política, ela pode migrar.

  `CONDICAO_COMERCIAL` e `DECISAO` têm teto `sugerir` gravado na política e conferido em código: nem editando o JSON elas chegam a `automatico`. Nesta entrega elas são só tipadas; o pré-preenchimento de resumo e rascunho fica para depois da Fase 4.

- **Contrato da proposta** (JSON Schema em `config/proposal.schema.json`, com `strict: true` no tool use):

  ```json
  {"excecao_id": "PEN-...", "classe": "MOVIMENTO_SEM_REGRA", "acao": "CLASSIFICAR_CONTA",
   "parametros": {"conta_codigo": "4.2.01"},
   "evidencias": [{"arquivo": "05a_extrato_...csv", "ref": "L37", "trecho": "TAR PACOTE SERVICOS"}],
   "justificativa": "...", "requer_humano": false}
  ```

  Ajustes ao contrato mínimo: `acao` é enum fechado por classe; `parametros` tem schema por `acao`, sem nenhum campo monetário (princípio 1, imposto pelo schema e não só pelo prompt); `trecho` tem que ser substring literal da linha citada, e o validador confere isso relendo a fonte. Não existe campo de confiança autodeclarada.

- **Validador de `MOVIMENTO_SEM_REGRA`** (só aprova se tudo passar):
  1. a evidência cita o `ref_origem` da própria exceção e o `trecho` existe literalmente na descrição;
  2. a conta existe, é `ANALITICA` e `ACEITA_LANCTO = S`;
  3. o par (sinal do movimento, grupo de 1º nível da conta) já aparece em alguma `bank_rule` aplicada no backtest. Par novo vai para humano;
  4. conta de provisão de folha ou tributos (`2.1.03.*`, `2.1.04.*`) vai para humano: baixar provisão exige obrigação conhecida, e o pacote não traz a lista de obrigações;
  5. conta de disponibilidade própria (`1.1.01.*`) e transferência entre contas (`1.1.09.001`) vão para humano: o casamento exige a contrapartida por valor exato e data, e isso é regra do núcleo, não do LLM.
- **Política de promoção** (`config/inference-policy.json`): por classe, `modo`, `teto`, `criterio` (casos, erros, versão do backtest, data) e `aprovado_por`. Promoção exige **35 casos seguidos sem erro** no backtest da classe; `automatico` exige ainda aprovação da Helena registrada com nome e data. `confianca` = limite inferior de Wilson (95%) da precisão da classe no backtest, gravada na política e copiada para a linha.
- **Efeito por modo** em `MOVIMENTO_SEM_REGRA`:
  - `sombra`: a proposta e o resultado do validador vão só para a auditoria; CSVs iguais ao `--no-llm`.
  - `sugerir`: igual na saída até haver decisão. Aprovada, a linha sai com `metodo=IA`, a conta, `confianca` da política e `status=SUGERIDO`, e a pendência vira `RESOLVIDA`.
  - `automatico`: proposta validada aplica sem humano, com o mesmo formato.
- **Decisões e revisões**: uma decisão (`aprovar` / `rejeitar` / `editar`, com `decidido_por` e `motivo`) nunca reescreve uma execução. Ela gera uma revisão nova (`rev-N`) com `run_id` próprio e o `run_id` pai no manifest. A CLI recebe decisões por `--decisoes decisoes.json`; a API grava a decisão e enfileira a revisão pelo mesmo caminho. `editar` em `MOVIMENTO_SEM_REGRA` troca a conta e passa pelo mesmo validador.
- **Aprovar não cria regra.** A decisão vale para aquele movimento. O resolvedor pode rascunhar uma `bank_rule` no log, mas ela só entra na `closing-policy.json` por mudança explícita e versionada.
- **Resolvedor Anthropic** (`src/tarvo_close/resolver.py`): interface `Resolver.propose(excecao, contexto) -> Proposta | Falha`. A implementação usa o SDK oficial `anthropic` (versão fixada), modelo `ANTHROPIC_MODEL` (padrão `claude-opus-5-5`) com `effort` explícito, tool use com `strict: true` e `tool_choice: auto` (o modelo recusa uso forçado), `max_tokens` fixo, timeout e retry com backoff do SDK, e fallback de recusa do lado do servidor. O contexto fixo (política, plano de contas, regras de `HIPOTESES.md` relevantes) vai no `system` com `cache_control`. Por exceção vai só a linha citada e os campos necessários. Os tokens de entrada, saída e cache são somados por exceção e por execução contra `LLM_BUDGET_TOKENS`; ao estourar, as exceções restantes caem para humano com motivo `ORCAMENTO_ESGOTADO`. Resposta fora do schema, recusa ou erro de rede vira humano, nunca zero ou chute.
- **Cache de respostas**: chave `sha256(versão do prompt, modelo, entrada canônica da exceção)`. Na CLI fica em `.cache/llm/`; na API, numa tabela do Postgres. Com cache, a reexecução não chama a rede e produz a mesma saída.
- **Auditoria**: proposta, evidência, resultado de cada verificação do validador, modo, decisão e quem decidiu, tokens e custo em US$ (preço por modelo numa tabela do código, com data). Na CLI vai para `auditoria.jsonl` ao lado das saídas; o arquivo fica fora da comparação byte a byte (como o `manifest.json`), e o CI confere que `--no-llm` não o gera.

### Serviço HTTP (Fase 4)

FastAPI + uvicorn em `0.0.0.0:$PORT`, chamando as mesmas funções da CLI, sem regra própria. Postgres para clientes (hash da chave), políticas versionadas por cliente, fechamentos, jobs, exceções, decisões, auditoria e cache do LLM. Arquivos em `DATA_DIR`. Um worker no mesmo processo consome a tabela de jobs com `SELECT ... FOR UPDATE SKIP LOCKED`, de modo que separar um serviço worker depois seja só subir outro processo com o mesmo código. As migrações rodam no start e são idempotentes. Cada cliente tem a própria `closing-policy` e `inference-policy`; a Tarvo entra como seed. Endpoints, autenticação, limites e LGPD como no pedido, detalhados em `docs/api.md`.

## Alternativas descartadas

- **LLM no lugar das regras de classificação**: perde a reprodutibilidade e o rastro, e põe o LLM decidindo política (princípio 2).
- **LLM gerando valores ou fórmulas**: viola o princípio 1. O schema da proposta não tem campo monetário.
- **Casamento por similaridade de nome ou embeddings**: viola o princípio 4.
- **Confiança autodeclarada pelo modelo**: não é medida e não é comparável entre execuções.
- **Aprovação humana virar `bank_rule` automaticamente**: o LLM passaria a escrever política por tabela.
- **Reescrever a execução no lugar ao decidir**: quebra a regra do ADR 0001 de não sobrescrever um fechamento e perde o histórico do que a Helena viu.
- **Fila externa (Redis, SQS) já na primeira versão**: mais um serviço sem necessidade no volume atual; a tabela de jobs no Postgres já deixa a separação pronta.
- **Política única para todos os clientes**: a `closing-policy` é da Tarvo; o isolamento por cliente é critério de aceite.

## Riscos

| Risco | Mitigação |
|---|---|
| Dados financeiros de terceiros enviados à Anthropic (LGPD) | Por padrão `usar_llm=false`. Saem só descrição, valor, data, banco e plano de contas; CPF e número de conta mascarados antes do envio; CNPJ só em exceção de cadastro. `docs/api.md` lista campo a campo o que sai. Contratar Zero Data Retention é decisão contratual da Tarvo; o ADR registra, não decide. |
| Proposta plausível e errada | Validador determinístico, teto por classe e modo `sombra` até 35 casos sem erro. |
| Backtest sem caso real (setembro não tem movimento sem regra) | Casos perturbados a partir dos 184 movimentos (descrição alterada, regra removida da policy), com gabarito = a conta da regra original. A precisão medida vale para esse tipo de perturbação, não para descrições de fornecedor nunca vistas; por isso a classe começa em `sombra`. |
| Custo ou latência fora de controle | `LLM_BUDGET_TOKENS` por execução, `max_tokens` por chamada, cache de prompt e de resposta, worker em segundo plano. |
| Prompt injection via descrição bancária ou evidência | Conteúdo das fontes vai como dado, delimitado, nunca no `system`; a proposta só tem efeito pelo validador; nenhum tool de escrita é exposto ao modelo. |
| Saída mudar sem ninguém perceber | Teste de `--no-llm` idêntico e o diff de `saida/` no CI (já existe) continuam sendo o portão. |
| Divergência entre CLI e API | A API chama as mesmas funções; um teste roda o mesmo pacote pelos dois caminhos e compara os bytes. |

### Custo por fechamento (estimativa, preços de 2026-10)

`claude-opus-5-5`: US$ 4 por milhão de tokens de entrada, US$ 20 de saída, US$ 0,20 de leitura de cache e US$ 5 de escrita de cache (1,25×).

Por exceção: cerca de 8 mil tokens de contexto fixo em cache, 1,5 mil de contexto da exceção e 1,5 mil de saída (com raciocínio, `effort=medium`). Isso dá ≈ US$ 0,0016 + 0,006 + 0,03 ≈ **US$ 0,04 por exceção**, mais uma escrita de cache de ≈ US$ 0,04 por execução.

- Setembro (13 pendências; só a classe ligada vai ao LLM): **< US$ 0,10**.
- Mês ruim, com 50 exceções elegíveis: **≈ US$ 2**.
- Teto: o orçamento padrão de 200 mil tokens limita a execução a ≈ US$ 2–4 no pior caso.

Reexecução com cache custa zero. Os números reais saem da auditoria e substituem esta estimativa depois do primeiro uso.

## Premissas (o que estou assumindo)

1. As regras de `HIPOTESES.md` valem como estão; nenhuma regra de negócio nova é criada aqui.
2. Os itens 3 a 5 do validador de `MOVIMENTO_SEM_REGRA` são restrições conservadoras derivadas dos dados de setembro, não regras novas: sempre que não dá para provar, o caso vai para humano.
3. Os modos iniciais das classes não ligadas nesta entrega ficam em `desligado`, até haver backtest (outubro para `ESPERA_DADO`, evidências reais para `ESPERA_EVIDENCIA`).
4. `ESPERA_DADO` futuro: o fechamento de outubro lê as exceções abertas do mês anterior (`--anterior` na CLI, fechamento vinculado na API) e resolve por regra determinística, sem reabrir setembro.
5. `ESPERA_EVIDENCIA` futuro: pasta opcional `evidencias/` no pacote, com `.eml`, `.txt` e JSON de export do Slack.
6. Limites padrão: `MAX_UPLOAD_MB=50`, 60 requisições por minuto por cliente, `LLM_BUDGET_TOKENS=200000`.
7. CI: o job atual do motor continua sem rede e sem chave; um job novo `api` sobe Postgres em service container. As versões do CI seguem o `Dockerfile` (Python 3.12 lido de `.python-version`).

## Plano em fases

Cada fase termina com os testes rodando, `saida/` regenerada e o diff dos arquivos de saída mostrado. Um commit por fase na branch `feat/camada-inferencia`, avisado antes, sem push.

1. **Exceções tipadas.** `exceptions.py` com `Classe` e `Excecao`; o `ClosingResult.pending` passa a registrar a exceção e gera a pendência a partir dela. Teste: todo `tipo` emitido tem classe; os testes atuais passam; `diff -r saida` vazio.
2. **Infraestrutura da camada.** Fila, `config/proposal.schema.json`, `validators.py` (base e registro por classe), cache por hash, `audit.py`, `config/inference-policy.json` com teto conferido em código, interface `Resolver` com `FakeResolver` e `AnthropicResolver` (SDK fixado em `requirements.txt`; testes sem rede). CLI ganha `--no-llm`, `--decisoes` e `--cache-dir`. Teste: teto de `DECISAO` e `CONDICAO_COMERCIAL` não sobe nem editando o JSON; resposta fora do schema vira humano; orçamento estourado vira humano.
3. **`MOVIMENTO_SEM_REGRA` de ponta a ponta.** Validador da classe; aplicação por modo; revisão por decisão; backtest em `tests/backtest/` com setembro perturbado (descrições alteradas e regras removidas, gabarito = conta original), medindo precisão e cobertura e gravando o critério na política. Testes: validador (cada verificação com caso que passa e que falha), `--no-llm` byte a byte, cache reproduzível, `metodo=IA` só com evidência no rastro.
4. **Serviço HTTP** (só com a Fase 3 verde). `api/` (FastAPI), migrações, worker, autenticação por hash, isolamento por cliente, limite de upload e de requisições, comando para criar a chave, `Dockerfile`, `railway.json`, `.env.example`, `docs/api.md`, job `api` no CI. Testes: rota sem chave → 401; cliente A não vê fechamento de B; download fora da lista recusado; decisão aparece na auditoria e muda a pendência; mesma saída pela CLI e pela API sem LLM.
5. **Documentação.** `README.md` (CLI, camada, serviço, deploy, variáveis, limitações) e `HIPOTESES.md` (premissas acima) atualizados. Sem deploy e sem criar recursos no Railway.
