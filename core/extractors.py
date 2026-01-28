import re
from abc import ABC, abstractmethod
from typing import Any, Dict

# 1. O Registro (Lista de plugins disponíveis)
EXTRACTOR_REGISTRY = []


def register_extractor(cls):
    """Decorador para registrar novas cidades automaticamente."""
    EXTRACTOR_REGISTRY.append(cls)
    return cls


def find_linha_digitavel(text: str) -> bool:
    """
    Procura por uma linha digitável no texto.

    IMPORTANTE: Exclui chaves de acesso de NF-e/NFS-e que têm formato similar
    mas contexto diferente (44 dígitos precedidos de palavras como 'Chave de Acesso').
    """
    text_upper = (text or "").upper()
    text_cleaned = text.replace("\n", " ")

    # Se o documento contém indicadores fortes de ser DANFSe/NF-e/NFS-e, não considera
    # sequências numéricas longas como linha digitável
    danfse_indicators = [
        "DANFSE",
        "DOCUMENTO AUXILIAR DA NFS-E",
        "DOCUMENTO AUXILIAR DA NOTA FISCAL",
        "DOCUMENTO AUXILIAR DA NOTA FISCAL DE SERVIÇO",
        "CHAVE DE ACESSO DA NFS-E",
        "CHAVE DE ACESSO DA NFE",
        "CHAVE DE ACESSO",
        "CÓDIGO DE VERIFICAÇÃO",
        "CODIGO DE VERIFICACAO",
        "NFS-E",
        "NOTA FISCAL DE SERVIÇO ELETRÔNICA",
        "NOTA FISCAL DE SERVICO ELETRONICA",
    ]

    is_danfse_context = any(ind in text_upper for ind in danfse_indicators)

    # Se for contexto DANFSe, não é boleto - retorna False imediatamente
    if is_danfse_context:
        return False

    # Padrões específicos de linha digitável de boleto bancário
    # Formato típico: XXXXX.XXXXX XXXXX.XXXXXX XXXXX.XXXXXX X XXXXXXXXXXXXXX
    boleto_patterns = [
        # Padrão com pontos e espaços (mais específico)
        r"(\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}\s+\d\s+\d{14})",
        # Padrão com pontos
        r"(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14})",
        # Padrão flexível com grupos
        r"(\d{5}[\.\s]?\d{5}\s+\d{5}[\.\s]?\d{6}\s+\d{5}[\.\s]?\d{6}\s+\d\s+\d{14})",
    ]

    for pattern in boleto_patterns:
        match = re.search(pattern, text_cleaned)
        if match:
            return True

    # Padrão de sequência numérica longa (47-48 dígitos) - APENAS se não for contexto DANFSe
    # Isso evita confundir chave de acesso de 44 dígitos com linha digitável
    if not is_danfse_context:
        # Verifica se há uma sequência de 47-48 dígitos que NÃO esteja próxima de "CHAVE"
        long_sequence = re.search(r"(\d{47,48})", text_cleaned)
        if long_sequence:
            # Verifica o contexto ao redor - não deve ter "CHAVE" nas proximidades
            match_start = long_sequence.start()
            context_before = text_cleaned[
                max(0, match_start - 50) : match_start
            ].upper()
            if "CHAVE" not in context_before and "ACESSO" not in context_before:
                return True

    return False


# 2. A Interface Base
class BaseExtractor(ABC):
    """Contrato que toda cidade deve implementar."""

    @classmethod
    @abstractmethod
    def can_handle(cls, text: str) -> bool:
        """Retorna True se este extrator reconhece o texto da nota."""
        pass

    @abstractmethod
    def extract(self, text: str) -> Dict[str, Any]:
        """Recebe o texto bruto e retorna o dicionário de dados."""
        pass
