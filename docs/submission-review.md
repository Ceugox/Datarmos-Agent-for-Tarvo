# Critérios de correção e entregas — conferência de 17/10/2026

Referência: `01_instrucoes_participantes.docx.pdf`, a cópia local das instruções (7 páginas). O documento original foi lido integralmente e preservado. Esta revisão relaciona o enunciado às evidências; não substitui o gabarito nem atribui nota à solução.

## Critérios de avaliação

| Dimensão | Peso | Evidência e ressalva |
|---|---|---|
| Causa raiz | 15% | Pitch, slides 2–3: regras tácitas, fontes heterogêneas e falha de comunicação de condições comerciais; não se resume a automatizar Excel |
| Hipóteses | 10% | `HIPOTESES.md`, política versionada e limitações do README distinguem regra respondida de premissa e pendência |
| Perguntar antes de construir | 10% | `docs/slack-financeiro.md` e evidências da política registram perguntas e respostas; decisões financeiras não são delegadas ao modelo |
| Raciocínio e comunicação | 10% | Pitch de 13 slides e site explicam causa, resultados, rastro, intervenção humana, limites e próximos passos; README separa uso local de HTTP |
| Uso de IA | 20% | Histórico em `PROMPTS/` e quatro momentos selecionados mostram direção, verificação e correção pelo autor, inclusive o erro de overfit relatado por ele |
| Correção dos números | 25% | Case reexecutado, seis CSVs com colunas obrigatórias, formato fixo e cinco checagens PASS; 368 saídas monetárias reconciliadas e 2.374 linhas cobertas. O gabarito privado da organização não está disponível, portanto não há alegação de correção oficial |
| Tempo e pontualidade | 10% | Exige comprovantes de presença, checkpoints e envio no thread da equipe. Não é demonstrado por benchmark do motor ou status do Railway; não foi conferido no Slack nesta sessão |

As instruções não pontuam capricho visual, elegância de código, ferramenta escolhida ou quantidade de funcionalidades. O visual ajuda a comunicação; API e inferência são meios para a operação, não pontos extras garantidos.

## Entregas obrigatórias

| Exigência | Evidência | Situação |
|---|---|---|
| Repositório público no GitHub | `https://github.com/Ceugox/Datarmos-Agent-for-Tarvo`, consultado sem autenticação | Público; a referência remota consultada foi `ec812dc`. Alterações locais posteriores não são automaticamente publicadas por deploy do site |
| README: instalar, rodar, chaves e limitações | `README.md`, com site destacado, exemplos local e HTTP, autenticação e limites | Atualizado nesta revisão; consultar a versão do commit que contém esta conferência |
| HIPOTESES na raiz | `HIPOTESES.md`, com perguntas e respostas detalhadas também em `docs/slack-financeiro.md` | Presente no GitHub e no checkout |
| Histórico de todas as sessões | Sessões existentes e exportação desta conversa em `PROMPTS/` | Exportação incluída nesta revisão; verificar que não exista outra sessão usada pelo autor fora das exportações disponíveis |
| MOMENTOS com 2–4 momentos, incluindo um erro da IA | `PROMPTS/MOMENTOS.md` revisado para quatro momentos | Pedido principal e erro de overfit registrados conforme relato do autor; seleção anterior preservada separadamente |
| Seis CSVs em `saida/` | Arquivos existem no GitHub; execução nova em `analysis/engine-runs/audit-2026-10-17/closing/` e relatório publicado | Conferidos na execução nova e na cópia isolada; `saida/` original está inacessível neste ambiente, sem ter sido sobrescrita |
| Código, fluxos e configurações | `src/`, `api/`, `config/` e documentação | Motor real, executável; site e pitch não são apresentados como substitutos do motor |
| Link do repositório no thread da equipe | Canal `#hackathon-entregas` | Não verificado; esta sessão não enviou mensagens ao Slack |
| Pitch em PDF, slides ou vídeo | `https://datarmos.up.railway.app/pitch/`, 13 slides HTML navegáveis | Publicado e acessível; vídeo não é obrigatório quando os slides são a entrega. O vídeo fornecido depois pelo autor foi adicionado à abertura do site e à seção de apresentação |
| Link do pitch no thread da equipe | Canal `#hackathon-entregas` | Não verificado |

O enunciado fixa repositório até **18h30 de 17/10** e pitch até **19h**, e informa que commits posteriores a 18h30 não são considerados. Consultar timestamps de commit, publicação e thread; não confundir uma atualização posterior do site com cumprimento retroativo do prazo. A apresentação dos finalistas é de 15 minutos mais 5 de perguntas, às 19h30.

## Contrato das saídas

As colunas obrigatórias das páginas 4–5 foram conferidas por nome nos seis arquivos gerados. Colunas extras são permitidas. O verificador `tests/output_format.py` validou `;`, decimal com ponto, datas ISO e CNPJ textual com 14 dígitos. Valores desconhecidos ficam vazios, nunca zero fabricado.

- `comissoes_por_lojista.csv`: comissão por lojista e linha de negócio, com IDs e CNPJ.
- `divergencias_taxa.csv`: contrato versus taxa aplicada, referência e diferença em reais.
- `notas_a_emitir.csv`: tomador, linha, valor e discriminação; são propostas, não notas já emitidas.
- `lancamentos_classificados.csv`: os dois bancos, referência original, data, descrição, valor, conta, método e confiança.
- `pendencias.csv`: tipo, referência, valor quando conhecido, motivo e responsável.
- `rastro.csv`: saída vinculada a arquivo, referência e valor; soma reconciliada por saída.

O nível **mínimo** e o **alvo** têm evidências implementadas. No **extra**, há rastro e pendências explicadas, além de testes de perturbação e de competência seguinte simulada. Isso não comprova fechamento de um pacote real de outubro nem suporte a qualquer layout futuro. Cadastro não usa aproximação por nome. O teste com resolvedor falso valida o medidor, não a precisão do LLM real.

## Cobertura exigida no pitch

| Pergunta do enunciado | Onde está |
|---|---|
| O que quebra na operação e por quê | Slides 2–3 |
| O que a solução faz para o financeiro | Slides 1 e 4 |
| Quanto dinheiro está em jogo | Slides 3–6; valores identificados não são economia realizada |
| Como a analista usa em outubro | Slide 13, README e seção “Usar a API” do site: pacote da competência, execução, relatório e revisão |
| Onde a IA atua, onde não e por quê | Slides 8, 10–11; inferência opcional, núcleo determinístico e decisão humana |
| Onde falha e o que acontece | Slide 11; fonte bloqueada, provisório e fila de pendências |
| O que faria com mais um mês | Slide 12; propostas para validação, sem prometer funcionalidades já entregues |

O pedido central do autor é um **motor determinístico com camada de inferência via LLM para reduzir a fricção da análise das exceções que exigem intervenção humana**. Cálculo financeiro reproduzível, evidência verificável e autoria da decisão são partes distintas da solução. O modo sombra padrão não muda os CSVs; o modo demo em sugerir exige aprovação para aplicar uma proposta de classificação.

## O que ainda precisa de confirmação

1. Conferir o commit publicado e seu horário no GitHub; o autor autorizou o push desta revisão, mas a aceitação depende do prazo aplicável da organização.
2. Comprovantes de envio dos links e checkpoints no thread da equipe; nenhuma mensagem foi enviada por esta sessão.
3. Resultado do gabarito e da avaliação oficial, que não podem ser deduzidos dos testes internos.
4. Suíte de integração com Postgres e backtest real da inferência, explicitamente separados da validação local já concluída.
