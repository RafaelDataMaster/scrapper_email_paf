"""
Módulo de Filtros de E-mail para Ingestão de Notas Fiscais.

Este módulo implementa a "Filter Strategy" que decide se um e-mail deve
ser processado ou ignorado, baseado em regras de negócio derivadas do
diagnóstico da caixa de entrada (inbox_patterns.json).

Regras de Negócio:
1. Regra de Ouro: E-mails COM anexo válido (PDF/XML) SEMPRE são processados
2. E-mails SEM anexo: Processados apenas se têm indícios fortes + assunto relevante
3. Blacklist: Assuntos de SPAM/comunicados são descartados imediatamente
4. Status de leitura: NÃO usamos critério UNSEEN (e-mails lidos também são processados)

Autor: Sistema de Ingestão
Versão: 1.0.0
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class FilterDecision(Enum):
    """Resultado da decisão de filtragem."""
    PROCESS = "PROCESS"           # Deve ser processado
    SKIP_BLACKLIST = "SKIP_BLACKLIST"  # Ignorado por blacklist
    SKIP_NO_CONTENT = "SKIP_NO_CONTENT"  # Ignorado por falta de conteúdo relevante
    SKIP_NO_SUBJECT_MATCH = "SKIP_NO_SUBJECT_MATCH"  # Ignorado: tem indícios mas assunto não é de cobrança
    SKIP_SENDER_BLACKLIST = "SKIP_SENDER_BLACKLIST"  # Ignorado: remetente na blacklist


class ContentType(Enum):
    """Tipos de conteúdo detectados no e-mail."""
    COM_ANEXO = "COM_ANEXO"
    LINK_DOWNLOAD = "LINK_DOWNLOAD"
    LINK_COM_CODIGO = "LINK_COM_CODIGO"
    APENAS_CODIGO = "APENAS_CODIGO"
    IRRELEVANTE = "IRRELEVANTE"


@dataclass
class FilterResult:
    """Resultado detalhado da filtragem de um e-mail."""
    decision: FilterDecision
    reason: str
    subject: str = ""
    sender: str = ""
    content_type: Optional[ContentType] = None
    blacklist_match: Optional[str] = None
    whitelist_matches: List[str] = field(default_factory=list)
    sender_blacklist_match: Optional[str] = None

    @property
    def should_process(self) -> bool:
        """Retorna True se o e-mail deve ser processado."""
        return self.decision == FilterDecision.PROCESS

    def __str__(self) -> str:
        status = "✓ PROCESS" if self.should_process else f"✗ {self.decision.value}"
        return f"[{status}] {self.reason}"


class EmailFilter:
    """
    Filtro de e-mails para ingestão de notas fiscais.

    Implementa regras de negócio para decidir se um e-mail contém
    documentos fiscais relevantes para processamento.

    Uso:
        filter = EmailFilter()
        result = filter.should_process_email(email_metadata)
        if result.should_process:
            # processar e-mail
    """

    # =========================================================================
    # BLACKLIST: Padrões de assuntos que SEMPRE devem ser ignorados
    # =========================================================================
    BLACKLIST_PATTERNS: List[re.Pattern] = [
        # Comunicados e informativos genéricos
        re.compile(r'\b(feliz\s+)?(natal|ano\s*novo|páscoa|festas)\b', re.IGNORECASE),
        re.compile(r'\bcomunicado\b', re.IGNORECASE),
        re.compile(r'\b(horário|funcionamento|expediente)\b', re.IGNORECASE),
        re.compile(r'\bnews(letter)?\b', re.IGNORECASE),
        re.compile(r'\bnotícias\b', re.IGNORECASE),
        re.compile(r'\bconfira\b', re.IGNORECASE),  # "Confira o nosso horário"

        # Conversas de resposta sem anexo (apenas RE:/RES: sem conteúdo fiscal)
        # Nota: RES: sozinho não é blacklist, mas combinado com ausência de conteúdo, sim
        re.compile(r'^(re|res|fw|fwd|enc):\s*(re|res|fw|fwd|enc):', re.IGNORECASE),  # Múltiplos RE:RE:

        # Marketing e propaganda
        re.compile(r'\b(promoção|oferta|desconto)\b', re.IGNORECASE),
        re.compile(r'\binscreva-?se\b', re.IGNORECASE),
        re.compile(r'\bimpactar\s+seu\s+negócio\b', re.IGNORECASE),

        # Notificações genéricas sem valor fiscal
        re.compile(r'\bnotificação\s+de\s+regularização\b', re.IGNORECASE),
        re.compile(r'\baviso\s+de\s+vencimento\b', re.IGNORECASE),  # Genérico demais
        re.compile(r'\blembrete\s+aci\b', re.IGNORECASE),  # Associação comercial

        # Pré-cobranças sem documento (apenas aviso)
        re.compile(r'\bpré[\s-]?cobrança\b', re.IGNORECASE),

        # Conversas internas sem documento
        re.compile(r'\bajuste\s+(de\s+)?nf\b', re.IGNORECASE),  # Apenas discussão
        re.compile(r'\bdistrato\b', re.IGNORECASE),
    ]

    # =========================================================================
    # WHITELIST: Palavras-chave que indicam e-mail de cobrança/NF
    # (Usado para validar e-mails SEM anexo)
    # =========================================================================
    WHITELIST_SUBJECT_PATTERNS: List[re.Pattern] = [
        # Documentos fiscais explícitos
        re.compile(r'\bnota\s*fiscal\b', re.IGNORECASE),
        re.compile(r'\bnf[\s-]?e\b', re.IGNORECASE),
        re.compile(r'\bnf[\s-]?s[\s-]?e\b', re.IGNORECASE),
        re.compile(r'\bnfcom\b', re.IGNORECASE),
        re.compile(r'\bdanfe\b', re.IGNORECASE),

        # Cobranças e pagamentos
        re.compile(r'\bfatura\b', re.IGNORECASE),
        re.compile(r'\bboleto\b', re.IGNORECASE),
        re.compile(r'\bcobrança\b', re.IGNORECASE),
        re.compile(r'\bpagamento\b', re.IGNORECASE),
        re.compile(r'\bvencimento\b', re.IGNORECASE),
        re.compile(r'\bdébito\b', re.IGNORECASE),
        re.compile(r'\bdívida\b', re.IGNORECASE),

        # Ações relacionadas a renovação/contrato
        re.compile(r'\brenovação\b', re.IGNORECASE),
        re.compile(r'\bcontrato\b', re.IGNORECASE),
        re.compile(r'\bmensalidade\b', re.IGNORECASE),
        re.compile(r'\bassinatura\b', re.IGNORECASE),
        re.compile(r'\baluguel\b', re.IGNORECASE),

        # Energia e telecom (comum ter NF via link)
        re.compile(r'\b(energia|luz|cemig|edp|conta\s+de\s+luz)\b', re.IGNORECASE),
        re.compile(r'\b(telecom|internet|fibra)\b', re.IGNORECASE),

        # Indicadores de envio de documento
        re.compile(r'\benvio\s+de\b', re.IGNORECASE),
        re.compile(r'\bsua\s+(fatura|conta|nf)\b', re.IGNORECASE),
        re.compile(r'\bfaturamento\b', re.IGNORECASE),
        re.compile(r'\bdocumento\b', re.IGNORECASE),
    ]

    # =========================================================================
    # SENDER BLACKLIST: Domínios/remetentes que SEMPRE devem ser ignorados
    # =========================================================================
    SENDER_BLACKLIST_PATTERNS: List[re.Pattern] = [
        # Marketing e newsletters
        re.compile(r'@(mail\.)?mailchimp\.com$', re.IGNORECASE),
        re.compile(r'@(mail\.)?sendgrid\.(net|com)$', re.IGNORECASE),
        re.compile(r'@(email\.)?hubspot\.com$', re.IGNORECASE),
        re.compile(r'@(mail\.)?rdstation\.com\.br$', re.IGNORECASE),
        re.compile(r'@(e\.)?mailjet\.com$', re.IGNORECASE),
        re.compile(r'noreply@.*\.marketing\.', re.IGNORECASE),
        re.compile(r'newsletter@', re.IGNORECASE),
        re.compile(r'marketing@', re.IGNORECASE),
        re.compile(r'promocoes@', re.IGNORECASE),
        re.compile(r'ofertas@', re.IGNORECASE),

        # Notificações de sistemas não-fiscais
        re.compile(r'@.*\.slack\.com$', re.IGNORECASE),
        re.compile(r'@.*\.atlassian\.(com|net)$', re.IGNORECASE),
        re.compile(r'@github\.com$', re.IGNORECASE),
        re.compile(r'@linkedin\.com$', re.IGNORECASE),
        re.compile(r'@facebookmail\.com$', re.IGNORECASE),

        # Suporte/tickets genéricos (podem gerar falsos positivos)
        re.compile(r'@.*zendesk\.com$', re.IGNORECASE),
        re.compile(r'@freshdesk\.com$', re.IGNORECASE),
    ]

    # =========================================================================
    # SENDER WHITELIST: Domínios/remetentes que indicam conteúdo fiscal
    # (Usado para dar prioridade - não é obrigatório estar na lista)
    # =========================================================================
    SENDER_WHITELIST_PATTERNS: List[re.Pattern] = [
        # Sistemas de NF-e conhecidos
        re.compile(r'@.*nfe\.fazenda\.gov\.br$', re.IGNORECASE),
        re.compile(r'@.*\.gov\.br$', re.IGNORECASE),  # Domínios governamentais
        re.compile(r'@.*sefaz.*\.gov\.br$', re.IGNORECASE),
        re.compile(r'@.*prefeitura.*\.gov\.br$', re.IGNORECASE),

        # ERPs e sistemas de faturamento
        re.compile(r'@.*omie\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*bling\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*tiny\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*contaazul\.com$', re.IGNORECASE),
        re.compile(r'@.*enotas\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*nfe\.io$', re.IGNORECASE),
        re.compile(r'@.*plugnotas\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*tecnospeed\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*totvs\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*sankhya\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*senior\.com\.br$', re.IGNORECASE),

        # Concessionárias e utilities
        re.compile(r'@.*cemig\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*cpfl\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*copel\.com$', re.IGNORECASE),
        re.compile(r'@.*sabesp\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*vivo\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*claro\.com\.br$', re.IGNORECASE),
        re.compile(r'@.*tim\.com\.br$', re.IGNORECASE),

        # Padrões genéricos de faturamento
        re.compile(r'faturamento@', re.IGNORECASE),
        re.compile(r'cobranca@', re.IGNORECASE),
        re.compile(r'financeiro@', re.IGNORECASE),
        re.compile(r'nfe@', re.IGNORECASE),
        re.compile(r'nfse@', re.IGNORECASE),
        re.compile(r'notafiscal@', re.IGNORECASE),
        re.compile(r'boleto@', re.IGNORECASE),
    ]

    # =========================================================================
    # EXTENSÕES VÁLIDAS DE ANEXO
    # =========================================================================
    VALID_ATTACHMENT_EXTENSIONS: Set[str] = {
        '.pdf', '.xml', '.zip', '.rar', '.7z'
    }

    def __init__(
        self,
        custom_blacklist: Optional[List[str]] = None,
        custom_whitelist: Optional[List[str]] = None,
        sender_blacklist: Optional[List[str]] = None,
        sender_whitelist: Optional[List[str]] = None,
        strict_mode: bool = False,
    ):
        """
        Inicializa o filtro de e-mails.

        Args:
            custom_blacklist: Padrões adicionais para blacklist de assunto (regex strings)
            custom_whitelist: Palavras-chave adicionais para whitelist de assunto (regex strings)
            sender_blacklist: Padrões adicionais para blacklist de remetente (regex strings)
            sender_whitelist: Padrões adicionais para whitelist de remetente (regex strings)
            strict_mode: Se True, requer correspondência mais forte para processar
        """
        self.strict_mode = strict_mode

        # Adiciona padrões customizados para assunto
        self._blacklist = list(self.BLACKLIST_PATTERNS)
        self._whitelist = list(self.WHITELIST_SUBJECT_PATTERNS)

        # Adiciona padrões customizados para remetente
        self._sender_blacklist = list(self.SENDER_BLACKLIST_PATTERNS)
        self._sender_whitelist = list(self.SENDER_WHITELIST_PATTERNS)

        if custom_blacklist:
            for pattern in custom_blacklist:
                self._blacklist.append(re.compile(pattern, re.IGNORECASE))

        if custom_whitelist:
            for pattern in custom_whitelist:
                self._whitelist.append(re.compile(pattern, re.IGNORECASE))

        if sender_blacklist:
            for pattern in sender_blacklist:
                self._sender_blacklist.append(re.compile(pattern, re.IGNORECASE))

        if sender_whitelist:
            for pattern in sender_whitelist:
                self._sender_whitelist.append(re.compile(pattern, re.IGNORECASE))

    def should_process_email(self, email_metadata: Dict[str, Any]) -> FilterResult:
        """
        Decide se um e-mail deve ser processado para ingestão.

        Esta é a função principal de filtragem que implementa todas as
        regras de negócio para classificação de e-mails.

        Args:
            email_metadata: Dicionário com metadados do e-mail:
                - subject: Assunto do e-mail
                - has_attachment: bool - Se tem anexo válido
                - has_links_nfe: bool - Se tem links de NF-e no corpo
                - has_verification_code: bool - Se tem código de verificação
                - content_type: str - Tipo de conteúdo (opcional)
                - sender_address: str - Endereço do remetente (opcional)
                - attachments: List[str] - Lista de nomes de anexos (opcional)

        Returns:
            FilterResult com a decisão e justificativa
        """
        subject = email_metadata.get('subject', '') or ''
        sender = email_metadata.get('sender_address', '') or ''
        has_attachment = email_metadata.get('has_attachment', False)
        has_links_nfe = email_metadata.get('has_links_nfe', False)
        has_verification_code = email_metadata.get('has_verification_code', False)
        content_type_str = email_metadata.get('content_type', '')

        # Determina o tipo de conteúdo
        content_type = self._parse_content_type(content_type_str)

        # Verifica anexos válidos se lista de anexos fornecida
        if 'attachments' in email_metadata:
            has_attachment = self._has_valid_attachment(email_metadata['attachments'])

        # =================================================================
        # REGRA 0: Verificar Sender Blacklist PRIMEIRO (exceto se tem anexo)
        # Remetentes de marketing/spam são descartados mesmo com links
        # =================================================================
        if not has_attachment:
            sender_blacklist_match = self._check_sender_blacklist(sender)
            if sender_blacklist_match:
                return FilterResult(
                    decision=FilterDecision.SKIP_SENDER_BLACKLIST,
                    reason=f"Remetente corresponde à blacklist: '{sender_blacklist_match}'",
                    subject=subject,
                    sender=sender,
                    content_type=content_type,
                    sender_blacklist_match=sender_blacklist_match,
                )

        # =================================================================
        # REGRA 1 (Regra de Ouro): Anexo válido = SEMPRE processar
        # =================================================================
        if has_attachment:
            return FilterResult(
                decision=FilterDecision.PROCESS,
                reason="E-mail possui anexo válido (PDF/XML)",
                subject=subject,
                sender=sender,
                content_type=content_type,
            )

        # =================================================================
        # REGRA 3: Verificar Blacklist de assunto ANTES de processar sem anexo
        # =================================================================
        blacklist_match = self._check_blacklist(subject)
        if blacklist_match:
            return FilterResult(
                decision=FilterDecision.SKIP_BLACKLIST,
                reason=f"Assunto corresponde à blacklist: '{blacklist_match}'",
                subject=subject,
                sender=sender,
                content_type=content_type,
                blacklist_match=blacklist_match,
            )

        # =================================================================
        # REGRA 2: E-mails SEM anexo - verificar indícios + assunto
        # =================================================================
        has_strong_indicators = has_links_nfe or has_verification_code

        if not has_strong_indicators:
            return FilterResult(
                decision=FilterDecision.SKIP_NO_CONTENT,
                reason="Sem anexo e sem indícios de NF-e (links ou códigos)",
                subject=subject,
                sender=sender,
                content_type=content_type,
            )

        # Tem indícios - verifica se remetente é de fonte confiável (whitelist)
        sender_in_whitelist = self._check_sender_whitelist(sender)

        # Verifica se assunto é relevante
        whitelist_matches = self._check_whitelist(subject)

        # Se remetente é confiável OU assunto é relevante, processa
        if whitelist_matches or sender_in_whitelist:
            indicator_type = "link de download" if has_links_nfe else "código de verificação"
            reason_parts = []
            if sender_in_whitelist:
                reason_parts.append(f"remetente confiável ({sender_in_whitelist})")
            if whitelist_matches:
                reason_parts.append(f"assunto relevante: {', '.join(whitelist_matches)}")

            return FilterResult(
                decision=FilterDecision.PROCESS,
                reason=f"E-mail com {indicator_type} e {' e '.join(reason_parts)}",
                subject=subject,
                sender=sender,
                content_type=content_type,
                whitelist_matches=whitelist_matches,
            )

        # Tem indícios MAS assunto não é de cobrança e remetente não é confiável
        # Este é o caso do falso positivo: "Evolua | Confira o nosso horário"
        return FilterResult(
            decision=FilterDecision.SKIP_NO_SUBJECT_MATCH,
            reason="Tem indícios de NF-e mas assunto não corresponde a cobrança/fatura",
            subject=subject,
            sender=sender,
            content_type=content_type,
        )

    def _check_sender_blacklist(self, sender: str) -> Optional[str]:
        """
        Verifica se o remetente corresponde a algum padrão da blacklist.

        Args:
            sender: Endereço de e-mail do remetente

        Returns:
            O padrão correspondente ou None se não houver match
        """
        if not sender:
            return None

        for pattern in self._sender_blacklist:
            if pattern.search(sender):
                return pattern.pattern

        return None

    def _check_sender_whitelist(self, sender: str) -> Optional[str]:
        """
        Verifica se o remetente corresponde a algum padrão da whitelist.

        Args:
            sender: Endereço de e-mail do remetente

        Returns:
            O padrão correspondente ou None se não houver match
        """
        if not sender:
            return None

        for pattern in self._sender_whitelist:
            if pattern.search(sender):
                return pattern.pattern

        return None

    def _check_blacklist(self, subject: str) -> Optional[str]:
        """
        Verifica se o assunto corresponde a algum padrão da blacklist.

        Args:
            subject: Assunto do e-mail

        Returns:
            String com o padrão encontrado ou None
        """
        for pattern in self._blacklist:
            match = pattern.search(subject)
            if match:
                return match.group()
        return None

    def _check_whitelist(self, subject: str) -> List[str]:
        """
        Verifica quais palavras-chave da whitelist estão no assunto.

        Args:
            subject: Assunto do e-mail

        Returns:
            Lista de palavras-chave encontradas
        """
        matches = []
        for pattern in self._whitelist:
            match = pattern.search(subject)
            if match:
                matches.append(match.group())
        return matches

    def _has_valid_attachment(self, attachments: List[str]) -> bool:
        """
        Verifica se há anexos com extensões válidas.

        Args:
            attachments: Lista de nomes de arquivos anexados

        Returns:
            True se houver pelo menos um anexo válido
        """
        if not attachments:
            return False

        for filename in attachments:
            if not filename:
                continue
            # Extrai extensão
            ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            if ext in self.VALID_ATTACHMENT_EXTENSIONS:
                return True

        return False

    def _parse_content_type(self, content_type_str: str) -> Optional[ContentType]:
        """
        Converte string de content_type para enum.

        Args:
            content_type_str: String do tipo de conteúdo

        Returns:
            ContentType enum ou None
        """
        if not content_type_str:
            return None

        try:
            return ContentType(content_type_str)
        except ValueError:
            return None

    def filter_batch(
        self,
        emails: List[Dict[str, Any]],
        log_decisions: bool = True,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Filtra uma lista de e-mails em lote.

        Args:
            emails: Lista de metadados de e-mails
            log_decisions: Se True, loga cada decisão

        Returns:
            Tupla (e-mails a processar, e-mails ignorados)
        """
        to_process = []
        to_skip = []

        stats = {
            FilterDecision.PROCESS: 0,
            FilterDecision.SKIP_BLACKLIST: 0,
            FilterDecision.SKIP_NO_CONTENT: 0,
            FilterDecision.SKIP_NO_SUBJECT_MATCH: 0,
        }

        for email in emails:
            result = self.should_process_email(email)
            stats[result.decision] += 1

            if log_decisions:
                logger.debug(f"{result} - Subject: {result.subject[:60]}...")

            if result.should_process:
                # Adiciona resultado ao metadata para uso posterior
                email['_filter_result'] = result
                to_process.append(email)
            else:
                email['_filter_result'] = result
                to_skip.append(email)

        # Log resumo
        logger.info(
            f"Filtro concluído: {stats[FilterDecision.PROCESS]} processar, "
            f"{stats[FilterDecision.SKIP_BLACKLIST]} blacklist, "
            f"{stats[FilterDecision.SKIP_NO_CONTENT]} sem conteúdo, "
            f"{stats[FilterDecision.SKIP_NO_SUBJECT_MATCH]} assunto irrelevante"
        )

        return to_process, to_skip


