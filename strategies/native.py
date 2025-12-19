import pdfplumber
from core.interfaces import TextExtractionStrategy

class NativePdfStrategy(TextExtractionStrategy):
    """
    Estratégia de leitura rápida para PDFs vetoriais (baseados em texto).

    Utiliza a biblioteca `pdfplumber` para acessar a camada de texto do PDF diretamente.
    É a estratégia preferencial por ser mais rápida e precisa que o OCR.
    """
    def extract(self, file_path: str) -> str:
        """
        Extrai texto de um PDF vetorial com múltiplas estratégias.
        
        Tenta primeiro com layout preservado (melhor para documentos tabulares),
        depois com extração simples como fallback.

        Args:
            file_path (str): Caminho absoluto ou relativo do arquivo PDF.

        Returns:
            str: Texto extraído ou string vazia se a extração falhar/for insuficiente.
        """
        try:
            with pdfplumber.open(file_path) as pdf:
                if not pdf.pages:
                    return ""
                
                # Tentativa 1: Extração com layout preservado
                # Útil para documentos onde rótulos e valores estão separados espacialmente
                text_layout = ""
                for page in pdf.pages:
                    page_text = page.extract_text(
                        layout=True,
                        x_tolerance=3,
                        y_tolerance=3
                    ) or ""
                    text_layout += page_text + "\n"
                
                # Se layout preservado deu bom resultado, usa ele
                if len(text_layout.strip()) > 100:
                    return text_layout
                
                # Fallback: Extração simples (original)
                text_simple = ""
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    text_simple += page_text + "\n"
                
                # Regra de Ouro: Se extraiu pouco texto, considere falha!
                if len(text_simple.strip()) < 50: 
                    return ""  # Força o fallback para OCR
                
                return text_simple
                
        except Exception as e:
            # Logar o erro se necessário
            return ""