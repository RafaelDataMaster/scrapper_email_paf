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
        
        Campos Core (Prioridade Alta):
        - Razão Social (fornecedor_nome)
        - Impostos individuais (IR, INSS, CSLL, ISS, ICMS)
        - Vencimento

        Args:
            text (str): Texto bruto do documento.

        Returns:
            Dict[str, Any]: Dicionário com os campos extraídos.
        """
        data = {}
        data['tipo_documento'] = 'NFSE'
        
        # Campos básicos (já existentes)
        data['cnpj_prestador'] = self._extract_cnpj(text)
        data['numero_nota'] = self._extract_numero_nota(text)
        data['valor_total'] = self._extract_valor(text)
        data['data_emissao'] = self._extract_data_emissao(text)
        
        # Campos Core PAF (Prioridade Alta)
        data['fornecedor_nome'] = self._extract_fornecedor_nome(text)
        data['vencimento'] = self._extract_vencimento(text)
        
        # Impostos individuais (Política 5.9 - campos obrigatórios)
        data['valor_ir'] = self._extract_ir(text)
        data['valor_inss'] = self._extract_inss(text)
        data['valor_csll'] = self._extract_csll(text)
        data['valor_iss'] = self._extract_valor_iss(text)
        data['valor_icms'] = self._extract_valor_icms(text)
        data['base_calculo_icms'] = self._extract_base_calculo_icms(text)
        
        # TODO: Implementar em segunda fase - campos secundários para compliance fiscal completo
        # data['cfop'] = self._extract_cfop(text)
        # data['cst'] = self._extract_cst(text)
        # data['ncm'] = self._extract_ncm(text)
        # data['natureza_operacao'] = self._extract_natureza_operacao(text)
        
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
    
    def _extract_fornecedor_nome(self, text: str) -> str:
        """
        Extrai a Razão Social do prestador de serviço.
        
        Busca por padrões comuns: "Prestador", "Razão Social", "Tomador de Serviço",
        ou texto logo após o CNPJ.
        
        Returns:
            str: Razão Social ou None se não encontrado
        """
        patterns = [
            r'(?i)Prestador[^\n]*?[:\s]+([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][A-Za-zÀ-ÿ\s&\.\-]{5,100})',
            r'(?i)Raz[ãa]o\s+Social[^\n]*?[:\s]+([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][A-Za-zÀ-ÿ\s&\.\-]{5,100})',
            r'(?i)Tomador[^\n]*?[:\s]+([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][A-Za-zÀ-ÿ\s&\.\-]{5,100})',
            r'(?i)Nome[^\n]*?[:\s]+([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][A-Za-zÀ-ÿ\s&\.\-]{5,100})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                nome = match.group(1).strip()
                # Remove números e limpa espaços extras
                nome = re.sub(r'\d+', '', nome).strip()
                if len(nome) >= 5:  # Razão social mínima
                    return nome
        
        # Fallback: busca texto logo após CNPJ
        cnpj_match = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', text)
        if cnpj_match:
            # Pega os próximos 100 caracteres após o CNPJ
            start_pos = cnpj_match.end()
            text_after_cnpj = text[start_pos:start_pos+100]
            nome_match = re.search(r'([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][A-Za-zÀ-ÿ\s&\.\-]{5,80})', text_after_cnpj)
            if nome_match:
                nome = nome_match.group(1).strip()
                # Remove padrões de data e números
                nome = re.sub(r'\d{2}/\d{2}/\d{4}', '', nome).strip()
                nome = re.sub(r'\d+', '', nome).strip()
                if len(nome) >= 5:
                    return nome
        
        return None
    
    def _extract_vencimento(self, text: str) -> str:
        """
        Extrai a data de vencimento da nota fiscal.
        
        Similar à extração de data_emissao, mas busca por keywords específicas.
        
        Returns:
            str: Data no formato ISO (YYYY-MM-DD) ou None
        """
        patterns = [
            r'(?i)Vencimento[:\s]+(\d{2}/\d{2}/\d{4})',
            r'(?i)Data\s+de\s+Vencimento[:\s]+(\d{2}/\d{2}/\d{4})',
            r'(?i)Venc[:\.\s]+(\d{2}/\d{2}/\d{4})',
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
    
    def _extract_ir(self, text: str) -> float:
        """
        Extrai o valor do Imposto de Renda retido.
        
        Conformidade: Política 5.9 exige captura de retenções.
        
        Returns:
            float: Valor do IR ou None se não encontrado
        """
        patterns = [
            r'(?i)(?:Valor\s+)?(?:do\s+)?IR\s*(?:Retido)?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Imposto\s+de\s+Renda[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Reten[çc][ãa]o\s+IR[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        ]
        
        return self._extract_valor_generico(patterns, text)
    
    def _extract_inss(self, text: str) -> float:
        """
        Extrai o valor do INSS retido.
        
        Returns:
            float: Valor do INSS ou None se não encontrado
        """
        patterns = [
            r'(?i)(?:Valor\s+)?(?:do\s+)?INSS\s*(?:Retido)?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Reten[çc][ãa]o\s+INSS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        ]
        
        return self._extract_valor_generico(patterns, text)
    
    def _extract_csll(self, text: str) -> float:
        """
        Extrai o valor da CSLL retido.
        
        Returns:
            float: Valor da CSLL ou None se não encontrado
        """
        patterns = [
            r'(?i)(?:Valor\s+)?(?:da\s+)?CSLL\s*(?:Retida)?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Reten[çc][ãa]o\s+CSLL[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Contribui[çc][ãa]o\s+Social[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        ]
        
        return self._extract_valor_generico(patterns, text)
    
    def _extract_valor_iss(self, text: str) -> float:
        """
        Extrai o valor do ISS (Imposto Sobre Serviços).
        
        Conformidade: Campo de alta prioridade para validação fiscal.
        
        Returns:
            float: Valor do ISS ou None se não encontrado
        """
        patterns = [
            r'(?i)(?:Valor\s+)?(?:do\s+)?ISS\s*(?:Retido)?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Imposto\s+(?:Sobre\s+)?Servi[çc]os?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Reten[çc][ãa]o\s+ISS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        ]
        
        return self._extract_valor_generico(patterns, text)
    
    def _extract_valor_icms(self, text: str) -> float:
        """
        Extrai o valor do ICMS.
        
        Returns:
            float: Valor do ICMS ou None se não encontrado
        """
        patterns = [
            r'(?i)(?:Valor\s+)?(?:do\s+)?ICMS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)Imposto\s+(?:sobre\s+)?Circula[çc][ãa]o[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        ]
        
        return self._extract_valor_generico(patterns, text)
    
    def _extract_base_calculo_icms(self, text: str) -> float:
        """
        Extrai a base de cálculo do ICMS.
        
        Returns:
            float: Base de cálculo do ICMS ou None se não encontrado
        """
        patterns = [
            r'(?i)Base\s+(?:de\s+)?C[áa]lculo\s+(?:do\s+)?ICMS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
            r'(?i)BC\s+ICMS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})',
        ]
        
        return self._extract_valor_generico(patterns, text)
    
    def _extract_valor_generico(self, patterns: list, text: str) -> float:
        """
        Helper genérico para extração de valores monetários.
        
        Args:
            patterns: Lista de padrões regex a tentar
            text: Texto onde buscar
            
        Returns:
            float: Valor encontrado ou None
        """
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                valor_str = match.group(1)
                try:
                    valor = float(valor_str.replace('.', '').replace(',', '.'))
                    if valor >= 0:  # Aceita zero para impostos
                        return valor
                except ValueError:
                    continue
        
        return None