# =============================================================================
# FUNÇÃO DE CONVENIÊNCIA
# =============================================================================

def should_process_email(email_metadata: Dict[str, Any]) -> bool:
    """
    Função de conveniência para verificar se e-mail deve ser processado.

    Esta função cria um filtro com configurações padrão e retorna
    apenas um booleano simples para facilitar integração.

    Args:
        email_metadata: Dicionário com metadados do e-mail

    Returns:
        True se o e-mail deve ser processado, False caso contrário

    Exemplo:
        >>> metadata = {
        ...     'subject': 'ENC: Renovação de Escritório Virtual',
        ...     'has_attachment': False,
        ...     'has_links_nfe': True,
        ...     'has_verification_code': False,
        ... }
        >>> should_process_email(metadata)
        True

        >>> metadata = {
        ...     'subject': 'Evolua | Confira o nosso horário de funcionamento',
        ...     'has_attachment': False,
        ...     'has_links_nfe': False,
        ...     'has_verification_code': True,  # Código no rodapé - falso positivo!
        ... }
        >>> should_process_email(metadata)
        False
    """
    filter_instance = EmailFilter()
    result = filter_instance.should_process_email(email_metadata)
    return result.should_process


def get_filter_decision(email_metadata: Dict[str, Any]) -> FilterResult:
    """
    Retorna o resultado detalhado da filtragem.

    Útil para debugging e logging detalhado.

    Args:
        email_metadata: Dicionário com metadados do e-mail

    Returns:
        FilterResult com decisão e justificativa detalhada
    """
    filter_instance = EmailFilter()
    return filter_instance.should_process_email(email_metadata)


