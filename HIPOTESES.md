# Hipóteses, decisões e respostas do financeiro

As regras de negócio vieram das respostas da Helena (financeiro da Tarvo) no canal `#duvidas-hackathon-ai` em 16 e 17/10/2026. As perguntas foram feitas por todos os times participantes; as respostas valem para todos. O motor lê essas regras de `config/closing-policy.json`, onde cada uma registra quem aprovou e quando.

## Regras confirmadas pelo financeiro

| Tema | Regra aplicada | Fonte |
|---|---|---|
| Base do checkout | Comissão = valor bruto × taxa contratada da planilha, linha a linha. O `valor_taxa` da Orbe é o que ela cobrou; não entra na comissão. Sem desconto de custo da Orbe. | 16/10 20h05; 22h34 |
| Arredondamento | Arredondamento comum ao centavo, meio centavo para cima, simétrico no negativo (−0,005 → −0,01). Linha a linha, depois soma. Remessa: por operação (R$ 131,005 → R$ 131,01). | 16/10 21h13 |
| Estornos | Abatem a comissão do mês do estorno, pela taxa vigente na data da venda original, inclusive vendas de agosto. Agosto não é reaberto. | 16/10 20h06 |
| Antecipação | Bruto × taxa de antecipação contratada, na mesma nota do lojista. A reversão anula só a taxa da antecipação que reverte. | 16/10 20h47 |
| Divergência de checkout | Taxa aplicada diferente da contratada. Valor = bruto × (aplicada − contratada). Centavo de truncamento da Orbe não é divergência. Venda e estorno se anulam: cobra-se da Orbe só a diferença líquida. A cobrança é decidida caso a caso pela Helena. | 16/10 20h05, 21h13; 17/10 9h44 |
| Rota Global | Não houve mudança de contrato: as taxas +0,50 p.p. a partir de 12/09 são divergência. | 16/10 20h49 |
| Casa do Estudante | Tarifa zerada no checkout de setembro a dezembro (MDR e antecipação), por acordo do comercial. A Orbe não foi avisada e cobrou pela planilha: o valor é devolução ao lojista, separado das divergências de contrato, sem cobrança à Orbe. Estorno de venda anterior (TX88445133, venda de 21/08) usa a taxa de agosto. | 16/10 20h49; 17/10 9h44 |
| ECs sem cadastro | 1043300981 = Novo Horizonte Intercambio; 1043396662 = Horizonte Viagens; 1038867654 = Kiwi Experience. CNPJ e taxas nas linhas da aba vigente. | 16/10 20h24 |
| Atlas Idiomas | Sem contrato assinado. Não faturar até o comercial confirmar. Quando confirmar, a taxa vale desde 10/09 e o fechamento seguinte puxa as linhas de setembro. | 16/10 20h24; 17/10 9h47 |
| Antecipação acima das vendas | Não deveria acontecer e não há trava. Registrar alerta para financeiro e comercial. | 17/10 9h44 |
| Notas de checkout | Uma por lojista por mês. Saldo zero ou negativo não emite; o negativo não passa ao mês seguinte automaticamente e vira pendência da Helena. Sem texto padrão: serviço e competência. | 16/10 20h47 |
| Comissão de remessa | 50% do "Spread R$" realizado, como no e-mail da Ponte. | 16/10 20h48 |
| Nota de remessa | Uma nota, tomadora Ponte Câmbio, pelo total da participação do mês. O excesso da Mundo Aberto entra pelo realizado; se a Ponte devolver, a participação é ajustada no mês do ajuste. | 16/10 20h47, 21h45 |
| Competência da remessa | Data de contratação. | 16/10 20h48 |
| Spread padrão | Célula em branco ou "padrão" = 1,5% sobre a PTAX de referência. | 16/10 20h48 |
| Divergência de remessa | Lojista pagou spread diferente do contratado. Valor cheio, não a metade da Tarvo. A Mundo Aberto negociou 1,20% em julho. | 16/10 20h48, 20h58; 17/10 9h44 |
| Spread negativo | Não aceito: a trava vale 2 horas e venceu. Fora da comissão e da nota; pendência de contestação, de natureza diferente da divergência. | 16/10 20h48; 17/10 9h44 |
| Operação repetida | O número da operação é único: conta uma vez e entra na lista para a Ponte corrigir o relatório. | 16/10 20h48, 22h34 |
| "Aprovado c/ ressalva" | Não muda nada para a Tarvo. | 16/10 20h48 |
| Contestação | Nada foi contestado; prazo considerado aberto. Pendência com valor e operações, mais um rascunho de e-mail por contraparte com as operações anexas, para a Helena revisar e enviar. Não presumir desconto no repasse; conferir o TED quando cair. | 16/10 22h33, 22h34; 17/10 9h53 |
| Plano de contas | `conta_codigo` é a contrapartida do movimento bancário. Folha, ISS, INSS, FGTS e DARFs de agosto estavam provisionados (baixam o passivo); todo mês a folha e os impostos ficam provisionados. O repasse da Ponte de 04/09 baixa a comissão a receber. Tarifas, aluguel, cloud, assinaturas e serviços entram na despesa do mês. | 16/10 20h49, 21h14; 17/10 9h48 |
| Orbe no banco | A Orbe deposita tudo no Aurora; débito e Pix em D+1, crédito por parcelas. O saldo negativo é a conta garantida. Classificar os créditos da Orbe sem conciliar parcela por parcela. | 16/10 22h34 |
| PIX de R$ 18.240 (Meridiano) | Ponte Aérea Estudantil (lojista) adiantando uma remessa que sai em outubro: recurso de lojista para remessa. | 17/10 9h44 |
| Transferência de R$ 300.000 | Saiu do Aurora em 30/09 e cai no Meridiano em 01/10. | 16/10 20h49 |
| Quem aprova | Taxa e condição comercial: comercial aprova, financeiro registra. Regra de fechamento: Helena. | 17/10 9h49 |
| Granularidade das pendências | Uma pendência por contraparte e por lojista, com o detalhe das transações anexado (é o que vira o rascunho de contestação). | 17/10 11h01 |
| Cadastro e contrato | Quem decide é o comercial. A Bia mantém a planilha de taxas, mas não decide taxa. | 17/10 11h01 |
| Parcelamento acima de 12x | A Tarvo não vende acima de 12x; se aparecer, é pendência. Não ocorreu em setembro. | 17/10 11h01 |
| Repasse à Atlas | O repasse não para: o dinheiro é do lojista. Fica suspenso só o faturamento da taxa da Tarvo. | 17/10 11h03 |
| Repasse antes da liquidação | Pela regra, o repasse é do que a Orbe já liquidou. Na prática, quando um lojista pressiona, a Bia às vezes paga antes, usando a conta garantida, sem regra escrita e sem limite. | 17/10 10h59 |

