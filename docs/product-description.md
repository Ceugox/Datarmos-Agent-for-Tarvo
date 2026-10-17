# Motor de fechamento Tarvo

O problema é fechar o mês a partir de fontes incompatíveis e regras tácitas, sem perder o vínculo entre saída e origem. A analista roda o fechamento, a Helena (financeiro) decide as exceções e revisa notas e contestações.

A entrega é um comando local que lê os arquivos do mês (pasta ou ZIP), aplica as regras do financeiro e gera os seis CSVs, um HTML de revisão e rascunhos de contestação por contraparte. O próximo mês usa arquivos no mesmo formato, sem contagens de setembro no código.

Entradas: CSV, XLSX, EML com anexo e OFX. Saídas locais. Não há integração online com Slack, bancos, ERP ou emissor fiscal, nem autenticação ou uso multiusuário.

Critérios de aceite: cobertura de todas as linhas de origem, somas em decimal, rastro que recompõe cada valor, cadastro sem aproximação de nomes, regras versionadas com evidência e pendências com motivo e responsável. Versões conflitantes não são escolhidas pela ordem de chegada; falhas de leitura não viram zero.

As regras de negócio foram respondidas pelo financeiro no Slack em 16 e 17/10/2026 (`HIPOTESES.md`, `docs/slack-financeiro.md`). Nada é emitido, pago, enviado ou lançado pelo motor.
