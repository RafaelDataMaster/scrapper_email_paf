import re
from datetime import datetime
from socket import has_ipv6
from typing import Any, Dict

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
        other_keywords = [
            "DEMONSTRATIVO",
            "LOCAWEB",
            "FATURA",
        ]
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
        texto_limpo = re.sub(r"\d{2}/\d{2}/\d{4}", " ", texto_limpo)
        padroes_lixo = r"(?i)\b(RPS|Lote|Protocolo|Recibo|S[eé]rie)\b\D{0,10}?\d+"
        texto_limpo = re.sub(padroes_lixo, " ", texto_limpo)

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

    def _extract_fornecedor_nome(self, text: str) -> str:
        text = self._normalize_text(text or "")

        m_before_cnpj = re.search(
            r"(?is)([A-ZÀ-ÿ][A-ZÀ-ÿ0-9\s&\.\-]{5,140})\s+CNPJ\s*[:\-]?\s*"
            r"\d{2}\D?\d{3}\D?\d{3}\D?\d{4}\D?\d{2}",
            text,
        )
        if m_before_cnpj:
            nome = re.sub(r"\s+", " ", m_before_cnpj.group(1)).strip()
            if not re.match(r"(?i)^(TOMADOR|CPF|CNPJ|INSCRI|PREFEITURA|NOTA\s+FISCAL)\b", nome):
                return nome

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
                if len(nome) >= 5:
                    return nome

        cnpj_match = re.search(r"\d{2}\D?\d{3}\D?\d{3}\D?\d{4}\D?\d{2}", text)
        if cnpj_match:
            start_pos = cnpj_match.end()
            text_after_cnpj = text[start_pos : start_pos + 100]
            nome_match = re.search(r"([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][A-Za-zÀ-ÿ\s&\.\-]{5,80})", text_after_cnpj)
            if nome_match:
                nome = nome_match.group(1).strip()
                nome = re.sub(r"\d{2}/\d{2}/\d{4}", "", nome).strip()
                nome = re.sub(r"\d+", "", nome).strip()
                if len(nome) >= 5:
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