## Decisões do time, onde o financeiro deixou a escolha conosco

| Tema | Decisão | Motivo |
|---|---|---|
| Tolerância de remessa | Divergência só acima de 0,01 p.p. entre spread aplicado e contratado. | Os demais lojistas oscilam ±0,002 p.p. por arredondamento da cotação; a Mundo Aberto fica 0,30 p.p. acima. A Helena pediu critério escrito que evite alarme de centavo sem deixar passar diferença real (16/10 20h58). |
| Spread aplicado | Calculado como `Spread R$ / (valor ME × PTAX de referência)`, sem usar a coluna percentual arredondada. Diferença = `Spread R$ − valor ME × PTAX × contratado`. | Evita erro de centavo introduzido pelo arredondamento da coluna percentual. Total da Mundo Aberto: R$ 1.418,88 (a fórmula com o percentual arredondado dá R$ 1.418,85). A Helena deixou a escolha com o time: "São três centavos. Escolham um critério e escrevam qual" (17/10 11h01). |
| Spreads negativos na lista de divergências | Não entram em `divergencias_taxa`; ficam em `pendencias` e na contestação da Ponte. | Pela definição da Helena, o lojista não pagou a mais; listá-los misturaria naturezas. |
| Devolução da Casa do Estudante | Valor = `valor_taxa` cobrado pela Orbe durante a isenção (R$ 15.396,77), em pendência separada. Alternativa descartada, registrada no motivo da pendência: bruto × taxa aplicada com o arredondamento do fechamento (comum) = R$ 15.397,42 (+R$ 0,65, truncamento da Orbe em 67 de 118 lançamentos). | A Helena separou o caso das divergências ("É diferente de uma divergência comum [...] é devolução ao lojista", 17/10) e fixou a base: "O que foi cobrado eu devolvo ao lojista" (16/10 20h49). O "a gente não trunca" e a fórmula bruto × (aplicada − contratada) (16/10 21h13) são do cálculo da comissão e da divergência; numa devolução, o arredondado devolveria R$ 0,65 a mais do que o lojista pagou. Sobre onde listar: a proposta da Fox AI foi a pendência com o total mais as 118 linhas marcadas em `divergencias_taxa`, e a Helena respondeu "Do jeito que vocês propuseram serve: uma pendência com o total e o detalhe por transação marcado. Só não pode entrar na cobrança da Orbe" (17/10 10h58); antes, tinha pedido "Deixem separado das divergências de contrato, com o valor" (17/10). Decisão do time: o total fica na pendência e o detalhe por transação, marcado com a fórmula, no `rastro.csv` da mesma pendência; as linhas não são repetidas em `divergencias_taxa`, para não somar 118 lançamentos de outra natureza à lista de divergências de contrato. |
| Devolução de PIX da Mundo Aberto (R$ 12.400) | Conta 2.1.01.001 (repasses a lojistas a pagar), com pendência do motivo. | O repasse volta a ser devido; é a mesma conta do pagamento original. A Helena aceitou as duas contas, desde que o critério seja mantido (17/10 9h48). |
| PIX sem identificação (R$ 7.350) | Conta 1.1.09.002 (créditos não identificados), com pendência. | "Não é receita até alguém identificar." |
| Transferência de R$ 300.000 | Conta 1.1.09.001 (transferências entre contas próprias), pendência para conferir o crédito no extrato de outubro. | Está em trânsito no fechamento. |
| Alerta de antecipação | Só para lojista sem atividade anterior no pacote (primeiro movimento depois do dia 1º e nenhum estorno de mês anterior). A cada antecipação, compara as antecipações em aberto naquela data com as vendas acumuladas até ela; a reversão só conta a partir da data dela. O alerta mostra o momento de maior diferença: valor e operações são as antecipações em aberto nesse momento, e o motivo cita as reversões posteriores. Em setembro: Atlas, R$ 179.592,82 em aberto em 15/09 (AN88445637, AN88445646, AN88445703, AN88445766) contra R$ 55.357,50 em vendas; a AN88445637 foi revertida em 17/09. | Sem a agenda de recebíveis, para lojistas antigos não se sabe o que já foi vendido antes do mês. Sobre as reversões, a Helena deixou o critério com o time (resposta ao Datarmos, 17/10): a antecipação foi feita acima do vendido, e a reversão posterior não apaga que o risco existiu, então ela entra pelo que estava em aberto na data. A versão anterior somava as antecipações que dispararam o alerta em datas diferentes (R$ 183.581,24, incluindo a AN88446517, revertida em 26/09), o que não correspondia a nenhum saldo real e não batia com o texto. O alerta não muda nenhum número do fechamento. |
| CNPJ de remessa fora da planilha | Participação calculada mesmo assim, pendência de cadastro para o comercial; spread padrão na comparação. | Proposta aceita como premissa (17/10 9h45). Não ocorreu em setembro. |

