import re
import unicodedata
from typing import Any, Dict, Optional

from core.extractors import BaseExtractor, register_extractor


def _strip_accents(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _extract_cnpj_like(text: str) -> Optional[str]:
    if not text:
        return None

    # Prefer formatted CNPJ.
    m = re.search(r"\b(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b", text)
    if m:
        return m.group(1)

    # Fallback: 14 digits.
    m = re.search(r"\b(\d{14})\b", re.sub(r"\D+", " ", text))
    if m:
        return m.group(1)

    return None


def _format_cnpj_digits(cnpj_digits: str) -> str:
    digits = re.sub(r"\D+", "", cnpj_digits or "")
    if len(digits) != 14:
        return cnpj_digits
    return f"{digits[0:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"


def _parse_br_money_to_float(value: str) -> Optional[float]:
    if not value:
        return None
    s = value.strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _parse_date_ddmmyyyy_to_iso(value: str) -> Optional[str]:
    if not value:
        return None
    m = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", value)
    if not m:
        return None
    dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
    return f"{yyyy}-{mm}-{dd}"


@register_extractor
class NetCenterExtractor(BaseExtractor):
    """Extrator cirúrgico para faturas/boletos da Net Center Unaí.

    Objetivo: evitar capturar rótulos (ex: CPF/CNPJ) como nome de fornecedor,
    garantindo um fornecedor_nome limpo e estável.
    """

    FORNECEDOR_FIXO = "NET CENTER UNAI PROVEDOR DE INTERNET LTDA"
    CNPJ_NETCENTER = "05.382.200/0001-70"
    CNPJ_NETCENTER_DIGITS = "05382200000170"

    @classmethod
    def can_handle(cls, text: str) -> bool:
        text_up = (text or "").upper()
        text_norm = _strip_accents(text_up)
        text_compact = re.sub(r"[^A-Z0-9]+", "", text_norm)

        digits_only = re.sub(r"\D+", "", text or "")

        # Assinatura forte: CNPJ do beneficiário.
        if cls.CNPJ_NETCENTER_DIGITS in digits_only:
            return True

        has_vendor = (
            "NETCENTER" in text_compact
            or "NET CENTER" in text_norm
            or "NETCENTERUNAI" in text_compact
            or "NETCENTERUNAI" in text_compact
            or "UNAI" in text_norm and "NET" in text_norm and "CENTER" in text_norm
        )

        # Evita falso-positivo em docs não-boleto: exige também sinais típicos de boleto.
        boleto_markers = [
            "LINHA DIGITAVEL",
            "LINHA DIGITÁVEL",
            "BENEFICI",
            "VENCIMENTO",
            "VALOR DO DOCUMENTO",
            "CODIGO DE BARRAS",
            "CÓDIGO DE BARRAS",
        ]
        markers_score = sum(1 for kw in boleto_markers if re.sub(r"[^A-Z0-9]+", "", _strip_accents(kw.upper())) in text_compact)

        # Também aceita a presença de uma linha digitável (OCR às vezes perde labels).
        has_linha_digitavel = bool(
            re.search(
                r"\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}",
                text or "",
            )
        )

        return bool(has_vendor and (markers_score >= 1 or has_linha_digitavel))

    def extract(self, text: str) -> Dict[str, Any]:
        # Lazy import para não antecipar o registro do BoletoExtractor (ordem do registry).
        from extractors.boleto import BoletoExtractor

        generic = BoletoExtractor()
        data = generic.extract(text)

        # Correção 1: fornecedor fixo (layout identificado)
        data["fornecedor_nome"] = self.FORNECEDOR_FIXO

        # Correção 2: garante CNPJ do beneficiário se o genérico falhar
        if not data.get("cnpj_beneficiario"):
            # Ex: "CPF/CNPJ: 05.382.200/0001-70" / "CNPJ: 05.382.200/0001-70"
            m = re.search(
                r"(?i)\b(?:CPF\s*/\s*CNPJ|CNPJ)\s*:?[\s\n\r]*"
                r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})\b",
                text or "",
            )
            if m:
                data["cnpj_beneficiario"] = m.group(1)
            else:
                cnpj_any = _extract_cnpj_like(text or "")
                if cnpj_any:
                    # Se vier só em dígitos, tenta formatar
                    if re.fullmatch(r"\d{14}", str(cnpj_any)):
                        data["cnpj_beneficiario"] = _format_cnpj_digits(str(cnpj_any))
                    else:
                        data["cnpj_beneficiario"] = cnpj_any

        # Correção 2.1: se o genérico capturou o label como nome (ex: "CPF/CNPJ"), força mesmo assim.
        # (Mantém o fornecedor fixo; aqui é só um reforço caso alguém altere acima.)
        if not data.get("fornecedor_nome") or re.search(r"(?i)\bCPF\b\s*/\s*\bCNPJ\b|\bCPF/CNPJ\b", data.get("fornecedor_nome") or ""):
            data["fornecedor_nome"] = self.FORNECEDOR_FIXO

        # Correção 3: valor total (layout Net Center costuma ter "Valor total a pagar")
        m_total = re.search(
            r"(?is)\bValor\s+total\s+a\s+pagar\b\s*:?\s*(?:R\$\s*)?([\d\.,]+)",
            text or "",
        )
        if m_total:
            v = _parse_br_money_to_float(m_total.group(1))
            if v is not None:
                data["valor_documento"] = v

        # Correção 3: valor do documento (se existir em formato bem definido)
        m_val = re.search(
            r"(?i)\bValor\s+documento\b\s*[\n\r]*\s*R?\$?\s*([\d\.,]+)",
            text or "",
        )
        if m_val:
            v = _parse_br_money_to_float(m_val.group(1))
            if v is not None:
                data["valor_documento"] = v

        # Fallback (bem específico/seguro para este layout): pega o maior valor monetário com vírgula.
        # Evita capturar "1" (quantidade) como valor do documento.
        money_vals = []
        for m in re.finditer(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", text or ""):
            fv = _parse_br_money_to_float(m.group(0))
            if fv is not None:
                money_vals.append(fv)
        if money_vals:
            max_v = max(money_vals)
            cur = data.get("valor_documento")
            try:
                cur_f = float(cur) if cur is not None else None
            except Exception:
                cur_f = None
            if cur_f is None or cur_f < max_v:
                data["valor_documento"] = max_v

        # Correção 4: emissão e vencimento (muito estável no topo do layout)
        # Ex: "Emissão Vencimento" + linha com "26/12/2023 20/01/2024"
        m_dates = re.search(
            r"(?is)\bEmiss[aã]o\b\s+Vencim\s*ento\b.*?(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})",
            text or "",
        )
        if m_dates:
            emissao_iso = _parse_date_ddmmyyyy_to_iso(m_dates.group(1))
            venc_iso = _parse_date_ddmmyyyy_to_iso(m_dates.group(2))
            if emissao_iso:
                data["data_emissao"] = emissao_iso
            if venc_iso:
                data["vencimento"] = venc_iso

        # Fallback: vencimento também aparece como "Local de pagamento Vencimento".
        m_venc = re.search(
            r"(?is)\bLocal\s+de\s+pagamento\s+Vencimento\b.*?(\d{2}/\d{2}/\d{4})",
            text or "",
        )
        if m_venc:
            venc_iso = _parse_date_ddmmyyyy_to_iso(m_venc.group(1))
            if venc_iso:
                data["vencimento"] = venc_iso

        return data
