"""
Extrator de dados do corpo de e-mail (HTML/texto).

Este módulo implementa a extração de valores monetários, datas de vencimento,
números de nota e links de NF-e do corpo do e-mail quando não há anexo PDF/XML.

Casos de uso:
1. E-mails da Omie: Boleto em PDF, mas NF-e é um link
2. E-mails de Prefeituras: Notificação com link para download da NF-e
3. E-mails ProScore: Faturamento com dados no corpo

Princípios SOLID:
- SRP: Foca apenas em extração de dados do corpo de e-mail
- OCP: Extensível via novos padrões sem modificar código existente
- DIP: Depende de abstrações (interfaces), não implementações
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EmailBodyExtractionResult:
    """
    Resultado da extração de dados do corpo do e-mail.

    Attributes:
        valor_total: Valor monetário extraído (maior valor encontrado)
        valores_encontrados: Lista de todos os valores encontrados
        vencimento: Data de vencimento extraída
        numero_nota: Número da nota fiscal
        link_nfe: Link para acesso/download da NF-e
        codigo_verificacao: Código de autenticação
        fornecedor_nome: Nome do fornecedor (se identificado)
        confianca: Score de confiança (0.0 a 1.0)
        fonte: Origem do dado ('subject', 'body_text', 'body_html')
    """
    valor_total: float = 0.0
    valores_encontrados: List[float] = field(default_factory=list)
    vencimento: Optional[str] = None
    numero_nota: Optional[str] = None
    link_nfe: Optional[str] = None
    codigo_verificacao: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    confianca: float = 0.0
    fonte: str = ""

    def has_valor(self) -> bool:
        """Retorna True se encontrou algum valor monetário."""
        return self.valor_total > 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            'valor_total': self.valor_total,
            'valores_encontrados': self.valores_encontrados,
            'vencimento': self.vencimento,
            'numero_nota': self.numero_nota,
            'link_nfe': self.link_nfe,
            'codigo_verificacao': self.codigo_verificacao,
            'fornecedor_nome': self.fornecedor_nome,
            'confianca': self.confianca,
            'fonte': self.fonte,
        }


class HTMLTextExtractor(HTMLParser):
    """
    Parser HTML para extrair texto limpo removendo tags.
    """

    def __init__(self):
        super().__init__()
        self.text_parts: List[str] = []
        self.skip_tags = {'script', 'style', 'head', 'meta', 'link'}
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.skip_tags:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    def get_text(self) -> str:
        return " ".join(self.text_parts)


class EmailBodyExtractor:
    """
    Extrator de dados do corpo de e-mail.

    Processa HTML e texto plano do corpo do e-mail para extrair:
    - Valores monetários (R$ XXX,XX)
    - Datas de vencimento
    - Números de nota fiscal
    - Links de NF-e

    Usage:
        extractor = EmailBodyExtractor()
        result = extractor.extract(body_text, subject)
    """

    # Padrões de valores monetários (formato brasileiro)
    VALOR_PATTERNS = [
        # R$ 1.234,56 ou R$1234,56
        r'R\$\s*([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})',
        # Valor: 1.234,56 ou Valor 1234,56
        r'[Vv]alor[:\s]+(?:R\$\s*)?([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})',
        # Total: R$ 1.234,56
        r'[Tt]otal[:\s]+(?:R\$\s*)?([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})',
        # Valor da NF: 1.234,56
        r'[Vv]alor\s+(?:da\s+)?(?:NF|NFe|NFS-?e|Nota)[:\s]+(?:R\$\s*)?([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})',
        # Valor do Boleto: 1.234,56
        r'[Vv]alor\s+(?:do\s+)?[Bb]oleto[:\s]+(?:R\$\s*)?([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})',
        # TOTAL A PAGAR: 1.234,56
        r'TOTAL\s+A\s+PAGAR[:\s]+(?:R\$\s*)?([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})',
        # Valor Líquido: 1.234,56
        r'[Vv]alor\s+[Ll][íi]quido[:\s]+(?:R\$\s*)?([\d]{1,3}(?:\.[\d]{3})*,[\d]{2})',
    ]

    # Padrões de vencimento
    VENCIMENTO_PATTERNS = [
        # Vencimento: 29/12/2025 ou Venc.: 29/12
        r'[Vv]enc(?:imento)?\.?[:\s]+(\d{1,2}[/\-\.]\d{1,2}(?:[/\-\.]\d{2,4})?)',
        # Data de Vencimento: 29/12/2025
        r'[Dd]ata\s+(?:de\s+)?[Vv]encimento[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        # Vence em: 29/12/2025
        r'[Vv]ence\s+(?:em)?[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        # Até 29/12/2025
        r'[Aa]t[ée]\s+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        # "- 29/12 Seg" (formato Omie)
        r'[-–]\s*(\d{1,2}[/\-\.]\d{1,2})\s*(?:Seg|Ter|Qua|Qui|Sex|Sáb|Sab|Dom)',
    ]

    # Padrões de número de nota no assunto/corpo
    NUMERO_NOTA_PATTERNS = [
        # NFS-e nº 3406 ou NFSe nº 3406
        r'NFS-?[Ee]\s*(?:n[ºo°]\.?\s*)?(\d{3,15})',
        # NF-e nº 12345 ou NFe 12345
        r'NF-?[Ee]?\s*(?:n[ºo°]\.?\s*)?(\d{3,15})',
        # Nota Fiscal 12345 ou Nota Fiscal nº 12345
        r'[Nn]ota\s+[Ff]iscal\s*(?:n[ºo°]\.?\s*)?(\d{3,15})',
        # Fatura 50446 ou Fatura nº 50446
        r'[Ff]atura\s*(?:n[ºo°]\.?\s*)?(\d{3,15})',
        # Nº 3406 (após contexto de NF)
        r'(?:NF|Nota|Fatura)[^\d]{0,20}n[ºo°]\.?\s*(\d{3,15})',
    ]

    # Domínios conhecidos de NF-e
    DOMINIOS_NFE = [
        'nfe.prefeitura.sp.gov.br',
        'nfse.goiania.go.gov.br',
        'iss.campinas.sp.gov.br',
        'nfe.salvador.ba.gov.br',
        'notacarioca.rio.gov.br',
        'nfse.curitiba.pr.gov.br',
        'click.omie.com.br',
        'omie.com.br',
        'proscore.com.br',
    ]

    # Links de NF-e (padrões genéricos)
    LINK_NFE_PATTERNS = [
        # Links de prefeituras
        r'(https?://[^\s<>"]*(?:nf[es]|nota|verificacao|autenticidade)[^\s<>"]*)',
        # Links Omie
        r'(https?://click\.omie\.com\.br[^\s<>"]+)',
        # Links genéricos com "nf" ou "nota"
        r'(https?://[^\s<>"]*(?:/nf/|/nota/|/verificar/)[^\s<>"]*)',
    ]

    def __init__(self):
        """Inicializa o extrator."""
        pass

    def extract(
        self,
        body_text: Optional[str] = None,
        subject: Optional[str] = None,
        html_content: Optional[str] = None
    ) -> EmailBodyExtractionResult:
        """
        Extrai dados do corpo do e-mail.

        Args:
            body_text: Corpo do e-mail em texto plano
            subject: Assunto do e-mail
            html_content: Corpo do e-mail em HTML (opcional)

        Returns:
            EmailBodyExtractionResult com os dados extraídos
        """
        result = EmailBodyExtractionResult()

        # Separa HTML do texto se estiver junto
        if body_text and "--- HTML CONTENT ---" in body_text:
            parts = body_text.split("--- HTML CONTENT ---", 1)
            text_part = parts[0].strip()
            html_part = parts[1].strip() if len(parts) > 1 else ""
        else:
            text_part = body_text or ""
            html_part = html_content or ""

        # Extrai texto limpo do HTML
        html_text = ""
        if html_part:
            html_text = self._extract_text_from_html(html_part)

        # Combina todas as fontes de texto
        all_text = f"{subject or ''} {text_part} {html_text}"

        # 1. Extrai valores monetários
        valores = self._extract_valores(all_text)
        if valores:
            result.valores_encontrados = sorted(valores, reverse=True)
            # Usa o maior valor como valor principal (geralmente é o total)
            result.valor_total = result.valores_encontrados[0]
            result.confianca = self._calculate_valor_confidence(result.valor_total, all_text)

        # 2. Extrai vencimento
        result.vencimento = self._extract_vencimento(all_text, subject)

        # 3. Extrai número da nota (prioriza assunto)
        result.numero_nota = self._extract_numero_nota(subject) or self._extract_numero_nota(all_text)

        # 4. Extrai link de NF-e
        result.link_nfe = self._extract_link_nfe(all_text)

        # 5. Extrai código de verificação
        if result.link_nfe:
            result.codigo_verificacao = self._extract_codigo_verificacao(result.link_nfe)
        if not result.codigo_verificacao:
            result.codigo_verificacao = self._extract_codigo_from_text(all_text)

        # 6. Tenta extrair fornecedor do assunto
        result.fornecedor_nome = self._extract_fornecedor_from_subject(subject)

        # Define fonte principal
        if result.valor_total > 0:
            if subject and str(result.valor_total).replace('.', ',') in (subject or ''):
                result.fonte = 'subject'
            elif result.valor_total in self._extract_valores(text_part):
                result.fonte = 'body_text'
            else:
                result.fonte = 'body_html'

        return result

    def _extract_text_from_html(self, html: str) -> str:
        """
        Extrai texto limpo do HTML.

        Args:
            html: Conteúdo HTML

        Returns:
            Texto limpo sem tags HTML
        """
        try:
            parser = HTMLTextExtractor()
            parser.feed(html)
            return parser.get_text()
        except Exception as e:
            logger.warning(f"Erro ao parsear HTML: {e}")
            # Fallback: remove tags com regex
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text)
            return text.strip()

    def _extract_valores(self, text: str) -> List[float]:
        """
        Extrai todos os valores monetários do texto.

        Args:
            text: Texto para análise

        Returns:
            Lista de valores encontrados (em float)
        """
        valores = []

        for pattern in self.VALOR_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    # Converte formato brasileiro para float
                    valor_str = match.replace('.', '').replace(',', '.')
                    valor = float(valor_str)
                    if 0.01 <= valor <= 10_000_000:  # Valores razoáveis
                        valores.append(valor)
                except (ValueError, AttributeError):
                    continue

        # Remove duplicatas mantendo ordem
        seen = set()
        unique_valores = []
        for v in valores:
            if v not in seen:
                seen.add(v)
                unique_valores.append(v)

        return unique_valores

    def _extract_vencimento(self, text: str, subject: Optional[str] = None) -> Optional[str]:
        """
        Extrai data de vencimento do texto.

        Args:
            text: Texto para análise
            subject: Assunto do e-mail (priorizado)

        Returns:
            Data em formato ISO (YYYY-MM-DD) ou None
        """
        # Prioriza assunto
        sources = [subject or '', text]

        for source in sources:
            for pattern in self.VENCIMENTO_PATTERNS:
                match = re.search(pattern, source, re.IGNORECASE)
                if match:
                    date_str = match.group(1)
                    normalized = self._normalize_date(date_str)
                    if normalized:
                        return normalized

        return None

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """
        Normaliza data para formato ISO (YYYY-MM-DD).

        Args:
            date_str: Data em formato brasileiro

        Returns:
            Data em formato ISO ou None
        """
        if not date_str:
            return None

        # Remove espaços
        date_str = date_str.strip()

        # Padrão completo: DD/MM/YYYY
        match = re.match(r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})', date_str)
        if match:
            dia, mes, ano = match.groups()

            # Converte ano de 2 dígitos
            if len(ano) == 2:
                ano_int = int(ano)
                ano = f"20{ano}" if ano_int <= 50 else f"19{ano}"

            try:
                dia_int = int(dia)
                mes_int = int(mes)
                ano_int = int(ano)

                if 1 <= dia_int <= 31 and 1 <= mes_int <= 12:
                    return f"{ano_int:04d}-{mes_int:02d}-{dia_int:02d}"
            except ValueError:
                pass

        # Padrão parcial: DD/MM (assume ano atual)
        match = re.match(r'(\d{1,2})[/\-\.](\d{1,2})$', date_str)
        if match:
            dia, mes = match.groups()
            ano = datetime.now().year

            try:
                dia_int = int(dia)
                mes_int = int(mes)

                if 1 <= dia_int <= 31 and 1 <= mes_int <= 12:
                    # Se o mês já passou, assume próximo ano
                    if mes_int < datetime.now().month:
                        ano += 1
                    return f"{ano:04d}-{mes_int:02d}-{dia_int:02d}"
            except ValueError:
                pass

        return None

    def _extract_numero_nota(self, text: Optional[str]) -> Optional[str]:
        """
        Extrai número da nota fiscal do texto.

        Args:
            text: Texto para análise

        Returns:
            Número da nota ou None
        """
        if not text:
            return None

        for pattern in self.NUMERO_NOTA_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                numero = match.group(1)
                # Valida que não é apenas um ano
                if numero.isdigit() and len(numero) == 4 and numero.startswith('20'):
                    continue
                return numero

        return None

    def _extract_link_nfe(self, text: str) -> Optional[str]:
        """
        Extrai link de NF-e do texto.

        Args:
            text: Texto para análise

        Returns:
            URL do link ou None
        """
        # Prioriza domínios conhecidos
        for dominio in self.DOMINIOS_NFE:
            pattern = rf'(https?://[^\s<>"]*{re.escape(dominio)}[^\s<>"]*)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        # Padrões genéricos
        for pattern in self.LINK_NFE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_codigo_verificacao(self, link: str) -> Optional[str]:
        """
        Extrai código de verificação de um link de NF-e.

        Args:
            link: URL do link

        Returns:
            Código de verificação ou None
        """
        if not link:
            return None

        # Padrões de código em query string
        patterns = [
            r'[?&](?:verificacao|cod|codigo|auth|token)=([A-Za-z0-9]+)',
            r'/verificar/([A-Za-z0-9]+)',
            r'/v/([A-Za-z0-9]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, link, re.IGNORECASE)
            if match:
                codigo = match.group(1)
                if len(codigo) >= 4:  # Códigos válidos têm pelo menos 4 chars
                    return codigo

        return None

    def _extract_codigo_from_text(self, text: str) -> Optional[str]:
        """
        Extrai código de verificação do texto (quando não está no link).

        Args:
            text: Texto para análise

        Returns:
            Código de verificação ou None
        """
        patterns = [
            r'[Cc][óo]digo\s+(?:de\s+)?[Vv]erifica[çc][ãa]o[:\s]+([A-Za-z0-9]{4,12})',
            r'[Cc][óo]digo\s+(?:de\s+)?[Aa]utenticidade[:\s]+([A-Za-z0-9]{4,12})',
            r'[Vv]erifica[çc][ãa]o[:\s]+([A-Za-z0-9]{4,12})',
            r'[Aa]utenticar[:\s]+([A-Za-z0-9]{4,12})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        return None

    def _extract_fornecedor_from_subject(self, subject: Optional[str]) -> Optional[str]:
        """
        Tenta extrair nome do fornecedor do assunto.

        Args:
            subject: Assunto do e-mail

        Returns:
            Nome do fornecedor ou None
        """
        if not subject:
            return None

        # Padrões comuns no assunto (ordem de prioridade)
        patterns = [
            # "EMPRESA - BPO - Lembrete..." ou "EMPRESA - Fatura..."
            r'^([A-Z][A-Za-z0-9\s&\.]+?)\s*[-–]\s*(?:BPO|Fatura|Boleto|NF|Nota|Cobrança|Lembrete)',
            # "EMPRESA :: Faturamento..."
            r'^([A-Z][A-Za-z0-9\s&\.]+?)\s*::\s*',
            # "EMPRESA - Fatura..."
            r'^([A-Z][A-Za-z0-9\s&\.]+?)\s*[-–:]\s*(?:Fatura|Boleto|NF|Nota|Cobrança)',
            # "[EMPRESA] Fatura..."
            r'^\[([A-Za-z0-9\s&\.]+)\]\s*',
        ]

        for pattern in patterns:
            match = re.search(pattern, subject)
            if match:
                fornecedor = match.group(1).strip()
                # Filtra palavras genéricas e muito curtas
                palavras_invalidas = [
                    'sua', 'seu', 'a', 'o', 'de', 'da', 'do', 'res', 're', 'fw', 'fwd',
                    'enc', 'lembrete', 'aviso', 'urgente', 'importante'
                ]
                if fornecedor.lower() not in palavras_invalidas and len(fornecedor) > 3:
                    return fornecedor

        return None

    def _calculate_valor_confidence(self, valor: float, text: str) -> float:
        """
        Calcula score de confiança para o valor extraído.

        Args:
            valor: Valor extraído
            text: Texto original

        Returns:
            Score de 0.0 a 1.0
        """
        confidence = 0.5  # Base

        # Aumenta se encontrou contexto de "total" ou "valor"
        valor_str = f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        if re.search(rf'[Tt]otal[:\s]+R?\$?\s*{re.escape(valor_str)}', text):
            confidence += 0.3
        elif re.search(rf'[Vv]alor[:\s]+R?\$?\s*{re.escape(valor_str)}', text):
            confidence += 0.2

        # Aumenta se valor aparece múltiplas vezes
        if text.count(valor_str) > 1:
            confidence += 0.1

        # Diminui se há muitos valores diferentes
        valores = self._extract_valores(text)
        if len(valores) > 5:
            confidence -= 0.2

        return min(max(confidence, 0.0), 1.0)


def extract_from_email_body(
    body_text: Optional[str] = None,
    subject: Optional[str] = None,
    html_content: Optional[str] = None
) -> EmailBodyExtractionResult:
    """
    Função de conveniência para extrair dados do corpo de e-mail.

    Args:
        body_text: Corpo do e-mail em texto
        subject: Assunto do e-mail
        html_content: Corpo HTML (opcional)

    Returns:
        EmailBodyExtractionResult com dados extraídos
    """
    extractor = EmailBodyExtractor()
    return extractor.extract(body_text, subject, html_content)
