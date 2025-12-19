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
        
        Tenta primeiro com rótulo explícito, depois busca qualquer data válida.
        """
        # Padrões com rótulo explícito
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
        
        # Fallback: busca primeira data no formato DD/MM/YYYY (sem rótulo)
        # Comum em boletos onde o vencimento está próximo ao rótulo mas separado por espaços
        date_match = re.search(r'\b(\d{2}/\d{2}/\d{4})\b', text)
        if date_match:
            try:
                dt = datetime.strptime(date_match.group(1), '%d/%m/%Y')
                # Valida se é uma data futura razoável (até 2030)
                if 2024 <= dt.year <= 2030:
                    return dt.strftime('%Y-%m-%d')
            except ValueError:
                pass
        
        return None

    def _extract_numero_documento(self, text: str) -> Optional[str]:
        """
        Extrai o número do documento/fatura referenciado no boleto.
        
        Comum em boletos de serviços (pode conter o número da NF).
        Evita capturar números muito curtos (1 dígito) que são genéricos.
        Aceita formatos: "123", "2025.122", "2/1", "NF-12345", etc.
        """
        patterns = [
            # 1. PRIORIDADE ALTA - Layout tabular com data: "Nº Documento ... data ... X/Y"
            # Comum em boletos VSP/Itaú onde data vem antes do número
            r'(?i)N.?\s*Documento.*?\d{2}/\d{2}/\d{4}\s+(\d+/\d+)',
            
            # 2-6. Padrões específicos com diferentes variações de "número"
            r'(?i)N[uú]mero\s+do\s+Documento\s*[:\s]*([0-9]+(?:\.[0-9]+)?)',  # Com ú ou u
            r'(?i)Numero\s+do\s+Documento\s*[:\s]*([0-9]+(?:\.[0-9]+)?)',  # Sem acento
            r'(?i)Num\.?\s*Documento\s*[:\s]*([0-9]+(?:\.[0-9]+)?)',
            r'(?i)N[ºº°]\s*Documento\s*[:\s]*([0-9]+(?:[/\.][0-9]+)?)',  # Aceita / ou .
            r'(?i)N\.\s*documento\s*[:\s]*([0-9]+(?:\.[0-9]+)?)',
            
            # 7. Busca "Número do Documento" seguido do valor na próxima linha
            r'(?i)N.mero\s+do\s+Documento\s+.+?\n\s+.+?\s+([0-9]+\.[0-9]+)',  # Qualquer char em "Número"
            
            # 8. Padrão contextual: palavra "documento" seguida de número (NÃO data)
            # Regex negativa para evitar capturar datas DD/MM/YYYY
            r'(?i)documento\s+(?!\d{2}/\d{2}/\d{4})([0-9]+(?:\.[0-9]+)?)',
            
            # 9. Genérico: busca por padrão ano.número (ex: 2025.122)
            r'\b(20\d{2}\.\d+)\b'  # 2024.xxx, 2025.xxx, etc.
        ]
        
        for i, pattern in enumerate(patterns):
            # Padrão 0 (índice 0) precisa de re.DOTALL para atravessar linhas
            flags = re.DOTALL if i == 0 else 0
            match = re.search(pattern, text, flags)
            if match:
                numero = match.group(1).strip()
                # Valida: deve ter pelo menos 2 caracteres e não ser apenas "1"
                if len(numero) >= 2 or (len(numero) == 1 and numero != '1'):
                    return numero
        
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
        Formatos comuns: "12345", "12345-6", "109/00000507-1"
        """
        patterns = [
            # Formato bancário completo: XXX/XXXXXXX-X (ex: 109/00000507-1)
            # Padrão robusto: 2-3 dígitos / 7+ dígitos - 1 dígito
            # Evita capturar CNPJ que tem formato diferente
            r'(?i)Nosso\s+N.mero.*?(\d{2,3}/\d{7,}-\d+)',
            
            # Formato simples sem encoding específico
            r'(?i)Nosso\s+Numero.*?(\d{2,3}/\d{7,}-\d+)',
            
            # Fallback: qualquer sequência de dígitos com separadores
            r'(?i)Nosso\s+N[úu]mero\s*[:\s]*([\d\-/]+)',
            r'(?i)Nosso\s+Numero\s*[:\s]*([\d\-/]+)'
        ]
        
        for i, pattern in enumerate(patterns):
            # Primeiros 2 padrões precisam de DOTALL para atravessar linhas
            flags = re.DOTALL if i < 2 else 0
            match = re.search(pattern, text, flags)
            if match:
                numero = match.group(1).strip()
                # Validação: não deve ser parte de CNPJ (que tem pontos)
                if '.' not in numero or numero.count('/') == 1:
                    return numero
        
        # Fallback genérico: busca padrão XXX/XXXXXXXX-X sem label
        # Usado quando "Nosso Número" está como imagem ou ausente
        # Formato: 3 dígitos / 8 dígitos - 1 dígito (ex: 109/42150105-8)
        # Evita Agência/Conta que tem 4 dígitos ou espaços (ex: "2938 / 0053345-8")
        fallback_pattern = r'\b(\d{3}/\d{8}-\d)\b'
        match = re.search(fallback_pattern, text)
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
