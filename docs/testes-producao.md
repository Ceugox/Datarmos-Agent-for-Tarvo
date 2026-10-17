# Testes contra a API publicada

A suíte de `tests/` roda sem rede, com cliente falso e Postgres local ou de CI. Ela não pega o que só aparece no serviço publicado: a API da Anthropic recusando o schema, o volume do Railway, o proxy reescrevendo caminhos, o limite de requisições sob carga real. Para isso existe uma bateria que roda contra o serviço no ar, em `scripts/bateria_producao.py`.

## Como rodar

São necessários dois clientes diferentes. A chave de cada um é criada dentro do container, porque o banco só é acessível pela rede interna do Railway, e vai direto para um arquivo, sem aparecer na tela:

```bash
railway ssh --service api -- python -m api.keys criar --cliente teste-a > chave-a.txt
railway ssh --service api -- python -m api.keys criar --cliente teste-b > chave-b.txt
```

Com o checkout no commit publicado, já que a referência de comparação é a CLI rodada nesse checkout:

```bash
pip install -r requirements-api.txt
python scripts/bateria_producao.py --url https://<domínio da API> --chave-a chave-a.txt --chave-b chave-b.txt
```

- O script sai com código 0 quando todas as verificações passam.
- As chaves nunca são impressas. Os arquivos de chave ficam fora do repositório.
- `--sem-camada` pula o bloco 10. Na primeira execução de um cliente, esse bloco chama o modelo para as 4 tarifas, a uns US$ 0,13. Nas execuções seguintes as respostas vêm do cache do cliente e o custo é zero.

Não existe comando para revogar chave. Clientes de teste ficam no banco, e por isso é melhor reaproveitar os mesmos dois.

## O que a bateria verifica

| Bloco | Verificações |
|---|---|
| 1. Infra | `/health` com o banco; nenhum `Access-Control-Allow-Origin`; `X-Content-Type-Options: nosniff` |
| 2. Autenticação | 401 com `WWW-Authenticate: Bearer` sem cabeçalho, com esquema `Basic` e com chave inválida, em todas as rotas; `bearer` minúsculo aceito |
| 3. Upload | 422 para período `2026-9`, `usar_llm=talvez`, arquivo fora do padrão do pacote, nome com `../`, nomes repetidos e corpo JSON; 413 para `Content-Length` de 60 MB, antes de ler o corpo |
| 4. Fechamento sem a camada | Os 9 CSVs e `metrics`, `checks` e `policy` byte a byte iguais à CLI; formato fixo dos CSVs; `run_id` igual; manifest com `execucao` e `camada`; sem `auditoria.jsonl` |
| 5. ZIP | O mesmo pacote em `.zip` dá o mesmo resultado |
| 6. Download | 404 para caminhos com `..`, mandados crus (sem a normalização do cliente HTTP), para nomes fora da lista e para maiúsculas; `Content-Type` certo para HTML, JSON e texto |
| 7. Fila | 13 exceções de setembro sem a camada, por classe, todas `SEM_CAMADA` e `PENDENTE` |
| 8. Decisões | 404 e 422 para id e corpo inválidos. Rejeitar uma `CONDICAO_COMERCIAL` e depois aprovar uma `DECISAO` na mesma linhagem gera as revisões 1 e 2: a 2 mantém a `REJEITADA` da 1, traz a `APROVADA` nova, não muda nenhum valor, aponta o pai no manifest e registra quem decidiu na auditoria. Decidir de novo a mesma exceção não aplica. |
| 9. Isolamento | O cliente B recebe 404 no fechamento, na fila, na auditoria, nos arquivos e nas decisões do cliente A, e vice-versa; B fecha o próprio mês |
| 10. Camada | Setembro com as 4 tarifas com descrição nova (nenhuma regra as reconhece): 4 `MOVIMENTO_SEM_REGRA`, sem erro de API ou de rede; toda proposta validada passou em todas as verificações; em `sombra` nada muda no CSV, e aprovar uma proposta vista em `sombra` não aplica |
| 11. Rate limit | 70 requisições seguidas do mesmo cliente recebem 429 com `Retry-After` |

As chamadas respeitam o `Retry-After`, menos as do bloco 11, que existe justamente para provocar o 429. Sem isso, a bateria esgota o próprio limite de 60 requisições por minuto e compara respostas 429 como se fossem arquivos.

## Resultado em 17/10/2026

Commit publicado `ec812dc`, que é o merge do PR #1, com deploy pelo repositório ligado ao Railway e "Wait for CI" ativo.

| Bloco | Resultado |
|---|---|
| 1. Infra | 3/3 |
| 2. Autenticação | 9/9 |
| 3. Upload | 7/7 |
| 4. Fechamento sem a camada | 17/17 |
| 5. ZIP | 2/2 |
| 6. Download | 10/10 |
| 7. Fila | 4/4 |
| 8. Decisões | 12/12 |
| 9. Isolamento | 7/7 |
| 10. Camada | 6/6: 3 propostas `VALIDADA` com a conta 4.2.01 e 1 encaminhada a humano pelo próprio modelo; respostas do cache, 0 tokens |
| 11. Rate limit | 1/1 |
| **Total** | **78/78** |

## Defeitos que só apareceram em produção

Cada defeito foi encontrado ao rodar o serviço publicado e corrigido com um teste offline que impede a volta.

| O que apareceu | Causa | Correção |
|---|---|---|
| Fila vazia em fechamento sem a camada | A fila era montada só a partir da `auditoria.jsonl`, que não existe sem a camada | A fila sai das exceções do núcleo em todo fechamento; o manifest grava o marcador `camada` |
| API da Anthropic: 400 `For 'anyOf', 'type' is not supported` | O schema da proposta tinha `type` e `anyOf` no mesmo nó, o que o tool strict não aceita | `type` removido da raiz; teste das palavras-chave aceitas pelo strict |
| API da Anthropic: 400 `The compiled grammar is too large` | As 8 variantes de classe num único tool | Cada chamada manda só a variante da classe da exceção |
| Erro de API registrado como erro de rede, sem detalhe | `APIStatusError` estava na lista de erros de rede | `ERRO_API` (4xx) separado de `ERRO_REDE` (conexão, 429, 5xx); a auditoria grava status, mensagem e `request_id` |
| As 4 propostas acertaram a conta, mas foram rejeitadas | A instrução pedia trecho "da linha citada" e o validador exige trecho da descrição | A instrução pede parte da descrição, e o payload leva `descricao_movimento` |
| Uma resposta de tool antigo poderia sair do cache | A política gravada por cliente fixava o `prompt_version` | A versão do resolvedor entra na chave do cache |

## Pontos de atenção

- O `saida/manifest.json` versionado é de antes dos dois últimos commits do resolvedor, por isso o `run_id` dele difere do publicado. Os CSVs não mudam, e o CI ignora `manifest.json` e `index.html` no diff. A bateria compara com a CLI rodada na hora, e não com esse arquivo.
- Os dados enviados à API nos testes são os do pacote de setembro do case. Nenhum dado real de cliente.
