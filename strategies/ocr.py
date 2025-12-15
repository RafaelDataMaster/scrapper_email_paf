import pytesseract
from pdf2image import convert_from_path
from core.interfaces import TextExtractionStrategy
from config import settings
# Importe suas configs de caminhos aqui

class TesseractOcrStrategy(TextExtractionStrategy):
    def extract(self, file_path: str) -> str:
        # Configurações isoladas aqui dentro
        custom_config = r'--psm 6' 
        
        try:
            # Converter PDF para imagem
            imagens = convert_from_path(file_path, first_page=1, last_page=1)
            texto_final = ""
            
            for img in imagens:
                # Opcional: Pré-processamento com PIL/OpenCV aqui
                texto_final += pytesseract.image_to_string(img, lang='por', config=custom_config)
            
            return texto_final
        except Exception as e:
            raise Exception(f"Erro fatal no OCR: {e}")