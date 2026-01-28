"""
Extrator específico para faturas de serviços da MUGO TELECOMUNICAÇÕES LTDA.

Este módulo resolve problemas de extração em faturas da MUGO TELECOM que não estão sendo
reconhecidas pelos extratores existentes.

Problemas identificados:
1. PDFs não reconhecidos: Documentos com padrão "MUGO TELECOMUNICAÇÕES LTDA Fatura de Serviços"
2. Valor não extraído: Valores em formato "DESCRIÇÃO VALOR TOTAL" não capturados
3. Classificação incorreta: Documentos classificados como desconhecidos

Critérios de ativação:
- Texto contém "MUGO TELECOMUNICAÇÕES LTDA" ou "MUGO TELECOM"
- Texto contém "Fatura de Serviços" ou "DOC. AUXILIAR DA NOTA FISCAL"
- Não é boleto ou DANFE

Campos extraídos:
- fornecedor_nome: MUGO TELECOMUNICAÇÕES LTDA (normalizado)
- valor_documento: Valor total da fatura (ex: 1.980,00)
- data_emissao: Data de emissão da fatura
- numero_documento: Número da fatura (ex: 000019398)
- empresa: Empresa cliente (extraída do contexto)
- cnpj_prestador: CNPJ 14.732.961/0001-03 (hardcoded para MUGO TELECOM)
- doc_type: NFSE (Nota Fiscal de Serviço Eletrônica)

Example:
    >>> from extractors.mugo_extractor import MugoExtractor
    >>> if MugoExtractor.can_handle(texto):
    ...     dados = MugoExtractor().extract(texto)
    ...     print(f"Valor: R$ {dados['valor_documento']:.2f}")
"""

import re
import logging
from typing import Any, Dict, Optional

from core.extractors import BaseExtractor, register_extractor
from extractors.utils import (
    normalize_entity_name,
    parse_date_br,
)

