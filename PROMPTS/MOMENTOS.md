# Momentos da preparação e construção

Resumo dos momentos da conversa com a IA (Claude Code e Orca). Não substitui o histórico integral exportado do aplicativo.

1. **Investigar antes de construir.** A IA leu o enunciado, extraiu o anexo do e-mail e separou volume, taxas, comissão e caixa, deixando as regras financeiras como perguntas.
2. **Corrigir um critério que criaria falsos alarmes.** A comparação inicial produzia diferenças de um centavo; a conferência das vendas mostrou que a Orbe trunca. Depois o financeiro confirmou: a Orbe trunca, a Tarvo arredonda, e centavo de truncamento não é divergência.
3. **Primeiro motor com premissas explícitas.** Sem acesso ao Slack na primeira sessão, o motor saiu com status provisório e cada premissa registrada, sem inventar respostas.
4. **Fazer o teste revelar uma omissão.** O teste de estornos históricos achou oito das nove vendas originais ausentes; a checagem foi corrigida antes da resolução de cadastro.
5. **Ler o canal do cliente.** Na segunda sessão (17/10), o conector Slack só via outro workspace. A IA leu o canal pelo app do Slack aberto, via Orca computer use, buscando as respostas do financeiro e abrindo cada thread.
6. **Trocar premissas por regras.** As respostas mudaram a base da comissão (taxa contratada em vez de taxa cobrada), a competência da remessa (contratação), o tratamento de spreads negativos, a isenção da Casa do Estudante e o cadastro de três ECs. A política passou à versão 2, com evidência por regra, e os testes foram reescritos para os números novos.
7. **Conferir contra o que o canal já validou.** A participação de remessa (R$ 39.543,45) e o total de spreads negativos (R$ 1.834,05) bateram com os valores discutidos no canal.
