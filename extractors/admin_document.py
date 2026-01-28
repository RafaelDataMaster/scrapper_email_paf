"""
Extrator especializado para documentos administrativos.

Este módulo trata documentos administrativos que não são cobranças/faturas:
    - Lembretes gentis de vencimento (sem valores)
    - Ordens de serviço/agendamento (Equinix, etc.)
    - Distratos e rescisões contratuais
    - Encerramentos de contrato
    - Notificações automáticas
    - Guias jurídicas/fiscais
    - Invoices internacionais vazias
    - Relatórios/planilhas de conferência
    - Contratos (documentação, não cobrança)

Características:
    1. Reconhece padrões de assunto e conteúdo típicos de documentos administrativos
    2. Tenta extrair valores quando presentes (alguns contratos têm valores)
    3. Classifica subtipos específicos para melhor organização
    4. Prioridade sobre extratores genéricos (NfseGenericExtractor, OutrosExtractor)
    5. Princípio SOLID: não modifica extratores existentes, apenas adiciona nova especialização

Campos extraídos:
    - tipo_documento: Sempre "OUTRO"
    - subtipo: Categoria administrativa específica (ex: "ENCERRAMENTO", "DISTRATO")
    - admin_type: Descrição amigável (ex: "Documento de encerramento de contrato")
    - fornecedor_nome: Nome do fornecedor/remetente
    - cnpj_fornecedor: CNPJ quando presente
    - valor_total: Valor total a pagar (quando presente)
    - vencimento: Data de vencimento (quando aplicável)
    - data_emissao: Data de emissão
    - numero_documento: Número do documento/processo

Example:
    >>> from extractors.admin_document import AdminDocumentExtractor
    >>> extractor = AdminDocumentExtractor()
    >>> if extractor.can_handle(texto):
    ...     dados = extractor.extract(texto)
    ...     print(f"Tipo: {dados['subtipo']} - {dados['admin_type']}")
"""

import logging
import re
from typing import Any, Dict

from core.extractors import BaseExtractor, register_extractor
from extractors.utils import (
    BR_MONEY_RE,
    parse_br_money,
    parse_date_br,
)