# =============================================================================
# INSTÂNCIA GLOBAL (SINGLETON)
# =============================================================================

_default_filter: Optional[EmailFilter] = None


def get_default_filter() -> EmailFilter:
    """
    Retorna instância global do filtro.

    Útil para evitar recriar o filtro em cada chamada quando
    usado em loops de processamento.

    Returns:
        Instância singleton do EmailFilter
    """
    global _default_filter
    if _default_filter is None:
        _default_filter = EmailFilter()
    return _default_filter


# =============================================================================
# TESTES INLINE (para validação rápida)
# =============================================================================

if __name__ == "__main__":
    # Configura logging para ver output
    logging.basicConfig(level=logging.DEBUG)

    # Casos de teste baseados no inbox_patterns.json
    test_cases = [
        # DEVE PROCESSAR: Anexo válido
        {
            "subject": "ENC: Sua fatura de energia da VSG Energia",
            "has_attachment": True,
            "has_links_nfe": False,
            "has_verification_code": False,
            "expected": True,
            "reason": "Tem anexo válido",
        },
        # DEVE PROCESSAR: Link de download + assunto de renovação
        {
            "subject": "ENC: Renovação de Escritório Virtual - Lembrete de Cortesia",
            "has_attachment": False,
            "has_links_nfe": True,
            "has_verification_code": False,
            "content_type": "LINK_DOWNLOAD",
            "expected": True,
            "reason": "Link de download + assunto 'Renovação'",
        },
        # DEVE PROCESSAR: Código de verificação + assunto de boleto
        {
            "subject": "Evolua | Lembrete: Seu boleto vence hoje!",
            "has_attachment": False,
            "has_links_nfe": False,
            "has_verification_code": True,
            "content_type": "APENAS_CODIGO",
            "expected": True,
            "reason": "Código de verificação + assunto 'boleto'",
        },
        # NÃO PROCESSAR: Código mas assunto é SPAM
        {
            "subject": "Evolua | Confira o nosso horário de funcionamento",
            "has_attachment": False,
            "has_links_nfe": False,
            "has_verification_code": True,
            "expected": False,
            "reason": "Falso positivo - 'Confira' está na blacklist",
        },
        # NÃO PROCESSAR: Conversa sem anexo
        {
            "subject": "RES: KM Delvani - Dezembro/25",
            "has_attachment": False,
            "has_links_nfe": False,
            "has_verification_code": False,
            "content_type": "IRRELEVANTE",
            "expected": False,
            "reason": "Conversa sem indícios de NF",
        },
        # NÃO PROCESSAR: Comunicado genérico
        {
            "subject": "Notícias que podem impactar seu negócio",
            "has_attachment": False,
            "has_links_nfe": False,
            "has_verification_code": False,
            "expected": False,
            "reason": "Newsletter - blacklist",
        },
        # DEVE PROCESSAR: CEMIG FATURA com anexo
        {
            "subject": "CEMIG FATURA ONLINE - 214687921",
            "has_attachment": True,
            "has_links_nfe": False,
            "has_verification_code": False,
            "expected": True,
            "reason": "Anexo de fatura CEMIG",
        },
        # DEVE PROCESSAR: NFS-e com boleto no assunto
        {
            "subject": "VCOM TECNOLOGIA - BPO - NFS-e  + Boleto Nº 3494",
            "has_attachment": True,
            "has_links_nfe": False,
            "has_verification_code": False,
            "expected": True,
            "reason": "Anexo de NFS-e + Boleto",
        },
        # NÃO PROCESSAR: Pré-cobrança sem documento
        {
            "subject": "PRÉ COBRANÇA - ATIVE TELECOMUNICACOES S.A",
            "has_attachment": False,
            "has_links_nfe": False,
            "has_verification_code": False,
            "expected": False,
            "reason": "Pré-cobrança na blacklist",
        },
    ]

    print("=" * 70)
    print("TESTES DO FILTRO DE E-MAIL")
    print("=" * 70)

    filter_instance = EmailFilter()
    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        result = filter_instance.should_process_email(test)
        actual = result.should_process
        expected = test["expected"]

        status = "✓ PASS" if actual == expected else "✗ FAIL"
        if actual == expected:
            passed += 1
        else:
            failed += 1

        print(f"\nTeste {i}: {status}")
        print(f"  Subject: {test['subject'][:50]}...")
        print(f"  Esperado: {expected}, Obtido: {actual}")
        print(f"  Motivo esperado: {test['reason']}")
        print(f"  Resultado: {result}")

    print("\n" + "=" * 70)
    print(f"RESULTADO: {passed}/{len(test_cases)} testes passaram")
    if failed > 0:
        print(f"ATENÇÃO: {failed} teste(s) falharam!")
    print("=" * 70)
