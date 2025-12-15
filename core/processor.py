# core/processor.py
import re
import os
from abc import ABC, abstractmethod
from datetime import datetime
from core.models import InvoiceData
from strategies.fallback import smart_extraction_strategy

class BaseInvoiceProcessor(ABC):
    def __init__(self):
        # Instancia a estratégia de leitura que você já criou
        self.reader = smart_extraction_strategy()

    def process(self, file_path: str) -> InvoiceData:
        """Método Template: Define o esqueleto do processo"""
        
        # 1. Leitura (Já implementado nas suas strategies)
        raw_text = self.reader.extract(file_path)
        
        # 2. Inicializa o modelo
        data = InvoiceData(
            arquivo_origem=os.path.basename(file_path),
            texto_bruto=raw_text[:100].replace('\n', ' ') # Guardando snippet como no seu teste
        )

        if not raw_text or "Falha" in raw_text:
            return data

        # 3. Extração dos Campos (Migrando lógica do extracao_1_teste.py)
        data.cnpj_prestador = self._extract_cnpj(raw_text)
        data.numero_nota = self._extract_numero_nota(raw_text)
        data.valor_total = self._extract_valor(raw_text)
        data.data_emissao = self._extract_data_emissao(raw_text)

        return data

    # --- Métodos Auxiliares Migrados de extracao_1_teste.py ---
    
    def _extract_cnpj(self, text: str):
        match = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', text)
        return match.group(0) if match else None

    def _extract_valor(self, text: str):
        # Migrando sua função limpar_valor_monetario
        match = re.search(r'R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})', text)
        if match:
            valor_str = match.group(1)
            return float(valor_str.replace('.', '').replace(',', '.'))
        return 0.0

    def _extract_data_emissao(self, text: str):
        # Migrando converter_data_iso
        match = re.search(r'\d{2}/\d{2}/\d{4}', text)
        if match:
            try:
                dt = datetime.strptime(match.group(0), '%d/%m/%Y')
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass
        return None

    def _extract_numero_nota(self, text: str):
        # AQUI entra a sua lógica complexa de "extrair_numero_nota_flexivel"
        # Você deve copiar aquela função inteira do extracao_1_teste.py para cá
        # ajustando para ser um método da classe (self).
        
        texto_limpo = text
        texto_limpo = re.sub(r'\d{2}/\d{2}/\d{4}', ' ', texto_limpo)
        # ... (restante da lógica do seu regex) ...
        # Por brevidade, use a lógica do seu arquivo original aqui
        
        # Exemplo simplificado para teste:
        match = re.search(r'(?i)Número\s+da\s+Nota.*?(?<!\d)(\d{1,15})(?!\d)', texto_limpo)
        return match.group(1) if match else None