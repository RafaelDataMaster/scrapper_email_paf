from abc import ABC, abstractmethod

class text_extraction_strategy(ABC):
    """Contrato para qualquer motor de leitura de arquivos."""
    
    @abstractmethod
    def extract(self, file_path: str) -> str:
        """
        Retorna o texto bruto do arquivo.
        Deve lançar ExtractionError se falhar.
        """
        pass