import re
from datetime import datetime
from typing import Dict, Any
from core.extractors import BaseExtractor, register_extractor

@register_extractor
class GenericExtractor(BaseExtractor):
    """
    Extrator generalista baseado em Expressões Regulares (Regex).

    Tenta identificar padrões comuns de NFS-e (CNPJ, Datas, Valores) sem depender
    de um layout visual específico. Serve como "rede de segurança" para prefeituras desconhecidas.
    """
    
    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se este extrator pode processar o texto fornecido.
        
        Este é o extrator genérico para NFSe. Ele aceita qualquer documento
        QUE NÃO SEJA um boleto bancário OU DANFE (Nota Fiscal Eletrônica de Produto).

        Args:
            text (str): Texto extraído do PDF.

        Returns:
            bool: True se NÃO for um boleto ou DANFE (fallback padrão para NFSe).
        """
        text_upper = text.upper()
        
        # Indicadores fortes de que é um BOLETO (não deve ser processado aqui)
        boleto_keywords = [
            'LINHA DIGITÁVEL',
            'LINHA DIGITAVEL',
            'BENEFICIÁRIO',
            'BENEFICIARIO',
            'CÓDIGO DE BARRAS',
            'CODIGO DE BARRAS',
            'CEDENTE'
        ]
        
        # Verifica linha digitável (padrão de boleto)
        linha_digitavel = re.search(r'\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}', text)
        
        boleto_score = sum(1 for kw in boleto_keywords if kw in text_upper)
        
        # Se parece com boleto, NÃO processa aqui
        if boleto_score >= 2 or linha_digitavel:
            return False
        
        # Caso contrário, aceita como NFSe (fallback)
        return True 

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai campos padronizados (CNPJ, Valor, Data, Número) usando Regex.

        Args:
            text (str): Texto bruto do documento.

        Returns:
            Dict[str, Any]: Dicionário com os campos extraídos.
        """
        data = {}
        data['tipo_documento'] = 'NFSE'  # Identifica como NFSe
        data['cnpj_prestador'] = self._extract_cnpj(text)
        data['numero_nota'] = self._extract_numero_nota(text)
        data['valor_total'] = self._extract_valor(text)
        data['data_emissao'] = self._extract_data_emissao(text)
        return data

    def _extract_cnpj(self, text: str):
        match = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', text)
        return match.group(0) if match else None

    def _extract_valor(self, text: str):
        """
        Extrai valor com regex flexível (R$ opcional).
        
        Tenta múltiplos padrões em ordem de especificidade:
        - Padrões com R$ explícito (mais específicos)
        - Padrões sem R$ obrigatório (mais flexíveis)
        - Fallback genérico
        
        Returns:
            float: Valor encontrado ou 0.0 se não houver valor válido.
        """
        patterns = [
            # Padrões com R$ explícito (mais específicos)
            r'(?i)Valor\s+Total\s*[:\s]*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Valor\s+da\s+Nota\s*[:\s]*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Valor\s*[:\s]*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            
            # Padrões sem R$ obrigatório (mais flexíveis)
            # Aceita "Valor Total: 1.234,56" sem símbolo monetário
            r'(?i)Valor\s+Total\s*[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})\b',
            r'(?i)Valor\s+da\s+Nota\s*[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})\b',
            r'(?i)Total\s+Nota\s*[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})\b',
            r'(?i)Valor\s+L[ií]quido\s*[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})\b',
            
            # Fallback genérico (último recurso)
            r'\bR\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                valor_str = match.group(1)
                try:
                    valor = float(valor_str.replace('.', '').replace(',', '.'))
                    if valor > 0:
                        return valor
                except ValueError:
                    continue
        
        return 0.0

    def _extract_data_emissao(self, text: str):
        match = re.search(r'\d{2}/\d{2}/\d{4}', text)
        if match:
            try:
                dt = datetime.strptime(match.group(0), '%d/%m/%Y')
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass
        return None

    def _extract_numero_nota(self, text: str):
        if not text:
            return None

        # Limpeza: remove datas e identificadores auxiliares (RPS, Lote, Série)
        texto_limpo = text
        texto_limpo = re.sub(r'\d{2}/\d{2}/\d{4}', ' ', texto_limpo)
        padroes_lixo = r'(?i)\b(RPS|Lote|Protocolo|Recibo|S[eé]rie)\b\D{0,10}?\d+'
        texto_limpo = re.sub(padroes_lixo, ' ', texto_limpo)

        # Padrões de extração ordenados por especificidade
        padroes = [
            r'(?i)Número\s+da\s+Nota.*?(?<!\d)(\d{1,15})(?!\d)',
            r'(?i)(?:(?:Número|Numero|N[º°o])\s*da\s*)?NFS-e\s*(?:N[º°o]|Num)?\.?\s*[:.-]?\s*\b(\d{1,15})\b',
            r'(?i)Número\s+da\s+Nota[\s\S]*?\b(\d{1,15})\b',
            r'(?i)Nota\s*Fiscal\s*(?:N[º°o]|Num)?\.?\s*[:.-]?\s*(\d{1,15})',
            r'(?i)(?<!RPS\s)(?<!Lote\s)(?<!S[eé]rie\s)(?:Número|N[º°o])\s*[:.-]?\s*(\d{1,15})',
        ]
        
        for regex in padroes:
            match = re.search(regex, texto_limpo, re.IGNORECASE)
            if match:
                resultado = match.group(1)
                # Remove pontos e espaços do número extraído
                resultado = resultado.replace('.', '').replace(' ', '')
                return resultado
        
        return None
