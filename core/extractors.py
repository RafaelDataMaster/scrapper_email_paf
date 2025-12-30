import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

# 1. O Registro (Lista de plugins disponíveis)
EXTRACTOR_REGISTRY = []

def register_extractor(cls):
    """Decorador para registrar novas cidades automaticamente."""
    EXTRACTOR_REGISTRY.append(cls)
    return cls

def find_linha_digitavel(text: str) -> bool:
    """Procura por uma linha digitável no texto."""
    patterns = [
        r'(\d{5}[\.\s]\d{5}\s*\d{5}[\.\s]\d{6}\s*\d{5}[\.\s]\d{6}\s*\d\s*\d{14})',
        r'(\d{5}\.\d{5}\s*\d{5}\.\d{6}\s*\d{5}\.\d{6})',
        r'(\d{5}[\.\s]?\d{5}\s*\d{5}[\.\s]?\d{6}\s*\d{5}[\.\s]?\d{6}\s*\d\s*\d{14})',
        r'(\d{47,48})'
    ]

    text_cleaned = text.replace('\n', ' ')

    for pattern in patterns:
        match = re.search(pattern, text_cleaned)
        if match:
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
