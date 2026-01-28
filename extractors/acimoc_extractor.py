"""
Extrator específico para boletos da ACIMOC (Associação Comercial Industrial e de Serviços de Montes Claros).

Este módulo resolve problemas de extração em boletos da ACIMOC que estão sendo classificados
erroneamente como documentos administrativos, e extraindo valores zero quando há valores reais.

Problemas identificados:
1. Classificação incorreta: Boletos ACIMOC sendo capturados por AdminDocumentExtractor
2. Valor zero falso: Múltiplos "R$ 0,00" como placeholders ocultam valor real (ex: R$ 79,00)
3. Formato específico: Recibo do Sacado com estrutura não padronizada

Critérios de ativação:
- Texto contém "ACIMOC" (Associação Comercial Industrial e de Serviços de Montes Claros)
- Texto contém "RECIBO DO SACADO"
- Ausência de indicadores fortes de documentos administrativos (guia processual, distrato, etc.)

Campos extraídos:
- fornecedor_nome: ASSOCIAÇÃO COML. INDL. E SERVIÇOS DE MONTES CLAROS (normalizado)
- valor_documento: Primeiro valor não-zero encontrado após "VALOR DO DOCUMENTO" ou similar
- vencimento: Data extraída do contexto
- numero_documento: Número do boleto (ex: 401-301)
- empresa: Empresa pagadora (extraída do contexto ou assunto do email)
- cnpj_beneficiario: CNPJ 22.677.702/0001-47 (hardcoded para ACIMOC)

Example:
    >>> from extractors.acimoc_extractor import AcimocExtractor
    >>> if AcimocExtractor.can_handle(texto):
    ...     dados = AcimocExtractor().extract(texto)
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
class AcimocExtractor(BaseExtractor):
    """
    Extrator especializado em boletos da ACIMOC.

    Identifica e extrai campos específicos de boletos da Associação Comercial
    Industrial e de Serviços de Montes Claros, resolvendo problemas de
    classificação e extração de valores.
    """

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se o documento é um boleto da ACIMOC.

        Critérios:
        - Contém "ACIMOC" ou nome completo da associação
        - Contém "RECIBO DO SACADO"
        - Não é documento administrativo (guia processual, distrato, etc.)
        - Não é DANFSe ou NFSe

        Args:
            text: Texto completo do documento

        Returns:
            True se for boleto da ACIMOC, False caso contrário
        """
        if not text:
            return False

        text_upper = text.upper()
        text_compact = _compact(text_upper)

        # Indicadores positivos da ACIMOC
        acimoc_indicators = [
            "ACIMOC",
            "ASSOCIAÇÃO COMERCIAL INDUSTRIAL E DE SERVIÇOS DE MONTES CLAROS",
            "ASSOCIAÇÃO COML. INDL. E SERVIÇOS DE MONTES CLAROS",
            "RECIBO DO SACADO",  # Padrão específico dos boletos ACIMOC
        ]

        # Verificar indicadores da ACIMOC
        has_acimoc = False
        for indicator in acimoc_indicators:
            if indicator in text_upper or _compact(indicator) in text_compact:
                has_acimoc = True
                break

        if not has_acimoc:
            return False

        # EXCLUSÕES: Não deve ser documento administrativo ou fiscal
        exclusion_patterns = [
            # Documentos fiscais
            r"CHAVE\s+DE\s+ACESSO",
            r"DANFSE",
            r"DOCUMENTO\s+AUXILIAR",
            r"NOTA\s+FISCAL",
            r"NFSE",
            r"NFS-E",
            # Documentos administrativos problemáticos
            r"GUIA\s+[-–]\s+PROCESSO",
            r"DISTRATO",
            r"RESCIS[ÓO]RIO",
            r"ENCERRAMENTO\s+DE\s+CONTRATO",
            r"SOLICITA[ÇC][AÃ]O\s+DE\s+ENCERRAMENTO",
        ]

        for pattern in exclusion_patterns:
            if re.search(pattern, text_upper, re.IGNORECASE):
                logging.getLogger(__name__).debug(
                    f"AcimocExtractor: can_handle rejeitado - documento excluído pelo padrão: {pattern}"
                )
                return False

        # Verificar se tem características de boleto
        boleto_indicators = [
            "VALOR",
            "VENCIMENTO",
            "DOCUMENTO",
            "CEDENTE",
            "SACADO",
            "PAGADOR",
        ]

        boleto_score = sum(1 for ind in boleto_indicators if ind in text_upper)

        # É boleto da ACIMOC se tem indicadores suficientes
        # e não foi excluído pelos padrões acima
        return boleto_score >= 2

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados estruturados do boleto da ACIMOC.

        Estratégia especial:
        1. Prioriza valores não-zero (ignora múltiplos "R$ 0,00" como placeholders)
        2. Busca valores próximos a contextos específicos ("VALOR DO DOCUMENTO")
        3. Extrai fornecedor normalizado (padrão ACIMOC)
        4. CNPJ hardcoded para consistência

        Args:
            text: Texto completo do boleto

        Returns:
            Dicionário com campos extraídos
        """
        data = {}
        data["tipo_documento"] = "BOLETO"
        data["doc_type"] = "BOLETO"

        # Fornecedor hardcoded para consistência
        data["fornecedor_nome"] = "ASSOCIAÇÃO COML. INDL. E SERVIÇOS DE MONTES CLAROS"
        data["cnpj_beneficiario"] = "22.677.702/0001-47"  # CNPJ da ACIMOC

        # Campos extraídos
        data["valor_documento"] = self._extract_valor_acimoc(text)
        data["valor_total"] = data["valor_documento"]  # Alias para compatibilidade
        data["vencimento"] = self._extract_vencimento(text)
        data["numero_documento"] = self._extract_numero_documento(text)
        data["numero_nota"] = data["numero_documento"]  # Alias para compatibilidade
        data["empresa"] = self._extract_empresa(text)
        data["data_emissao"] = self._extract_data_emissao(text)

        logging.getLogger(__name__).info(
            f"AcimocExtractor: documento processado - "
            f"valor: R$ {data['valor_documento']:.2f}, "
            f"vencimento: {data['vencimento']}, "
            f"numero: {data['numero_documento']}, "
            f"empresa: {data['empresa']}"
        )

        return data

    def _extract_valor_acimoc(self, text: str) -> float:
        """
        Extrai valor do boleto ACIMOC, priorizando valores não-zero.

        Estratégia:
        1. Busca valores próximos a contextos específicos: "VALOR DO DOCUMENTO", "VALOR"
        2. Ignora múltiplos "R$ 0,00" que são placeholders
        3. Prioriza primeiro valor não-zero encontrado

        Args:
            text: Texto completo do boleto

        Returns:
            Valor como float, 0.0 se não encontrado
        """
        lines = text.split("\n")

        # Contextos prioritários para busca de valor
        priority_contexts = [
            "VALOR DO DOCUMENTO",
            "VALOR",
            "VALOR A PAGAR",
            "VALOR DO BOLETO",
        ]

        # Coletar todos os valores monetários encontrados
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
                # Padrão monetário: R$ 1.234,56 ou 1.234,56
                matches = re.findall(r"R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})", check_line)

                for match in matches:
                    try:
                        valor = float(match.replace(".", "").replace(",", "."))
                        # Se for contexto prioritário, adicionar com peso
                        if has_priority_context and offset == 0:
                            all_values.append((valor, 2))  # Peso 2 para prioridade
                        else:
                            all_values.append((valor, 1))  # Peso 1 padrão
                    except (ValueError, AttributeError):
                        continue

        # Se não encontrou valores, retorna 0
        if not all_values:
            return 0.0

        # Priorizar valores não-zero
        non_zero_values = [(val, weight) for val, weight in all_values if val > 0.0]

        if non_zero_values:
            # Ordenar por peso (maior primeiro) e valor (maior primeiro)
            non_zero_values.sort(key=lambda x: (-x[1], -x[0]))
            return non_zero_values[0][0]

        # Se só tem zeros, retorna 0
        return 0.0

    def _extract_vencimento(self, text: str) -> Optional[str]:
        """
        Extrai data de vencimento do boleto.

        Estratégia:
        1. Busca "VENCIMENTO" no texto
        2. Procura datas nas linhas próximas
        3. Tenta múltiplos formatos (dd/mm/aaaa, aaaa-mm-dd)

        Args:
            text: Texto completo do boleto

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

                    # Tentar formato aaaa-mm-dd
                    match = re.search(r"(\d{4}-\d{2}-\d{2})", check_line)
                    if match:
                        return match.group(1)

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

    def _extract_numero_documento(self, text: str) -> Optional[str]:
        """
        Extrai número do documento/boleto.

        Padrões comuns na ACIMOC:
        - "Número: 401-301"
        - "Documento: 401-301"
        - Padrão XXX-XXX

        Args:
            text: Texto completo do boleto

        Returns:
            Número do documento ou None
        """
        # Padrão XXX-XXX (ex: 401-301)
        pattern1 = r"(?:N[ÚU]MERO|DOCUMENTO|BOLETO)[:\s]+(\d{3,4}-\d{3,4})"
        match = re.search(pattern1, text, re.IGNORECASE)
        if match:
            return match.group(1)

        # Buscar padrão XXX-XXX em qualquer lugar
        pattern2 = r"\b(\d{3,4}-\d{3,4})\b"
        match = re.search(pattern2, text)
        if match:
            return match.group(1)

        # Buscar números sequenciais
        pattern3 = r"(?:N[ÚU]MERO|DOCUMENTO)[:\s]+(\d{6,10})"
        match = re.search(pattern3, text, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _extract_empresa(self, text: str) -> Optional[str]:
        """
        Extrai nome da empresa pagadora.

        Procura por:
        1. "Sacado:" seguido de nome
        2. "Pagador:" seguido de nome
        3. Empresas conhecidas do grupo (MOC, etc.)

        Args:
            text: Texto completo do boleto

        Returns:
            Nome da empresa ou None
        """
        lines = text.split("\n")

        # Empresas conhecidas do grupo
        known_companies = [
            "MOC",
            "MOC COMUNICACAO",
            "CSC",
            "CARRIER",
            "ITACOLOMI",
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
            if "SACADO:" in line_upper or "PAGADOR:" in line_upper:
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

    def _extract_data_emissao(self, text: str) -> Optional[str]:
        """
        Extrai data de emissão do boleto.

        Args:
            text: Texto completo do boleto

        Returns:
            Data no formato aaaa-mm-dd ou None
        """
        # Buscar "EMISSÃO", "DATA", "DATA DO DOCUMENTO"
        lines = text.split("\n")

        for i, line in enumerate(lines):
            line_upper = line.upper()

            if any(
                keyword in line_upper
                for keyword in ["EMISSÃO", "EMISSAO", "DATA DO DOCUMENTO", "DATA"]
            ):
                # Verificar linha atual e próximas 2 linhas
                for offset in range(0, 3):
                    if i + offset >= len(lines):
                        break

                    check_line = lines[i + offset]
                    date_obj = parse_date_br(check_line)
                    if date_obj:
                        return date_obj

        return None
