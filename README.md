# Tarvo: motor de fechamento mensal

Motor local para o case Barte AI. Recebe a pasta (ou o ZIP) com os seis arquivos do mês, aplica as regras do financeiro da Tarvo e gera os seis CSVs de `saida/`, um relatório HTML de revisão e rascunhos de contestação para a Orbe e a Ponte. Um único comando, sem limpeza manual dos arquivos.

**Não há chave de API.** O cálculo é determinístico e não chama modelos de IA em execução; a IA foi usada na investigação e no desenvolvimento (ver `PROMPTS/`).

## Rodar do zero

Python 3.12 ou superior (testado em 3.14):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_engine.py --input Tarvo_Data_Pack_set2026 --period 2026-09 --output saida-banca
```

Em Linux/macOS, troque `.\.venv\Scripts\python.exe` por `.venv/bin/python`.

Abra `saida-banca/index.html` no navegador. Os CSVs ficam direto na pasta de saída e devem coincidir com os de `saida/` entregues.

- `--input`: pasta ou `.zip` com os arquivos do mês. Os arquivos são identificados pelos prefixos `01_`, `02_`, `03_`, `04_`, `05a_` e `05b_`; nada é fixo para setembro.
- `--period`: competência `AAAA-MM`.
- `--output`: pasta nova. Se a pasta já existir com conteúdo diferente, o motor recusa sobrescrever (para não perder um fechamento anterior); com conteúdo idêntico, apenas confirma.
- `--policy`: regras (padrão `config/closing-policy.json`).

Para outubro: `--input <pasta de outubro> --period 2026-10 --output saida-2026-10`.

## Saídas

| Arquivo | Conteúdo |
|---|---|
| `comissoes_por_lojista.csv` | Comissão por CNPJ e linha de negócio (CHECKOUT, REMESSA). |
| `divergencias_taxa.csv` | Lançamentos com taxa/spread aplicado diferente do contratado, com o valor a contestar e a contraparte (Orbe ou Ponte). |
| `notas_a_emitir.csv` | Uma nota por lojista de checkout com saldo positivo e uma nota para a Ponte Câmbio pela participação nas remessas. Status `A_EMITIR_APOS_REVISAO`. |
| `lancamentos_classificados.csv` | Cada movimento dos dois extratos com a conta contábil da contrapartida. |
| `pendencias.csv` | O que depende de decisão: valor, motivo e quem decide. |
| `rastro.csv` | Para cada `id_saida`, as linhas de origem cuja soma reproduz o valor. |

Também: `contestacoes/` (rascunho de e-mail e lista de operações por contraparte), `cobertura.csv` (destino de cada linha de origem), `metrics.json`, `checks.json`, `policy.json`, `manifest.json` (hashes de entradas, regras, motor e saídas) e `anexos/` (anexo do e-mail da Ponte).

CSV com `;`, ponto decimal, datas ISO e CNPJ com 14 dígitos em texto. Valor de pendência desconhecido fica vazio, não zero.

## Resultado de setembro/2026

- Comissão de checkout: **R$ 207.039,73** (bruto × taxa contratada, linha a linha).
- Participação em remessas: **R$ 39.543,45** (50% do spread realizado de 228 operações; 4 spreads negativos fora; operação repetida contada uma vez).
- 21 notas: 20 de checkout e 1 para a Ponte Câmbio, somando R$ 246.588,68. A Casa do Estudante fica sem nota (saldo de −R$ 5,50 por estorno de venda de agosto) e a Atlas não é faturada até o comercial confirmar a taxa.
- 115 divergências: Rota Global (87) e Bridge (5) contra a Orbe, R$ 1.576,23 líquidos; Mundo Aberto (23) contra a Ponte, R$ 1.418,88.
- Devolução à Casa do Estudante pela isenção não informada à Orbe: R$ 15.396,77.
- 184 movimentos bancários classificados; 2.360 linhas de origem com destino registrado.

## Chaves e credenciais

Nenhuma. O motor não chama APIs nem modelos de IA, e não há `.env` para configurar.

## Limitações conhecidas

- Notas, contestações e lançamentos são propostas para revisão: o motor não emite nota, não envia e-mail e não lança no ERP.
- Atlas Idiomas fica sem faturamento até o comercial confirmar a taxa; o motor ainda não carrega automaticamente as linhas pendentes de um mês para o seguinte.
- Sem conciliação da Orbe contra o banco parcela por parcela (depende da agenda de recebíveis, fora do pacote).
- O alerta de antecipação só avalia lojistas sem histórico anterior no pacote.
- A confiança da classificação bancária é um escore de regra, não probabilidade calibrada.
- Detalhes e decisões do time em `HIPOTESES.md`.

## Regras

As regras vêm das respostas do financeiro no Slack e estão em `config/closing-policy.json`, cada uma com evidência e data. O resumo, as decisões que o financeiro deixou para o time e as limitações estão em `HIPOTESES.md`; a transcrição das perguntas e respostas, em `docs/slack-financeiro.md`.

## Conferir um valor

No HTML, escolha uma saída, copie o `id_saida`, mude para `rastro` e pesquise o ID. A soma da coluna `valor` é o valor da saída; `formula` mostra a conta e a taxa usada.

## Testes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Cobrem os números de setembro, as regras do financeiro (estorno de agosto, isenção da Casa, spreads negativos, duplicata, nota única da Ponte, alerta de antecipação), a reconciliação dos CSVs com o rastro, ZIP de entrada, reexecução sem sobrescrita, reordenação, conflito de versões, período seguinte simulado e rejeição de dados corrompidos.

## Estrutura

- `run_engine.py`, `src/tarvo_close/`: leitura das fontes, cálculo, validação e publicação.
- `config/closing-policy.json`: regras e decisões.
- `Tarvo_Data_Pack_set2026/`: arquivos do case.
- `saida/`: execução entregue de setembro.
- `PROMPTS/`, `HIPOTESES.md`, `docs/`: histórico de IA, premissas e respostas do financeiro.
- `analysis/`: scripts e materiais da investigação inicial.
