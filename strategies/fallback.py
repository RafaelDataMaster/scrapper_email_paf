import re
from core.interfaces import TextExtractionStrategy
from .native import NativePdfStrategy
from .table import TablePdfStrategy
from .ocr import TesseractOcrStrategy
from config import settings

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
            ExtractionError: Se todas as estratégias falharem.
        """
        from core.exceptions import ExtractionError

        def looks_incomplete(text: str) -> bool:
            """Heurística: detecta PDF híbrido (texto parcial + dados em imagem).

            A ideia é evitar rodar OCR sempre (caro), e só complementar quando
            o texto nativo parece insuficiente para extração de campos básicos.
            """
            if not text:
                return True

            t = text.strip()
            if len(t) < 200:
                return True

            # Alguns PDFs retornam datas/CNPJ/valores com espaços entre separadores
            # (ex: "01 / 09 / 2025" ou "12 . 345 . 678 / 0001 - 90").
            # Para decisão de OCR, usamos regex tolerante (não altera o texto retornado).
            date_re = re.compile(r"\b\d{2}\s*/\s*\d{2}\s*/\s*\d{4}\b")
            money_re = re.compile(r"\b\d{1,3}(?:\s*\.\s*\d{3})*\s*,\s*\d{2}\b")
            cnpj_re = re.compile(r"\b\d{2}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*/\s*\d{4}\s*-\s*\d{2}\b")

            # Sinais comuns que esperamos ver em documentos financeiros.
            dates = date_re.findall(t)
            money = money_re.findall(t)
            cnpj = cnpj_re.findall(t)
            has_barcode = re.search(r"\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}", t) is not None

            # Se tem linha digitável mas não tem data/valor suficientes, é um forte sinal de híbrido.
            if has_barcode and (len(dates) < 1 or len(money) < 1):
                return True

            # Se tem CNPJ mas quase não tem datas/valores, também sinaliza incompleto.
            if cnpj and (len(dates) < 1 or len(money) < 1):
                return True

            # Texto muito “curto” para 1 página de boleto/nf costuma ser incompleto.
            if len(t) < 600 and (len(dates) < 2 or len(money) < 1):
                return True

            return False
        
        # 1) Tenta texto nativo primeiro.
        try:
            texto_native = self.strategies[0].extract(file_path)
            if texto_native and len(texto_native.strip()) >= 50:
                # Complemento híbrido com OCR (quando necessário)
                if getattr(settings, 'HYBRID_OCR_COMPLEMENT', True) and looks_incomplete(texto_native):
                    try:
                        texto_ocr = self.strategies[2].extract(file_path)
                        if texto_ocr and len(texto_ocr.strip()) >= 50:
                            return texto_native + "\n\n" + texto_ocr
                    except Exception:
                        pass
                return texto_native
        except Exception:
            pass

        # 2) Tenta extração por tabela.
        try:
            texto_table = self.strategies[1].extract(file_path)
            if texto_table and len(texto_table.strip()) >= 50:
                if getattr(settings, 'HYBRID_OCR_COMPLEMENT', True) and looks_incomplete(texto_table):
                    try:
                        texto_ocr = self.strategies[2].extract(file_path)
                        if texto_ocr and len(texto_ocr.strip()) >= 50:
                            return texto_table + "\n\n" + texto_ocr
                    except Exception:
                        pass
                return texto_table
        except Exception:
            pass

        # 3) OCR puro (último recurso)
        try:
            texto_ocr = self.strategies[2].extract(file_path)
            if texto_ocr and len(texto_ocr.strip()) >= 50:
                return texto_ocr
        except Exception:
            pass
        
        # Todas falharam: agora sim é erro crítico
        raise ExtractionError(f"Nenhuma estratégia conseguiu extrair texto de {file_path}")