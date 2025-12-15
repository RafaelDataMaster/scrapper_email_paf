from abc import ABC, abstractmethod

class TextExtractionStrategy(ABC):
    """Contrato para qualquer motor de leitura de arquivos."""
    
    @abstractmethod
    def extract(self, file_path: str) -> str:
        """
        Retorna o texto bruto do arquivo.
        Deve lançar ExtractionError se falhar.
        """
        pass