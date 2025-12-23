from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class NfCandidateResult:
    value: Optional[str]
    confidence: float
    reason: str


_LABEL_PATTERNS: list[tuple[re.Pattern[str], float, str]] = [
    # NFS-e / Nota Fiscal
    (re.compile(r"\bNFS[-\s]?E\b\s*(?:n[ºo°]\s*)?[:\-\s]*([0-9]{3,12})", re.IGNORECASE), 1.0, "label=nfse"),
    (re.compile(r"\bNOTA\s+FISCAL\b.*?\b(?:n[ºo°]|n\.|nro|nº)\b\s*[:\-\s]*([0-9]{3,12})", re.IGNORECASE | re.DOTALL), 0.9, "label=nota_fiscal"),
    (re.compile(r"\bNOTA\s+FISCAL\b\s*[:\-\s]*([0-9]{3,12})", re.IGNORECASE), 0.7, "label=nota_fiscal_short"),
    # Genéricos bem comuns
    (re.compile(r"\bN[ºo°]\b\s*[:\-\s]*([0-9]{3,12})"), 0.55, "label=n"),
    (re.compile(r"\bN[Uu]\s*M\s*[:\-\s]*([0-9]{3,12})"), 0.55, "label=num"),
    (re.compile(r"\bN[Úu]MERO\b\s*[:\-\s]*([0-9]{3,12})", re.IGNORECASE), 0.55, "label=numero"),
    (re.compile(r"\bN[Úu]MERO\s*[:\-\s]*([0-9]{3,12})", re.IGNORECASE), 0.5, "label=numero_short"),

    # Boleto: muitos títulos trazem "Número do Documento" (às vezes ano.seq: 2025.122)
    # Mantemos dígitos apenas (ex: 2025.122 -> 2025122) para compatibilidade com debug/obs_interna.
    (re.compile(r"\bN[Úu]mero\s+do\s+Documento\b[\s\S]{0,80}?([0-9]{2,6}[\./-][0-9]{1,8}|[0-9]{3,12})\b", re.IGNORECASE | re.DOTALL), 0.7, "label=numero_documento"),
    (re.compile(r"\bN\.\s*documento\b[\s\S]{0,80}?([0-9]{2,6}[\./-][0-9]{1,8}|[0-9]{3,12})\b", re.IGNORECASE | re.DOTALL), 0.65, "label=n_documento"),
]

# Palavras que geralmente indicam que o número NÃO é NF
_NEGATIVE_CONTEXT = re.compile(
    r"\b(rps|protocolo|autentic|pedido|pc\b|ordem|os\b|boleto|linha\s+digit[áa]vel|nosso\s+n[úu]mero|ag[êe]ncia|conta|cnpj|cpf|cep)\b",
    re.IGNORECASE,
)

# Formatos típicos que não são NF
_DATE_LIKE = re.compile(r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b")
_MONEY_LIKE = re.compile(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b")


def _iter_context_windows(text: str, spans: Iterable[tuple[int, int]], window: int = 80):
    for start, end in spans:
        a = max(0, start - window)
        b = min(len(text), end + window)
        yield text[a:b]


def extract_nf_candidate(text: str) -> NfCandidateResult:
    """Heurística para sugerir um número de NF (candidato) a partir do texto.

    Importante: isso NÃO garante que seja a NF correta — é apenas uma sugestão
    para apoiar debug/análise. A decisão de preencher NF no PAF continua fora do MVP.
    """
    if not text:
        return NfCandidateResult(None, 0.0, "empty_text")

    # Mantém uma versão compacta para padrões de mesma linha
    text_flat = " ".join(text.split())

    best_value: Optional[str] = None
    best_score = 0.0
    best_reason = "no_match"

    for pattern, base_score, reason in _LABEL_PATTERNS:
        for m in pattern.finditer(text):
            raw = m.group(1) if m.groups() else None
            if not raw:
                continue
            value = re.sub(r"\D+", "", raw)
            if not value:
                continue

            # filtros simples
            if len(value) < 3 or len(value) > 12:
                continue

            # Se o match original parece data/valor, ignora
            snippet = text[m.start():m.end()]
            if _DATE_LIKE.search(snippet) or _MONEY_LIKE.search(snippet):
                continue

            score = base_score

            # Penaliza se contexto tem palavras de "não-NF"
            for ctx in _iter_context_windows(text, [(m.start(), m.end())], window=90):
                if _NEGATIVE_CONTEXT.search(ctx):
                    score *= 0.55

            # Bônus se aparece bem no começo (muitos layouts trazem no topo)
            if m.start() < 500:
                score += 0.05

            if score > best_score:
                best_score = score
                best_value = value
                best_reason = reason

    # fallback bem leve: procura "Número: 12345" no texto achatado
    if best_value is None:
        m = re.search(r"\bN[Úu]MERO\s*[:\-]\s*([0-9]{3,12})\b", text_flat, flags=re.IGNORECASE)
        if m:
            best_value = m.group(1)
            best_score = 0.45
            best_reason = "fallback=numero_colon"

    # Converte score em uma "confiança" simples (0..1)
    confidence = max(0.0, min(1.0, best_score)) if best_value else 0.0

    # Só retorna candidato se tiver alguma confiança mínima
    if not best_value or confidence < 0.35:
        return NfCandidateResult(None, confidence, best_reason)

    return NfCandidateResult(best_value, confidence, best_reason)
