# Auditoria do repositório — 17/10/2026

Escopo: código, configuração, suíte local, reexecução do case e consistência entre README, descrição de produto, site e pitch. Referência inicial: `6a0e4e7`. Esta auditoria não é uma certificação de segurança, novo backtest do modelo ou validação completa da infraestrutura publicada.

## O que temos

| Parte | Implementado | Limite |
|---|---|---|
| Motor local | Pasta/ZIP, CSV/XLSX/EML/OFX, regras versionadas, valores decimais, seis CSVs principais, HTML, cobertura, rastro e hashes | Layouts conhecidos do case; sem integração com bancos, ERP ou emissor fiscal |
| Fontes indisponíveis | Bloqueio por fonte, pendência e fechamento provisório das partes independentes | Falha de regra/configuração interrompe tudo; a dependência é por fonte inteira |
| Inferência | Resolvedor Anthropic, cache, orçamento, evidência validada, tetos por classe e auditoria | Política padrão em sombra para movimento sem regra; backtest real sem critérios preenchidos |
| Revisões | Aprovar/rejeitar/editar gera nova execução, com pai e autoria | Decidir condição comercial não altera os valores calculados nem cria regra |
| Serviço HTTP | FastAPI, autenticação Bearer por cliente, Postgres, políticas versionadas, fila, arquivos, exceções e auditoria | Sem retomada de job interrompido; sem revogação individual de chave; limite por processo |
| Demonstração | Autoatendimento de chave, prazo, limites por IP e modo sugerir para clientes demo | Enquanto ativa, IA é o padrão da API; `usar_llm=false` desliga. Não é uma garantia de disponibilidade permanente |
| Site e pitch | Página estática, gráficos do case, guia HTTP, atalho para o GitHub, vídeo de abertura e 13 slides navegáveis | Sem upload, autenticação ou aprovação conectados à API; áudio automático depende da política do navegador |
| CI | Jobs do motor e da API com Postgres | Código de workflow inspecionado; não houve consulta ao resultado atual do GitHub Actions |

## Evidência financeira reproduzida

Executado com `--no-llm`, a partir dos arquivos do case e das políticas atuais:

| Medida | Resultado |
|---|---|
| Comissão de checkout | R$ 203.735,34 |
| Participação em remessas | R$ 39.543,45 |
| Propostas de nota | 21, total R$ 243.284,29 |
| Divergências | 115; Orbe R$ 1.576,23 e Ponte R$ 1.418,88 |
| Pendências | 13, com responsáveis do financeiro, comercial e tesouraria |
| Movimentos bancários | 184 |
| Cobertura | 2.374 linhas de origem |
| Checagens do fechamento | 5 PASS; 368 saídas na reconciliação monetária |

O `run_id` reproduzido foi `2026-09-0f5dc9b0948c6539`. Outra execução sem o arquivo opcional `06_` reproduziu comissão de R$ 207.039,73 e notas de R$ 246.588,68: a variação é −R$ 3.304,39 em ambos os casos. O núcleo não foi alterado nesta auditoria.

Checkout + remessas somam R$ 243.278,79. As notas somam R$ 5,50 a mais porque a Casa tem saldo negativo de R$ 5,50, que não gera nota; não é falha de soma.

Os R$ 20.225,93 do material de defesa são a soma de devolução comercial (R$ 15.396,77), spreads negativos a contestar (R$ 1.834,05), divergências Orbe (R$ 1.576,23) e divergências Ponte (R$ 1.418,88). Representam valores identificados para revisão, com naturezas distintas, e não economia ou recuperação realizada.

## Divergências corrigidas

| Antes | Alinhamento |
|---|---|
| Descrição dizia somente local, sem autenticação | Inventário de motor, API por cliente, revisões e apresentação estática |
| README não destacava os dois caminhos de uso | Início com execução local e requisições HTTP, incluindo consulta e download |
| “IA em construção” | Inferência implementada, política padrão em sombra e exceção explícita do modo demo |
| Proposta de IA ilustrativa atribuída a um Pix já classificado | Exemplo removido; slide explica a fila real e a ausência de movimentos elegíveis em setembro |
| “Corrigidos” / “economia” | Valores identificados para devolução ou contestação, sujeitos a revisão |
| “Conciliado linha por linha” | Rastro de origem; conciliação Orbe × banco parcela a parcela continua fora do escopo |
| 0,5 s equiparado aos 8 dias úteis | Removida a promessa; processamento não mede o prazo completo do fechamento |
| 46 testes | Removida a contagem obsoleta da apresentação; números atuais ficam nesta evidência datada |
| Gráficos com valores fixos e tempos sem registro verificável | Valores derivados das saídas; baseline explícita; tempos fixos removidos |
| Valor desconhecido convertido em zero no gerador do site | Preservado como `null` |
| Histórico do README dizia que só houve chamada Anthropic rejeitada | Atualizado para o registro de produção já existente, sem tratá-lo como validação nova |
| “Dados reais” | Material do case, sem afirmar origem em clientes reais |

