"""
Extrator específico para documentos da PRÓ - PAINEL LTDA.

Este módulo resolve problemas de extração em documentos da PRÓ - PAINEL que não estão sendo
reconhecidos pelos extratores existentes.

Problemas identificados:
1. Boletos PIX da PRÓ PAINEL não reconhecidos
2. Faturas de locação não classificadas corretamente
3. Valores não extraídos de documentos de locação

Critérios de ativação:
- Texto contém "PRÓ - PAINEL", "PRÓ PAINEL", "PRO PAINEL" ou "PRO PAINEL LTDA"
- Pode ser boleto PIX ou fatura de locação

Campos extraídos:
- fornecedor_nome: PRÓ - PAINEL LTDA (normalizado)
- valor_documento: Valor total (ex: 2.415,66)
- vencimento: Data de vencimento (para boletos)
- data_emissao: Data de emissão (para faturas)
- numero_documento: Número do documento (ex: 9638)
- empresa: Empresa cliente (CSC, etc.)
- cnpj_beneficiario (BOLETO) ou cnpj_prestador (NFSE): CNPJ 23.129.448/0001-05
- doc_type: BOLETO ou NFSE (conforme tipo detectado)

Example:
    >>> from extractors.pro_painel_extractor import ProPainelExtractor
    >>> if ProPainelExtractor.can_handle(texto):
    ...     dados = ProPainelExtractor().extract(texto)
    ...     print(f"Valor: R$ {dados['valor_documento']:.2f}")
"""

import re
import logging
from typing import Any, Dict, Optional

from core.extractors import BaseExtractor, register_extractor
from extractors.utils import (
    normalize_entity_name,
    parse_date_br,
    strip_accents,
)


def _compact(text: str) -> str:
    """Compacta texto removendo caracteres não alfanuméricos."""
    return re.sub(r"[^A-Z0-9]+", "", strip_accents((text or "").upper()))


