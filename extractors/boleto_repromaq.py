"""
Extrator específico para boletos REPROMAQ/Bradesco.

Este módulo resolve problemas de performance (catastrophic backtracking)
e precisão causados por OCR em boletos da REPROMAQ emitidos via Bradesco.

Problema específico:
    O layout tabular do boleto faz com que dados de colunas vizinhas
    (ex: dígito da "Carteira") invadam o espaço entre rótulos e valores,
    quebrando regexes genéricos e causando loops infinitos.

    Exemplo de texto OCR problemático:
        (=) Valor do Documento
        9  <-- LIXO DA COLUNA VIZINHA (Carteira)
        R$
        2.970,00

Solução técnica:
    - Abordagem baseada em linhas ao invés de regex guloso
    - Regexes com limites rígidos de caracteres (sem .* ou [\\s\\S]*)
    - Filtragem de linhas com ruído (dígitos isolados)

Critérios de ativação:
    - Texto contém "REPROMAQ" (case insensitive)
    - Texto contém "BRADESCO" (case insensitive)

Campos extraídos:
    - cnpj_beneficiario
    - fornecedor_nome (hardcoded: "REPROMAQ COM. E IND. LTDA")
    - data_emissao
    - vencimento
    - valor_documento (valor_total)
    - linha_digitavel
    - numero_documento (padrão: DDDD-D)
    - banco_nome (hardcoded: "Bradesco")

Example:
    >>> from extractors.boleto_repromaq import BoletoRepromaqExtractor
    >>> if BoletoRepromaqExtractor.can_handle(texto):
    ...     dados = BoletoRepromaqExtractor().extract(texto)
    ...     print(f"Valor: R$ {dados['valor_documento']:.2f}")
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.extractors import BaseExtractor, register_extractor
from extractors.utils import (
    normalize_entity_name,
    parse_date_br,
    strip_accents,
)


def _compact(text: str) -> str:
    """Compacta texto removendo caracteres não alfanuméricos."""
    return re.sub(r"[^A-Z0-9]+", "", strip_accents((text or "").upper()))


def _is_noise_line(line: str) -> bool:
    """
    Verifica se uma linha é ruído do OCR (ex: dígito isolado da carteira).

    Args:
        line: Linha de texto a verificar.

    Returns:
        True se a linha parece ser ruído (ex: apenas 1-2 dígitos).
    """
    stripped = line.strip()
    if not stripped:
        return True
    # Linha com apenas 1-2 dígitos é ruído (ex: "9" da carteira)
    if re.fullmatch(r"\d{1,2}", stripped):
        return True
    # Linha com apenas "R$" ou "$" isolado
    if re.fullmatch(r"R?\$?", stripped, re.IGNORECASE):
        return True
    return False


def _extract_money_from_line(line: str) -> Optional[float]:
    """
    Extrai valor monetário de uma linha.

    Padrão esperado: "R$ 2.970,00" ou "2.970,00"

    Args:
        line: Linha de texto.

    Returns:
        Valor como float ou None.
    """
    # Padrão monetário brasileiro: 1.234,56 ou 1234,56
    match = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})", line)
    if match:
        valor_str = match.group(1)
        try:
            return float(valor_str.replace(".", "").replace(",", "."))
        except ValueError:
            return None
    return None


@register_extractor
class BoletoRepromaqExtractor(BaseExtractor):
    """
    Extrator otimizado para boletos REPROMAQ/Bradesco.

    Usa abordagem baseada em linhas para evitar catastrophic backtracking
    causado por regexes gulosos em texto OCR com ruído de colunas vizinhas.
    """

    # Constantes do fornecedor
    FORNECEDOR_NOME = "REPROMAQ COM. E IND. LTDA"
    BANCO_NOME = "Bradesco"

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se o documento é um boleto REPROMAQ/Bradesco.

        Critérios:
        - Contém "REPROMAQ" ou "REPROMAO" (variação OCR comum: Q → O)
        - Contém "BRADESCO" (case insensitive)

        Args:
            text: Texto extraído do documento.

        Returns:
            True se é um boleto REPROMAQ/Bradesco.
        """
        if not text:
            return False

        text_compact = _compact(text)

        # REPROMAQ ou REPROMAO (OCR frequentemente confunde Q com O)
        has_repromaq = "REPROMAQ" in text_compact or "REPROMAO" in text_compact
        has_bradesco = "BRADESCO" in text_compact

        return has_repromaq and has_bradesco

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados estruturados do boleto REPROMAQ/Bradesco.

        Usa abordagem baseada em linhas para máxima robustez.

        Args:
            text: Texto extraído do boleto.

        Returns:
            Dicionário com campos extraídos.
        """
        data: Dict[str, Any] = {
            "tipo_documento": "BOLETO",
            "banco_nome": self.BANCO_NOME,
            "fornecedor_nome": self._extract_fornecedor_nome(text),
        }

        # Extrai campos usando métodos específicos sem backtracking
        data["cnpj_beneficiario"] = self._extract_cnpj_beneficiario(text)
        data["valor_documento"] = self._extract_valor_documento(text)
        data["vencimento"] = self._extract_vencimento(text)
        data["data_emissao"] = self._extract_data_emissao(text)
        data["numero_documento"] = self._extract_numero_documento(text)
        data["linha_digitavel"] = self._extract_linha_digitavel(text)
        data["nosso_numero"] = self._extract_nosso_numero(text)

        # Alias para compatibilidade
        data["valor_total"] = data["valor_documento"]

        return data

    def _get_lines(self, text: str) -> List[str]:
        """Retorna lista de linhas não vazias do texto."""
        return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]

    def _extract_fornecedor_nome(self, text: str) -> str:
        """
        Extrai ou retorna o nome do fornecedor.

        Tenta extrair do texto, mas usa valor hardcoded como fallback
        pois sabemos que é REPROMAQ.

        Args:
            text: Texto do boleto.

        Returns:
            Nome do fornecedor.
        """
        # Tenta extrair nome completo do beneficiário
        lines = self._get_lines(text)

        for i, line in enumerate(lines):
            if re.search(r"(?i)\bBenefici[aá]rio\b", line):
                # Procura nas próximas 3 linhas por "REPROMAQ"
                for j in range(i, min(i + 4, len(lines))):
                    if "REPROMAQ" in lines[j].upper():
                        # Captura a linha toda e limpa
                        nome = lines[j].strip()
                        # Remove CNPJ e label "CNPJ/CPF:" se presente
                        nome = re.sub(
                            r"\s*[-–]?\s*(?:CNPJ\s*[:/]?\s*)?(?:CPF\s*[:/]?\s*)?\d{2}[\.\d/\-]+",
                            "",
                            nome,
                        ).strip()
                        # Remove "CNPJ/CPF:" sozinho
                        nome = re.sub(r"\s*CNPJ/CPF\s*:?\s*$", "", nome, flags=re.IGNORECASE).strip()
                        if nome:
                            return normalize_entity_name(nome)

        return self.FORNECEDOR_NOME

    def _extract_cnpj_beneficiario(self, text: str) -> Optional[str]:
        """
        Extrai CNPJ do beneficiário (REPROMAQ).

        Args:
            text: Texto do boleto.

        Returns:
            CNPJ formatado ou None.
        """
        lines = self._get_lines(text)

        # Procura CNPJ próximo a "Beneficiário" ou "REPROMAQ"
        for i, line in enumerate(lines):
            line_upper = line.upper()
            if "BENEFICI" in line_upper or "REPROMAQ" in line_upper:
                # Procura CNPJ nesta linha e nas próximas 3
                for j in range(i, min(i + 4, len(lines))):
                    match = re.search(
                        r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", lines[j]
                    )
                    if match:
                        return match.group(1)

        # Fallback: primeiro CNPJ encontrado
        match = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", text)
        return match.group(1) if match else None

    def _extract_valor_documento(self, text: str) -> float:
        """
        Extrai valor do documento com tratamento especial para ruído OCR.

        Estratégia:
        1. Localiza linha com "Valor do Documento" (ou variações)
        2. Percorre as próximas 5 linhas buscando valor monetário
        3. Ignora linhas de ruído (dígito isolado, "R$" sozinho)

        Esta abordagem evita catastrophic backtracking ao não usar
        regexes gulosos entre o label e o valor.

        Args:
            text: Texto do boleto.

        Returns:
            Valor como float ou 0.0.
        """
        lines = self._get_lines(text)

        # Localiza linha com label "Valor do Documento"
        for i, line in enumerate(lines):
            # Usa regex com limite rígido, sem backtracking
            if re.search(r"(?i)\bValor\s{0,3}do\s{0,3}Documento\b", line):
                # Tenta extrair valor da mesma linha primeiro
                valor = _extract_money_from_line(line)
                if valor and valor > 0:
                    return valor

                # Procura nas próximas linhas (até 5), ignorando ruído
                for j in range(i + 1, min(i + 6, len(lines))):
                    candidate = lines[j]

                    # Ignora linhas de ruído
                    if _is_noise_line(candidate):
                        continue

                    # Tenta extrair valor monetário
                    valor = _extract_money_from_line(candidate)
                    if valor and valor > 0:
                        return valor

        # Fallback: "Valor Cobrado" ou "Valor Nominal"
        for i, line in enumerate(lines):
            if re.search(r"(?i)\bValor\s{0,3}(?:Cobrado|Nominal)\b", line):
                valor = _extract_money_from_line(line)
                if valor and valor > 0:
                    return valor

                for j in range(i + 1, min(i + 4, len(lines))):
                    if _is_noise_line(lines[j]):
                        continue
                    valor = _extract_money_from_line(lines[j])
                    if valor and valor > 0:
                        return valor

        # Fallback final: extrai da linha digitável
        return self._extract_valor_from_linha_digitavel(text)

    def _extract_valor_from_linha_digitavel(self, text: str) -> float:
        """
        Extrai valor dos últimos 10 dígitos da linha digitável.

        Formato padrão: últimos 14 dígitos = fator vencimento (4) + valor (10)

        Args:
            text: Texto do boleto.

        Returns:
            Valor em reais ou 0.0.
        """
        # Padrão linha digitável com espaços/pontos
        match = re.search(
            r"\d{5}[\.\s]\d{5}\s{1,5}\d{5}[\.\s]\d{6}\s{1,5}\d{5}[\.\s]\d{6}\s{1,5}\d\s{1,5}(\d{4})(\d{10})",
            text,
        )
        if match:
            try:
                valor_centavos = int(match.group(2))
                return valor_centavos / 100.0
            except ValueError:
                pass

        return 0.0

    def _extract_vencimento(self, text: str) -> Optional[str]:
        """
        Extrai data de vencimento do boleto.

        Usa abordagem baseada em linhas sem backtracking.

        Args:
            text: Texto do boleto.

        Returns:
            Data no formato ISO (YYYY-MM-DD) ou None.
        """
        lines = self._get_lines(text)

        for i, line in enumerate(lines):
            # Verifica se linha contém "Vencimento"
            if re.search(r"(?i)\bVencimento\b", line):
                # Tenta extrair data da mesma linha
                match = re.search(r"(\d{2}/\d{2}/\d{4})", line)
                if match:
                    parsed = parse_date_br(match.group(1))
                    if parsed:
                        return parsed

                # Procura nas próximas 3 linhas
                for j in range(i + 1, min(i + 4, len(lines))):
                    match = re.search(r"(\d{2}/\d{2}/\d{4})", lines[j])
                    if match:
                        parsed = parse_date_br(match.group(1))
                        if parsed:
                            return parsed

        return None

    def _extract_data_emissao(self, text: str) -> Optional[str]:
        """
        Extrai data de emissão/documento do boleto.

        Args:
            text: Texto do boleto.

        Returns:
            Data no formato ISO (YYYY-MM-DD) ou None.
        """
        lines = self._get_lines(text)

        # Procura por labels comuns de data de emissão
        # "Documento" sozinho também pode indicar data do documento
        labels = [
            r"(?i)\bData\s{0,3}do\s{0,3}Documento\b",
            r"(?i)\bData\s{0,3}de\s{0,3}Emiss[aã]o\b",
            r"(?i)\bEmiss[aã]o\b",
            r"(?i)\bData\s{0,3}Processamento\b",
            r"(?i)\bProcessamento\b",
        ]

        for label_pattern in labels:
            for i, line in enumerate(lines):
                if re.search(label_pattern, line):
                    # Tenta extrair da mesma linha
                    match = re.search(r"(\d{2}/\d{2}/\d{4})", line)
                    if match:
                        parsed = parse_date_br(match.group(1))
                        if parsed:
                            return parsed

                    # Próximas 4 linhas
                    for j in range(i + 1, min(i + 5, len(lines))):
                        match = re.search(r"(\d{2}/\d{2}/\d{4})", lines[j])
                        if match:
                            parsed = parse_date_br(match.group(1))
                            if parsed:
                                return parsed

        # Fallback: menor data encontrada (geralmente é a emissão)
        all_dates = []
        for line in lines:
            for m in re.finditer(r"\b(\d{2}/\d{2}/\d{4})\b", line):
                parsed = parse_date_br(m.group(1))
                if parsed:
                    all_dates.append(parsed)
        
        if all_dates:
            return min(all_dates)  # Menor data = emissão

        return None

    def _extract_numero_documento(self, text: str) -> Optional[str]:
        """
        Extrai número do documento (padrão REPROMAQ: DDDD-D).

        Formato esperado: 4+ dígitos, hífen, 1 dígito (ex: "8394-2")

        Args:
            text: Texto do boleto.

        Returns:
            Número do documento ou None.
        """
        lines = self._get_lines(text)

        # Procura label "Número do Documento" ou "Nº Documento"
        for i, line in enumerate(lines):
            if re.search(r"(?i)\b(?:N[úu]mero|N[ºo\.])?\s*(?:do\s+)?Documento\b", line):
                # Busca nas próximas linhas (não na mesma, pois pode ter CNPJ)
                for j in range(i + 1, min(i + 5, len(lines))):
                    current = lines[j]
                    # Ignora linhas com CNPJ
                    if re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", current):
                        continue
                    # Padrão específico REPROMAQ: DDDD-D
                    match = re.search(r"\b(\d{4,}-\d{1,2})\b", current)
                    if match:
                        candidate = match.group(1)
                        # Ignora se parece com parte de CNPJ (0001-XX)
                        if not candidate.startswith("0001-"):
                            return candidate

        # Fallback: procura padrão DDDD-D em todo texto (fora de CNPJ/datas)
        for line in lines:
            # Ignora linhas com CNPJ ou datas
            if re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", line):
                continue
            if re.search(r"\d{2}/\d{2}/\d{4}", line):
                continue

            match = re.search(r"\b(\d{4,6}-\d{1,2})\b", line)
            if match:
                return match.group(1)

        return None

    def _extract_linha_digitavel(self, text: str) -> Optional[str]:
        """
        Extrai linha digitável do boleto.

        Formato padrão Bradesco:
        XXXXX.XXXXX XXXXX.XXXXXX XXXXX.XXXXXX X XXXXXXXXXXXXXX

        Args:
            text: Texto do boleto.

        Returns:
            Linha digitável formatada ou None.
        """
        # Padrão com pontos e espaços
        patterns = [
            # Formato completo com pontos
            r"(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14})",
            # Formato com espaços variáveis
            r"(\d{5}[\.\s]\d{5}\s{1,5}\d{5}[\.\s]\d{6}\s{1,5}\d{5}[\.\s]\d{6}\s{1,5}\d\s{1,5}\d{14})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)

        # Fallback: sequência de 47 dígitos
        # Remove espaços e pontos, verifica se tem 47 dígitos
        text_digits = re.sub(r"[\s\.]", "", text)
        match = re.search(r"(\d{47})", text_digits)
        if match:
            digits = match.group(1)
            # Formata no padrão XXXXX.XXXXX XXXXX.XXXXXX XXXXX.XXXXXX X XXXXXXXXXXXXXX
            formatted = (
                f"{digits[0:5]}.{digits[5:10]} "
                f"{digits[10:15]}.{digits[15:21]} "
                f"{digits[21:26]}.{digits[26:32]} "
                f"{digits[32]} "
                f"{digits[33:47]}"
            )
            return formatted

        return None

    def _extract_nosso_numero(self, text: str) -> Optional[str]:
        """
        Extrai "Nosso Número" do boleto (identificação interna do banco).

        Args:
            text: Texto do boleto.

        Returns:
            Nosso número ou None.
        """
        lines = self._get_lines(text)

        for i, line in enumerate(lines):
            if re.search(r"(?i)\bNosso\s{0,3}N[úu]mero\b", line):
                # Tenta extrair da mesma linha (após o label)
                # Padrão: sequência com / ou - (ex: 00/000103372-0)
                match = re.search(r"(?i)Nosso\s+N[úu]mero\s*[:\s]*(\d{2}/\d{6,12}-?\d?)", line)
                if match:
                    return match.group(1).strip()

                # Próximas linhas - busca padrão específico de nosso número
                for j in range(i + 1, min(i + 4, len(lines))):
                    current = lines[j]
                    # Ignora linhas que parecem datas
                    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", current.strip()):
                        continue
                    # Padrão: XX/XXXXXXXXXX-X
                    match = re.search(r"(\d{2}/\d{6,12}-?\d?)", current)
                    if match:
                        return match.group(1).strip()

        return None