## Limitações conhecidas

- Atlas: as 57 linhas de setembro (R$ 262.138,61 brutos) estão em pendência. O motor fatura só lançamentos com data de movimento no período; faturar em outubro as linhas de setembro exige uma evolução (ler a pendência anterior ou aceitar um período de vigência retroativo). Hoje isso fica manual, com o valor e as linhas na pendência.
- Linhas repetidas de remessa são listadas para correção mesmo quando a operação sai da comissão por outro motivo (competência ou spread negativo).
- A provisão de folha e impostos de setembro fica fora do fechamento: é feita pela contabilidade com a Helena, com a folha e as guias, que não estão no pacote (resposta ao Datarmos, 17/10). O motor classifica só o que passou nos extratos.
- A conciliação da Orbe contra o banco parcela por parcela não foi feita, a pedido do financeiro: depende da agenda de recebíveis.
- Notas, contestações e lançamentos são entregues para revisão. O motor não emite nota, não envia e-mail e não lança no ERP.
- Confiança da classificação bancária é um escore de regra, não uma probabilidade calibrada.

## Perguntas feitas ao financeiro e respostas recebidas

As perguntas foram feitas no canal compartilhado por vários times; as respostas da Helena valem para todos e foram as usadas aqui. Transcrição completa em `docs/slack-financeiro.md`.