O dashboard continua sendo um retrato editorial de setembro: `results.js` deriva gráficos das saídas e identifica a execução, mas os exemplos e números escritos nos HTMLs exigem revisão ao mudar competência. Sem `--baseline`, o gráfico antes/depois informa comparação indisponível.

## Verificações e limites

- No diretório original, `saida/` está inacessível por permissão e aparece como removida no Git. A primeira suíte descobriu 256 testes: 215 passaram, 37 foram pulados e 4 falharam por depender desses arquivos. A pasta não foi restaurada ou sobrescrita.
- Em uma cópia isolada de `git archive HEAD`, os mesmos 256 testes passaram sem falhas: 219 executados e 37 pulados. Isso reproduz a causa das quatro falhas do diretório original.
- Quatro testes novos protegem o gerador do site: valor desconhecido, origem dos valores, baseline real e rejeição de competência diferente. Eles falham no gerador original. A suíte final na cópia isolada, com as alterações sobrepostas, descobriu 260 testes: 223 executados sem falhas e 37 pulados.
- As 37 verificações de integração com Postgres não foram executadas: `TEST_DATABASE_URL` não está configurado e o acesso local ao daemon Docker foi negado. Não foram substituídas por banco falso.
- Não houve chamada ao modelo nem criação de clientes/chaves/fechamentos no serviço publicado. Os 78/78 em `docs/testes-producao.md` são evidência histórica, não repetida aqui.
- O domínio informado, `https://datarmos.up.railway.app`, respondeu 200 em `/`, `/pitch/`, `/relatorio/` e `/health`. Na consulta, a versão publicada ainda continha a narrativa antiga. O `/health` do site é uma resposta estática do Caddy, não um teste da API.
- A API em `https://api-production-0e0e3.up.railway.app/health` respondeu 200 com `status=ok` e `banco=ok`. Isso verifica disponibilidade naquele instante; não valida upload, revisão, isolamento ou retomada.

Os registros locais ficam em `analysis/engine-runs/audit-2026-10-17/` (ignorado pelo Git): execução atual, baseline, cópia isolada e logs de teste. Alterações anteriores em `PROMPTS/` e a condição de `saida/` foram preservadas. Nenhum commit ou push foi realizado nesta auditoria; os deploys posteriores foram solicitados pelo usuário e estão registrados abaixo.

## Incidente e publicação do site

O usuário informou que o site caiu após a troca de domínio. O deployment `67e12d23-f06d-4ca9-9f91-4e4112d2aafd` estava `CRASHED`: o serviço `site`, ligado à raiz do repositório, construiu o Dockerfile da API e iniciou uvicorn. O log terminou com `RuntimeError: DATABASE_URL não definido`. O site estático não precisa dessa variável; faltava direcionar o build para o site.

Foi reaproveitado o último build estático saudável para restaurar o serviço (`33fd05a8-e322-48cf-80fd-21f37eb24fc8`, `SUCCESS`). A configuração persistida foi conferida: Root Directory `/site`, Dockerfile `Dockerfile`, healthcheck `/health`, timeout 60 segundos e domínio na porta 8080. Uma tentativa de definir `railwayConfigFile` pela ferramenta foi recusada por depreciação; a correção foi aplicada diretamente aos campos do serviço.

O pacote local alinhado, com relatório reproduzido, foi publicado em `6917cf0b-acbc-42f0-a79d-e6ec922d0c2a`, `SUCCESS`. O log mostrou `site/Dockerfile` e Caddy. Página, pitch, relatório, dados e healthcheck responderam 200, e relatório/dashboard identificaram o mesmo `run_id`. O script de deploy também foi ajustado para montar o diretório `/site` e aceitar uma pasta de relatório legível.

O usuário pediu em seguida a explicação de uso da API, o atalho para o repositório e melhor preenchimento dos cards. Essas alterações foram incorporadas à página; a citação principal passou de um card esticado pela coluna vizinha para um bloco compacto e centralizado, com autoria próxima. Métricas e cards de texto também foram equilibrados. O pitch mantém 13 slides.

A publicação desse conjunto foi `e0c24fd4-88b6-4c73-b6ab-f96d0c1080ce`, confirmada como `SUCCESS`. Página com seção de API e atalho GitHub, pitch, relatório, dados e healthcheck responderam 200. A referência pública `/docs` da API também respondeu 200. A seleção de momentos foi ajustada para quatro conforme o enunciado e esta conversa foi exportada para `PROMPTS/`. A conferência completa dos critérios, pesos, formato dos CSVs e entregas está em `docs/submission-review.md`.

