window.RESULTS = {
 "source": {
  "run_id": "2026-09-0f5dc9b0948c6539",
  "engine_sha256": "2a7df6c8ebc978acb274d51e8274c4ebbc8fe8cf277679742f3a2d54e0c9307d",
  "period": "2026-09",
  "kind": "static_case_snapshot"
 },
 "metrics": {
  "checkout_bruto_nao_faturado": "262138.61",
  "checkout_comparados": 1900,
  "checkout_lidos": 1957,
  "checkout_nao_faturado": 57,
  "checkout_sem_contrato": 0,
  "comissao_checkout": "203735.34",
  "devolucao_condicao_comercial": "15396.77",
  "diferenca_checkout_brl": "1576.23",
  "diferenca_remessa_brl": "1418.88",
  "divergencias": 115,
  "divergencias_checkout": 92,
  "movimentos_bancarios_exportados": 184,
  "movimentos_bancarios_lidos": 184,
  "notas": 21,
  "participacao_remessas": "39543.45",
  "pendencias": 13,
  "periodo": "2026-09",
  "regras": "REGRAS_DO_FINANCEIRO",
  "remessas_contestadas": 4,
  "remessas_distintas_sem_conflito": 232,
  "remessas_elegiveis": 228,
  "remessas_lidas": 233,
  "saldos_bancarios": {
   "AURORA": {
    "closing": "-1920088.60",
    "opening": "612334.81",
    "opening_status": "EXPLICITO"
   },
   "MERIDIANO": {
    "closing": "1320453.26",
    "opening": "204118.03",
    "opening_status": "INFERIDO"
   }
  },
  "spread_elegivel": "79085.76",
  "status": "CALCULADO",
  "valor_notas": "243284.29"
 },
 "merchants": [
  {
   "name": "Mundo Aberto",
   "checkout": 18508.09,
   "remessa": 3547.69
  },
  {
   "name": "Rota Global Intercâmbio Ltda",
   "checkout": 15621.27,
   "remessa": 4918.34
  },
  {
   "name": "Maple Study Assessoria Educacional Ltda",
   "checkout": 14165.77,
   "remessa": 4295.03
  },
  {
   "name": "Canguru",
   "checkout": 11679.43,
   "remessa": 3764.05
  },
  {
   "name": "EduAbroad",
   "checkout": 11858.16,
   "remessa": 2520.25
  },
  {
   "name": "Oxford Prep Cursos Ltda",
   "checkout": 13845.71,
   "remessa": 0.0
  },
  {
   "name": "Dublin Hub Intercâmbio Ltda",
   "checkout": 11876.37,
   "remessa": 1772.61
  },
  {
   "name": "Kiwi Experience",
   "checkout": 10886.22,
   "remessa": 2668.36
  },
  {
   "name": "Escola Bridge de Idiomas Ltda",
   "checkout": 11769.74,
   "remessa": 0.0
  },
  {
   "name": "Lisboa Cursos e Viagens Ltda",
   "checkout": 8470.78,
   "remessa": 3196.36
  },
  {
   "name": "Novo Horizonte Intercambio",
   "checkout": 7767.78,
   "remessa": 2207.48
  },
  {
   "name": "Bem-Vindo Exchange Ltda",
   "checkout": 9259.74,
   "remessa": 363.22
  },
  {
   "name": "Campus Global Ltda",
   "checkout": 9336.06,
   "remessa": 0.0
  },
  {
   "name": "Vela",
   "checkout": 9315.31,
   "remessa": 0.0
  },
  {
   "name": "Horizonte Viagens",
   "checkout": 9014.42,
   "remessa": 0.0
  },
  {
   "name": "Bagagem Livre Turismo Ltda",
   "checkout": 7703.98,
   "remessa": 1292.67
  },
  {
   "name": "Fluente Idiomas Online Ltda",
   "checkout": 7316.07,
   "remessa": 0.0
  },
  {
   "name": "Sol Nascente Viagens Ltda",
   "checkout": 5898.02,
   "remessa": 0.0
  },
  {
   "name": "Trilha Jovem Turismo Ltda",
   "checkout": 5628.57,
   "remessa": 0.0
  },
  {
   "name": "Andes Expedições Ltda",
   "checkout": 3819.35,
   "remessa": 0.0
  },
  {
   "name": "Casa do Estudante Viagens Ltda",
   "checkout": -5.5,
   "remessa": 3075.91
  },
  {
   "name": "Ponte Aérea Estudantil Ltda",
   "checkout": 0.0,
   "remessa": 3007.3
  },
  {
   "name": "Nórdica Educação Internacional Ltda",
   "checkout": 0.0,
   "remessa": 2914.18
  }
 ],
 "divergences": [
  {
   "name": "ORBE · Rota Global Intercâmbio Ltda",
   "count": 87,
   "brl": 1546.28
  },
  {
   "name": "PONTE · Mundo Aberto",
   "count": 23,
   "brl": 1418.88
  },
  {
   "name": "ORBE · Bridge Idiomas (NOVA)",
   "count": 5,
   "brl": 29.95
  }
 ],
 "pending_by_owner": {
  "Helena (financeiro)": 8,
  "Helena (financeiro) / Comercial": 2,
  "Helena (financeiro) / Tesouraria": 1,
  "Comercial / Helena (financeiro)": 1,
  "Tesouraria": 1
 },
 "pending": [
  {
   "tipo": "DIVERGENCIA_A_CONTESTAR_PONTE",
   "valor": 1418.88,
   "quem": "Helena (financeiro)"
  },
  {
   "tipo": "OPERACAO_REPETIDA_CONTESTAR",
   "valor": 821.88,
   "quem": "Helena (financeiro)"
  },
  {
   "tipo": "SALDO_NAO_POSITIVO_SEM_NOTA",
   "valor": -5.5,
   "quem": "Helena (financeiro)"
  },
  {
   "tipo": "DIVERGENCIA_A_CONTESTAR_ORBE",
   "valor": 1546.28,
   "quem": "Helena (financeiro)"
  },
  {
   "tipo": "ALERTA_ANTECIPACAO",
   "valor": 179592.82,
   "quem": "Helena (financeiro) / Comercial"
  },
  {
   "tipo": "DIVERGENCIA_A_CONTESTAR_ORBE",
   "valor": 29.95,
   "quem": "Helena (financeiro)"
  },
  {
   "tipo": "CREDITO_NAO_IDENTIFICADO",
   "valor": 7350.0,
   "quem": "Helena (financeiro) / Tesouraria"
  },
  {
   "tipo": "LOJISTA_NAO_FATURAR",
   "valor": 262138.61,
   "quem": "Comercial / Helena (financeiro)"
  },
  {
   "tipo": "SPREAD_NEGATIVO_CONTESTAR",
   "valor": -1834.05,
   "quem": "Helena (financeiro)"
  },
  {
   "tipo": "REPASSE_DEVOLVIDO",
   "valor": 12400.0,
   "quem": "Helena (financeiro)"
  },
  {
   "tipo": "DEVOLUCAO_CONDICAO_COMERCIAL",
   "valor": 15396.77,
   "quem": "Helena (financeiro) / Comercial"
  },
  {
   "tipo": "TRANSFERENCIA_EM_TRANSITO",
   "valor": -300000.0,
   "quem": "Tesouraria"
  },
  {
   "tipo": "DECISAO_DO_FINANCEIRO",
   "valor": null,
   "quem": "Helena (financeiro)"
  }
 ],
 "bank_accounts": [
  {
   "name": "Recursos de lojistas para remessas a liquidar",
   "count": 85,
   "brl": 11241134.24
  },
  {
   "name": "Repasses a lojistas a pagar",
   "count": 45,
   "brl": 4242667.61
  },
  {
   "name": "Recebíveis de adquirente - Orbe",
   "count": 21,
   "brl": 3557246.29
  },
  {
   "name": "Transferências entre contas próprias",
   "count": 7,
   "brl": 2600000.0
  },
  {
   "name": "Aplicação automática Meridiano",
   "count": 6,
   "brl": 1061005.0
  },
  {
   "name": "Tarifas bancárias",
   "count": 4,
   "brl": 1156.4
  },
  {
   "name": "IRRF a recolher",
   "count": 1,
   "brl": 22104.35
  },
  {
   "name": "Seguros",
   "count": 1,
   "brl": 1830.44
  },
  {
   "name": "Comissões de intermediação a receber - câmbio",
   "count": 1,
   "brl": 61884.12
  },
  {
   "name": "Rendimentos de aplicações",
   "count": 1,
   "brl": 3912.66
  },
  {
   "name": "Serviços contábeis e jurídicos",
   "count": 1,
   "brl": 6800.0
  },
  {
   "name": "Créditos não identificados",
   "count": 1,
   "brl": 7350.0
  },
  {
   "name": "Cloud e infraestrutura",
   "count": 1,
   "brl": 41208.77
  },
  {
   "name": "PIS a recolher",
   "count": 1,
   "brl": 9811.2
  },
  {
   "name": "COFINS a recolher",
   "count": 1,
   "brl": 45282.46
  },
  {
   "name": "Aluguel e condomínio",
   "count": 1,
   "brl": 28450.0
  },
  {
   "name": "INSS a recolher",
   "count": 1,
   "brl": 51320.66
  },
  {
   "name": "Softwares e assinaturas",
   "count": 1,
   "brl": 2210.0
  },
  {
   "name": "IOF",
   "count": 1,
   "brl": 48.21
  },
  {
   "name": "ISS a recolher",
   "count": 1,
   "brl": 21877.4
  },
  {
   "name": "Salários a pagar",
   "count": 1,
   "brl": 184732.18
  },
  {
   "name": "FGTS a recolher",
   "count": 1,
   "brl": 14778.57
  }
 ],
 "coverage": {
  "INCLUIDO": 2128,
  "NAO_FATURAR": 57,
  "CLASSIFICADO": 184,
  "REPETIDO": 1,
  "CONTESTAR": 4
 },
 "late_adjustments": {
  "commission_before": 207039.73,
  "commission_after": 203735.34,
  "notes_before": 246588.68,
  "notes_after": 243284.29
 },
 "amounts_to_review": {
  "Casa do Estudante · devolução a revisar": 15396.77,
  "Spreads negativos · contestação a revisar": 1834.05,
  "Orbe · divergências a contestar": 1576.23,
  "Ponte · divergências a contestar": 1418.88
 }
};
