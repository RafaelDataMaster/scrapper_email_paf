"""
Estratégia de extração via OCR (Reconhecimento Óptico de Caracteres).

Este módulo implementa a última camada de fallback para PDFs que não
possuem camada de texto (documentos escaneados, imagens).

Dependências:
    - Tesseract OCR: Engine de reconhecimento de texto
    - Poppler: Biblioteca para conversão PDF→imagem
    - pdf2image: Wrapper Python para Poppler

Configuração (via config/settings.py):
    - TESSERACT_CMD: Caminho do executável Tesseract
    - POPPLER_PATH: Caminho da pasta bin do Poppler
    - OCR_LANG: Idioma do OCR (padrão: "por" para português)
    - OCR_CONFIG: Parâmetros adicionais do Tesseract

Limitações:
    - Processo lento (rasterização + OCR)
    - Qualidade depende da resolução do documento original
    - Pode falhar em documentos muito degradados

Inclui suporte a PDFs protegidos por senha, tentando desbloquear
automaticamente usando CNPJs das empresas cadastradas.

Example:
    >>> from strategies.ocr import TesseractOcrStrategy
    >>> strategy = TesseractOcrStrategy()
    >>> texto = strategy.extract("documento_escaneado.pdf")
"""
import logging
import os
import time

import pytesseract

from config import settings
from core.interfaces import TextExtractionStrategy

from .pdf_utils import abrir_pypdfium_com_senha

logger = logging.getLogger(__name__)


class TesseractOcrStrategy(TextExtractionStrategy):
    """
    Estratégia de leitura baseada em OCR (Reconhecimento Óptico de Caracteres).

    Utiliza `pypdfium2` para rasterizar o PDF em memória e `pytesseract` para extrair texto.
    Acionada quando o PDF não possui camada de texto (ex: digitalizações).

    Inclui estratégia de desbloqueio por força bruta usando CNPJs das empresas
    cadastradas como candidatos a senha.
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
        Converte PDF em imagem usando pypdfium2 e executa OCR.

        pypdfium2 rasteriza o PDF em memória (sem subprocessos),
        oferecendo performance significativamente melhor que pdf2image/Poppler.

        Implementa desbloqueio automático de PDFs protegidos usando CNPJs
        das empresas cadastradas como candidatos a senha.

        Args:
            file_path (str): Caminho do arquivo PDF.

        Returns:
            str: Texto extraído da imagem. Retorna string vazia se falhar.

        Raises:
            Exception: Se houver erro na conversão ou no OCR.
        """
        custom_config = settings.OCR_CONFIG
        filename = os.path.basename(file_path)

        logger.info(f"🔍 [OCR] Iniciando: {filename}")
        start_time = time.time()

        try:
            # Rasterização em memória com pypdfium2 (muito mais rápido que Poppler)
            # Usa função utilitária que tenta desbloquear PDFs protegidos
            pdf = abrir_pypdfium_com_senha(file_path)

            # Se não conseguiu abrir o PDF, retorna vazio
            if pdf is None:
                logger.warning(f"❌ [OCR] Não foi possível abrir PDF: {filename}")
                return ""

            try:
                texto_final = ""
                # Processa apenas a primeira página (otimização para notas fiscais)
                page = pdf[0]

                # Renderiza a página como bitmap (300 DPI é bom equilíbrio qualidade/velocidade)
                bitmap = page.render(scale=300 / 72)  # 300 DPI
                pil_image = bitmap.to_pil()

                # Executa OCR na imagem
                texto_final = pytesseract.image_to_string(
                    pil_image,
                    lang=settings.OCR_LANG,
                    config=custom_config
                )

            finally:
                # Libera recursos do PDF
                pdf.close()

            elapsed = time.time() - start_time
            logger.info(f"✅ [OCR] Concluído: {filename} ({len(texto_final)} chars em {elapsed:.1f}s)")

            # Validação: Se OCR retornou texto muito curto, considere falha
            if len(texto_final.strip()) < 50:
                logger.warning(f"OCR extraiu texto insuficiente (<50 chars) de {file_path}")
                return ""  # Falha recuperável, força próxima estratégia

            return texto_final

        except Exception as e:
            # Log do erro para rastreabilidade, mas mantém fluxo (LSP)
            logger.warning(f"Falha na estratégia OCR para {file_path}: {e}")
            return ""
