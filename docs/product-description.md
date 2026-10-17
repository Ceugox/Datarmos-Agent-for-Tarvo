# Motor de fechamento Tarvo

O problema é fechar o mês a partir de fontes incompatíveis e regras tácitas, sem perder o vínculo entre saída e origem. A analista roda o fechamento, a Helena (financeiro) decide as exceções e revisa notas e contestações.

A entrega implementada tem três partes: motor local, serviço HTTP e apresentação estática do case. O motor lê os arquivos do mês (pasta ou ZIP), aplica as regras do financeiro e gera seis CSVs principais, HTML de revisão e rascunhos de contestação. O próximo mês usa arquivos no mesmo formato, sem contagens de setembro no núcleo.

Entradas: CSV, XLSX, EML com anexo e OFX; seis fontes-base e ajustes tardios opcionais. Fonte bloqueada gera fechamento provisório das partes independentes, com motivo e responsável. Erro de regra ou configuração interrompe a execução.

A API reutiliza o mesmo motor, autentica por chave de cliente e persiste políticas versionadas, jobs, exceções, decisões e auditoria no Postgres. Os arquivos ficam em disco. O fluxo é enviar pacote, acompanhar estado, consultar resultados e exceções, registrar decisão e consultar a revisão. Revisões preservam o original. O worker não retoma jobs interrompidos pela morte do processo.

A inferência opcional propõe classificação de movimentos sem regra, com evidência validada; não calcula valores nem decide condições comerciais. A política padrão usa modo sombra, sem alterar os CSVs. Promoção depende de backtest por classe e, para automático, aprovação registrada. A demonstração temporária é uma exceção configurável: cliente demo nasce em sugerir, exige aprovação para aplicar e expira em DEMO_ATE. O pacote original de setembro não tem movimento sem regra elegível.

O pedido central do autor é manter o cálculo determinístico e usar o LLM para reduzir a fricção de análise das exceções que exigem intervenção humana. A evidência deve facilitar a decisão da pessoa responsável, preservando sua autoria e os limites da política.

O site em https://datarmos.up.railway.app e seu pitch de 13 slides apresentam um retrato estático de setembro; não são interface de upload ou aprovação da API. Os valores identificados para devolução e contestação não são economia realizada. Tempo de processamento do motor não mede o prazo completo do fechamento.

Não há integração online com Slack, bancos, ERP ou emissor fiscal. Não há emissão, pagamento, envio de contestação nem conciliação parcela a parcela. Cadastro de cliente e políticas parte das regras Tarvo; autenticação por cliente não equivale a um produto genérico de onboarding para outras empresas.

Critérios de aceite: cobertura de todas as linhas de origem, somas em decimal, rastro que recompõe cada valor, cadastro sem aproximação de nomes, regras versionadas com evidência e pendências com motivo e responsável. Versões conflitantes não são escolhidas pela ordem de chegada; falhas de leitura não viram zero.

As regras de negócio foram respondidas pelo financeiro no Slack em 16 e 17/10/2026 (`HIPOTESES.md`, `docs/slack-financeiro.md`). Nada é emitido, pago, enviado ou lançado pelo motor.