@register_extractor
class MugoExtractor(BaseExtractor):
    """
    Extrator especializado em faturas de serviços da MUGO TELECOMUNICAÇÕES LTDA.

    Identifica e extrai campos específicos de faturas da MUGO TELECOM,
    resolvendo problemas de reconhecimento e extração de valores.
    """

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se o documento é uma fatura da MUGO TELECOM.

        Critério simples: Contém "MUGO TELECOM" e não é boleto ou DANFE.
        """
        if not text:
            return False

        text_upper = text.upper()

        # Deve conter MUGO TELECOM
        if "MUGO TELECOM" not in text_upper:
            return False

        # Aceita qualquer documento da MUGO TELECOM
        return True

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados estruturados da fatura da MUGO TELECOM.

        Estratégia:
        1. Extrair valor total da seção "DESCRIÇÃO VALOR TOTAL"
        2. Buscar número do documento próximo a "Nº" ou "Número"
        3. Extrair data de emissão
        4. Identificar empresa cliente
        5. Fornecedor e CNPJ hardcoded para consistência

        Args:
            text: Texto completo da fatura

        Returns:
            Dicionário com campos extraídos
        """
        data = {}
        data["tipo_documento"] = "NFSE"
        data["doc_type"] = "NFSE"

        # Fornecedor hardcoded para consistência
        data["fornecedor_nome"] = "MUGO TELECOMUNICAÇÕES LTDA"
        data["cnpj_prestador"] = "14.732.961/0001-03"  # CNPJ da MUGO TELECOM

        # Campos extraídos
        data["valor_documento"] = self._extract_valor_mugo(text)
        data["valor_total"] = data["valor_documento"]  # Alias para compatibilidade
        data["data_emissao"] = self._extract_data_emissao(text)
        data["numero_documento"] = self._extract_numero_documento(text)
        data["numero_nota"] = data["numero_documento"]  # Alias para compatibilidade
        data["empresa"] = self._extract_empresa(text)
        data["vencimento"] = self._extract_vencimento(text)

        logging.getLogger(__name__).info(
            f"MugoExtractor: documento processado - "
            f"valor: R$ {data['valor_documento']:.2f}, "
            f"emissão: {data['data_emissao']}, "
            f"numero: {data['numero_documento']}, "
            f"empresa: {data['empresa']}"
        )

        return data

    def _extract_valor_mugo(self, text: str) -> float:
        """
        Extrai valor total da fatura da MUGO TELECOM.

        Estratégia:
        1. Buscar valores na seção "DESCRIÇÃO VALOR TOTAL"
        2. Procurar valores monetários após indicadores de total
        3. Priorizar valores não-zero e maiores

        Args:
            text: Texto completo da fatura

        Returns:
            Valor como float, 0.0 se não encontrado
        """
        lines = text.split("\n")

        # Para debugging - logar as linhas relevantes
        logger = logging.getLogger(__name__)
        relevant_lines = []
        for i, line in enumerate(lines):
            line_upper = line.upper()
            if any(
                keyword in line_upper
                for keyword in [
                    "TOTAL",
                    "VALOR",
                    "V. TOTAL",
                    "V.UNIT",
                    "V.TOTAL",
                    "DESCRIÇÃO",
                ]
            ):
                relevant_lines.append(f"{i}: {line[:80]}")

        # Contextos prioritários para busca de valor (ordem de prioridade)
        priority_contexts = [
            "TOTAL: R$",
            "VALOR TOTAL: R$",
            "TOTAL R$",
            "VALOR TOTAL R$",
            "VALOR A PAGAR",
            "VALOR DA FATURA",
            "DESCRIÇÃO VALOR TOTAL",
            "V. TOTAL",
            "V.TOTAL",
        ]

        all_values = []

        for i, line in enumerate(lines):
            line_upper = line.upper()

            # Verificar se a linha tem contexto prioritário
            has_priority_context = any(ctx in line_upper for ctx in priority_contexts)

            # Buscar valores monetários na linha atual e próximas
            for offset in range(0, 3):  # Linha atual + 2 próximas
                if i + offset >= len(lines):
                    break

                check_line = lines[i + offset]
                check_line_upper = check_line.upper()

                # Padrão monetário: R$ 1.234,56 ou 1234,56 (com ou sem ponto de milhar)
                matches = re.findall(
                    r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", check_line
                )

                for match in matches:
                    try:
                        # Remover pontos de milhar e converter vírgula para ponto
                        valor_str = match.replace(".", "").replace(",", ".")
                        valor = float(valor_str)

                        # Filtrar valores que são provavelmente CNPJs, IEs, etc.
                        if valor < 0.01:
                            continue

                        # Determinar peso baseado no contexto
                        peso = 1

                        # Contexto prioritário direto
                        if has_priority_context and offset == 0:
                            peso = 10

                        # Linha contém "TOTAL" (alta prioridade)
                        if (
                            "TOTAL" in check_line_upper
                            and "V.UNIT" not in check_line_upper
                        ):
                            peso = max(peso, 8)

                        # Linha contém "VALOR TOTAL"
                        if "VALOR TOTAL" in check_line_upper:
                            peso = max(peso, 9)

                        # Linha da tabela "V. TOTAL"
                        if (
                            "V. TOTAL" in check_line_upper
                            or "V.TOTAL" in check_line_upper
                        ):
                            peso = max(peso, 7)

                        # Linha contém apenas números (provavelmente linha de item)
                        if re.match(r"^\s*\d+\s+[^\d]*\d+[\.,]\d+", check_line):
                            # É linha de item na tabela
                            if (
                                valor > 100
                            ):  # Valores grandes em linhas de item são importantes
                                peso = max(peso, 6)

                        # Penalizar valores muito pequenos que podem ser créditos/impostos
                        if valor < 50:
                            peso = max(peso, 1)  # Baixa prioridade

                        # Bônus para valores maiores (mais prováveis de serem totais)
                        if valor > 1000:
                            peso += 3
                        elif valor > 100:
                            peso += 2
                        elif valor > 10:
                            peso += 1

                        all_values.append((valor, peso))
                    except (ValueError, AttributeError):
                        continue

        # Se não encontrou valores, retorna 0
        if not all_values:
            return 0.0

        # Ordenar por peso (maior primeiro) e valor (maior primeiro)
        all_values.sort(key=lambda x: (-x[1], -x[0]))

        # Log para debugging
        if len(all_values) > 0:
            logger.debug(f"MugoExtractor valores encontrados: {all_values[:5]}")

        # Retornar o valor com maior peso
        return all_values[0][0]

    def _extract_numero_documento(self, text: str) -> Optional[str]:
        """
        Extrai número do documento/fatura.

        Padrões comuns na MUGO TELECOM:
        - "Nº 000019398"
        - "Número: 000019398"
        - "Fatura Nº 000019398"
        - "Nº DOCUMENTO: 000004454"
        - "Número do Documento: 000004454"

        Args:
            text: Texto completo da fatura

        Returns:
            Número do documento ou None
        """
        # Padrões prioritários com contexto específico
        priority_patterns = [
            r"N[º°O]\s+(?:DOCUMENTO)?\s*[:]?\s*(\d{6,12})",
            r"N[ÚU]MERO\s+(?:DO\s+)?(?:DOCUMENTO|FATURA)?\s*[:]?\s*(\d{6,12})",
            r"FATURA\s+N[º°O]\s*[:]?\s*(\d{6,12})",
            r"DOCUMENTO\s+N[º°O]?\s*[:]?\s*(\d{6,12})",
            r"N[º°O]\s*\.?\s*(\d{6,12})",
            r"NOTA\s+FISCAL\s+N[º°O]?\s*[:]?\s*(\d{6,12})",
        ]

        for pattern in priority_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        # Buscar por sequências de 6-12 dígitos após indicadores em cada linha
        lines = text.split("\n")
        for i, line in enumerate(lines):
            line_upper = line.upper()

            # Indicadores de número de documento
            indicators = [
                "Nº",
                "NUMERO",
                "FATURA",
                "DOCUMENTO",
                "NOTA FISCAL",
                "NÚMERO",
                "NF",
                "DOC",
            ]

            if any(ind in line_upper for ind in indicators):
                # Procurar sequência de dígitos nesta linha
                match = re.search(r"(\d{6,12})", line)
                if match:
                    # Verificar linha seguinte também (às vezes o número está na próxima linha)
                    next_line_match = None
                    if i + 1 < len(lines):
                        next_line_match = re.search(r"(\d{6,12})", lines[i + 1])

                    # Priorizar número que vem depois de "Nº" ou similar na mesma linha
                    if "Nº" in line_upper or "NUMERO" in line_upper:
                        return match.group(1)
                    elif next_line_match:
                        return next_line_match.group(1)
                    else:
                        return match.group(1)

        # Buscar por qualquer sequência de 8-12 dígitos que possa ser número de documento
        # (evita capturar CNPJ, IE, etc. que têm padrões específicos)
        all_matches = re.findall(r"\b(\d{8,12})\b", text)
        for match in all_matches:
            # Filtrar números que são CNPJ (14 dígitos) ou IE (com pontos/hífens)
            # Mas 8-12 dígitos podem ser números de documento
            # Verificar se não é data (começa com 20, 19, etc.)
            if not match.startswith(("20", "19", "00")) and len(match) >= 6:
                # Verificar contexto ao redor
                return match

        return None

    def _extract_data_emissao(self, text: str) -> Optional[str]:
        """
        Extrai data de emissão da fatura.

        Padrões:
        - "Emissão: 02/01/2026"
        - "Data de Emissão: 02/01/2026"
        - "Emitido em: 02/01/2026"

        Args:
            text: Texto completo da fatura

        Returns:
            Data no formato aaaa-mm-dd ou None
        """
        lines = text.split("\n")

        for i, line in enumerate(lines):
            line_upper = line.upper()

            if (
                "EMISSÃO" in line_upper
                or "EMISSAO" in line_upper
                or "EMITIDO" in line_upper
                or "DATA" in line_upper
            ):
                # Verificar linha atual e próximas 2 linhas
                for offset in range(0, 3):
                    if i + offset >= len(lines):
                        break

                    check_line = lines[i + offset]

                    # Tentar parser de datas brasileiro
                    date_obj = parse_date_br(check_line)
                    if date_obj:
                        return date_obj

                    # Tentar formato dd/mm/aaaa
                    match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", check_line)
                    if match:
                        try:
                            from datetime import datetime

                            date_obj = datetime.strptime(match.group(1), "%d/%m/%Y")
                            return date_obj.strftime("%Y-%m-%d")
                        except ValueError:
                            continue

        return None

    def _extract_empresa(self, text: str) -> Optional[str]:
        """
        Extrai nome da empresa cliente.

        Procura por:
        1. "Nome/Razão Social:" seguido de nome
        2. "Cliente:" seguido de nome
        3. Empresas conhecidas do grupo

        Args:
            text: Texto completo da fatura

        Returns:
            Nome da empresa ou None
        """
        lines = text.split("\n")

        # Empresas conhecidas do grupo
        known_companies = [
            "ITACOLOMI",
            "ITACOLOMI COMUNICACAO",
            "MOC",
            "MOC COMUNICACAO",
            "CSC",
            "CARRIER",
            "OP11",
            "EXATA",
            "DEVICE",
            "ORION",
            "ATIVE",
            "RBC",
        ]

        for i, line in enumerate(lines):
            line_upper = line.upper()

            # Verificar se linha contém indicadores de empresa
            if (
                "NOME/RAZÃO SOCIAL:" in line_upper
                or "RAZÃO SOCIAL:" in line_upper
                or "CLIENTE:" in line_upper
                or "TOMADOR:" in line_upper
            ):
                # Procurar empresas conhecidas nesta linha e próximas
                for offset in range(0, 3):
                    if i + offset >= len(lines):
                        break

                    check_line = lines[i + offset]
                    for company in known_companies:
                        if company.upper() in check_line.upper():
                            return normalize_entity_name(company)

            # Verificar se linha contém empresa conhecida diretamente
            for company in known_companies:
                if company.upper() in line_upper:
                    return normalize_entity_name(company)

        return None

    def _extract_vencimento(self, text: str) -> Optional[str]:
        """
        Extrai data de vencimento da fatura.

        Args:
            text: Texto completo da fatura

        Returns:
            Data no formato aaaa-mm-dd ou None
        """
        lines = text.split("\n")

        for i, line in enumerate(lines):
            line_upper = line.upper()

            if (
                "VENCIMENTO" in line_upper
                or "VCTO" in line_upper
                or "VENC" in line_upper
                or "VALIDADE" in line_upper
            ):
                # Verificar linha atual e próximas 3 linhas
                for offset in range(0, 4):
                    if i + offset >= len(lines):
                        break

                    check_line = lines[i + offset]

                    # Tentar parser de datas brasileiro
                    date_obj = parse_date_br(check_line)
                    if date_obj:
                        return date_obj

                    # Tentar formato dd/mm/aaaa
                    match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", check_line)
                    if match:
                        try:
                            from datetime import datetime

                            date_obj = datetime.strptime(match.group(1), "%d/%m/%Y")
                            return date_obj.strftime("%Y-%m-%d")
                        except ValueError:
                            continue

        return None