| # | Pergunta | Resposta da Helena |
|---|---|---|
| 1 | Comissão de checkout: `valor_taxa` da Orbe ou bruto × taxa contratada? | Taxa contratada, linha a linha; a diferença é divergência, decidida caso a caso. |
| 2 | Estorno abate a comissão? E venda de agosto estornada em setembro? | Abate, no mês do estorno, pela taxa da data da venda original. Agosto não reabre. |
| 3 | Quais CNPJs e taxas dos 4 ECs sem cadastro? Atlas é cliente ativa? | Três correspondem às linhas sem EC; Atlas sem contrato: não faturar até o comercial confirmar. |
| 4 | Regra das notas: uma por lojista? Antecipação? Saldo negativo? Tomador da remessa? | Uma por lojista; antecipação na mesma nota, reversão anula; negativo não emite e vira pendência; remessa: uma nota para a Ponte. |
| 5 | Remessa: 50% do realizado ou do contratado? Negativo, repetida, ressalva, competência? | Realizado; negativo não aceito (contestar); número de operação é único; ressalva não muda nada; vale a contratação; padrão 1,5%. |
| 6 | Rota Global +0,50 p.p.: reajuste ou divergência? Casa do Estudante tem condição especial? Competência de folha/impostos? Créditos sem origem? | Rota: divergência. Casa: tarifa zerada set–dez, devolver o cobrado. Folha e tributos de agosto provisionados. R$ 7.350 desconhecido; R$ 12.400 repasse devolvido; R$ 300 mil cai no Meridiano em 01/10. |
| 7 | Divergência de remessa: valor cheio ou metade? Tolerância? | Valor cheio; tolerância é critério do time, escrito com motivo. |
| 8 | Arredondamento e fórmula da divergência? | Arredondamento comum, linha a linha; divergência = bruto × (aplicada − contratada); remessa por operação. |
| 9 | Plano de contas: contrapartida ou natureza? | Contrapartida; o que estava provisionado baixa a provisão. |
| 10 | O excesso da Mundo Aberto entra na nota de setembro? | Entra pelo realizado; ajuste no mês em que a Ponte devolver. |
| 11 | Prazo de contestação venceu? Duplicata precisa ser contestada? | Nada contestado, prazo aberto; manter pendência com valor e operações; duplicata conta uma vez e vai na lista. |
| 12 | Fluxo de liquidação da Orbe e saldo negativo do Aurora? | Tudo no Aurora; crédito por parcelas; saldo negativo é conta garantida; não conciliar parcela a parcela agora. |
| 13 | Spreads negativos entram na lista de divergências? | Divergência é quando o lojista pagou diferente; negativo é pendência de contestação, outra natureza. |
| 14 | Casa: cobrança durante a isenção, estorno pré-isenção, PIX de R$ 18.240, antecipação da Atlas, Orbe abaixo do contrato? | Devolução ao lojista, separada; taxa de agosto no estorno; adiantamento de remessa de outubro; alerta ao financeiro e comercial; também divergência, caso a caso. |
| 15 | Atlas confirmada: setembro é faturado depois? | Sim, taxa vale desde 10/09; outubro puxa as linhas de setembro. |
| 16 | Quem avisa Orbe/Ponte de condição nova? Rascunho de contestação serve? | Ninguém tem essa função; Bridge avisada com atraso, Casa e Mundo Aberto não. Rascunho por contraparte serve. |
| 17 | Quem aprova regra fixa? | Taxa: comercial; regra de fechamento: Helena. |
| 18 | Repasses incluem valores ainda não liquidados pela Orbe? | Pela regra, não; na prática a Bia às vezes antecipa com a conta garantida, sem regra escrita nem limite. |
| 19 | Casa do Estudante: só pendência ou também em divergências, marcada? | "Do jeito que vocês propuseram serve: uma pendência com o total e o detalhe por transação marcado. Só não pode entrar na cobrança da Orbe." |
| 20 | Pendência por transação ou por lojista? Quem decide cadastro? Mais de 12x? 1.418,85 ou 1.418,88? | Por contraparte e lojista, com detalhe anexo; cadastro é do comercial; acima de 12x é pendência; três centavos, escolher e escrever o critério. |
| 21 | Repasse à Atlas continua sem faturamento? | Continua; só o faturamento da taxa fica suspenso. |

