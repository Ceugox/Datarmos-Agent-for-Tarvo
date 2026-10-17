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

## Decisões do time, onde o financeiro deixou a escolha conosco

| Tema | Decisão | Motivo |
|---|---|---|
| Tolerância de remessa | Divergência só acima de 0,01 p.p. entre spread aplicado e contratado. | Os demais lojistas oscilam ±0,002 p.p. por arredondamento da cotação; a Mundo Aberto fica 0,30 p.p. acima. A Helena pediu critério escrito que evite alarme de centavo sem deixar passar diferença real (16/10 20h58). |
| Spread aplicado | Calculado como `Spread R$ / (valor ME × PTAX de referência)`, sem usar a coluna percentual arredondada. Diferença = `Spread R$ − valor ME × PTAX × contratado`. | Evita erro de centavo introduzido pelo arredondamento da coluna percentual. Total da Mundo Aberto: R$ 1.418,88 (a fórmula com o percentual arredondado dá R$ 1.418,85). |
| Spreads negativos na lista de divergências | Não entram em `divergencias_taxa`; ficam em `pendencias` e na contestação da Ponte. | Pela definição da Helena, o lojista não pagou a mais; listá-los misturaria naturezas. |
| Devolução da Casa do Estudante | Valor = `valor_taxa` cobrado pela Orbe durante a isenção (R$ 15.396,77), em pendência separada. | "O que foi cobrado eu devolvo ao lojista." |
| Devolução de PIX da Mundo Aberto (R$ 12.400) | Conta 2.1.01.001 (repasses a lojistas a pagar), com pendência do motivo. | O repasse volta a ser devido; é a mesma conta do pagamento original. A Helena aceitou as duas contas, desde que o critério seja mantido (17/10 9h48). |
| PIX sem identificação (R$ 7.350) | Conta 1.1.09.002 (créditos não identificados), com pendência. | "Não é receita até alguém identificar." |
| Transferência de R$ 300.000 | Conta 1.1.09.001 (transferências entre contas próprias), pendência para conferir o crédito no extrato de outubro. | Está em trânsito no fechamento. |
| Alerta de antecipação | Só para lojista sem atividade anterior no pacote (primeiro movimento depois do dia 1º e nenhum estorno de mês anterior) cuja antecipação acumulada supere as vendas acumuladas. | Sem a agenda de recebíveis, para lojistas antigos não se sabe o que já foi vendido antes do mês. Em setembro só a Atlas dispara. |
| CNPJ de remessa fora da planilha | Participação calculada mesmo assim, pendência de cadastro para o comercial; spread padrão na comparação. | Proposta aceita como premissa (17/10 9h45). Não ocorreu em setembro. |

## Limitações conhecidas

- Atlas: as 57 linhas de setembro (R$ 262.138,61 brutos) estão em pendência. O motor ainda não lê automaticamente pendências do mês anterior; em outubro, a taxa confirmada deve ser registrada no contrato e as linhas de setembro fornecidas junto.
- A conciliação da Orbe contra o banco parcela por parcela não foi feita, a pedido do financeiro: depende da agenda de recebíveis.
- Notas, contestações e lançamentos são entregues para revisão. O motor não emite nota, não envia e-mail e não lança no ERP.
- Confiança da classificação bancária é um escore de regra, não uma probabilidade calibrada.

## Perguntas e respostas no Slack

A transcrição das perguntas relevantes e das respostas da Helena, como lidas no canal em 17/10/2026, está em `docs/slack-financeiro.md`.
