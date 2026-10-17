"""Typed closing exceptions: every pending item the core emits has a class, the source rows it cites and what resolves it.

The class decides who may act on the exception (ADR 0002). Amounts stay in the core: an exception carries the
amount the core computed, never one proposed by the inference layer.
"""
from dataclasses import dataclass, field

LAYOUT_FONTE = 'LAYOUT_FONTE'
CADASTRO = 'CADASTRO'
MOVIMENTO_SEM_REGRA = 'MOVIMENTO_SEM_REGRA'
ESPERA_DADO = 'ESPERA_DADO'
ESPERA_EVIDENCIA = 'ESPERA_EVIDENCIA'
CONDICAO_COMERCIAL = 'CONDICAO_COMERCIAL'
DECISAO = 'DECISAO'
DADO_INVALIDO = 'DADO_INVALIDO'

CLASSES = (LAYOUT_FONTE, CADASTRO, MOVIMENTO_SEM_REGRA, ESPERA_DADO, ESPERA_EVIDENCIA, CONDICAO_COMERCIAL, DECISAO, DADO_INVALIDO)

# tipo -> (class, what is missing to resolve it). A tipo missing here stops the closing: no silent default class.
KINDS = {
    'FONTE_BLOQUEADA': (DADO_INVALIDO, 'exatamente um arquivo da fonte no pacote do mês'),
    'CONFLITO_DE_VERSAO': (DADO_INVALIDO, 'versão correta do registro, confirmada pelo fornecedor da fonte'),
    'DATA_AUSENTE': (DADO_INVALIDO, 'data de contratação da operação na fonte'),
    'STATUS_DESCONHECIDO': (DADO_INVALIDO, 'regra aprovada para o status da operação'),
    'BASE_REMESSA_INVALIDA': (DADO_INVALIDO, 'valor em moeda estrangeira e PTAX da operação na fonte'),
    'TAXA_NAO_RESOLVIDA': (CADASTRO, 'taxa contratada para a modalidade e parcelas, definida pelo comercial'),
    'CADASTRO_REMESSA_AUSENTE': (CADASTRO, 'cadastro do CNPJ na planilha de taxas, pelo comercial'),
    'CADASTRO_OU_CONTRATO_AUSENTE': (CADASTRO, 'EC ligado a um CNPJ e a um contrato vigente, confirmado por chave (CNPJ ou EC)'),
    'CONTRATO_AMBIGUO': (CADASTRO, 'um único contrato vigente para o lojista na data'),
    'TOMADOR_NAO_IDENTIFICADO': (CADASTRO, 'CNPJ do parceiro de remessa no e-mail da Ponte'),
    'CONCILIACAO_BANCARIA': (MOVIMENTO_SEM_REGRA, 'conta de contrapartida para a descrição do movimento'),
    'TRANSFERENCIA_EM_TRANSITO': (ESPERA_DADO, 'crédito correspondente, por valor exato, no extrato da outra conta'),
    'REPASSE_DEVOLVIDO': (ESPERA_EVIDENCIA, 'motivo da devolução, citando o valor ou a operação'),
    'CREDITO_NAO_IDENTIFICADO': (ESPERA_EVIDENCIA, 'pagador identificado por documento que cite o valor exato'),
    'DEVOLUCAO_CONDICAO_COMERCIAL': (CONDICAO_COMERCIAL, 'aprovação do comercial e da Helena para devolver ao lojista e avisar a adquirente'),
    'LOJISTA_NAO_FATURAR': (CONDICAO_COMERCIAL, 'taxa confirmada pelo comercial'),
    'DIVERGENCIA_A_CONTESTAR_ORBE': (DECISAO, 'decisão da Helena: cobrar ou não da Orbe'),
    'DIVERGENCIA_A_CONTESTAR_PONTE': (DECISAO, 'decisão da Helena: contestar ou não com a Ponte'),
    'SPREAD_NEGATIVO_CONTESTAR': (DECISAO, 'decisão da Helena: contestar com a Ponte'),
    'OPERACAO_REPETIDA_CONTESTAR': (DECISAO, 'decisão da Helena: pedir correção do relatório'),
    'SALDO_NAO_POSITIVO_SEM_NOTA': (DECISAO, 'decisão da Helena sobre o saldo com o lojista'),
    'ALERTA_ANTECIPACAO': (DECISAO, 'ciência do financeiro e do comercial'),
    'REVERSAO_SEM_ANTECIPACAO': (DECISAO, 'decisão da Helena sobre a reversão sem antecipação correspondente'),
    'REVERSAO_IRREGULAR': (DECISAO, 'decisão da Helena sobre a reversão com sinal ou valor inesperado'),
    'DECISAO_DO_FINANCEIRO': (DECISAO, 'resposta da Helena à pergunta em aberto'),
}

# FONTE_BLOQUEADA has two natures: a missing or duplicated file is invalid data; an unreadable file is a layout problem.
BLOCK_CLASS = {'AUSENTE_OU_DUPLICADO': DADO_INVALIDO, 'ILEGIVEL_OU_LAYOUT': LAYOUT_FONTE}
BLOCK_MISSING = {'ILEGIVEL_OU_LAYOUT': 'leitor para o layout recebido, conferido pelos totais da própria fonte'}


@dataclass
class ClosingException:
    excecao_id: str
    classe: str
    tipo: str
    escopo: str
    quem_decide: str
    motivo: str
    falta: str
    valor_brl: object = None
    refs: list = field(default_factory=list)

    def as_dict(self):
        return {'excecao_id':self.excecao_id, 'classe':self.classe, 'tipo':self.tipo, 'escopo':self.escopo, 'quem_decide':self.quem_decide,
                'motivo':self.motivo, 'falta':self.falta, 'valor_brl':self.valor_brl, 'refs':list(self.refs)}


def classify(kind, block_cause=None):
    if kind not in KINDS:
        raise ValueError(f'Pending kind without exception class: {kind}')
    exception_class, missing = KINDS[kind]
    if kind == 'FONTE_BLOQUEADA' and block_cause:
        exception_class = BLOCK_CLASS[block_cause]
        missing = BLOCK_MISSING.get(block_cause, missing)
    return exception_class, missing


def source_refs(contributions):
    """Distinct source rows cited by an exception, in a stable order."""
    refs = {(c['arquivo_origem'], c['aba_origem'], c['ref_origem'], c['linha_origem']) for c in contributions}
    return [{'arquivo':file, 'aba':sheet, 'ref':ref, 'linha':line} for file, sheet, ref, line in sorted(refs)]
