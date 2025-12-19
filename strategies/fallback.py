from core.interfaces import TextExtractionStrategy
from .native import NativePdfStrategy
from .table import TablePdfStrategy
from .ocr import TesseractOcrStrategy  

class SmartExtractionStrategy(TextExtractionStrategy):
    """
    Estratégia composta (Composite) que gerencia tentativas de leitura.

    Implementa um padrão de **Fallback em 3 níveis**:
    1. Estratégia nativa com layout preservado (rápida, ~90% dos casos)
    2. Extração de tabelas estruturadas (casos com layout tabular complexo)
    3. OCR via Tesseract (última opção, documentos escaneados/corrompidos)
    
    Garante resiliência máxima na extração de texto de PDFs.
    """
    def __init__(self):
        # Define a ordem de prioridade
        self.strategies = [
            NativePdfStrategy(),      # 1. Tenta ser rápido com layout
            TablePdfStrategy(),       # 2. Tenta extrair tabelas estruturadas
            TesseractOcrStrategy()    # 3. Se falhar, usa força bruta (OCR)
        ]

    def extract(self, file_path: str) -> str:
        """
        Tenta extrair texto usando as estratégias em ordem de prioridade.

        Args:
            file_path (str): Caminho do arquivo PDF.

        Returns:
            str: Texto extraído pela primeira estratégia bem-sucedida.

        Raises:
            Exception: Se todas as estratégias falharem.
        """
        for strategy in self.strategies:
            texto = strategy.extract(file_path)
            if texto: # Se retornou algo válido
                return texto
        
        raise Exception("Falha: Nenhum método conseguiu ler o arquivo.")