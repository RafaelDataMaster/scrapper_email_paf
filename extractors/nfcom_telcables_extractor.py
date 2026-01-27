"""
Extrator específico para NFCom (Nota Fiscal de Comunicação) da Telcables Brasil.

Este extrator lida com o layout específico de documentos NFCom emitidos pela
Telcables Brasil LTDA (CNPJ: 20.609.743/0004-13) para empresas do grupo,
como a Carrier Telecom S/A.

Layout característico:
- "DOCUMENTO AUXILIAR DA NOTA FISCAL FATURA DE SERVIÇOS DE COMUNICAÇÃO ELETRÔNICA"
- "NOME: TELCABLES BRASIL LTDA FILIAL SAO PAULO"
- "NOTA FISCAL FATURA: [número]"
- "SÉRIE: 1 VENCIMENTO: [data]"
- "TOTAL A PAGAR: R$ [valor]"
- Chave de acesso de 44 dígitos (formato NFCom)

Criado para resolver casos como:
- "01_NFcom 114 CARRIER TELECOM.pdf"
- Valor R$ 0,00 extraído incorretamente pelo extrator genérico
- Fornecedor "Cobrança BR" (fallback do remetente) em vez de "TELCABLES BRASIL"
"""

import re
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from core.extractors import BaseExtractor, register_extractor
from core.models import InvoiceData
from extractors.utils import (
    parse_br_money,
    parse_date_br,
    extract_cnpj_flexible,
    format_cnpj,
    normalize_text_for_extraction,
    normalize_entity_name,
)


