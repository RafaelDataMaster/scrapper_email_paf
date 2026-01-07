# scrapper/extractors/nfse_montes_claros.py
"""
Extrator específico para NFS-e do município de Montes Claros (MG).

Motivação:
- Notas de Montes Claros frequentemente incluem o texto:
    "nota.montesclaros.mg.gov.br/NFSe.Portal Nº NFSe:202500000015059"
  onde o número "202500000015059" é a forma canônica (longa) da NFS-e e
  não deve ser confundida com números curtos que aparecem no PDF (ex: "12").

Objetivo:
- Reconhecer com alta prioridade documentos de Montes Claros e extrair:
  cnpj_prestador, fornecedor_nome, numero_nota (forma longa quando presente),
  data_emissao, valor_total (ValorLiquidoNfse / ValorServicos), valor_iss, etc.

Implementação:
- Usa heurísticas específicas do layout observado em PDFs gerados pelo portal
  de Montes Claros e recai para padrões genéricos como fallback.
"""

import re
from typing import Any, Dict, Optional

from core.extractors import BaseExtractor, find_linha_digitavel, register_extractor
from extractors.utils import (
    normalize_text_for_extraction,
    parse_br_money,
    parse_date_br,
)


@register_extractor
class NfseCustomMontesClarosExtractor(BaseExtractor):
    """
    Extrator para notas de Montes Claros (MG).

    Critério de ativação:
    - Texto contém "MONTES CLAROS" (ou domínio nota.montesclaros.mg.gov.br), e
    - Indicadores típicos de NFS-e, e não apresenta linha digitável de boleto.
    """

    @classmethod
    def can_handle(cls, text: str) -> bool:
        if not text:
            return False

        t = (text or "").upper()
        # Indicadores fortes de Montes Claros
        if "MONTES CLAROS" in t or "NOTA.MONTESCLAROS.MG.GOV.BR" in t or "NOTA.MONTESCLAROS" in t:
            # Evitar confundir com boletos
            if find_linha_digitavel(text):
                return False
            # Confirma que é NFS-e
            if "NFSE" in t or "NOTA FISCAL DE SERVIÇO" in t or "NFS-E" in t or "CÓDIGO DE VERIFICAÇÃO" in t:
                return True
        return False

    def extract(self, text: str) -> Dict[str, Any]:
        text_norm = self._normalize_text(text or "")
        data: Dict[str, Any] = {"tipo_documento": "NFSE"}

        data["cnpj_prestador"] = self._extract_cnpj(text_norm)
        data["fornecedor_nome"] = self._extract_fornecedor_nome(text_norm)
        data["numero_nota"] = self._extract_numero_nota(text_norm)
        data["valor_total"] = self._extract_valor(text_norm)
        data["valor_iss"] = self._extract_valor_iss(text_norm)
        data["valor_ir"] = self._extract_ir(text_norm)
        data["valor_inss"] = self._extract_inss(text_norm)
        data["valor_csll"] = self._extract_csll(text_norm)
        data["data_emissao"] = self._extract_data_emissao(text_norm)
        data["vencimento"] = self._extract_vencimento(text_norm)
        data["valor_icms"] = self._extract_valor_icms(text_norm)
        data["base_calculo_icms"] = self._extract_base_calculo_icms(text_norm)

        return data

    def _normalize_text(self, text: str) -> str:
        return normalize_text_for_extraction(text)

    def _extract_cnpj(self, text: str) -> Optional[str]:
        # Procura o CNPJ do prestador (preferir próximo ao rótulo "Prestador" ou "PrestadorServico")
        # Padrão robusto, retorna formatado com pontos/ barra/ hífen
        m = re.search(r"(?:PrestadorServico|Prestador|Prestador\s*:\s*|Prestador\s+Servico|Prestador\s+Serviço)?\s*.*?(?:CNPJ|CPF)\s*[:\-\s]*([0-9\.\-/\s]{14,20})", text, re.IGNORECASE)
        if m:
            candidate = re.sub(r'\D', '', m.group(1))
            if len(candidate) == 14:
                return f"{candidate[:2]}.{candidate[2:5]}.{candidate[5:8]}/{candidate[8:12]}-{candidate[12:14]}"
        # Fallback: qualquer CNPJ no documento
        m2 = re.search(r"(\d{2}\D?\d{3}\D?\d{3}\D?\d{4}\D?\d{2})", text)
        if m2:
            c = re.sub(r'\D', '', m2.group(1))
            if len(c) == 14:
                return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:14]}"
        return None

    def _extract_numero_nota(self, text: str) -> Optional[str]:
        # Padrões específicos observados em Montes Claros:
        # "Nº NFSe:202500000015059" ou "Nº NFSe: 202500000015059"
        patterns = [
            r"N[º°o]?\s*NFSe\s*[:\-]?\s*([0-9]{12,20})",   # N° NFSe: 202500000015059
            r"N[º°o]?\s*NFSe[:\s]*\b([0-9]{12,20})\b",
            r"N[º°o]?\s*NFSe[:\s]*N[º°o]?\s*[:\s]*([0-9]{12,20})",
            r"\bN[Ff][Ss][Ee]\b[^0-9]{0,10}([0-9]{12,20})",  # NFSe ... 2025...
            # Também aceitar "Nº NFSe:" com pequeno ruído
        ]

        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()

        # Há casos onde aparece "Nº NFSe:202500000015059" sem espaço, já coberto.
        # Fallback: procurar sequências longas de 14-20 dígitos que pareçam número de nota
        m2 = re.search(r"\b(20\d{12,14}|20\d{10,14}|[0-9]{12,20})\b", text)
        if m2:
            candidate = m2.group(1)
            # evitar capturar datas/telefones curtos; exigir comprimento >= 12
            if len(re.sub(r'\D', '', candidate)) >= 12:
                return candidate

        # Por fim, tenta padrões compostos (ano/sequencial) como "2025/12" — só se não existir a forma longa
        m3 = re.search(r"(\d{4}[/\-]\d{1,6})", text)
        if m3:
            return m3.group(1).strip()

        return None

    def _extract_valor(self, text: str) -> float:
        # Padrões específicos que costumam aparecer em PDF de Montes Claros
        patterns = [
            r"Valor\s+dos\s+Serviços:\s*([\d\.,]+)",
            r"Valor\s+líquido\s+da\s+nota:\s*([\d\.,]+)",
            r"ValorLiquidoNfse[:\s]*R?\$?\s*([\d\.\,]{4,})",
            r"Valor\s+Liquido[:\s]*R?\$?\s*([\d\.\,]{4,})",
            r"ValorServicos[:\s]*R?\$?\s*([\d\.\,]{4,})",
            r"Valor\s*[:\s]*R\$\s*([\d\.\,]{1,})",
            r"Valor\s+Total[:\s]*R?\$?\s*([\d\.\,]{1,})",
            r"\bR\$\s*([\d\.\,]{1,})\b",
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                v = parse_br_money(m.group(1))
                if v and v > 0:
                    return v
        return 0.0

    def _extract_valor_iss(self, text: str) -> float:
        patterns = [
            r"ValorIss[:\s]*R?\$?\s*([\d\.\,]{1,})",
            r"Valor\s+ISS[:\s]*R?\$?\s*([\d\.\,]{1,})",
            r"ISS[:\s]*R?\$?\s*([\d\.\,]{1,})",
            r"Total\s+Aprox[:\s]*R?\$?\s*([\d\.\,]{1,})",  # sometimes in OutrasInformacoes
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                val = parse_br_money(m.group(1))
                if val is not None:
                    return val
        return 0.0

    def _extract_valor_generico(self, patterns, text: str) -> float:
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                val = parse_br_money(m.group(1))
                if val is not None:
                    return val
        return 0.0

    def _extract_ir(self, text: str) -> float:
        patterns = [r"Valor\s+IR[:\s]*R?\$?\s*([\d\.\,]{1,})", r"ValorIR[:\s]*R?\$?\s*([\d\.\,]{1,})"]
        return self._extract_valor_generico(patterns, text)

    def _extract_inss(self, text: str) -> float:
        patterns = [r"Valor\s+INSS[:\s]*R?\$?\s*([\d\.\,]{1,})", r"ValorINSS[:\s]*R?\$?\s*([\d\.\,]{1,})"]
        return self._extract_valor_generico(patterns, text)

    def _extract_csll(self, text: str) -> float:
        patterns = [r"Valor\s+CSLL[:\s]*R?\$?\s*([\d\.\,]{1,})", r"ValorCSLL[:\s]*R?\$?\s*([\d\.\,]{1,})"]
        return self._extract_valor_generico(patterns, text)

    def _extract_valor_icms(self, text: str) -> float:
        patterns = [r"Valor\s+ICMS[:\s]*R?\$?\s*([\d\.\,]{1,})", r"ICMS[:\s]*R?\$?\s*([\d\.\,]{1,})"]
        return self._extract_valor_generico(patterns, text)

    def _extract_base_calculo_icms(self, text: str) -> float:
        patterns = [r"BaseCalculo[:\s]*R?\$?\s*([\d\.\,]{1,})", r"Base\s+de\s+C[aá]lculo[:\s]*R?\$?\s*([\d\.\,]{1,})"]
        return self._extract_valor_generico(patterns, text)

    def _extract_data_emissao(self, text: str) -> Optional[str]:
        # Procura por datas com horário ISO ou dd/mm/yyyy
        # Exemplo encontrado: "Data Emissão:13/08/2025 - 03:09:53" ou "2025-08-13T03:09:53"
        m_iso = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", text)
        if m_iso:
            return m_iso.group(1).split("T")[0]
        m_iso2 = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m_iso2:
            return m_iso2.group(1)
        m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
        if m:
            return parse_date_br(m.group(1))
        return None

    def _extract_vencimento(self, text: str) -> Optional[str]:
        # Montes Claros NFS-e normalmente não trazem vencimento, manter como None
        # Mas tenta capturar se houver "Vencimento: DD/MM/YYYY"
        m = re.search(r"Vencimento[:\s]+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE)
        if m:
            return parse_date_br(m.group(1))
        return None

    def _extract_fornecedor_nome(self, text: str) -> Optional[str]:
        # Preferir RazaoSocial / NomeFantasia rótulos comuns em layout municipal
        m = re.search(r"Raz[ãa]o\s+Social[:\s\-]*([A-ZÀ-ÿ0-9\-\.\&\s\/]{4,120})", text, re.IGNORECASE)
        if m:
            nome = m.group(1).strip()
            if nome:
                return re.sub(r"\s+", " ", nome).strip()
        # Padrão após "Prestador" ou "PrestadorServico"
        m2 = re.search(r"(?:PrestadorServico|Prestador)[^\n\r]{0,80}\n?\s*([A-ZÀ-ÿ0-9\-\.\&\s\/]{4,120})", text, re.IGNORECASE)
        if m2:
            nome = m2.group(1).strip()
            if nome:
                return re.sub(r"\s+", " ", nome).strip()
        # Alternativa: texto anterior ao CNPJ
        cnpj_m = re.search(r"([A-ZÀ-ÿ0-9\-\.\&\s\/]{5,120})\s+(?:CNPJ|CPF)\s*[:\-\s]*\d", text, re.IGNORECASE)
        if cnpj_m:
            nome = cnpj_m.group(1).strip()
            return re.sub(r"\s+", " ", nome).strip()
        return None