O usuário forneceu depois um MP4 de 44 segundos (H.264 + AAC) e definiu abertura automática com som e opção de pular. O arquivo foi preparado para streaming com faststart, sem recodificar áudio ou imagem. A abertura tenta autoplay audível; se bloqueado, oferece início por clique. Ao fim, a logo Datarmos e um raio laranja aparecem no player antes de liberar o site, mantendo a opção de pular. O vídeo original não recebeu a animação incorporada ao MP4; o encerramento é composição da página. A reprodução completa local terminou com `muted=false`, `volume=1`, animação exibida e diálogo fechado automaticamente. Pular interrompe o áudio. Layout mobile e movimento reduzido foram verificados em navegador emulado; não houve teste em aparelho físico.

O autor autorizou em seguida o push do conjunto revisado. O commit desta sessão inclui somente os arquivos desse trabalho; a alteração preexistente em `PROMPTS/sessao-cowork-2026-10-17.md` e as remoções aparentes de `saida/` ficam fora. Na limpeza solicitada, o inventário do Git continha apenas três HTMLs, todos usados: `site/index.html`, `site/pitch/index.html` e `saida/index.html`. Nenhum deles foi removido, e as prévias ignoradas ficaram fora do commit.

Para que o próximo build automático pelo GitHub preserve `/relatorio/`, o retrato reproduzido do case também foi incluído em `site/relatorio/`. Seu HTML é usado pela página pública e seus CSVs são downloads da entrega; não é uma prévia descartada. Assim o deploy pelo repositório e o upload manual têm os mesmos arquivos públicos, sem depender da pasta local `saida/` inacessível.

### Verificação pré-deploy do pacote estático

Foi aplicada a skill `pre-deploy-security`, limitada ao serviço estático: o scanner retornou `0 finding(s)` em `site/` e no pacote isolado publicado. É uma revisão de código e configuração, não um pentest ou uma certificação da API.

| Item da checklist | Resultado | Evidência / motivo |
|---|---|---|
| 1. Segredos no bundle | PASS | Scanner com zero achados; `site/config.js` contém apenas vídeo e URL pública do repositório |
| 2. Histórico Git sem segredos | Não verificado | O scanner do pacote não certifica todo o histórico |
| 3. Chave administrativa no cliente | N/A | Site não tem cliente de banco ou credencial administrativa |
| 4. RLS | N/A | O serviço estático não acessa banco |
| 5. Campos sensíveis | N/A | Publica material do case, sem cadastro ou armazenamento de chaves de usuário |
| 6. Autorização | N/A | Arquivos de apresentação públicos; API é um serviço separado |
| 7. Testes de isolamento | N/A | Não há contas ou registros privados no site; testes da API exigem Postgres |
| 8. Mass assignment | N/A | Nenhum endpoint de escrita no site |
| 9. Cookies e sessão | N/A | Site não autentica nem guarda token em localStorage |
| 10. Senhas | N/A | Site não recebe senhas |
| 11. Limite de rotas custosas | N/A | Site serve arquivos; exemplos HTTP são texto e não enviam chamadas pelo navegador |
| 12. CSRF | N/A | Nenhuma mutação autenticada por cookie |
| 13. SQL | N/A | Nenhuma consulta SQL no site |
| 14. Validação de entrada | N/A | Sem formulário ou endpoint de entrada; ZIP é enviado diretamente à API |
| 15. Conteúdo renderizado | PASS | `site/app.js` restringe ID YouTube a 11 caracteres permitidos e usa conteúdo fixo no HTML gerado |
| 16. Upload | N/A | Não há upload pelo site |
| 17. Erros internos | N/A | Site estático não executa lógica de aplicação |
| 18. Cabeçalhos de segurança | FAIL parcial | `site/Caddyfile` define nosniff e Referrer-Policy, mas não CSP, frame-ancestors ou HSTS. Endurecimento desses cabeçalhos permanece pendente |
| 19. Transporte HTTPS | PASS no caminho conferido | As páginas foram consultadas com HTTPS; a política completa de redirecionamento na borda não foi auditada |
| 20. Dependências | Não verificado | Caddy e dependências CDN não passaram por varredura de vulnerabilidades nesta sessão |

## Pendências técnicas

1. Restabelecer acesso a `saida/` para comparar a entrega diretamente nesse diretório. O script de deploy pode receber outra execução legível por argumento.
2. Executar a suíte com Postgres e conferir CI para o commit que for publicado.
3. Medir a precisão do resolvedor com backtest real antes de qualquer promoção; o pacote original de setembro não possui movimento sem regra elegível.
4. Tratar retomada de jobs e revogação individual de chave antes de ampliar o uso operacional; limites em memória não se somam corretamente entre instâncias.
5. Conciliação parcela a parcela, faturamento de pendências de meses anteriores e aviso automático de condições comerciais continuam fora da entrega atual. Propostas de ampliação exigem descoberta e aceite próprios.
