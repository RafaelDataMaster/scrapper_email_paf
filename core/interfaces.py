from abc import ABC, abstractmethod
from typing import List, Dict, Any

class TextExtractionStrategy(ABC):
    """
    Contrato (Interface) para qualquer motor de leitura de arquivos.
    
    Define como as estratégias de leitura (PDF Nativo, OCR, etc.) devem se comportar.
    """
    
    @abstractmethod
    def extract(self, file_path: str) -> str:
        """
        Extrai o texto bruto de um arquivo.

        Args:
            file_path (str): Caminho absoluto para o arquivo.

        Returns:
            str: O texto extraído do arquivo.

        Raises:
            ExtractionError: Se houver falha crítica na leitura do arquivo.
        """
        pass


class EmailIngestorStrategy(ABC):
    """
    Contrato (Interface) para conectores de e-mail (Gmail, Outlook, IMAP).
    
    Permite trocar a implementação de ingestão (ex: de IMAP para API Graph)
    sem quebrar o restante do sistema.
    """
    
    @abstractmethod
    def connect(self) -> None:
        """
        Estabelece conexão com o servidor de e-mail.

        Raises:
            IngestionError: Se a autenticação ou conexão falhar.
        """
        pass

    @abstractmethod
    def fetch_attachments(self, filter_query: str) -> List[Dict[str, Any]]:
        """
        Busca e-mails e retorna lista de anexos baixados.

        Args:
            filter_query (str): Termo para filtrar e-mails (ex: Assunto).

        Returns:
            List[Dict[str, Any]]: Lista de dicionários contendo:
                - filename (str): Nome do arquivo.
                - content (bytes): Conteúdo binário.
                - metadata (dict): Metadados do e-mail (remetente, data).
        """
        pass