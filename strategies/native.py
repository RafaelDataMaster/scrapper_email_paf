import pdfplumber
from core.interfaces import text_extraction_strategy

class native_pdf_strategy(text_extraction_strategy):
    def extract(self, file_path: str) -> str:
        try:
            with pdfplumber.open(file_path) as pdf:
                if not pdf.pages:
                    return ""
                # Extrai texto da primeira página (ou loop por todas)
                text = pdf.pages[0].extract_text() or ""
                
                # Regra de Ouro: Se extraiu pouco texto, considere falha!
                if len(text.strip()) < 50: 
                    return "" # Força o fallback
                
                return text
        except Exception as e:
            # Logar o erro se necessário
            return ""