@register_extractor
class ProPainelExtractor(BaseExtractor):
    """
    Extrator especializado em documentos da PRÓ - PAINEL LTDA.

    Identifica e extrai campos específicos de boletos PIX e faturas de locação
    da PRÓ PAINEL, resolvendo problemas de reconhecimento e extração.
    """

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se o documento é da PRÓ - PAINEL LTDA.

        Critérios:
        - Contém "PRÓ - PAINEL", "PRÓ PAINEL", "PRO PAINEL" ou similar
        - Não é documento de outro fornecedor específico

        Args:
            text: Texto completo do documento

        Returns:
            True se for documento da PRÓ PAINEL, False caso contrário
        """
        if not text:
            return False

        text_upper = text.upper()
        text_compact = _compact(text_upper)

        # Indicadores positivos da PRÓ PAINEL
        propainel_indicators = [
            "PRÓ - PAINEL",
            "PRÓ PAINEL",
            "PRO PAINEL",
            "PRO PAINEL LTDA",
            "PRÓ-PAINEL",
            "PROPAINEL",
        ]

        # Verificar indicadores
        has_propainel = False
        for indicator in propainel_indicators:
            if indicator in text_upper or _compact(indicator) in text_compact:
                has_propainel = True
                break

        if not has_propainel:
            return False

        # EXCLUSÕES: Não deve ser documento de outro fornecedor específico
        # (mas pode ser boleto ou fatura de locação)
        exclusion_patterns = [
            # Outros fornecedores específicos
            r"MUGO TELECOM",
            r"ACIMOC",
            r"REPROMAQ",
            r"EMC TECNOLOGIA",
            r"NET CENTER",
        ]

        for pattern in exclusion_patterns:
            if re.search(pattern, text_upper, re.IGNORECASE):
                logging.getLogger(__name__).debug(
                    f"ProPainelExtractor: can_handle rejeitado - documento de outro fornecedor: {pattern}"
                )
                return False

        return True

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados estruturados do documento da PRÓ PAINEL.

        Estratégia:
        1. Determinar tipo do documento (boleto ou fatura de locação)
        2. Extrair valor total
        3. Extrair datas (vencimento/emissão)
        4. Extrair número do documento
        5. Identificar empresa cliente
        6. Fornecedor e CNPJ hardcoded para consistência

        Args:
            text: Texto completo do documento

        Returns:
            Dicionário com campos extraídos
        """
        data = {}

        # Determinar tipo do documento
        text_upper = text.upper()
        if "BOLETO PIX" in text_upper or "VALOR DO DOCUMENTO" in text_upper:
            data["tipo_documento"] = "BOLETO"
            data["doc_type"] = "BOLETO"
        elif "FATURA DE LOCAÇÃO" in text_upper or "LOCAÇÃO" in text_upper:
            data["tipo_documento"] = "NFSE"
            data["doc_type"] = "NFSE"
        else:
            # Padrão default
            data["tipo_documento"] = "NFSE"
            data["doc_type"] = "NFSE"

        # Fornecedor hardcoded para consistência
        data["fornecedor_nome"] = "PRÓ - PAINEL LTDA"
        # CNPJ conforme tipo do documento
        if data.get("tipo_documento") == "BOLETO":
            data["cnpj_beneficiario"] = "23.129.448/0001-05"  # CNPJ da PRÓ PAINEL
        else:
            data["cnpj_prestador"] = "23.129.448/0001-05"  # CNPJ da PRÓ PAINEL

        # Campos extraídos
        data["valor_documento"] = self._extract_valor_propainel(text)
        data["valor_total"] = data["valor_documento"]  # Alias para compatibilidade
        data["vencimento"] = self._extract_vencimento(text)
        data["data_emissao"] = self._extract_data_emissao(text)
        data["numero_documento"] = self._extract_numero_documento(text)
        data["numero_nota"] = data["numero_documento"]  # Alias para compatibilidade
        data["empresa"] = self._extract_empresa(text)

        logging.getLogger(__name__).info(
            f"ProPainelExtractor: documento processado - "
            f"tipo: {data['tipo_documento']}, "
            f"valor: R$ {data['valor_documento']:.2f}, "
            f"vencimento: {data['vencimento']}, "
            f"numero: {data['numero_documento']}, "
            f"empresa: {data['empresa']}"
        )

        return data

    def _extract_valor_propainel(self, text: str) -> float:
        """
        Extrai valor total do documento da PRÓ PAINEL.

        Estratégia:
        1. Buscar "VALOR DO DOCUMENTO" em boletos
        2. Buscar valores em contextos de total em faturas
        3. Priorizar valores maiores e não-zero

        Args:
            text: Texto completo do documento

        Returns:
            Valor como float, 0.0 se não encontrado
        """
        lines = text.split("\n")

        # Contextos prioritários para busca de valor
        priority_contexts = [
            "VALOR DO DOCUMENTO",
            "VALOR",
            "TOTAL",
            "VALOR TOTAL",
            "VALOR A PAGAR",
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

                # Padrão monetário: R$ 1.234,56 ou 1.234,56
                matches = re.findall(
                    r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})", check_line
                )

                for match in matches:
                    try:
                        # Remover pontos de milhar e converter vírgula para ponto
                        valor_str = match.replace(".", "").replace(",", ".")
                        valor = float(valor_str)

                        # Filtrar valores muito pequenos
                        if valor < 0.01:
                            continue

                        # Determinar peso baseado no contexto
                        peso = 1

                        # Contexto prioritário direto
                        if has_priority_context and offset == 0:
                            peso = 10

                        # Linha contém "VALOR DO DOCUMENTO" (muito específico de boleto)
                        if "VALOR DO DOCUMENTO" in check_line_upper:
                            peso = max(peso, 12)

                        # Linha contém "TOTAL"
                        if "TOTAL" in check_line_upper:
                            peso = max(peso, 8)

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

        # Retornar o valor com maior peso
        return all_values[0][0]

    def _extract_numero_documento(self, text: str) -> Optional[str]:
        """
        Extrai número do documento.

        Padrões comuns na PRÓ PAINEL:
        - "N.O: 9638" (fatura de locação)
        - "Entrada N.o: 9638"
        - "Nosso Número: 00019/112/9055516972-4" (boleto)
        - "Fatura: 9638 - MASTERCABO"

        Args:
            text: Texto completo do documento

        Returns:
            Número do documento ou None
        """
        # Padrões prioritários
        patterns = [
            r"N\.?O?:?\s*(\d{4,6})",  # N.O: 9638
            r"ENTRADA\s+N\.?O?:?\s*(\d{4,6})",  # Entrada N.o: 9638
            r"DOCUMENTO\s*[:]?\s*(\d{4,10})",  # Documento: 1234
            r"FATURA\s*[:]?\s*(\d{4,10})",  # Fatura: 1234
            r"NOSSO\s+N[ÚU]MERO\s*[:]?\s*([\d\/\-]{8,30})",  # Nosso Número: 00019/112/9055516972-4
            r"FATURA\s*[:]?\s*(\d{4,6})\s*[-–]\s*[A-Z]+",  # Fatura: 9638 - MASTERCABO
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                numero = match.group(1)
                # Limpar caracteres extras se necessário
                if "/" in numero or "-" in numero:
                    # Para números com formato 00019/112/9055516972-4, pegar a primeira parte ou o número completo
                    # Remover barras e hífens para padronização
                    numero_limpo = re.sub(r"[\/\-]", "", numero)
                    # Se for muito longo, pode ser linha digitável, então tentar pegar parte numérica menor
                    if len(numero_limpo) > 15:
                        # Procurar por sequência de 4-10 dígitos dentro do padrão
                        digitos = re.findall(r"\d{4,10}", numero)
                        if digitos:
                            return digitos[0]
                    return numero
                return numero

        # Buscar por sequências de 4-6 dígitos que podem ser números de documento
        all_matches = re.findall(r"\b(\d{4,6})\b", text)
        for match in all_matches:
            # Filtrar números que são datas, CEPs, etc.
            # 4-6 dígitos são bons candidatos para números de documento
            if not (
                match.startswith(("20", "19", "30", "31"))  # Datas, CEPs iniciais
                or len(match) == 5  # CEPs têm 5 dígitos antes do hífen
            ):
                return match

        return None

    def _extract_vencimento(self, text: str) -> Optional[str]:
        """
        Extrai data de vencimento.

        Args:
            text: Texto completo do documento

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

    def _extract_data_emissao(self, text: str) -> Optional[str]:
        """
        Extrai data de emissão.

        Args:
            text: Texto completo do documento

        Returns:
            Data no formato aaaa-mm-dd ou None
        """
        lines = text.split("\n")

        for i, line in enumerate(lines):
            line_upper = line.upper()

            if (
                "EMISSÃO" in line_upper
                or "EMISSAO" in line_upper
                or "DATA" in line_upper
                or "EMITIDO" in line_upper
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
        1. "Pagador:" seguido de nome (em boletos)
        2. Empresas conhecidas do grupo
        3. Nomes no contexto de cliente

        Args:
            text: Texto completo do documento

        Returns:
            Nome da empresa ou None
        """
        lines = text.split("\n")

        # Empresas conhecidas do grupo
        known_companies = [
            "CSC",
            "CSC GESTÃO INTEGRADA",
            "CSC GESTAO INTEGRADA",
            "MOC",
            "MOC COMUNICACAO",
            "ITACOLOMI",
            "ITACOLOMI COMUNICACAO",
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
            if "PAGADOR" in line_upper or "CLIENTE" in line_upper:
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
