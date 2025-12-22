import re
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Union, Optional
from core.models import InvoiceData, BoletoData
from core.interfaces import TextExtractionStrategy
from strategies.fallback import SmartExtractionStrategy
from core.extractors import EXTRACTOR_REGISTRY
from config.settings import TRAT_PAF_RESPONSAVEL
import extractors.generic
import extractors.boleto

class BaseInvoiceProcessor(ABC):
    """
    Classe orquestradora principal do processo de extração.

    Responsável por coordenar o fluxo completo:
    1.  **Leitura**: Converte PDF em texto (via `SmartExtractionStrategy`).
    2.  **Classificação**: Identifica se é NFSe ou Boleto.
    3.  **Seleção**: Escolhe o extrator adequado para o texto.
    4.  **Extração**: Executa a mineração de dados.
    5.  **Normalização**: Retorna objeto `InvoiceData` ou `BoletoData`.
    
    Args:
        reader: Estratégia de extração de texto. Se None, usa SmartExtractionStrategy.
                Permite injeção de dependência para testes (DIP).
    """
    def __init__(self, reader: Optional[TextExtractionStrategy] = None):
        self.reader = reader if reader is not None else SmartExtractionStrategy()

    def _get_extractor(self, text: str):
        """Factory Method: Escolhe o extrator certo para o texto."""
        for extractor_cls in EXTRACTOR_REGISTRY:
            if extractor_cls.can_handle(text):
                return extractor_cls()
        raise ValueError("Nenhum extrator compatível encontrado para este documento.")

    def process(self, file_path: str) -> Union[InvoiceData, BoletoData]:
        """
        Executa o pipeline de processamento para um único arquivo.

        Args:
            file_path (str): Caminho absoluto ou relativo do arquivo PDF.

        Returns:
            Union[InvoiceData, BoletoData]: Objeto contendo os dados extraídos.
        """
        # 1. Leitura
        raw_text = self.reader.extract(file_path)
        
        if not raw_text or "Falha" in raw_text:
            # Retorna objeto vazio de NFSe por padrão
            return InvoiceData(
                arquivo_origem=os.path.basename(file_path),
                texto_bruto="Falha na leitura"
            )

        # 2. Seleção do Extrator
        try:
            extractor = self._get_extractor(raw_text)
            extracted_data = extractor.extract(raw_text)
            
            # Dados comuns PAF (aplicados a todos os documentos)
            now_iso = datetime.now().strftime('%Y-%m-%d')
            common_data = {
                'data_processamento': now_iso,
                'dt_classificacao': now_iso,
                'trat_paf': TRAT_PAF_RESPONSAVEL,
                'lanc_sistema': 'PENDENTE',
            }
            
            # 3. Identifica o tipo e cria o modelo apropriado
            if extracted_data.get('tipo_documento') == 'BOLETO':
                return BoletoData(
                    arquivo_origem=os.path.basename(file_path),
                    texto_bruto=' '.join(raw_text.split())[:500],
                    # Campos PAF comuns
                    **common_data,
                    # Campos básicos do boleto
                    cnpj_beneficiario=extracted_data.get('cnpj_beneficiario'),
                    valor_documento=extracted_data.get('valor_documento', 0.0),
                    vencimento=extracted_data.get('vencimento'),
                    numero_documento=extracted_data.get('numero_documento'),
                    linha_digitavel=extracted_data.get('linha_digitavel'),
                    nosso_numero=extracted_data.get('nosso_numero'),
                    referencia_nfse=extracted_data.get('referencia_nfse'),
                    # Campos PAF (novos)
                    fornecedor_nome=extracted_data.get('fornecedor_nome'),
                    banco_nome=extracted_data.get('banco_nome'),
                    agencia=extracted_data.get('agencia'),
                    conta_corrente=extracted_data.get('conta_corrente'),
                    numero_pedido=extracted_data.get('numero_pedido'),
                )
            else:
                # NFSe
                return InvoiceData(
                    arquivo_origem=os.path.basename(file_path),
                    texto_bruto=' '.join(raw_text.split())[:500],
                    # Campos PAF comuns
                    **common_data,
                    # Campos básicos da NFSe
                    cnpj_prestador=extracted_data.get('cnpj_prestador'),
                    numero_nota=extracted_data.get('numero_nota'),
                    valor_total=extracted_data.get('valor_total', 0.0),
                    data_emissao=extracted_data.get('data_emissao'),
                    # Campos PAF (novos)
                    fornecedor_nome=extracted_data.get('fornecedor_nome'),
                    vencimento=extracted_data.get('vencimento'),
                    numero_pedido=extracted_data.get('numero_pedido'),
                    forma_pagamento=extracted_data.get('forma_pagamento'),
                    # Impostos individuais
                    valor_ir=extracted_data.get('valor_ir'),
                    valor_inss=extracted_data.get('valor_inss'),
                    valor_csll=extracted_data.get('valor_csll'),
                    valor_iss=extracted_data.get('valor_iss'),
                    valor_icms=extracted_data.get('valor_icms'),
                    base_calculo_icms=extracted_data.get('base_calculo_icms'),
                )
            
        except ValueError as e:
            print(f"Erro ao processar {file_path}: {e}")
            return InvoiceData(
                arquivo_origem=os.path.basename(file_path),
                texto_bruto=' '.join(raw_text.split())[:500]  # Remove whitespace, then take 500 chars
            )



