import pytesseract
from pdf2image import convert_from_path
from core.interfaces import TextExtractionStrategy
from config import settings  # Importando suas configurações

class TesseractOcrStrategy(TextExtractionStrategy):
    """
    Estratégia de leitura baseada em OCR (Reconhecimento Óptico de Caracteres).

    Utiliza `pdf2image` para rasterizar o PDF e `pytesseract` para extrair texto da imagem.
    Acionada quando o PDF não possui camada de texto (ex: digitalizações).
    """
    def __init__(self):
        """
        Inicializa a estratégia configurando o caminho do executável Tesseract.
        """
        # 1. Configurar o caminho do Tesseract (VITAL NO WINDOWS)
        # Se não fizer isso, vai dar erro de "tesseract not found" depois
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

    def extract(self, file_path: str) -> str:
        """
        Converte PDF em imagem e executa OCR.

        Args:
            file_path (str): Caminho do arquivo PDF.

        Returns:
            str: Texto extraído da imagem.

        Raises:
            Exception: Se houver erro na conversão ou no OCR.
        """
        custom_config = settings.OCR_CONFIG
        
        try:
            # 2. Passar o poppler_path explicitamente
            # Sem isso, ele grita "Unable to get page count"
            imagens = convert_from_path(
                file_path, 
                first_page=1, 
                last_page=1,
                poppler_path=settings.POPPLER_PATH ### AQUI ESTAVA FALTANDO!
            )
            
            texto_final = ""
            for img in imagens:
                texto_final += pytesseract.image_to_string(
                    img, 
                    lang=settings.OCR_LANG, 
                    config=custom_config
                )
            
            # Validação: Se OCR retornou texto muito curto, considere falha
            if len(texto_final.strip()) < 50:
                return ""  # Falha recuperável, força próxima estratégia
            
            return texto_final
            
        except Exception as e:
            # Retorna string vazia para permitir fallback
            # Em vez de lançar exceção (violação LSP)
            return ""