from core.interfaces import TextExtractionStrategy

class SmartExtractionStrategy(TextExtractionStrategy):
    def __init__(self):
        # Define a ordem de prioridade
        self.strategies = [
            NativePdfStrategy(),      # 1. Tenta ser rápido
            TesseractOcrStrategy()    # 2. Se falhar, usa força bruta
        ]

    def extract(self, file_path: str) -> str:
        for strategy in self.strategies:
            texto = strategy.extract(file_path)
            if texto: # Se retornou algo válido
                return texto
        
        raise Exception("Falha: Nenhum método conseguiu ler o arquivo.")