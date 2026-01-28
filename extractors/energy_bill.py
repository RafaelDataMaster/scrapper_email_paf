"""
Extrator para faturas de energia elétrica (EDP, CEMIG, COPEL, etc.).

Características típicas:
- Emitente: distribuidora de energia (ex: "EDP SP DISTRIB DE ENERGIA SA")
- Contém termos como "DISTRIB DE ENERGIA", "CONSUMO", "KWH", "FATURA DE ENERGIA"
- Possui número de instalação, classe de consumo, bandeira tarifária
- Valor total geralmente aparece próximo a "TOTAL", "VALOR", "A PAGAR"
"""

import logging
import re
from typing import Any, Dict, Optional

from core.extractors import BaseExtractor, register_extractor
from extractors.utils import parse_br_money, parse_date_br


@register_extractor
class EnergyBillExtractor(BaseExtractor):
    """Extrator para faturas de energia elétrica."""

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """Retorna True se o texto parece ser uma fatura de energia."""
        if not text:
            return False

        text_upper = text.upper()

        # Indicadores fortes de fatura de energia
        energy_indicators = [
            "DISTRIB DE ENERGIA",
            "DISTRIBUIDORA DE ENERGIA",
            "ENERGIA ELÉTRICA",
            "ENERGIA ELETRICA",
            "CONSUMO",
            "KWH",
            "KWH/MÊS",
            "KWH/MES",
            "INSTALAÇÃO",
            "INSTALACAO",
            "BANDEIRA TARIFÁRIA",
            "BANDEIRA TARIFARIA",
            "FATURA DE ENERGIA",
            "CONTA DE LUZ",
            "CONTA DE ENERGIA",
            "FATURA ELETRÔNICA",
            "FATURA ELETRONICA",
            # Distribuidoras conhecidas
            "EDP",
            "CEMIG",
            "COPEL",
            "CPFL",
            "ENERGISA",
            "NEOENERGIA",
            "ELEKTRO",
            "ENEL",
            "LIGHT",
            "COSERN",
            "CELESC",
            "CELPE",
            "COELBA",
            "COELCE",
        ]

        # Verificar pelo menos 2 indicadores (para reduzir falsos positivos)
        matches = sum(1 for indicator in energy_indicators if indicator in text_upper)
        return matches >= 2

    def _normalize_spaces_in_number(self, text: str) -> str:
        """Remove espaços dentro de números (ex: '369, 4 0' -> '369,40')."""
        # Encontra padrões como "369, 4 0" ou "348,19"
        pattern = r"(\d{1,3}(?:\.\d{3})*),\s*(\d)\s*(\d)"

        def replacer(match):
            int_part = match.group(1)
            dec1 = match.group(2)
            dec2 = match.group(3)
            return f"{int_part},{dec1}{dec2}"

        result = re.sub(pattern, replacer, text)
        return result

    def _extract_supplier_name(self, text: str) -> Optional[str]:
        """Extrai o nome da distribuidora de energia."""
        # Primeiro, tenta encontrar uma linha que contenha "DISTRIB DE ENERGIA"
        lines = text.split("\n")
        for line in lines:
            line_upper = line.upper()
            if "DISTRIB" in line_upper and "ENERGIA" in line_upper:
                # Limpar a linha: remover endereço, CNPJ, etc.
                clean_line = re.sub(r"\s+CNPJ.*$", "", line)
                clean_line = re.sub(r"\s+RUA.*$", "", clean_line)
                clean_line = re.sub(r"\s+AV\..*$", "", clean_line)
                clean_line = re.sub(r"\s+CEP.*$", "", clean_line)
                clean_line = re.sub(
                    r"\s+\d.*$", "", clean_line
                )  # Remove números no final
                clean_line = clean_line.strip()
                if clean_line and len(clean_line) > 10:
                    return clean_line

        # Fallback: procurar por nomes conhecidos de distribuidoras
        known_suppliers = [
            "EDP SP DISTRIB DE ENERGIA SA",
            "EDP",
            "CEMIG DISTRIBUIÇÃO S.A.",
            "CEMIG",
            "COPEL",
            "CPFL",
            "ENERGISA",
            "NEOENERGIA",
            "ELEKTRO",
            "ENEL",
            "LIGHT",
        ]

        for supplier in known_suppliers:
            if supplier.upper() in text.upper():
                return supplier

        return None

    def _extract_cnpj(self, text: str) -> Optional[str]:
        """Extrai CNPJ do fornecedor."""
        # Procurar CNPJ formatado próximo a "CNPJ" ou após o nome da distribuidora
        cnpj_patterns = [
            r"CNPJ\s*[:\-]?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})",
            r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})",
            r"CNPJ\s*[:\-]?\s*(\d{14})",
        ]

        for pattern in cnpj_patterns:
            match = re.search(pattern, text)
            if match:
                cnpj = match.group(1)
                # Se for apenas dígitos, formatar
                if re.match(r"^\d{14}$", cnpj):
                    return (
                        f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
                    )
                return cnpj

        return None

    def _extract_document_number(self, text: str) -> Optional[str]:
        """Extrai número da nota/fatura."""
        patterns = [
            r"NOTA\s+FISCAL\s*N[°º]?\s*[:\-]?\s*([0-9\.\-]+)",
            r"FATURA\s*N[°º]?\s*[:\-]?\s*([0-9\.\-]+)",
            r"N[°º]\s*DA\s*NOTA\s*[:\-]?\s*([0-9\.\-]+)",
            r"N[°º]\s*[:\-]?\s*([0-9\.\-]+)\s+\(?NOTA",
            r"DOCUMENTO\s*[:\-]?\s*([0-9\.\-]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    def _extract_install_number(self, text: str) -> Optional[str]:
        """Extrai número da instalação."""
        patterns = [
            r"INSTALA[ÇC][ÃA]O\s*[:\-]?\s*(\d+)",
            r"(\d{8,12})\s*(?:INSTALA[ÇC][ÃA]O|MATR[ÍI]CULA)",
            r"C[ÓO]DIGO\s+DA\s+INSTALA[ÇC][ÃA]O\s*[:\-]?\s*(\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Procurar sequência de 8-12 dígitos isolada (pode ser a instalação)
        digit_match = re.search(r"\b(\d{8,12})\b", text)
        if digit_match:
            # Verificar se não é CNPJ ou data
            digits = digit_match.group(1)
            if not re.match(
                r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", digits
            ) and not re.match(r"\d{2}/\d{2}/\d{4}", digits):
                return digits

        return None

    def _extract_total_value(self, text: str) -> float:
        """Extrai valor total da fatura."""
        # Primeiro, normalizar espaços dentro dos números
        normalized_text = self._normalize_spaces_in_number(text)

        # Procurar padrões específicos de TOTAL
        # Prioridade 1: "TOTAL" seguido de valor
        patterns = [
            # Padrão período-vencimento-valor (ex: "DEZ/2025 22/01/2026 369,40")
            r"(\w{3}/\d{4})\D+(\d{2}/\d{2}/\d{4})\D+(\d{1,3}(?:\.\d{3})*[,\s]\d{2})",
            # "TOTAL 369,40" ou "TOTAL: 369,40"
            r"TOTAL\s*[:\-]?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            # "VALOR TOTAL" ou "VALOR A PAGAR"
            r"VALOR\s+(?:TOTAL|A\s+PAGAR)\s*[:\-]?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            # "TOTAL GERAL"
            r"TOTAL\s+GERAL\s*[:\-]?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            # "TOTAL R$ 369,40"
            r"TOTAL\s*[:\-]?\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        ]

        # Primeiro, procurar na área próxima a "TOTAL" (últimos 500 caracteres)
        # Faturas geralmente têm o total no final
        last_part = (
            normalized_text[-500:] if len(normalized_text) > 500 else normalized_text
        )

        for pattern in patterns:
            match = re.search(pattern, last_part, re.IGNORECASE)
            if match:
                # Para o padrão período-vencimento-valor, o valor está no grupo 3
                if pattern.startswith(r"(\w{3}/\d{4})\D+(\d{2}/\d{2}/\d{4})\D+"):
                    value_str = match.group(3)
                else:
                    value_str = match.group(1)
                value = parse_br_money(value_str)
                if value > 0:
                    return value

        # Se não encontrou, procurar no texto todo
        for pattern in patterns:
            match = re.search(pattern, normalized_text, re.IGNORECASE)
            if match:
                # Para o padrão período-vencimento-valor, o valor está no grupo 3
                if pattern.startswith(r"(\w{3}/\d{4})\D+(\d{2}/\d{2}/\d{4})\D+"):
                    value_str = match.group(3)
                else:
                    value_str = match.group(1)
                value = parse_br_money(value_str)
                if value > 0:
                    return value

        # Fallback: procurar o maior valor monetário no texto
        # (geralmente o total é o maior)
        money_pattern = r"(\d{1,3}(?:\.\d{3})*,\d{2})"
        matches = re.findall(money_pattern, normalized_text)
        if matches:
            values = [parse_br_money(m) for m in matches]
            # Filtrar valores muito pequenos (como 0,00 ou centavos)
            valid_values = [v for v in values if v > 10.0]
            if valid_values:
                return max(valid_values)
            elif values:
                return max(values)

        return 0.0

    def _extract_due_date(self, text: str) -> Optional[str]:
        """Extrai data de vencimento."""
        # Procurar padrões específicos de vencimento
        patterns = [
            # "VENCIMENTO: 22/01/2026"
            r"VENCIMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            # "DATA DE VENCIMENTO"
            r"DATA\s+DE\s+VENCIMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            # "VENCE EM"
            r"VENCE\s+EM\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            # "VENC."
            r"VENC\.?\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            # "VENCIMENTO" seguido de data nos próximos 50 caracteres
            r"VENCIMENTO[^\d]{0,30}(\d{2}/\d{2}/\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                parsed_date = parse_date_br(date_str)
                if parsed_date:
                    return parsed_date

        # Procurar data no contexto de consumo (ex: "DEZ/2025 22/01/2026")
        # Padrão: mês/ano seguido de data
        period_due_match = re.search(
            r"(\w{3}/\d{4})\s+(\d{2}/\d{2}/\d{4})", text, re.IGNORECASE
        )
        if period_due_match:
            date_str = period_due_match.group(2)
            parsed_date = parse_date_br(date_str)
            if parsed_date:
                return parsed_date

        # Procurar qualquer data que não seja de emissão e que seja futura
        # (vencimento geralmente é posterior à emissão)
        date_matches = re.findall(r"\b(\d{2}/\d{2}/\d{4})\b", text)
        if date_matches:
            parsed_dates = []
            for date_str in date_matches:
                parsed = parse_date_br(date_str)
                if parsed:
                    parsed_dates.append(parsed)

            if len(parsed_dates) >= 2:
                # Ordenar datas e pegar a última (geralmente o vencimento)
                parsed_dates.sort()
                return parsed_dates[-1]

        return None

    def _extract_issue_date(self, text: str) -> Optional[str]:
        """Extrai data de emissão."""
        patterns = [
            r"EMISS[ÃA]O\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"DATA\s+DE\s+EMISS[ÃA]O\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"EMITIDO\s+EM\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"EMISSÃO:\s*(\d{2}/\d{2}/\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                return parse_date_br(date_str)

        # Procurar a primeira data no documento (geralmente é emissão)
        date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", text)
        if date_match:
            return parse_date_br(date_match.group(1))

        return None

    def _extract_period(self, text: str) -> Optional[str]:
        """Extrai período de referência (mês/ano)."""
        patterns = [
            r"REFER[ÊE]NCIA\s*[:\-]?\s*(\d{2}/\d{4})",
            r"PER[ÍI]ODO\s*[:\-]?\s*(\d{2}/\d{4})",
            r"M[ÊE]S\s+REFER[ÊE]NCIA\s*[:\-]?\s*(\d{2}/\d{4})",
            r"(\w{3}/\d{4})",  # Ex: DEZ/2025
            r"M[ÊE]S\s*[:\-]?\s*(\w{3}/\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                period = match.group(1).strip().upper()
                # Se for formato "DEZ/2025", garantir maiúsculas
                if "/" in period:
                    month, year = period.split("/")
                    month = month.upper()
                    return f"{month}/{year}"
                return period

        return None

    def extract(self, text: str) -> Dict[str, Any]:
        """Extrai dados de faturas de energia."""
        logger = logging.getLogger(__name__)
        logger.info("EnergyBillExtractor: iniciando extração")

        data: Dict[str, Any] = {"tipo_documento": "ENERGY_BILL"}

        # Extrair campos principais
        supplier_name = self._extract_supplier_name(text)
        if supplier_name:
            data["fornecedor_nome"] = supplier_name
            logger.debug(f"Fornecedor extraído: {supplier_name}")

        cnpj = self._extract_cnpj(text)
        if cnpj:
            data["cnpj_prestador"] = cnpj
            logger.debug(f"CNPJ extraído: {cnpj}")

        doc_number = self._extract_document_number(text)
        if doc_number:
            data["numero_nota"] = doc_number
            logger.debug(f"Número da nota extraído: {doc_number}")

        install_number = self._extract_install_number(text)
        if install_number:
            data["instalacao"] = install_number
            logger.debug(f"Instalação extraída: {install_number}")

        total_value = self._extract_total_value(text)
        if total_value > 0:
            data["valor_total"] = total_value
            logger.debug(f"Valor total extraído: R$ {total_value:.2f}")

        due_date = self._extract_due_date(text)
        if due_date:
            data["vencimento"] = due_date
            logger.debug(f"Vencimento extraído: {due_date}")

        issue_date = self._extract_issue_date(text)
        if issue_date:
            data["data_emissao"] = issue_date
            logger.debug(f"Data de emissão extraída: {issue_date}")

        period = self._extract_period(text)
        if period:
            data["periodo_referencia"] = period
            logger.debug(f"Período de referência extraído: {period}")

        # Log do resultado
        if data.get("valor_total"):
            logger.info(
                f"EnergyBillExtractor: documento processado - "
                f"Fornecedor: {data.get('fornecedor_nome', 'N/A')}, "
                f"Valor: R$ {data['valor_total']:.2f}, "
                f"Vencimento: {data.get('vencimento', 'N/A')}, "
                f"Nota: {data.get('numero_nota', 'N/A')}"
            )
        else:
            logger.warning(
                f"EnergyBillExtractor: documento processado mas valor_total não encontrado. "
                f"Texto (primeiros 500 chars): {text[:500]}"
            )

        return data