@register_extractor
class AdminDocumentExtractor(BaseExtractor):
    """Extrator especializado para documentos administrativos não-cobrança.

    Objetivo: Capturar documentos que estão sendo classificados incorretamente
    como NFSe/Boleto mas são na verdade administrativos, melhorando a extração
    de dados específicos e fornecendo classificações mais precisas.
    """

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se o documento é um documento administrativo.

        Baseado em:
        1. Padrões de assunto no conteúdo/texto
        2. Palavras-chave específicas de documentos administrativos
        3. Contexto que indica não ser cobrança/fatura

        Args:
            text: Texto completo do documento

        Returns:
            True se for documento administrativo, False caso contrário
        """
        if not text:
            return False

        t = text.upper()

        # Padrões negativos para excluir documentos fiscais/NFSEs
        # Baseado na análise dos casos problemáticos: 11/21 casos eram NFSEs capturadas incorretamente
        negative_patterns = [
            # 1. Estruturas formais de documentos fiscais
            r"DOCUMENTO\s+AUXILIAR\s+DA\s+(?:NOTA\s+FISCAL|NFS)",
            r"CHAVE\s+DE\s+ACESSO",
            r"\b\d{44}\b",  # Chave de acesso exata de 44 dígitos
            r"CONSULTE\s+PELA\s+CHAVE\s+DE\s+ACESSO",
            r"PROTOCOLO\s+DE\s+AUTORIZA[ÇC][AÃ]O",
            r"QR\s*CODE\s+P(?:ARA)?\s*PAGAMENTO\s*PIX",
            # 2. Cabeçalhos de faturas/NFSEs (combinados com números)
            r"^NOTA\s+FISCAL\s+FATURA:?\s*\d+",
            r"^FATURA\s+(?:DE\s+)?SERVI[ÇC]OS?\s*\d+",
            r"^NFS[E\-]?\s*\d+",
            r"^NF\s+COM\s*\d+",
            # 3. Seções específicas de documentos fiscais
            r"VALOR\s+(?:DO\s+)?SERVI[ÇC]O\b",
            r"BASE\s+DE\s+C[ÁA]LCULO\b",
            r"IMPOSTO\s+(?:SOBRE\s+)?SERVI[ÇC]OS?\b",
            r"ISS\b.*\bR\$\s*[\d\.]+,\d{2}",
            r"PIS/COFINS\b",
            r"ICMS\b",
            # 4. Padrões de fornecedores problemáticos identificados
            r"TELCABLES\s+BRASIL.*NOTA\s+FISCAL",
            r"TCF\s+TELECOM.*NOTA\s+FISCAL",
            r"BOX\s+BRAZIL",
            r"BOX\s+BRAZIL.*FATURAMENTO",
            r"FATURAMENTO.*BOX\s+BRAZIL",
            r"BOX\s+BRAZIL.*FATURA:",
            r"BOX\s+BRAZIL.*-\s*[A-Z]{3}\s*-\s*[A-Z]+",
            # 5. Estruturas de dados fiscais
            r"ITENS\s+DA\s+FATURA\b",
            r"UN\s+QUANT\s+PRE[ÇC]O\s+UNIT",
            r"CNTINT\d+\s*-\s*IP\s+TRANSIT",
            # 6. NFSEs municipais específicas (baseado em casos problemáticos)
            r"PREFEITURA\s+MUNICIPAL\s+DE",
            r"S[EÉ]CRETARIA\s+MUNICIPAL\s+(?:DA\s+)?FAZENDA",
            r"AUTENTICIDADE\s+[A-Z0-9\-]+",  # Código de autenticação (ex: F00N-GL8A)
            r"TOMADOR\s+DE\s+SERVI[ÇC]OS",
            r"PRESTADOR\s+DE\s+SERVI[ÇC]OS",
            r"NOTA\s+FISCAL\s+ELETR[ÔO]NICA\s+DE\s+SERVI[ÇC]OS",
            # 7. Dados específicos de NFSE de municípios
            r"IM:\d+",  # Inscrição Municipal
            r"IE:\d+",  # Inscrição Estadual
            # 8. Padrões de boletos bancários (excluir para evitar falsos positivos)
            r"RECIBO\s+DO\s+SACADO",
            r"VALOR\s+DO\s+DOCUMENTO",
            r"BOLETO",
            r"LINHA\s+DIGIT[ÁA]VEL",
            r"BENEFICI[ÁA]RIO",
            r"SACADO",
            r"CEDENTE",
            r"NOSSO\s+N[ÚU]MERO",
            r"AG[ÊE]NCIA",
            r"CONTA\s+CORRENTE",
            # 9. Padrões específicos de fornecedores problemáticos (boletos)
            r"ACIMOC",
            r"ASSOCIA[ÇC][AÃ]O\s+COMERCIAL\s+INDUSTRIAL",
            r"MUGO\s+TELECOM",
            r"PR[ÓO]\s*[-]?\s*PAINEL",
        ]

        # Primeiro verifica se é claramente um documento fiscal
        fiscal_document_score = 0
        for pattern in negative_patterns:
            if re.search(pattern, t, re.IGNORECASE):
                fiscal_document_score += 1

        # Se tiver múltiplos indicadores de documento fiscal, rejeita
        if fiscal_document_score >= 2:
            logging.getLogger(__name__).debug(
                f"AdminDocumentExtractor: can_handle rejeitado - documento fiscal detectado "
                f"(score: {fiscal_document_score})"
            )
            return False

        # Se tiver chave de acesso (indicador forte), rejeita mesmo sozinho
        if re.search(r"CHAVE\s+DE\s+ACESSO", t, re.IGNORECASE) or re.search(
            r"\b\d{44}\b", t
        ):
            logging.getLogger(__name__).debug(
                "AdminDocumentExtractor: can_handle rejeitado - chave de acesso detectada"
            )
            return False

        # Verificação forte para boletos bancários (evitar falsos positivos como ACIMOC)
        boleto_indicators = [
            r"RECIBO\s+DO\s+SACADO",
            r"VALOR\s+DO\s+DOCUMENTO",
            r"BOLETO",
            r"LINHA\s+DIGIT[ÁA]VEL",
            r"BENEFICI[ÁA]RIO",
            r"SACADO",
            r"CEDENTE",
            r"NOSSO\s+N[ÚU]MERO",
            r"AG[ÊE]NCIA",
            r"CONTA\s+CORRENTE",
            r"PAGADOR",
            r"VENCIMENTO",
            r"VALOR\s+A\s+PAGAR",
        ]

        boleto_score = 0
        for pattern in boleto_indicators:
            if re.search(pattern, t, re.IGNORECASE):
                boleto_score += 1

        # Se tiver múltiplos indicadores de boleto (>=3), rejeita como documento administrativo
        if boleto_score >= 3:
            logging.getLogger(__name__).debug(
                f"AdminDocumentExtractor: can_handle rejeitado - documento parece ser boleto "
                f"(score: {boleto_score})"
            )
            return False

        # Padrões baseados em análise dos casos problemáticos
        patterns = [
            # 1. Lembretes gentis (corrigido para capturar variações)
            (r"LEMBR(?:ETE|E)\s+GENTIL", "Lembrete administrativo"),
            # 2. Ordens de serviço/agendamento (Equinix, etc.)
            (r"SUA\s+ORDEM\s+.*\s+AGENDAD[OA]", "Ordem de serviço/agendamento"),
            (r"ORDEM\s+DE\s+SERVI[ÇC]O", "Ordem de serviço/agendamento"),
            (r"N[º°\.]?\s*\d+[- ]AGENDAMENTO", "Ordem de serviço/agendamento"),
            # 3. Distratos e rescisões
            (r"\bDISTRATO\b", "Documento de distrato"),
            (r"RESCIS[AÃ]O\s+CONTRATUAL", "Documento de rescisão contratual"),
            (r"RESCIS[OÓ]RIO", "Documento de rescisão contratual"),
            # 4. Encerramentos e cancelamentos
            (r"ENCERRAMENTO\s+DE\s+CONTRATO", "Documento de encerramento de contrato"),
            (
                r"SOLICITA[ÇC][AÃ]O\s+DE\s+ENCERRAMENTO",
                "Documento de encerramento de contrato",
            ),
            (r"CANCELAMENTO\s+DE\s+CONTRATO", "Documento de cancelamento"),
            # 5. Notificações automáticas
            (r"NOTIFICA[ÇC][AÃ]O\s+AUTOM[ÁA]TICA", "Notificação automática"),
            (
                r"DOCUMENTO\s+\d{6,9}\s+[-–]\s+NOTIFICA[ÇC][AÃ]O",
                "Notificação automática",
            ),
            (r"DOCUMENTO\s*:\s*\d{6,9}", "Notificação automática"),
            # 6. Guias jurídicas/fiscais
            (r"GUIA\s*[\|\-–]\s*PROCESSO", "Guia jurídica/fiscal"),
            (r"GUIA\s*[\|\-–]\s*EXECU[ÇC][AÃ]O", "Guia jurídica/fiscal"),
            (r"GUIAS?\s*[-–]?\s*(CSC|PROCESSO|EXECU[ÇC][AÃ]O)", "Guia jurídica/fiscal"),
            # 7. Contratos (documentação)
            (
                r"CONTRATO(_|\s+)(SITE|MASTER|RENOVA[ÇC][AÃ]O|ADITIVO)",
                "Documento de contrato",
            ),
            (r"MINUTA\s+DE\s+CONTRATO", "Documento de contrato"),
            # 8. Invoices internacionais vazias
            (
                r"(DECEMBER|JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|"
                r"AUGUST|SEPTEMBER|OCTOBER|NOVEMBER)\s*[-–]?\s*\d{4}\s+INVOICE\s+FOR",
                "Invoice internacional",
            ),
            # 9. Relatórios/planilhas
            (r"RELAT[OÓ]RIO\s+DE\s+FATURAMENTO", "Relatório/planilha de conferência"),
            (
                r"PLANILHA\s+DE\s+(CONFER[EÊ]NCIA|FATURAMENTO)",
                "Relatório/planilha de conferência",
            ),
            # 10. Câmbio/programação TV
            (
                r"C[ÂA]MBIO\s+(HBO|GLOBOSAT|BAND|SBT|RECORD|PROGRAMADORA)",
                "Documento de programação/câmbio",
            ),
            # 11. Processos jurídicos
            (r"PROCESSO\s+(FISCAL|TRABALHIST[AO]|JUDICIAL)", "Processo jurídico"),
            (
                r"EXECU[ÇC][AÃ]O\s+(FISCAL|TRABALHIST[AO]|JUDICIAL)",
                "Execução fiscal/judicial",
            ),
            # 12. Anuidades/taxas
            (r"ANUIDADE\s+(CREA|OAB|CRM|CFM|COREN)", "Taxa/anuidade de órgão"),
            # 13. Reembolsos internos
            (r"REEMBOLSO\s+DE\s+TARIFAS", "Reembolso interno"),
            # 14. Tarifas internas
            (r"TARIFAS\s+CSC", "Documento de tarifas internas"),
            # 15. Condomínio (Alvim Nogueira)
            (r"ALVIM\s+NOGUEIRA", "Documento de condomínio"),
            # 16. Cobranças indevidas (reclamações)
            (r"COBRAN[ÇC]A\s+INDEVIDA", "Reclamação de cobrança"),
            # 17. Comprovantes administrativos
            (r"COMPROVANTE\s+DE\s+SOLICITA[ÇC][AÃ]O", "Comprovante administrativo"),
            # 18. Documentos informativos de serviços públicos
            (r"INFORMATIVO\s+IMPORTANTE", "Documento informativo de serviço público"),
            (r"COPASA", "Documento informativo de serviço público (água/esgoto)"),
            (
                r"C[ÂA]MBIO\s+(MTV|HBO|GLOBOSAT|BAND|SBT|RECORD|PROGRAMADORA)",
                "Documento de programação/câmbio",
            ),
            (r"PROGRAMADORA\s+BRASILEIRA", "Documento de programação/câmbio"),
            (r"BOX\s+BRAZIL", "Documento de programação/câmbio"),
            (r"SERVI[ÇC]O\s+P[ÚU]BLICO", "Documento de serviço público"),
            (
                r"CONTA\s+(DE\s+)?(ÁGUA|LUZ|ENERGIA|TELEFONE)",
                "Documento de serviço público",
            ),
        ]

        for pattern, _ in patterns:
            if re.search(pattern, t, re.IGNORECASE):
                # Antes de aceitar, verificar se não é um documento fiscal disfarçado
                has_fiscal_indicator = bool(
                    re.search(r"CHAVE\s+DE\s+ACESSO", t, re.IGNORECASE)
                    or re.search(r"DOCUMENTO\s+AUXILIAR", t, re.IGNORECASE)
                    or re.search(r"NOTA\s+FISCAL\s+FATURA", t, re.IGNORECASE)
                    or re.search(r"\b\d{44}\b", t)
                    or re.search(
                        r"PROTOCOLO\s+DE\s+AUTORIZA[ÇC][AÃ]O", t, re.IGNORECASE
                    )
                )

                if has_fiscal_indicator:
                    logging.getLogger(__name__).debug(
                        "AdminDocumentExtractor: padrão administrativo detectado, "
                        "mas documento tem indicadores fiscais - rejeitando"
                    )
                    return False

                logging.getLogger(__name__).debug(
                    "AdminDocumentExtractor: can_handle detectou padrão administrativo"
                )
                return True

        # Fallback: verificar contexto de ausência de valores de cobrança
        # Se contém palavras administrativas mas não contém padrões de valor/vencimento
        admin_keywords = [
            "SOLICITAÇÃO",
            "AVISO",
            "NOTIFICAÇÃO",
            "INFORMAÇÃO",
            "COMUNICADO",
            "ORIENTAÇÃO",
            "LEMBRETE",
            "AGENDAMENTO",
            "CONFIRMAÇÃO",
            "STATUS",
            "ANDAMENTO",
        ]

        has_admin_keyword = any(keyword in t for keyword in admin_keywords)
        has_money_pattern = bool(BR_MONEY_RE.search(text))
        has_vencimento = bool(
            re.search(r"VENCIMENTO.*\d{2}/\d{2}/\d{4}", t, re.IGNORECASE)
        )
        has_fiscal_indicator = bool(
            re.search(r"CHAVE\s+DE\s+ACESSO", t, re.IGNORECASE)
            or re.search(r"DOCUMENTO\s+AUXILIAR", t, re.IGNORECASE)
            or re.search(r"NOTA\s+FISCAL\s+FATURA", t, re.IGNORECASE)
            or re.search(r"\b\d{44}\b", t)
        )

        # Se tem palavra administrativa mas não tem valores/vencimento de cobrança ou indicadores fiscais
        if has_admin_keyword and not (
            has_money_pattern or has_vencimento or has_fiscal_indicator
        ):
            logging.getLogger(__name__).debug(
                "AdminDocumentExtractor: can_handle detectou contexto administrativo "
                "(sem valores de cobrança ou indicadores fiscais)"
            )
            return True

        return False

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados de documentos administrativos.

        Args:
            text: Texto completo do documento

        Returns:
            Dicionário com dados extraídos
        """
        logger = logging.getLogger(__name__)
        data: Dict[str, Any] = {"tipo_documento": "OUTRO"}
        logger.debug(
            "AdminDocumentExtractor: iniciando extração de documento administrativo"
        )

        t = text.upper()

        # Mapeamento de padrões para subtipos e descrições
        patterns_map = [
            (r"LEMBR(?:ETE|E)\s+GENTIL", "LEMBRETE", "Lembrete administrativo"),
            (
                r"SUA\s+ORDEM\s+.*\s+AGENDAD[OA]",
                "ORDEM_SERVICO",
                "Ordem de serviço/agendamento",
            ),
            (
                r"ORDEM\s+DE\s+SERVI[ÇC]O",
                "ORDEM_SERVICO",
                "Ordem de serviço/agendamento",
            ),
            (r"\bDISTRATO\b", "DISTRATO", "Documento de distrato"),
            (
                r"RESCIS[AÃ]O\s+CONTRATUAL",
                "RESCISAO",
                "Documento de rescisão contratual",
            ),
            (
                r"ENCERRAMENTO\s+DE\s+CONTRATO",
                "ENCERRAMENTO",
                "Documento de encerramento de contrato",
            ),
            (
                r"SOLICITA[ÇC][AÃ]O\s+DE\s+ENCERRAMENTO",
                "ENCERRAMENTO",
                "Documento de encerramento de contrato",
            ),
            (
                r"NOTIFICA[ÇC][AÃ]O\s+AUTOM[ÁA]TICA",
                "NOTIFICACAO",
                "Notificação automática",
            ),
            (r"GUIA\s*[\|\-–]\s*PROCESSO", "GUIA_JURIDICA", "Guia jurídica/fiscal"),
            (
                r"GUIA\s*[\|\-–]\s*EXECU[ÇC][AÃ]O",
                "GUIA_JURIDICA",
                "Guia jurídica/fiscal",
            ),
            (
                r"CONTRATO(_|\s+)(SITE|MASTER|RENOVA[ÇC][AÃ]O|ADITIVO)",
                "CONTRATO",
                "Documento de contrato",
            ),
            (
                r"(DECEMBER|JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|"
                r"AUGUST|SEPTEMBER|OCTOBER|NOVEMBER)\s*[-–]?\s*\d{4}\s+INVOICE\s+FOR",
                "INVOICE_INTERNACIONAL",
                "Invoice internacional",
            ),
            (
                r"RELAT[OÓ]RIO\s+DE\s+FATURAMENTO",
                "RELATORIO",
                "Relatório/planilha de conferência",
            ),
            (
                r"PLANILHA\s+DE\s+(CONFER[EÊ]NCIA|FATURAMENTO)",
                "RELATORIO",
                "Relatório/planilha de conferência",
            ),
            (
                r"C[ÂA]MBIO\s+(HBO|GLOBOSAT|BAND|SBT|RECORD|PROGRAMADORA)",
                "CAMBIO",
                "Documento de programação/câmbio",
            ),
            (r"ALVIM\s+NOGUEIRA", "CONDOMINIO", "Documento de condomínio"),
            (r"COBRAN[ÇC]A\s+INDEVIDA", "RECLAMACAO", "Reclamação de cobrança"),
            (r"REEMBOLSO\s+DE\s+TARIFAS", "REEMBOLSO", "Reembolso interno"),
            (r"TARIFAS\s+CSC", "TARIFAS_INTERNAS", "Documento de tarifas internas"),
        ]

        # Identificar subtipo e admin_type
        for pattern, subtipo, admin_type in patterns_map:
            if re.search(pattern, t, re.IGNORECASE):
                data["subtipo"] = subtipo
                data["admin_type"] = admin_type
                logger.debug(
                    f"AdminDocumentExtractor: identificado subtipo '{subtipo}' - '{admin_type}'"
                )
                break

        # Fallback para subtipo genérico
        if "subtipo" not in data:
            data["subtipo"] = "ADMINISTRATIVO"
            data["admin_type"] = "Documento administrativo"
            logger.debug(
                "AdminDocumentExtractor: usando subtipo genérico 'ADMINISTRATIVO'"
            )

        # Fornecedor (tentativas)
        # 1. Procurar padrão "De:" ou "From:" no início (melhorado)
        m_from = re.search(
            r"(?:^|\n)\s*(?:De|From|DE|FROM)[:\s]+\s*([A-ZÀ-ÿ][A-ZÀ-ÿ0-9\s\.\-\&\,\(\)]{10,80})(?:\n|$)",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        if m_from:
            fornecedor = re.sub(r"\s+", " ", m_from.group(1)).strip()
            # Limpar partes comuns que não são nome
            if "CNPJ" not in fornecedor.upper() and "CPF" not in fornecedor.upper():
                if (
                    len(fornecedor) > 5 and len(fornecedor) < 100
                ):  # Evitar capturas muito curtas ou longas
                    data["fornecedor_nome"] = fornecedor
                    logger.debug(
                        f"AdminDocumentExtractor: fornecedor extraído (De/From): {fornecedor}"
                    )

        # 2. Procurar nome em caixa alta seguido de CNPJ (melhorado)
        if not data.get("fornecedor_nome"):
            m_nome_cnpj = re.search(
                r"([A-ZÀ-ÿ][A-ZÀ-ÿ0-9\s\.\-\&\,\(\)]{10,80}?)(?:\s+(?:CNPJ|CPF)[:\s]*|\s+\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})",
                text,
            )
            if m_nome_cnpj:
                fornecedor = re.sub(r"\s+", " ", m_nome_cnpj.group(1)).strip()
                if len(fornecedor) > 5:
                    data["fornecedor_nome"] = fornecedor
                    logger.debug(
                        f"AdminDocumentExtractor: fornecedor extraído (nome+CNPJ): {fornecedor}"
                    )

        # 3. Procurar linha com apenas nome em caixa alta (fallback)
        if not data.get("fornecedor_nome"):
            # Procura por linhas que parecem ser nomes de empresas (muitas maiúsculas, termina com LTDA, S/A, etc.)
            m_empresa = re.search(
                r"^\s*([A-ZÀ-ÿ][A-ZÀ-ÿ0-9\s\.\-\&\,\(\)]{10,80}(?:LTDA|S\.?A\.?|ME|EIRELI|\-ME))\s*$",
                text,
                re.MULTILINE,
            )
            if m_empresa:
                fornecedor = re.sub(r"\s+", " ", m_empresa.group(1)).strip()
                data["fornecedor_nome"] = fornecedor
                logger.debug(
                    f"AdminDocumentExtractor: fornecedor extraído (linha empresa): {fornecedor}"
                )

        # CNPJ (primeiro formatado)
        if not data.get("cnpj_fornecedor"):
            m_cnpj = re.search(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", text)
            if m_cnpj:
                data["cnpj_fornecedor"] = m_cnpj.group(0)
                logger.debug(
                    f"AdminDocumentExtractor: CNPJ extraído: {data['cnpj_fornecedor']}"
                )

        # Valor total - alguns documentos administrativos têm valores
        # (ex: contratos com valores, reclamações com valores indevidos)
        if data["subtipo"] in [
            "CONTRATO",
            "RECLAMACAO",
            "INVOICE_INTERNACIONAL",
            "GUIA_JURIDICA",
            "ORDEM_SERVICO",
        ]:
            # Tentar padrões específicos para contratos e guias
            value_patterns = [
                r"(?i)VALOR\s+(?:DO\s+)?(?:CONTRATO|PROCESSO|GUIA)\s*[:\-–]?\s*R\$\s*([\d\.,]+)",
                r"(?i)VALOR\s+TOTAL\s*[:\-–]?\s*R\$\s*([\d\.,]+)",
                r"(?i)TOTAL\s*[:\-–]?\s*R\$\s*([\d\.,]+)",
                r"\bR\$\s*([\d\.]+,\d{2})\b",
            ]

            for pattern in value_patterns:
                m = re.search(pattern, text)
                if m:
                    val = parse_br_money(m.group(1))
                    if val > 0:
                        data["valor_total"] = val
                        logger.debug(
                            f"AdminDocumentExtractor: valor_total extraído "
                            f"({data['subtipo']}): R$ {data['valor_total']:.2f}"
                        )
                        break

        # Se não encontrou valor ainda, tentar padrões genéricos (apenas para subtipos que podem ter valor)
        if not data.get("valor_total") and data["subtipo"] in [
            "CONTRATO",
            "GUIA_JURIDICA",
            "RECLAMACAO",
            "ORDEM_SERVICO",
        ]:
            for pattern in [r"\bR\$\s*([\d\.]+,\d{2})\b", BR_MONEY_RE]:
                matches = list(re.finditer(pattern, text))
                if matches:
                    # Filtrar valores muito pequenos que podem ser referências
                    values = [parse_br_money(m.group(1)) for m in matches]
                    values = [v for v in values if v > 10]  # Ignorar valores < R$10
                    if values:
                        data["valor_total"] = max(values)  # Pega o maior valor
                        logger.debug(
                            f"AdminDocumentExtractor: valor_total extraído (genérico): "
                            f"R$ {data['valor_total']:.2f}"
                        )
                        break

        # Datas
        # 1. Vencimento (quando aplicável)
        if data["subtipo"] in [
            "LEMBRETE",
            "CONTRATO",
            "CONDOMINIO",
            "GUIA_JURIDICA",
            "ORDEM_SERVICO",
        ]:
            # Padrão 1: VENCIMENTO seguido diretamente por data (mesma linha)
            m_venc = re.search(
                r"(?i)\bVENCIMENTO\b\s*[:\-–]?\s*(\d{2}/\d{2}/\d{4})", text
            )

            # Padrão 2: VENCIMENTO seguido por data em qualquer lugar próximo (até 50 caracteres, incluindo quebras)
            if not m_venc:
                # Usar re.DOTALL para que . capture quebras de linha também
                m_venc = re.search(
                    r"(?i)\bVENCIMENTO\b.{0,50}?(\d{2}/\d{2}/\d{4})", text, re.DOTALL
                )

            # Padrão 3: Para documentos de ordem de serviço, procurar datas próximas a "Vencimento" em tabelas
            if not m_venc and data["subtipo"] == "ORDEM_SERVICO":
                # Procurar padrão específico de tabela: "Vencimento" e data na mesma linha ou próxima
                lines = text.split("\n")
                for i, line in enumerate(lines):
                    if re.search(r"(?i)\bVENCIMENTO\b", line):
                        # Verificar se há data na mesma linha
                        date_match = re.search(r"(\d{2}/\d{2}/\d{4})", line)
                        if date_match:
                            m_venc = date_match
                            break
                        # Verificar próxima linha para data
                        if i + 1 < len(lines):
                            next_line = lines[i + 1]
                            date_match = re.search(r"(\d{2}/\d{2}/\d{4})", next_line)
                            if date_match:
                                m_venc = date_match
                                break
                        # Verificar linha anterior (caso "Vencimento" esteja após a data)
                        if i > 0:
                            prev_line = lines[i - 1]
                            date_match = re.search(r"(\d{2}/\d{2}/\d{4})", prev_line)
                            if date_match:
                                m_venc = date_match
                                break

            if m_venc:
                data["vencimento"] = parse_date_br(m_venc.group(1))
                logger.debug(
                    f"AdminDocumentExtractor: vencimento extraído: {data['vencimento']}"
                )

        # 2. Data de emissão (primeira data no documento, evitando datas em CNPJ)
        date_matches = list(re.finditer(r"\b(\d{2}/\d{2}/\d{4})\b", text))
        for match in date_matches:
            date_str = match.group(1)
            # Verificar se não é parte de um CNPJ (XX.XXX.XXX/XXXX-XX)
            if not re.search(
                r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}",
                text[max(0, match.start() - 20) : match.end() + 20],
            ):
                data["data_emissao"] = parse_date_br(date_str)
                logger.debug(
                    f"AdminDocumentExtractor: data_emissao extraída: {data['data_emissao']}"
                )
                break

        # Número do documento/processo - REGEX MELHORADAS
        # Padrões: "Documento 000000135", "Processo n.º 12345", "Nº 1-255425159203"
        num_patterns = [
            # Notificações automáticas: "Documento 000000135" ou "Documento: 000000135"
            r"(?i)(?:Documento|DOCUMENTO)\s*[:\-]?\s*(\d{6,9})\b",
            # Processos: "Processo n.º 12345" ou "Processo: 12345"
            r"(?i)(?:Processo|PROCESSO)\s*(?:n[º°\.]?\s*)?[:\-]?\s*(\d{5,12})\b",
            # Ordens Equinix: "Nº 1-255425159203" ou "n.º 1-255425159203" ou "Ordem: 1-255425159203"
            r"(?i)(?:N[º°\.]?\s*)?[:\-]?\s*(\d+-\d+)\b",
            r"(?i)ORDEM\s*(?:N[º°\.]?\s*)?[:\-]?\s*(\d+-\d+)\b",
            # Contratos: "Contrato MI-2023-0456"
            r"(?i)CONTRATO\s*[:\-]?\s*([A-Z]{2}-?\d{4}-?\d{3,4})\b",
            # Guias: "Processo 12345.678.910.2025"
            r"(?i)Processo\s*[:\-]?\s*(\d{5}\.\d{3}\.\d{3}\.\d{4})\b",
            # Padrão genérico para números longos após "Documento" ou "Nº"
            r"(?i)(?:Documento|DOCUMENTO|N[º°\.]?|ORDEM)\s*[:\-]?\s*([A-Z0-9\-\.]+)\b",
        ]

        for pattern in num_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                numero = m.group(1).strip()
                # Validar que o número tem formato razoável (não apenas dígitos soltos)
                if len(numero) >= 5 and not numero.isalpha():
                    data["numero_documento"] = numero
                    logger.debug(
                        f"AdminDocumentExtractor: numero_documento extraído: {data['numero_documento']}"
                    )
                    break

        # Log final do resultado
        if data.get("valor_total"):
            logger.info(
                f"AdminDocumentExtractor: documento processado - "
                f"subtipo: {data['subtipo']}, admin_type: {data['admin_type']}, "
                f"valor_total: R$ {data['valor_total']:.2f}, "
                f"fornecedor: {data.get('fornecedor_nome', 'N/A')}, "
                f"numero: {data.get('numero_documento', 'N/A')}"
            )
        else:
            logger.info(
                f"AdminDocumentExtractor: documento processado - "
                f"subtipo: {data['subtipo']}, admin_type: {data['admin_type']}, "
                f"sem valor (documento administrativo puro), "
                f"fornecedor: {data.get('fornecedor_nome', 'N/A')}, "
                f"numero: {data.get('numero_documento', 'N/A')}"
            )

        return data
