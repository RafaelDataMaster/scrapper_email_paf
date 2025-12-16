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


class EmailIngestorStrategy(ABC):
    """Contrato para conectores de e-mail (Gmail, Outlook, IMAP)."""
    
    @abstractmethod
    def connect(self):
        """Estabelece conexão com o servidor."""
        pass

    @abstractmethod
    def fetch_attachments(self, filter_query: str) -> list[dict]:
        """
        Busca e-mails e retorna lista de anexos baixados.
        Retorno esperado: [{'filename': 'nota.pdf', 'content': bytes, 'metadata': dict}]
        """
        pass