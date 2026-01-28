"""
Extrator específico para NFS-e da Prefeitura de Vila Velha - ES.

Este módulo trata notas fiscais de serviço eletrônicas emitidas pela
prefeitura de Vila Velha, que possuem layout diferenciado onde:

- O número da nota aparece após duas timestamps consecutivas
- O valor dos serviços pode ser confundido com valor da Lei 12.741/2012
- Data de competência e emissão podem estar em formatos distintos

Campos extraídos:
    - numero_nota: Número da NFS-e
    - valor_total: Valor dos serviços (não confundir com tributos)
    - vencimento: Data de vencimento ou emissão como fallback
    - data_emissao: Data de emissão da nota

Critérios de ativação:
    - Texto contém "VILA VELHA" e "PREFEITURA"

Example:
    >>> from extractors.nfse_custom_vila_velha import NfseCustomVilaVelhaExtractor
    >>> extractor = NfseCustomVilaVelhaExtractor()
    >>> dados = extractor.extract(texto)
    >>> print(f"Nota {dados['numero_nota']}: R$ {dados['valor_total']:.2f}")
"""
import re
from typing import Any, Dict, Optional

from core.extractors import BaseExtractor, register_extractor


@register_extractor
class NfseCustomVilaVelhaExtractor(BaseExtractor):
    """Extrator específico para NFS-e da Prefeitura de Vila Velha - ES.

    Este extrator tem prioridade sobre o genérico para documentos de Vila Velha.
    Não herda de NfseGenericExtractor para evitar import circular que quebra
    a ordem de registro dos extractors.
    """

    @classmethod
    def can_handle(cls, text: str) -> bool:
        text_upper = (text or "").upper()
        # Critério de ativação: Nome da prefeitura no documento
        return "VILA VELHA" in text_upper and "PREFEITURA" in text_upper

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados da NFS-e de Vila Velha.

        Aplica extração customizada e depois delega para o genérico
        para preencher campos faltantes.
        """
        # Extrai campos customizados específicos de Vila Velha
        data = {
            'tipo_documento': 'NFSE',
            'numero_nota': self._extract_numero_nota(text),
            'valor_total': self._extract_valor(text),
            'vencimento': self._extract_vencimento(text),
        }

        # Se conseguiu extrair os campos customizados, usa eles
        # Senão, delega para o genérico
        if not data.get('numero_nota') or not data.get('valor_total'):
            # Import lazy para evitar circular import
            from extractors.nfse_generic import NfseGenericExtractor
            generic = NfseGenericExtractor()
            generic_data = generic.extract(text)

            # Merge: prioriza dados customizados quando existem
            for key, value in generic_data.items():
                if key not in data or not data[key]:
                    data[key] = value
        else:
            # Preenche campos básicos que o genérico também extrai
            from extractors.nfse_generic import NfseGenericExtractor
            generic = NfseGenericExtractor()
            generic_data = generic.extract(text)

            # Pega campos não customizados do genérico
            campos_nao_customizados = [
                'cnpj_prestador', 'fornecedor_nome', 'data_emissao',
                'valor_ir', 'valor_inss', 'valor_csll', 'valor_iss',
                'forma_pagamento', 'numero_pedido'
            ]

            for campo in campos_nao_customizados:
                if campo in generic_data and generic_data[campo]:
                    data[campo] = generic_data[campo]

        return data

    def _extract_numero_nota(self, text: str) -> Optional[str]:
        """
        Extrai número da nota em Vila Velha.

        Em Vila Velha, o número vem após a data de competência na sequência do texto.
        Padrão: 03/11/2025 10:00:41 03/11/2025 10:00:41 00001158
        """
        # Padrão específico de Vila Velha: duas datas com horas seguidas do número
        match = re.search(
            r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}\s+(\d+)",
            text
        )
        if match:
            return match.group(1)

        # Fallback: busca "Número" seguido de dígitos
        match = re.search(r'N[úu]mero[:\s]+(\d+)', text, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _extract_valor(self, text: str) -> float:
        """
        Extrai valor total da nota em Vila Velha.

        O genérico falhou porque pegou o valor da Lei 12.741/2012.
        Aqui buscamos especificamente pelo rótulo da tabela de valores.
        """
        patterns = [
            # "Valor dos serviços R$ 4.748,86"
            r"Valor\s+dos\s+servi[çc]os\s+R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            # "Valor Líquido R$ 4.748,86"
            r"Valor\s+L[íi]quido\s+R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            # "Valor Total R$ 4.748,86"
            r"Valor\s+Total\s+R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                valor_str = match.group(1)
                # Converte formato brasileiro para float
                return float(valor_str.replace('.', '').replace(',', '.'))

        return 0.0

    def _extract_vencimento(self, text: str) -> Optional[str]:
        """
        Extrai data de vencimento.

        Para NFS-e de serviços, se não houver vencimento explícito,
        usa a data de emissão como fallback.
        """
        # Tenta padrão comum de vencimento
        match = re.search(r'Vencimento[:\s]+(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
        if match:
            data_str = match.group(1)
            # Converte para formato ISO (YYYY-MM-DD)
            dia, mes, ano = data_str.split('/')
            return f"{ano}-{mes}-{dia}"

        # Fallback: usa data de emissão
        return self._extract_data_emissao(text)

    def _extract_data_emissao(self, text: str) -> Optional[str]:
        """Extrai data de emissão."""
        # Padrão Vila Velha: "Emitida em ... 03/11/2025"
        patterns = [
            r'Emitida\s+em[:\s]+[^\d]*(\d{2}/\d{2}/\d{4})',
            r'Data\s+de\s+Emiss[ãa]o[:\s]+(\d{2}/\d{2}/\d{4})',
            r'Emiss[ãa]o[:\s]+(\d{2}/\d{2}/\d{4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data_str = match.group(1)
                # Converte para formato ISO (YYYY-MM-DD)
                dia, mes, ano = data_str.split('/')
                return f"{ano}-{mes}-{dia}"

        return None