## Perguntas enviadas pelo time Datarmos

As perguntas da tabela acima vieram de vários times; as três abaixo foram enviadas pelo Datarmos no canal em 17/10/2026. Saíram da revisão do fechamento contra o que já estava respondido no canal. Texto da mensagem, como enviado:

> [financeiro] [Datarmos]: três perguntas para fechar setembro.
>
> 1. Casa do Estudante: lista de divergências
> Na resposta para a Fox AI (17/10 10h58), a senhora aceitou as 118 transações também em divergencias_taxa.csv, marcadas como "isenção não informada à Orbe" e fora da cobrança da Orbe. Antes, tinha pedido para deixar separado das divergências de contrato. Hoje deixamos o total (R$ 15.396,77) só na pendência, com o detalhe por transação no rastro. A senhora precisa das 118 linhas em divergencias_taxa.csv, ou basta a pendência com o detalhe anexado?
>
> 2. Provisão de folha e impostos de setembro
> A senhora disse que todo mês a folha e os impostos do mês ficam provisionados no fechamento. O pacote só traz os pagamentos de agosto feitos em setembro, sem os valores de folha e impostos de setembro. O fechamento precisa gerar o lançamento de provisão de setembro? Se precisar, de onde vêm os valores? Ou isso fica com a senhora fora do fechamento automático?
>
> 3. Alerta de antecipação da Atlas: reversões contam?
> A Atlas antecipou R$ 179.592,82 até 15/09, com R$ 55.357,50 em vendas até essa data. Duas antecipações foram revertidas depois: AN88445637 (15/09, revertida em 17/09) e AN88446517 (24/09, revertida em 26/09). Para o alerta "antecipação acima das vendas", consideramos o que foi antecipado, mesmo que revertido depois, ou só o que ficou valendo depois das reversões?

| # | Tema | Por que perguntamos | Resposta da Helena |
|---|---|---|---|
| D1 | Casa do Estudante em `divergencias_taxa` | A aceitação da proposta da Fox AI (17/10 10h58) e o pedido anterior de separar das divergências de contrato apontam para lados diferentes; o arquivo é corrigido contra gabarito. | "Basta a pendência com o total e o detalhe por transação. Se quiserem pôr as linhas também em divergências, marcadas como isenção, tudo bem, mas não precisa. O que importa é ficar separado das divergências de contrato e fora da cobrança da Orbe." Mantido como está: total na pendência, detalhe no `rastro.csv`, fora de `divergencias_taxa`. |
| D2 | Provisão de folha e impostos de setembro | A regra diz que todo mês a folha e os impostos ficam provisionados, mas o pacote não traz os valores de setembro e o motor só classifica movimentos bancários. | "Fica fora do fechamento de vocês. A provisão de setembro quem faz é a contabilidade, comigo, com a folha e as guias, e isso não está no pacote. O fechamento de vocês classifica o que passou nos extratos." Registrado em Limitações conhecidas. |
| D3 | Reversões no alerta de antecipação da Atlas | Duas antecipações da Atlas foram revertidas; o critério define o valor, o texto e as operações do alerta. | "Esse critério é de vocês. O alerta é para mim e para o comercial e não muda nenhum número. Registrem a escolha no `HIPOTESES.md`." Critério escolhido em Decisões do time (Alerta de antecipação). |
