from core.interfaces import text_extraction_strategy

class smart_extraction_strategy(text_extraction_strategy):
    def __init__(self):
        # Define a ordem de prioridade
        self.strategies = [
            native_pdf_strategy(),      # 1. Tenta ser rápido
            tesseract_ocr_trategy()    # 2. Se falhar, usa força bruta
        ]

    def extract(self, file_path: str) -> str:
        for strategy in self.strategies:
            texto = strategy.extract(file_path)
            if texto: # Se retornou algo válido
                return texto
        
        raise Exception("Falha: Nenhum método conseguiu ler o arquivo.")