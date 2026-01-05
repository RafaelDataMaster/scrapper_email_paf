"""
Extrator especializado para Faturas de Locação EMC Tecnologia.

Este extrator foi criado para lidar com faturas de locação de equipamentos
que possuem múltiplas páginas com lista detalhada de itens e um TOTAL
na última página.

Problema original: O OutrosExtractor pegava apenas o primeiro valor (R$ 130,00)
ao invés do TOTAL correto (R$ 37.817,48) que está na última página.

Características do documento EMC:
- Título: "FATURA DE LOCAÇÃO"
- Emitente: EMC TECNOLOGIA LTDA
- Múltiplas páginas com itens de locação
- Total na última página no formato: "TOTAL R$ XX.XXX,XX"
- Referência ao contrato e período de locação
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional

from core.extractors import BaseExtractor, register_extractor


def _parse_br_money(value: str) -> float:
    """Converte valor monetário brasileiro para float."""
    if not value:
        return 0.0
    try:
        # Remove pontos de milhar e converte vírgula decimal
        return float(value.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def _parse_date_br(value: str) -> Optional[str]:
    """Converte data brasileira (DD/MM/YYYY) para ISO (YYYY-MM-DD)."""
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


@register_extractor
class EmcFaturaExtractor(BaseExtractor):
    """
    Extrator especializado para Faturas de Locação EMC Tecnologia.

    Este extrator tem prioridade sobre o OutrosExtractor para documentos
    EMC porque implementa lógica específica para encontrar o TOTAL
    em documentos de múltiplas páginas.
    """

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se o documento é uma fatura de locação EMC.

        Critérios:
        - Contém "FATURA DE LOCAÇÃO" ou "FATURA DE LOCACAO"
        - Contém "EMC TECNOLOGIA"
        - Contém "DADOS LOCAÇÃO" ou lista de itens de locação
        """
        if not text:
            return False

        t = text.upper()

        # Verificação principal: é uma fatura de locação EMC?
        is_fatura_locacao = (
            "FATURA DE LOCAÇÃO" in t or
            "FATURA DE LOCACAO" in t or
            ("FATURA" in t and "LOCAÇÃO" in t) or
            ("FATURA" in t and "LOCACAO" in t)
        )

        is_emc = "EMC TECNOLOGIA" in t

        # Indicador adicional: lista de equipamentos com valores
        has_equipment_list = (
            "NOTEBOOK" in t or
            "COMPUTADOR" in t or
            "MONITOR" in t or
            "SERVIDOR" in t
        ) and ("DELL" in t or "LENOVO" in t)

        # É fatura de locação EMC se:
        # 1. Tem os dois indicadores principais, ou
        # 2. Tem EMC + lista de equipamentos (mesmo sem "fatura de locação" explícito)
        return (is_fatura_locacao and is_emc) or (is_emc and has_equipment_list)

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados estruturados da fatura de locação EMC.

        Campos extraídos:
        - fornecedor_nome: EMC TECNOLOGIA LTDA
        - cnpj_fornecedor: CNPJ da EMC
        - valor_total: TOTAL da fatura (última página)
        - vencimento: Data de vencimento
        - numero_documento: Número da fatura
        - contrato: Número do contrato
        - periodo_referencia: Período de locação
        """
        data: Dict[str, Any] = {
            "tipo_documento": "OUTRO",
            "subtipo": "FATURA_LOCACAO_EMC"
        }

        # 1. Extrair fornecedor (sempre EMC para este extrator)
        data["fornecedor_nome"] = self._extract_fornecedor(text)

        # 2. Extrair CNPJ do fornecedor (EMC)
        data["cnpj_fornecedor"] = self._extract_cnpj_emc(text)

        # 3. Extrair TOTAL - CRÍTICO: procurar na última parte do documento
        data["valor_total"] = self._extract_valor_total(text)

        # 4. Extrair vencimento
        data["vencimento"] = self._extract_vencimento(text)

        # 5. Extrair data de emissão
        data["data_emissao"] = self._extract_data_emissao(text)

        # 6. Extrair número da fatura
        data["numero_documento"] = self._extract_numero_fatura(text)

        # 7. Extrair número do contrato
        data["contrato"] = self._extract_contrato(text)

        # 8. Extrair período de referência
        data["periodo_referencia"] = self._extract_periodo(text)

        return data

    def _extract_fornecedor(self, text: str) -> str:
        """Extrai nome do fornecedor (EMC Tecnologia)."""
        # Padrão específico EMC
        m = re.search(
            r'(?i)EMPRESA[:\s]*([^\n]*EMC\s+TECNOLOGIA[^\n]*LTDA)',
            text
        )
        if m:
            nome = m.group(1).strip()
            # Limpar TELEFONE se estiver junto
            nome = re.sub(r'\s*TELEFONE.*', '', nome, flags=re.IGNORECASE)
            return nome.strip()

        # Fallback: busca simples
        if "EMC TECNOLOGIA LTDA" in text.upper():
            return "EMC TECNOLOGIA LTDA"

        return "EMC TECNOLOGIA LTDA"

    def _extract_cnpj_emc(self, text: str) -> Optional[str]:
        """Extrai CNPJ da EMC Tecnologia."""
        # CNPJ conhecido da EMC: 22.261.093/0001-40
        emc_cnpj = "22.261.093/0001-40"
        if emc_cnpj in text:
            return emc_cnpj

        # Busca CNPJ próximo a "EMC" ou "EMPRESA:"
        m = re.search(
            r'(?i)(?:EMC|EMPRESA)[^\n]*CNPJ[:\s]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
            text
        )
        if m:
            return m.group(1)

        # Primeiro CNPJ no documento (geralmente é do emitente)
        m = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', text)
        if m:
            return m.group(0)

        return None

    def _extract_valor_total(self, text: str) -> float:
        """
        Extrai o TOTAL da fatura.

        IMPORTANTE: Em faturas de múltiplas páginas, o TOTAL está
        na última página, geralmente no formato "TOTAL R$ XX.XXX,XX"
        """
        # Estratégia 1: Procurar "TOTAL R$ XX.XXX,XX" (formato específico EMC)
        # Este é o padrão mais confiável
        m = re.search(
            r'(?i)\bTOTAL\s+R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            text
        )
        if m:
            return _parse_br_money(m.group(1))

        # Estratégia 2: "TOTAL" seguido de valor na mesma linha ou próxima
        m = re.search(
            r'(?i)\bTOTAL\b[^\d\n]*(\d{1,3}(?:\.\d{3})*,\d{2})',
            text
        )
        if m:
            return _parse_br_money(m.group(1))

        # Estratégia 3: Procurar o maior valor no documento
        # (fallback, menos confiável mas pode funcionar)
        all_values = re.findall(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', text)
        if all_values:
            values_float = [_parse_br_money(v) for v in all_values]
            # Filtrar valores muito pequenos (itens individuais)
            large_values = [v for v in values_float if v > 1000]
            if large_values:
                return max(large_values)
            # Se não há valores grandes, pegar o maior
            return max(values_float) if values_float else 0.0

        return 0.0

    def _extract_vencimento(self, text: str) -> Optional[str]:
        """Extrai data de vencimento."""
        # Padrão EMC: "VENCIMENTO: DD/MM/YYYY"
        m = re.search(
            r'(?i)\bVENCIMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})',
            text
        )
        if m:
            return _parse_date_br(m.group(1))

        # Padrão alternativo: "CONTRATO: XXXXX VENCIMENTO: DD/MM/YYYY"
        m = re.search(
            r'(?i)CONTRATO[:\s]*\d+[^\n]*VENCIMENTO[:\s]*(\d{2}/\d{2}/\d{4})',
            text
        )
        if m:
            return _parse_date_br(m.group(1))

        return None

    def _extract_data_emissao(self, text: str) -> Optional[str]:
        """Extrai data de emissão."""
        # Padrão EMC: "Emissão: DD/MM/YYYY HH:MM:SS"
        m = re.search(
            r'(?i)\bEmiss[ãa]o\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})',
            text
        )
        if m:
            return _parse_date_br(m.group(1))

        return None

    def _extract_numero_fatura(self, text: str) -> Optional[str]:
        """Extrai número da fatura."""
        # Padrão EMC: "FATURA DE LOCAÇÃO Nº:50446" ou "Nº: 50446"
        patterns = [
            r'(?i)FATURA\s+(?:DE\s+)?LOCA[ÇC][ÃA]O\s+N[º°]?\s*[:\-]?\s*(\d+)',
            r'(?i)N[º°]\s*[:\-]?\s*(\d{4,})',
        ]

        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)

        return None

    def _extract_contrato(self, text: str) -> Optional[str]:
        """Extrai número do contrato."""
        m = re.search(
            r'(?i)\bCONTRATO\s*[:\-]?\s*(\d+)',
            text
        )
        if m:
            return m.group(1)

        return None

    def _extract_periodo(self, text: str) -> Optional[str]:
        """Extrai período de referência da locação."""
        # Padrão EMC: "PERIODO DD/MM/YYYY ATÉ DD/MM/YYYY"
        m = re.search(
            r'(?i)PERIODO\s+(\d{2}/\d{2}/\d{4})\s+AT[ÉE]\s+(\d{2}/\d{2}/\d{4})',
            text
        )
        if m:
            return f"{m.group(1)} até {m.group(2)}"

        # Alternativo: "período entre DD/MM/YYYY até DD/MM/YYYY"
        m = re.search(
            r'(?i)per[ií]odo\s+(?:entre\s+)?(\d{2}/\d{2}/\d{4})\s+(?:at[ée]|e)\s+(\d{2}/\d{2}/\d{4})',
            text
        )
        if m:
            return f"{m.group(1)} até {m.group(2)}"

        return None
