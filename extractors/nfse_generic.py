import re
from datetime import datetime
from socket import has_ipv6
from typing import Any, Dict, Optional

from config.empresas import EMPRESAS_CADASTRO
from core.extractors import BaseExtractor, find_linha_digitavel, register_extractor


@register_extractor
class NfseGenericExtractor(BaseExtractor):
    """Extrator genérico (fallback) para NFSe.

    Importante: este extrator NÃO é "genérico" para qualquer documento.
    Ele é um fallback para NFS-e quando não há extrator específico.
    """

    @classmethod
    def can_handle(cls, text: str) -> bool:
        """Retorna True apenas para textos que parecem NFSe (e não boleto/DANFE/outros)."""
        text_upper = (text or "").upper()

        # Indicadores FORTES de NFS-e - se presentes, É NFS-e mesmo com outras palavras
        nfse_strong_indicators = [
            "NFS-E",
            "NFSE",
            "NOTA FISCAL DE SERVIÇO ELETRÔNICA",
            "NOTA FISCAL DE SERVICO ELETRONICA",
            "NOTA FISCAL ELETRÔNICA DE SERVIÇO",
            "NOTA FISCAL ELETRONICA DE SERVICO",
            "PREFEITURA MUNICIPAL",
            "CÓDIGO DE VERIFICAÇÃO",
            "CODIGO DE VERIFICACAO",
        ]
        is_strong_nfse = any(indicator in text_upper for indicator in nfse_strong_indicators)

        # Se for NFS-e forte, retorna True imediatamente (ignora outras verificações)
        if is_strong_nfse:
            # Mas ainda verifica se não é um boleto com linha digitável
            has_linha_digitavel = find_linha_digitavel(text)
            if not has_linha_digitavel:
                return True

        # DANFE / NF-e (produto) - não é NFSe
        danfe_keywords = [
            "DANFE",
            "DOCUMENTO AUXILIAR",
            "CHAVE DE ACESSO",
            "NF-E",
            "NFE",
        ]
        if any(kw in text_upper for kw in danfe_keywords):
            if ("DANFE" in text_upper) or ("CHAVE DE ACESSO" in text_upper):
                return False
            digits = re.sub(r"\D", "", text or "")
            if re.search(r"\b\d{44}\b", digits):
                return False

        # Outros documentos (faturas / demonstrativos) - deixar para extrator dedicado
        # NOTA: "NOTA FATURA" da VSP Solution é NFS-e, mas "FATURA" genérica não é
        other_keywords = [
            "DEMONSTRATIVO",
            "LOCAWEB",
        ]
        # FATURA só bloqueia se NÃO tiver indicadores de NFS-e
        if "FATURA" in text_upper and not is_strong_nfse:
            # Verifica se é "NOTA FATURA" (comum em NFS-e)
            if "NOTA FATURA" not in text_upper and "NOTA-FATURA" not in text_upper:
                return False
        if any(kw in text_upper for kw in other_keywords):
            return False

        # Indicadores fortes de que é um BOLETO
        boleto_keywords = [
            "LINHA DIGITÁVEL",
            "LINHA DIGITAVEL",
            "BENEFICIÁRIO",
            "BENEFICIARIO",
            "CÓDIGO DE BARRAS",
            "CODIGO DE BARRAS",
            "CEDENTE",
        ]
        has_linha_digitavel = find_linha_digitavel(text)
        if has_linha_digitavel:
            return False

        boleto_score = sum(1 for kw in boleto_keywords if kw in text_upper)
        if boleto_score >= 2:
            return False

        return True

    def extract(self, text: str) -> Dict[str, Any]:
        text = self._normalize_text(text or "")

        data: Dict[str, Any] = {"tipo_documento": "NFSE"}

        data["cnpj_prestador"] = self._extract_cnpj(text)
        data["numero_nota"] = self._extract_numero_nota(text)
        data["valor_total"] = self._extract_valor(text)
        data["data_emissao"] = self._extract_data_emissao(text)

        data["fornecedor_nome"] = self._extract_fornecedor_nome(text)
        data["vencimento"] = self._extract_vencimento(text)

        data["valor_ir"] = self._extract_ir(text)
        data["valor_inss"] = self._extract_inss(text)
        data["valor_csll"] = self._extract_csll(text)
        data["valor_iss"] = self._extract_valor_iss(text)
        data["valor_icms"] = self._extract_valor_icms(text)
        data["base_calculo_icms"] = self._extract_base_calculo_icms(text)

        return data

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\u00ad", "-")
        text = text.replace("\u2013", "-").replace("\u2014", "-")
        text = text.replace("\u00a0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        return text

    def _extract_cnpj(self, text: str):
        text = self._normalize_text(text or "")
        m = re.search(
            r"(?<!\d)(\d{2})\D?(\d{3})\D?(\d{3})\D?(\d{4})\D?(\d{2})(?!\d)",
            text,
        )
        if not m:
            return None
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}/{m.group(4)}-{m.group(5)}"

    def _extract_valor(self, text: str):
        patterns = [
            r"(?i)Valor\s+Total\s*[:\s]*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Valor\s+da\s+Nota\s*[:\s]*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Valor\s*[:\s]*R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Valor\s+Total\s*[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})\b",
            r"(?i)Valor\s+da\s+Nota\s*[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})\b",
            r"(?i)Total\s+Nota\s*[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})\b",
            r"(?i)Valor\s+L[ií]quido\s*[:\s]+(\d{1,3}(?:\.\d{3})*,\d{2})\b",
            r"\bR\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                valor_str = match.group(1)
                try:
                    valor = float(valor_str.replace(".", "").replace(",", "."))
                    if valor > 0:
                        return valor
                except ValueError:
                    continue
        return 0.0

    def _extract_data_emissao(self, text: str):
        match = re.search(r"\d{2}/\d{2}/\d{4}", text)
        if match:
            try:
                dt = datetime.strptime(match.group(0), "%d/%m/%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        return None

    def _extract_numero_nota(self, text: str):
        if not text:
            return None

        texto_limpo = text
        # Remove datas no formato DD/MM/YYYY para não confundir com números
        texto_limpo = re.sub(r"\d{2}/\d{2}/\d{4}", " ", texto_limpo)
        padroes_lixo = r"(?i)\b(RPS|Lote|Protocolo|Recibo|S[eé]rie)\b\D{0,10}?\d+"
        texto_limpo = re.sub(padroes_lixo, " ", texto_limpo)

        # Padrões que capturam números compostos (ex: 2025/44, 2025-44)
        padroes_compostos = [
            # "Nº: 2025/44" ou "N°: 2025-44" - padrão composto ano/sequencial
            r"(?i)N[º°o]\.?\s*[:.-]?\s*(\d{4}[/\-]\d{1,6})\b",
            # "NFS-e ... Nº: 2025/44"
            r"(?i)NFS-?e\s*(?:N[º°o]|Num)?\.?\s*[:.-]?\s*(\d{4}[/\-]\d{1,6})\b",
        ]

        # Primeiro tenta padrões compostos (mais específicos)
        for regex in padroes_compostos:
            match = re.search(regex, texto_limpo, re.IGNORECASE)
            if match:
                resultado = match.group(1)
                return resultado

        # Padrões para números simples (fallback)
        padroes = [
            r"(?i)Número\s+da\s+Nota.*?(?<!\d)(\d{1,15})(?!\d)",
            r"(?i)(?:(?:Número|Numero|N[º°o])\s*da\s*)?NFS-e\s*(?:N[º°o]|Num)?\.?\s*[:.-]?\s*\b(\d{1,15})\b",
            r"(?i)Número\s+da\s+Nota[\s\S]*?\b(\d{1,15})\b",
            r"(?i)Nota\s*Fiscal\s*(?:N[º°o]|Num)?\.?\s*[:.-]?\s*(\d{1,15})",
            r"(?i)(?<!RPS\s)(?<!Lote\s)(?<!S[eé]rie\s)(?:Número|N[º°o])\s*[:.-]?\s*(\d{1,15})",
        ]

        for regex in padroes:
            match = re.search(regex, texto_limpo, re.IGNORECASE)
            if match:
                resultado = match.group(1)
                resultado = resultado.replace(".", "").replace(" ", "")
                return resultado

        return None

    def _is_empresa_propria(self, nome: str, cnpj: Optional[str] = None) -> bool:
        """
        Verifica se o nome/CNPJ pertence ao grupo de empresas do usuário (Tomador).

        Isso evita capturar a própria empresa como "fornecedor" em NFS-e
        onde o Tomador aparece antes do Prestador no layout do PDF.

        Args:
            nome: Nome da empresa a verificar
            cnpj: CNPJ opcional para verificação mais precisa

        Returns:
            True se for empresa própria (deve ser rejeitada como fornecedor)
        """
        if not nome:
            return False

        nome_upper = nome.upper().strip()

        # Se temos CNPJ, verifica diretamente no cadastro
        if cnpj:
            cnpj_limpo = re.sub(r'\D', '', cnpj)
            if cnpj_limpo in EMPRESAS_CADASTRO:
                return True

        # Verifica se o nome contém alguma razão social do cadastro
        for dados in EMPRESAS_CADASTRO.values():
            razao = dados.get('razao_social', '').upper()
            if not razao:
                continue
            # Extrai a parte principal do nome (antes de parênteses)
            razao_principal = razao.split('(')[0].strip()
            # Remove sufixos comuns para comparação mais flexível
            razao_limpa = re.sub(r'\s*(LTDA|S/?A|EIRELI|ME|EPP|S\.A\.?|-\s*ME|-\s*EPP)\s*$', '', razao_principal, flags=re.IGNORECASE).strip()
            nome_limpo = re.sub(r'\s*(LTDA|S/?A|EIRELI|ME|EPP|S\.A\.?|-\s*ME|-\s*EPP)\s*$', '', nome_upper, flags=re.IGNORECASE).strip()

            # Verifica match exato ou se um contém o outro
            if razao_limpa and nome_limpo:
                if razao_limpa == nome_limpo:
                    return True
                # Verifica se o nome extraído é parte significativa da razão social
                if len(nome_limpo) >= 10 and nome_limpo in razao_limpa:
                    return True
                if len(razao_limpa) >= 10 and razao_limpa in nome_limpo:
                    return True

        return False

    def _extract_fornecedor_nome(self, text: str) -> str:
        text = self._normalize_text(text or "")

        # Padrão 1: Empresa com sufixo (LTDA, S/A, etc.) antes de CPF/CNPJ
        # Este é o padrão mais confiável para NFS-e
        m_empresa_antes_cnpj = re.search(
            r"([A-ZÀ-ÿ][A-Za-zÀ-ÿ0-9\s&\.\-]+(?:LTDA|S/?A|EIRELI|ME|EPP))\s*\n?\s*(?:CPF/)?CNPJ",
            text,
            re.IGNORECASE | re.MULTILINE
        )
        if m_empresa_antes_cnpj:
            nome = m_empresa_antes_cnpj.group(1).strip()
            # Limpar possível lixo no início (ex: "Código de Verificação\n12345\n")
            # Pega apenas a última linha (que contém o nome da empresa)
            if '\n' in nome:
                nome = nome.split('\n')[-1].strip()
            # Extrai CNPJ próximo para verificação
            cnpj_proximo = re.search(r"(?:CPF/)?CNPJ\s*[:\-]?\s*(\d{2}\D?\d{3}\D?\d{3}\D?\d{4}\D?\d{2})", text[m_empresa_antes_cnpj.start():m_empresa_antes_cnpj.end()+50])
            cnpj = cnpj_proximo.group(1) if cnpj_proximo else None
            if len(nome) >= 5 and not self._is_empresa_propria(nome, cnpj):
                return nome

        # Padrão 2: Após "Código de Verificação" + número (comum em NFS-e de prefeituras)
        m_apos_verificacao = re.search(
            r"(?i)(?:Código de Verificação|Verificação)\s+[\w\d]+\s+([A-ZÀ-ÿ][A-Za-zÀ-ÿ0-9\s&\.\-]+(?:LTDA|S/?A|EIRELI|ME|EPP))",
            text
        )
        if m_apos_verificacao:
            nome = m_apos_verificacao.group(1).strip()
            if len(nome) >= 5 and not self._is_empresa_propria(nome):
                return nome

        # Padrão 3: Texto antes de CNPJ (antigo padrão, agora suporta CPF/CNPJ)
        m_before_cnpj = re.search(
            r"(?is)([A-ZÀ-ÿ][A-ZÀ-ÿ0-9\s&\.\-]{5,140})\s+(?:CPF/)?CNPJ\s*[:\-]?\s*"
            r"\d{2}\D?\d{3}\D?\d{3}\D?\d{4}\D?\d{2}",
            text,
        )
        if m_before_cnpj:
            nome = re.sub(r"\s+", " ", m_before_cnpj.group(1)).strip()
            if not re.match(r"(?i)^(TOMADOR|CPF|CNPJ|INSCRI|PREFEITURA|NOTA\s+FISCAL)\b", nome):
                if not self._is_empresa_propria(nome):
                    return nome

        # Padrão 4: Busca por rótulos específicos
        patterns = [
            r"(?im)^\s*Raz[ãa]o\s+Social\s*[:\-]\s*([A-ZÀ-ÿ][A-Za-zÀ-ÿ\s&\.\-]{5,100})\s*$",
            r"(?i)Raz[ãa]o\s+Social[^\n]*?[:\-\s]+([A-ZÀ-ÿ][A-Za-zÀ-ÿ\s&\.\-]{5,100})",
            r"(?i)Prestador[^\n]*?:\s*([A-ZÀ-ÿ][A-Za-zÀ-ÿ\s&\.\-]{5,120})",
            r"(?i)Nome[^\n]*?[:\-\s]+([A-ZÀ-ÿ][A-Za-zÀ-ÿ\s&\.\-]{5,120})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                nome = match.group(1).strip()
                nome = re.sub(r"\d+", "", nome).strip()
                if len(nome) >= 5 and not self._is_empresa_propria(nome):
                    return nome

        # Padrão 5: Primeira empresa com sufixo no documento (fallback genérico)
        m_primeira_empresa = re.search(
            r"\b([A-ZÀ-ÿ][A-Za-zÀ-ÿ0-9\s&\.\-]{5,80}(?:LTDA|S/?A|EIRELI|ME|EPP))\b",
            text,
            re.IGNORECASE
        )
        if m_primeira_empresa:
            nome = m_primeira_empresa.group(1).strip()
            # Evitar capturar frases que terminam com sufixo por coincidência
            if not re.match(r"(?i)^(Documento|Regime|optante)", nome):
                if not self._is_empresa_propria(nome):
                    return nome

        # Padrão 6 (último fallback): Texto após primeiro CNPJ
        # Este é o fallback menos confiável, mas ainda útil em alguns casos
        cnpj_match = re.search(r"\d{2}\D?\d{3}\D?\d{3}\D?\d{4}\D?\d{2}", text)
        if cnpj_match:
            start_pos = cnpj_match.end()
            text_after_cnpj = text[start_pos : start_pos + 100]
            # Evitar capturar "Inscrição municipal" ou similar
            nome_match = re.search(r"([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][A-Za-zÀ-ÿ\s&\.\-]{5,80})", text_after_cnpj)
            if nome_match:
                nome = nome_match.group(1).strip()
                # Rejeitar se começar com palavras-chave de metadados
                if re.match(r"(?i)^(Inscri[çc][ãa]o|Municipal|Estadual|CEP|AV\.|RUA|Telefone|Email)", nome):
                    return None
                nome = re.sub(r"\d{2}/\d{2}/\d{4}", "", nome).strip()
                nome = re.sub(r"\d+", "", nome).strip()
                if len(nome) >= 5 and not self._is_empresa_propria(nome):
                    return nome

        return None

    def _extract_vencimento(self, text: str) -> str:
        patterns = [
            r"(?i)Vencimento[:\s]+(\d{2}/\d{2}/\d{4})",
            r"(?i)Data\s+de\s+Vencimento[:\s]+(\d{2}/\d{2}/\d{4})",
            r"(?i)Venc[:\.\s]+(\d{2}/\d{2}/\d{4})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    dt = datetime.strptime(match.group(1), "%d/%m/%Y")
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return None

    def _extract_valor_generico(self, patterns, text: str) -> float:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                valor_str = match.group(1)
                try:
                    valor = float(valor_str.replace(".", "").replace(",", "."))
                    if valor >= 0:
                        return valor
                except ValueError:
                    continue
        return 0.0

    def _extract_ir(self, text: str) -> float:
        patterns = [
            r"(?i)(?:Valor\s+)?(?:do\s+)?IR\s*(?:Retido)?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Imposto\s+de\s+Renda[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Reten[çc][ãa]o\s+IR[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        ]
        return self._extract_valor_generico(patterns, text)

    def _extract_inss(self, text: str) -> float:
        patterns = [
            r"(?i)(?:Valor\s+)?(?:do\s+)?INSS\s*(?:Retido)?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Reten[çc][ãa]o\s+INSS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        ]
        return self._extract_valor_generico(patterns, text)

    def _extract_csll(self, text: str) -> float:
        patterns = [
            r"(?i)(?:Valor\s+)?(?:da\s+)?CSLL\s*(?:Retida)?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Reten[çc][ãa]o\s+CSLL[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Contribui[çc][ãa]o\s+Social[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        ]
        return self._extract_valor_generico(patterns, text)

    def _extract_valor_iss(self, text: str) -> float:
        patterns = [
            r"(?i)(?:Valor\s+)?(?:do\s+)?ISS\s*(?:Retido)?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Imposto\s+(?:Sobre\s+)?Servi[çc]os?[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Reten[çc][ãa]o\s+ISS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        ]
        return self._extract_valor_generico(patterns, text)

    def _extract_valor_icms(self, text: str) -> float:
        patterns = [
            r"(?i)(?:Valor\s+)?(?:do\s+)?ICMS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)Imposto\s+(?:sobre\s+)?Circula[çc][ãa]o[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        ]
        return self._extract_valor_generico(patterns, text)

    def _extract_base_calculo_icms(self, text: str) -> float:
        patterns = [
            r"(?i)Base\s+de\s+C[aá]lculo\s+ICMS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?i)BC\s+ICMS[:\s]*R?\$?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
        ]
        return self._extract_valor_generico(patterns, text)
