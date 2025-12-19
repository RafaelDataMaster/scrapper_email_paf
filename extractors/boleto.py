import re
from datetime import datetime
from typing import Dict, Any, Optional
from core.extractors import BaseExtractor, register_extractor

@register_extractor
class BoletoExtractor(BaseExtractor):
    """
    Extrator especializado em Boletos Bancários.
    
    Identifica e extrai campos específicos de boletos:
    - Linha digitável (código de barras)
    - CNPJ do beneficiário
    - Valor do documento
    - Data de vencimento
    - Número do documento
    - Possível referência à NFSe
    """
    
    @classmethod
    def can_handle(cls, text: str) -> bool:
        """
        Verifica se o documento é um boleto.
        
        Critérios:
        - Presença de "Linha Digitável" ou código de barras padrão
        - Palavras-chave: "Beneficiário", "Vencimento", "Valor do Documento"
        - Ausência de "NFS-e" ou "Nota Fiscal de Serviço"
        """
        text_upper = text.upper()
        
        # Indicadores positivos de boleto
        boleto_keywords = [
            'LINHA DIGITÁVEL',
            'LINHA DIGITAVEL',
            'BENEFICIÁRIO',
            'BENEFICIARIO',
            'VENCIMENTO',
            'VALOR DO DOCUMENTO',
            'NOSSO NÚMERO',
            'NOSSO NUMERO',
            'CÓDIGO DE BARRAS',
            'CODIGO DE BARRAS',
            'AGÊNCIA/CÓDIGO',
            'AGENCIA/CODIGO',
            'CEDENTE'
        ]
        
        # Indicadores negativos (se é NFSe, não é boleto puro)
        nfse_keywords = ['NFS-E', 'NOTA FISCAL DE SERVIÇO ELETRÔNICA', 'NOTA FISCAL DE SERVICO ELETRONICA', 'PREFEITURA']
        
        boleto_score = sum(1 for kw in boleto_keywords if kw in text_upper)
        nfse_score = sum(1 for kw in nfse_keywords if kw in text_upper)
        
        # Também verifica padrão de linha digitável (5 blocos numéricos)
        linha_digitavel = re.search(r'\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}', text)
        
        # É boleto se:
        # - Tem alta pontuação de palavras-chave de boleto OU linha digitável
        # - E não tem muitas palavras de NFSe
        return (boleto_score >= 3 or linha_digitavel) and nfse_score < 2

    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extrai dados estruturados do boleto.
        """
        data = {}
        data['tipo_documento'] = 'BOLETO'
        data['cnpj_beneficiario'] = self._extract_cnpj_beneficiario(text)
        data['valor_documento'] = self._extract_valor(text)
        data['vencimento'] = self._extract_vencimento(text)
        data['numero_documento'] = self._extract_numero_documento(text)
        data['linha_digitavel'] = self._extract_linha_digitavel(text)
        data['nosso_numero'] = self._extract_nosso_numero(text)
        data['referencia_nfse'] = self._extract_referencia_nfse(text)
        
        return data

    def _extract_cnpj_beneficiario(self, text: str) -> Optional[str]:
        """
        Extrai CNPJ do beneficiário (quem está recebendo o pagamento).
        Busca próximo a palavras como "Beneficiário" ou "Cedente".
        """
        # Padrão: Procura CNPJ após "Beneficiário" ou "Cedente"
        patterns = [
            r'(?i)Benefici[aá]rio.*?(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
            r'(?i)Cedente.*?(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
            r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}'  # Fallback: qualquer CNPJ
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1) if match.lastindex else match.group(0)
        return None

    def _extract_valor(self, text: str) -> float:
        """
        Extrai o valor do documento do boleto.
        
        Implementa 3 níveis de fallback para extração robusta:
        1. Padrões específicos (com/sem R$)
        2. Heurística do maior valor monetário encontrado
        3. Extração do valor da linha digitável (10 últimos dígitos em centavos)
        
        Returns:
            float: Valor do documento em reais ou 0.0 se não encontrado.
        """
        # Padrão: Procura "Valor do Documento" ou valores monetários
        # Aceita formatos com ou sem R$
        patterns = [
            # Com R$ explícito
            r'(?i)Valor\s+do\s+Documento\s*[:\s]*R\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Valor\s+Nominal\s*[:\s]*R\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Valor\s+Cobrado\s*[:\s]*R\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            
            # Sem R$ explícito (valor logo após o rótulo)
            # Útil para boletos com layout tabular
            r'(?i)Valor\s+do\s+Documento[\s\n]+(\d{1,3}(?:\.\d{3})*,\d{2})\b',
            r'(?i)Valor\s+Nominal[\s\n]+(\d{1,3}(?:\.\d{3})*,\d{2})\b',
            
            # Genérico com R$
            r'(?i)Valor\s*[:\s]*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                valor_str = match.group(1)
                valor = float(valor_str.replace('.', '').replace(',', '.'))
                if valor > 0:
                    return valor
        
        # Fallback Nível 2: Heurística do maior valor monetário encontrado
        # Útil quando o texto está "amassado" e os rótulos estão longe dos valores
        todos_valores = re.findall(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', text)
        
        if todos_valores:
            valores_float = [
                float(v.replace('.', '').replace(',', '.'))
                for v in todos_valores
            ]
            if valores_float:
                maior_valor = max(valores_float)
                if maior_valor > 0:
                    return maior_valor
        
        # Fallback Nível 3: Extrai valor da linha digitável
        # Formato padrão: últimos 14 dígitos contêm fator de vencimento (4) + valor (10)
        # Exemplo: 75691.31407 01130.051202 02685.970010 3 11690000625000
        #          11690000625000 → 1169 (fator) + 0000625000 (valor em centavos = R$ 6.250,00)
        linha_digitavel_match = re.search(
            r'\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}\s+\d\s+(\d{4})(\d{10})',
            text
        )
        if linha_digitavel_match:
            # Segundo grupo: 10 dígitos do valor em centavos
            valor_centavos_str = linha_digitavel_match.group(2)
            try:
                valor_centavos = int(valor_centavos_str)
                valor = valor_centavos / 100.0
                if valor > 0:
                    return valor
            except ValueError:
                pass
        
        return 0.0

    def _extract_vencimento(self, text: str) -> Optional[str]:
        """
        Extrai a data de vencimento do boleto.
        """
        patterns = [
            r'(?i)Vencimento\s*[:\s]*(\d{2}/\d{2}/\d{4})',
            r'(?i)Data\s+Vencimento\s*[:\s]*(\d{2}/\d{2}/\d{4})',
            r'(?i)Data\s+de\s+Vencimento\s*[:\s]*(\d{2}/\d{2}/\d{4})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    dt = datetime.strptime(match.group(1), '%d/%m/%Y')
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    continue
        
        return None

    def _extract_numero_documento(self, text: str) -> Optional[str]:
        """
        Extrai o número do documento/fatura referenciado no boleto.
        Comum em boletos de serviços (pode conter o número da NF).
        """
        patterns = [
            r'(?i)N[úu]mero\s+do\s+Documento\s*[:\s]*(\d+)',
            r'(?i)Documento\s*[:\s]*(\d+)',
            r'(?i)N[º°]\s*Documento\s*[:\s]*(\d+)',
            r'(?i)Num\.\s*Documento\s*[:\s]*(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return None

    def _extract_linha_digitavel(self, text: str) -> Optional[str]:
        """
        Extrai a linha digitável do boleto (código de barras formatado).
        Formato padrão: 5 blocos numéricos separados por espaços/pontos.
        """
        # Formato completo: XXXXX.XXXXX XXXXX.XXXXXX XXXXX.XXXXXX X XXXXXXXXXXXXXX
        patterns = [
            r'(\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}\s+\d\s+\d{14})',
            r'(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6})'  # Formato mais curto
        ]
        
        text_cleaned = text.replace('\n', ' ')
        
        for pattern in patterns:
            match = re.search(pattern, text_cleaned)
            if match:
                return match.group(1).strip()
        
        return None

    def _extract_nosso_numero(self, text: str) -> Optional[str]:
        """
        Extrai o "Nosso Número" (identificação interna do banco).
        """
        patterns = [
            r'(?i)Nosso\s+N[úu]mero\s*[:\s]*(\d+[-/]?\d*)',
            r'(?i)Nosso\s+Numero\s*[:\s]*(\d+[-/]?\d*)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return None

    def _extract_referencia_nfse(self, text: str) -> Optional[str]:
        """
        Tenta encontrar uma referência explícita a um número de NFSe no boleto.
        Alguns boletos incluem "Ref. NF 12345" ou similar.
        """
        patterns = [
            r'(?i)Ref\.?\s*NF[:\s-]*(\d+)',
            r'(?i)Refer[eê]ncia\s*NF[:\s-]*(\d+)',
            r'(?i)Nota\s+Fiscal\s*n?[º°]?\s*[:\s]*(\d+)',
            r'(?i)NF\s*[:\s-]*(\d+)',
            r'(?i)N\.?\s*F\.?\s*[:\s-]*(\d+)',
            r'(?i)NFSe\s*[:\s-]*(\d+)',
            r'(?i)NFS-e\s*[:\s-]*(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return None