@register_extractor
class NfcomTelcablesExtractor(BaseExtractor):
    """Extrator específico para NFCom da Telcables Brasil."""

    # CNPJ da Telcables Brasil LTDA Filial Sao Paulo
    TELCABLES_CNPJ = "20.609.743/0004-13"
    TELCABLES_CNPJ_DIGITS = "20609743000413"

    # Padrões exclusivos deste fornecedor
    TELCABLES_IDENTIFIERS = [
        r"TELCABLES\s+BRASIL\s+LTDA",
        r"DOCUMENTO\s+AUXILIAR\s+DA\s+NOTA\s+FISCAL\s+FATURA\s+DE\s+SERVI[ÇC]OS\s+DE\s+COMUNICA[ÇC][AÃ]O\s+ELETR[ÔO]NICA",
        r"NOTA\s+FISCAL\s+FATURA\s*:\s*\d+",  # Formato específico: "NOTA FISCAL FATURA: 114"
        r"S[ÉE]RIE\s*:\s*1\s+VENCIMENTO",  # Série sempre 1 seguido de VENCIMENTO
    ]

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se o documento é uma NFCom da Telcables Brasil.

        Critérios (um dos seguintes):
        1. Contém CNPJ da Telcables Brasil (20.609.743/0004-13)
        2. Contém "TELCABLES BRASIL LTDA" + indicadores de NFCom
        3. Contém padrão específico "NOTA FISCAL FATURA: [número]" + "SÉRIE: 1 VENCIMENTO:"

        Args:
            text: Texto extraído do PDF

        Returns:
            True se for NFCom da Telcables Brasil
        """
        if not text:
            return False

        text_upper = text.upper()

        # 1. Verifica CNPJ da Telcables Brasil
        cnpj = extract_cnpj_flexible(text)
        if cnpj and cls.TELCABLES_CNPJ_DIGITS in cnpj.replace(".", "").replace(
            "/", ""
        ).replace("-", ""):
            logging.debug(
                f"NfcomTelcablesExtractor: CNPJ da Telcables detectado: {cnpj}"
            )
            return True

        # 2. Verifica nome da empresa + indicadores fortes
        if "TELCABLES BRASIL" in text_upper:
            # Verifica se tem indicadores de documento fiscal (não é administrativo)
            has_fiscal_indicators = (
                "DOCUMENTO AUXILIAR" in text_upper
                or "CHAVE DE ACESSO" in text_upper
                or "NOTA FISCAL" in text_upper
            )
            if has_fiscal_indicators:
                logging.debug(
                    "NfcomTelcablesExtractor: Nome Telcables + indicadores fiscais detectados"
                )
                return True

        # 3. Verifica padrões exclusivos do layout Telcables
        patterns_score = 0
        for pattern in cls.TELCABLES_IDENTIFIERS:
            if re.search(pattern, text_upper, re.IGNORECASE):
                patterns_score += 1

        # Se tem pelo menos 2 padrões exclusivos, é documento Telcables
        if patterns_score >= 2:
            logging.debug(
                f"NfcomTelcablesExtractor: {patterns_score} padrões exclusivos detectados"
            )
            return True

        return False

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados da NFCom da Telcables Brasil.

        Campos extraídos:
        - fornecedor_nome: "TELCABLES BRASIL LTDA FILIAL SAO PAULO"
        - cnpj_prestador: "20.609.743/0004-13"
        - numero_nota: número após "NOTA FISCAL FATURA:"
        - valor_total: valor após "TOTAL A PAGAR: R$"
        - vencimento: data após "VENCIMENTO:"
        - data_emissao: data após "DATA DE EMISSÃO:" ou data do protocolo

        Args:
            text: Texto extraído do PDF

        Returns:
            Dicionário com campos extraídos no formato do InvoiceData
        """
        text = normalize_text_for_extraction(text or "")
        text_upper = text.upper()

        data: Dict[str, Any] = {"tipo_documento": "NFSE"}

        # 1. Fornecedor - padrão específico "NOME: [nome completo]"
        fornecedor = self._extract_fornecedor(text)
        if fornecedor:
            data["fornecedor_nome"] = fornecedor

        # 2. CNPJ - usa CNPJ fixo da Telcables ou extrai do texto
        cnpj = self._extract_cnpj(text)
        if cnpj:
            data["cnpj_prestador"] = cnpj

        # 3. Número da nota - padrão: "NOTA FISCAL FATURA: 114"
        numero_nota = self._extract_numero_nota(text)
        if numero_nota:
            data["numero_nota"] = numero_nota

        # 4. Valor total - padrão: "TOTAL A PAGAR: R$ 29.250,00"
        valor_total = self._extract_valor(text)
        data["valor_total"] = valor_total

        # 5. Vencimento - padrão: "VENCIMENTO: 23/12/2025"
        vencimento = self._extract_vencimento(text)
        if vencimento:
            data["vencimento"] = vencimento

        # 6. Data de emissão - padrão: "DATA DE EMISSÃO:" ou do protocolo
        data_emissao = self._extract_data_emissao(text)
        if data_emissao:
            data["data_emissao"] = data_emissao

        # 7. Série - sempre "1" nos documentos Telcables
        data["serie_nf"] = "1"

        # 8. Campos padrão (setados como None)
        data["valor_ir"] = None
        data["valor_inss"] = None
        data["valor_csll"] = None
        data["valor_iss"] = None
        data["valor_icms"] = None
        data["base_calculo_icms"] = None
        data["forma_pagamento"] = None
        data["numero_pedido"] = None
        data["numero_fatura"] = None

        return data

    def _extract_fornecedor(self, text: str) -> Optional[str]:
        """
        Extrai nome do fornecedor usando padrão específico Telcables.

        Padrões:
        1. "NOME: TELCABLES BRASIL LTDA FILIAL SAO PAULO" (mais comum)
        2. Texto antes do CNPJ da Telcables
        3. "TELCABLES BRASIL LTDA" em qualquer posição

        Args:
            text: Texto normalizado

        Returns:
            Nome do fornecedor normalizado ou None
        """
        # Padrão 1: "NOME: [Nome completo]" (case insensitive)
        nome_pattern = r"(?i)NOME\s*[:\-]\s*([^\n]+)"
        match = re.search(nome_pattern, text)
        if match:
            fornecedor = match.group(1).strip()
            # Remove possíveis CNPJ/CPF que possam estar na mesma linha
            fornecedor = re.sub(
                r"\s*\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s*", " ", fornecedor
            )
            fornecedor = re.sub(r"\s*\d{3}\.\d{3}\.\d{3}-\d{2}\s*", " ", fornecedor)
            fornecedor = re.sub(r"\s+", " ", fornecedor).strip()
            return normalize_entity_name(fornecedor)

        # Padrão 2: Texto antes do CNPJ da Telcables
        cnpj_pattern = r"20[\.\s]?609[\.\s]?743[\.\s]?0004[\.\s]?13"
        cnpj_match = re.search(cnpj_pattern, text)
        if cnpj_match:
            # Pega até 100 caracteres antes do CNPJ
            start_pos = max(0, cnpj_match.start() - 100)
            text_before = text[start_pos : cnpj_match.start()]
            # Encontra a última sequência de palavras que parece nome de empresa
            empresa_match = re.search(
                r"([A-ZÀ-ÿ][A-Za-zÀ-ÿ\s&\.\-]{10,80}(?:LTDA|S/?A|EIRELI))", text_before
            )
            if empresa_match:
                return normalize_entity_name(empresa_match.group(1))

        # Padrão 3: "TELCABLES BRASIL LTDA" em qualquer lugar
        if "TELCABLES BRASIL" in text.upper():
            # Tenta capturar variações completas
            telcables_pattern = (
                r"(?i)(TELCABLES\s+BRASIL\s+LTDA(?:\s+FILIAL\s+[A-Z\s]+)?)"
            )
            match = re.search(telcables_pattern, text)
            if match:
                return normalize_entity_name(match.group(1))
            else:
                return "TELCABLES BRASIL LTDA"

        return None

    def _extract_cnpj(self, text: str) -> Optional[str]:
        """
        Extrai CNPJ da Telcables Brasil.

        Prioridade:
        1. CNPJ fixo da Telcables (já conhecido)
        2. CNPJ extraído do texto que corresponda ao da Telcables
        3. None se não encontrar

        Args:
            text: Texto normalizado

        Returns:
            CNPJ formatado ou None
        """
        # Primeiro tenta o CNPJ fixo (já sabemos qual é)
        cnpj = self.TELCABLES_CNPJ

        # Verifica se o CNPJ está no texto (validação extra)
        cnpj_digits = self.TELCABLES_CNPJ_DIGITS
        text_digits = re.sub(r"\D", "", text)
        if cnpj_digits in text_digits:
            return cnpj

        # Se não encontrou no texto, tenta extrair qualquer CNPJ
        # (pode ser que o documento tenha CNPJ formatado diferente)
        extracted_cnpj = extract_cnpj_flexible(text)
        if extracted_cnpj:
            extracted_digits = re.sub(r"\D", "", extracted_cnpj)
            if extracted_digits == cnpj_digits:
                return extracted_cnpj

        # Se chegou aqui, retorna o CNPJ fixo mesmo não estando no texto
        # (pode ser caso de OCR ruim, mas sabemos que é Telcables)
        return cnpj

    def _extract_numero_nota(self, text: str) -> Optional[str]:
        """
        Extrai número da nota usando padrão específico Telcables.

        Padrão: "NOTA FISCAL FATURA: 114"
        Também aceita: "NOTA FATURA: 114", "NF FATURA: 114"

        Args:
            text: Texto normalizado

        Returns:
            Número da nota ou None
        """
        # Padrão principal: "NOTA FISCAL FATURA: 114"
        patterns = [
            r"(?i)NOTA\s+FISCAL\s+FATURA\s*[:\-]?\s*(\d+)",
            r"(?i)NOTA\s+FATURA\s*[:\-]?\s*(\d+)",
            r"(?i)NF\s+FATURA\s*[:\-]?\s*(\d+)",
            r"(?i)FATURA\s*[:\-]?\s*(\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                numero = match.group(1).strip()
                # Remove zeros à esquerda não significativos, mas mantém o número
                return str(int(numero)) if numero.isdigit() else numero

        return None

    def _extract_valor(self, text: str) -> float:
        """
        Extrai valor total usando padrão específico Telcables.

        Padrão principal: "TOTAL A PAGAR: R$ 29.250,00"
        Fallback: qualquer valor R$ que seja o maior no documento

        Args:
            text: Texto normalizado

        Returns:
            Valor como float (0.0 se não encontrar)
        """
        # Padrão específico Telcables: "TOTAL A PAGAR: R$ 29.250,00"
        total_patterns = [
            r"(?i)TOTAL\s+A\s+PAGAR\s*[:\-]?\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)VALOR\s+TOTAL\s*[:\-]?\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)TOTAL\s*[:\-]?\s*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        ]

        for pattern in total_patterns:
            match = re.search(pattern, text)
            if match:
                valor_str = match.group(1)
                valor = parse_br_money(valor_str)
                if valor > 0:
                    logging.debug(
                        f"NfcomTelcablesExtractor: Valor extraído '{valor_str}' -> {valor}"
                    )
                    return valor

        # Fallback: busca qualquer valor R$ no texto
        # Pega o maior valor (provavelmente o total)
        money_pattern = r"R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})"
        matches = re.findall(money_pattern, text, re.IGNORECASE)
        valores = []
        for match in matches:
            valor = parse_br_money(match)
            if valor > 0:
                valores.append(valor)

        if valores:
            maior_valor = max(valores)
            logging.debug(
                f"NfcomTelcablesExtractor: Fallback - maior valor encontrado: {maior_valor}"
            )
            return maior_valor

        return 0.0

    def _extract_vencimento(self, text: str) -> Optional[str]:
        """
        Extrai data de vencimento usando padrão específico Telcables.

        Padrão: "VENCIMENTO: 23/12/2025"
        Observação: Série sempre "1" seguida de VENCIMENTO: "SÉRIE: 1 VENCIMENTO:"

        Args:
            text: Texto normalizado

        Returns:
            Data no formato ISO (YYYY-MM-DD) ou None
        """
        # Padrão específico Telcables: "SÉRIE: 1 VENCIMENTO: 23/12/2025"
        vencimento_patterns = [
            r"(?i)S[ÉE]RIE\s*[:\-]?\s*1\s+VENCIMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"(?i)VENCIMENTO\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"(?i)VENC\.?\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
        ]

        for pattern in vencimento_patterns:
            match = re.search(pattern, text)
            if match:
                data_str = match.group(1)
                data_iso = parse_date_br(data_str)
                if data_iso:
                    logging.debug(
                        f"NfcomTelcablesExtractor: Vencimento extraído '{data_str}' -> {data_iso}"
                    )
                    return data_iso

        return None

    def _extract_data_emissao(self, text: str) -> Optional[str]:
        """
        Extrai data de emissão.

        Padrões:
        1. "DATA DE EMISSÃO: [data]"
        2. Data do protocolo de autorização
        3. Primeira data encontrada no texto (fallback)

        Args:
            text: Texto normalizado

        Returns:
            Data no formato ISO (YYYY-MM-DD) ou None
        """
        # Padrão 1: "DATA DE EMISSÃO:"
        emissao_patterns = [
            r"(?i)DATA\s+DE\s+EMISS[AÃ]O\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"(?i)DATA\s+EMISS[AÃ]O\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
            r"(?i)EMISS[AÃ]O\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
        ]

        for pattern in emissao_patterns:
            match = re.search(pattern, text)
            if match:
                data_str = match.group(1)
                data_iso = parse_date_br(data_str)
                if data_iso:
                    return data_iso

        # Padrão 2: Data do protocolo "Protocolo de Autorização: 3352500028624395 - 10/11/2025 às 16:34:41"
        protocolo_pattern = (
            r"Protocolo\s+de\s+Autoriza[çc][aã]o[^\-]+\-\s*(\d{2}/\d{2}/\d{4})"
        )
        match = re.search(protocolo_pattern, text, re.IGNORECASE)
        if match:
            data_str = match.group(1)
            data_iso = parse_date_br(data_str)
            if data_iso:
                return data_iso

        # Fallback: primeira data encontrada que não seja vencimento
        # Extrai todas as datas e pega a mais antiga (provavelmente emissão)
        date_pattern = r"\b(\d{2}/\d{2}/\d{4})\b"
        dates = re.findall(date_pattern, text)
        if dates:
            # Converte para objetos datetime para comparar
            parsed_dates = []
            for date_str in dates:
                date_iso = parse_date_br(date_str)
                if date_iso:
                    try:
                        dt = datetime.strptime(date_iso, "%Y-%m-%d")
                        parsed_dates.append((dt, date_iso))
                    except ValueError:
                        continue

            if parsed_dates:
                # Ordena por data (mais antiga primeiro)
                parsed_dates.sort(key=lambda x: x[0])
                # Retorna a mais antiga (provavelmente emissão)
                return parsed_dates[0][1]

        return None


# Testes de validação (para incluir em testes unitários posteriormente)
"""
TESTES DE VALIDAÇÃO PARA NfcomTelcablesExtractor:

Caso 1: Documento Carrier Telecom (caso original)
Input:
    DOCUMENTO AUXILIAR DA NOTA FISCAL FATURA DE SERVIÇOS DE COMUNICAÇÃO ELETRÔNICA
    NOME: TELCABLES BRASIL LTDA FILIAL SAO PAULO
    CPF/CNPJ: 20.609.743/0004-13
    NOTA FISCAL FATURA: 114
    SÉRIE: 1 VENCIMENTO: 23/12/2025
    TOTAL A PAGAR: R$ 29.250,00

Output esperado:
    can_handle: True
    fornecedor_nome: "TELCABLES BRASIL LTDA FILIAL SAO PAULO"
    cnpj_prestador: "20.609.743/0004-13"
    numero_nota: "114"
    valor_total: 29250.0
    vencimento: "2025-12-23"
    serie_nf: "1"

Caso 2: Documento similar com variações
Input:
    DOC. AUX. NOTA FISCAL SERV COMUN ELETR
    TELCABLES BRASIL LTDA
    CNPJ: 20.609.743/0004-13
    NOTA FATURA: 115
    VENCIMENTO: 25/12/2025
    TOTAL: R$ 15.000,00

Output esperado:
    can_handle: True
    fornecedor_nome: "TELCABLES BRASIL LTDA"
    cnpj_prestador: "20.609.743/0004-13"
    numero_nota: "115"
    valor_total: 15000.0
    vencimento: "2025-12-25"

Caso 3: Documento não Telcables (deve ser rejeitado)
Input:
    NOTA FISCAL DE SERVIÇO ELETRÔNICA
    FORNECEDOR: OUTRA EMPRESA LTDA
    CNPJ: 12.345.678/0001-99
    VALOR TOTAL: R$ 1.000,00

Output esperado:
    can_handle: False

Caso edge 1: OCR com caracteres ruins
Input:
    DOCUMENTO AUXILIAR DA NOTA FISCAL FATURA DE SERVICOS DE COMUNICACAO ELETRONICA
    NOME: TELCABLES BRASIL LTDA FILIAL SAO PAULO
    CPF/CNPJ: 20.609.743/0004-13
    NOTA FISCAL FATURA: 114
    SERIE: 1 VENCIMENTO: 23/12/2025
    TOTAL A PAGAR: R$ 29.250,00

Output esperado:
    can_handle: True (deve tolerar acentos faltantes)

Caso edge 2: Documento administrativo mencionando Telcables
Input:
    RELATÓRIO DE SERVIÇOS TELCABLES BRASIL
    Este é um relatório administrativo, não uma nota fiscal.

Output esperado:
    can_handle: False (não tem indicadores fiscais)
"""
