from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# Match CNPJ even when PDF extraction inserts spaces between separators.
# Examples: "12.345.678/0001-90", "12 . 345 . 678 / 0001 - 90", "12345678000190"
_CNPJ_ANY_RE = re.compile(
    r"(?<!\d)(?:"
    r"\d{2}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*/\s*\d{4}\s*-\s*\d{2}"
    r"|\d{14}"
    r")(?!\d)",
    flags=re.MULTILINE,
)


@dataclass(frozen=True)
class EmpresaMatch:
    cnpj_digits: str
    razao_social: str
    codigo: str
    method: str
    score: int


def _normalize_cnpj_to_digits(value: str) -> Optional[str]:
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    if len(digits) != 14:
        return None
    return digits


def format_cnpj(digits: str) -> str:
    d = _normalize_cnpj_to_digits(digits)
    if not d:
        return ""
    return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"


def _empresa_codigo_from_razao(razao_social: str) -> str:
    if not razao_social:
        return ""
    # pega o primeiro token alfanumérico (ex: CSC, MASTER, OP11, RBC)
    cleaned = re.sub(r"\([^)]*\)", " ", razao_social)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    m = re.search(r"\b([A-Z0-9]{2,15})\b", cleaned.upper())
    return m.group(1) if m else cleaned[:20].upper()


def _load_empresas_cadastro() -> Dict[str, Dict[str, str]]:
    # Import local para não forçar carga em caminhos que não usam a feature
    try:
        from config.empresas import EMPRESAS_CADASTRO  # type: ignore

        # Normaliza chaves para dígitos
        normalized: Dict[str, Dict[str, str]] = {}
        for cnpj, payload in (EMPRESAS_CADASTRO or {}).items():
            cnpj_digits = _normalize_cnpj_to_digits(str(cnpj))
            if not cnpj_digits:
                continue
            normalized[cnpj_digits] = payload
        return normalized
    except Exception:
        return {}


def iter_cnpjs_in_text(text: str) -> Iterable[Tuple[str, int, int, str]]:
    """Itera CNPJs encontrados no texto.

    Returns tuples: (cnpj_digits, start, end, raw_match)
    """
    if not text:
        return []

    for m in _CNPJ_ANY_RE.finditer(text):
        raw = m.group(0)
        digits = _normalize_cnpj_to_digits(raw)
        if not digits:
            continue
        yield (digits, m.start(), m.end(), raw)


def find_empresa_no_texto(text: str) -> Optional[EmpresaMatch]:
    """Detecta a empresa "nossa" no documento via CNPJ (preferencial) e fallback por nome.

    Regra de negócio: se um CNPJ do cadastro aparece no documento, esta é a EMPRESA.
    """
    cadastro = _load_empresas_cadastro()
    if not cadastro or not text:
        return None

    # 1) Preferência: match por CNPJ
    best: Optional[EmpresaMatch] = None
    upper = text.upper()

    for cnpj_digits, start, end, _raw in iter_cnpjs_in_text(text):
        if cnpj_digits not in cadastro:
            continue

        payload = cadastro.get(cnpj_digits) or {}
        razao = (payload.get("razao_social") or "").strip()
        codigo = _empresa_codigo_from_razao(razao)

        # Score contextual (pagador/tomador/destinatário geralmente são "nós")
        window = upper[max(0, start - 250) : min(len(upper), end + 250)]
        score = 10
        if re.search(r"\b(DADOS\s+DO\s+PAGADOR|PAGADOR|SACADO)\b", window):
            score += 6
        if re.search(r"\b(TOMADOR|DESTINAT[ÁA]RIO|CLIENTE|CONTRATANTE)\b", window):
            score += 4
        if re.search(r"\bCNPJ\b", window):
            score += 1

        cand = EmpresaMatch(
            cnpj_digits=cnpj_digits,
            razao_social=razao,
            codigo=codigo,
            method="cnpj",
            score=score,
        )
        if best is None or cand.score > best.score:
            best = cand

    if best:
        return best

    # 2) Fallback: match por razão social (apenas se não achou CNPJ)
    # Mantém simples e barato: procura pelo "código" (primeiro token) e por parte do nome.
    # Evita varrer o texto inteiro por dezenas de nomes quando já existe CNPJ.
    for cnpj_digits, payload in cadastro.items():
        razao = (payload.get("razao_social") or "").strip()
        if not razao:
            continue
        codigo = _empresa_codigo_from_razao(razao)
        if codigo and re.search(rf"\b{re.escape(codigo)}\b", upper):
            return EmpresaMatch(
                cnpj_digits=cnpj_digits,
                razao_social=razao,
                codigo=codigo,
                method="nome",
                score=5,
            )

    return None


def is_cnpj_nosso(cnpj_value: Optional[str]) -> bool:
    if not cnpj_value:
        return False
    cadastro = _load_empresas_cadastro()
    digits = _normalize_cnpj_to_digits(cnpj_value)
    return bool(digits and digits in cadastro)


def is_nome_nosso(nome: Optional[str]) -> bool:
    if not nome:
        return False
    cadastro = _load_empresas_cadastro()
    if not cadastro:
        return False

    n_up = re.sub(r"\s+", " ", nome).strip().upper()
    if not n_up:
        return False

    # Heurística: se contém um "código" curto/distintivo (primeiro token) de alguma empresa nossa.
    # IMPORTANTe: evitar falsos positivos com tokens genéricos (ex: SERVICOS, CONSULTORIA).
    stopwords = {
        'SERVICO', 'SERVICOS',
        'CONSULTORIA',
        'GESTAO', 'INTEGRADA',
        'COMERCIO', 'INDUSTRIA',
        'TECNOLOGIA', 'SOLUCOES',
        'SISTEMA', 'SISTEMAS',
        'EMPRESA', 'EMPRESAS',
        'ADMINISTRACAO', 'ADMINISTRADORA',
        'PARTICIPACOES',
        'GRUPO', 'HOLDING',
        'COMPANHIA', 'CIA',
        'LTDA', 'SA', 'S/A',
    }
    for payload in cadastro.values():
        razao = (payload.get("razao_social") or "").strip()
        codigo = _empresa_codigo_from_razao(razao)
        if not codigo:
            continue

        codigo_up = codigo.upper().strip()

        # Só usa códigos curtos (tendem a ser siglas como CSC/OP11/RBC). Tokens longos
        # são frequentemente genéricos e geram falsos positivos.
        if len(codigo_up) < 2 or len(codigo_up) > 6:
            continue

        if codigo_up in stopwords:
            continue

        if re.search(rf"\b{re.escape(codigo_up)}\b", n_up):
            return True

    return False


def pick_first_non_our_cnpj(text: str) -> Optional[str]:
    """Pega o primeiro CNPJ no texto que NÃO é do nosso cadastro."""
    cadastro = _load_empresas_cadastro()
    if not text:
        return None

    for cnpj_digits, _start, _end, _raw in iter_cnpjs_in_text(text):
        if cnpj_digits in cadastro:
            continue
        return cnpj_digits

    return None


def infer_fornecedor_from_text(text: str, empresa_cnpj_digits: Optional[str]) -> Optional[str]:
    """Tenta inferir FORNECEDOR a partir de uma linha com CNPJ que não seja o da empresa.

    Mantém conservador: só usa quando encontra uma linha que parece ser nome de entidade.
    """
    if not text:
        return None

    cadastro = _load_empresas_cadastro()
    empresa_cnpj_digits_norm = _normalize_cnpj_to_digits(empresa_cnpj_digits or "")

    label_re = re.compile(
        r"\b(Raz[ãa]o\s+Social|Benefici[áa]rio|Cedente|Prestador(?:\s+de\s+Servi[çc]os)?)\b",
        flags=re.IGNORECASE,
    )

    noise_re = re.compile(
        r"\b(BANCO|AG[EÊ]NCIA|CONTA|LINHA\s+DIGIT[ÁA]VEL|NOSSO\s+N[ÚU]MERO|C[ÓO]DIGO\s+DE\s+BARRAS|VENCIMENTO|VALOR\s+DO\s+DOCUMENTO)\b",
        flags=re.IGNORECASE,
    )

    money_or_date_re = re.compile(
        r"(?:\b\d{2}\s*/\s*\d{2}\s*/\s*\d{4}\b|\b\d{1,3}(?:\s*\.\s*\d{3})*\s*,\s*\d{2}\b|\bR\$\b|\bREAL\b)",
        flags=re.IGNORECASE,
    )

    label_strip_re = re.compile(
        r"\b(Raz[ãa]o\s+Social|Benefici[áa]rio|Cedente|Prestador(?:\s+de\s+Servi[çc]os)?)\b\s*: ?",
        flags=re.IGNORECASE,
    )

    def clean_name(raw: str) -> str:
        s = re.sub(r"\s+", " ", (raw or "").strip())
        s = s.strip(" -–:\t")
        s = label_strip_re.sub(" ", s)
        s = re.sub(r"\s+", " ", s).strip(" -–:\t")
        return s

    lines = [ln.strip() for ln in text.splitlines() if (ln or "").strip()]

    linha_digitavel_re = re.compile(
        r"\d{5}[\.\s]\d{5}\s+\d{5}[\.\s]\d{6}\s+\d{5}[\.\s]\d{6}",
        flags=re.IGNORECASE,
    )

    best_name: Optional[str] = None
    best_cnpj: Optional[str] = None
    best_score = -10**9

    for i, ln in enumerate(lines):
        if not ln:
            continue

        # Não inferir fornecedor a partir de linha digitável/código de barras.
        if linha_digitavel_re.search(ln):
            continue

        for m in _CNPJ_ANY_RE.finditer(ln):
            digits = _normalize_cnpj_to_digits(m.group(0))
            if not digits:
                continue
            if digits in cadastro:
                continue
            if empresa_cnpj_digits_norm and digits == empresa_cnpj_digits_norm:
                continue

            name_raw = ln[: m.start()].strip(" -–:\t")
            if (not name_raw) and i > 0:
                name_raw = lines[i - 1]

            name = clean_name(name_raw)
            if len(name) < 5:
                continue
            # precisa conter letras (evita nome ser só números/linha digitável)
            if not re.search(r"[A-ZÀ-ÿ]", name, flags=re.IGNORECASE):
                continue
            if money_or_date_re.search(name):
                continue
            if is_nome_nosso(name):
                continue

            context = ((lines[i - 1] + " ") if i > 0 else "") + ln

            score = 0
            if label_re.search(context):
                score += 8
            if re.search(r"(?i)\ba\s+servi[çc]o\s+de\b", ln):
                score += 5
            if re.search(r"(?i)\bCPF/CNPJ\b", ln):
                score += 1
            if re.search(r"(?i)\bCNPJ\b", ln):
                score += 1
            if noise_re.search(ln):
                score -= 6
            if money_or_date_re.search(ln):
                score -= 3
            score += min(len(name) // 10, 3)

            if score > best_score:
                best_score = score
                best_name = name
                best_cnpj = digits

    if best_name and best_cnpj:
        return f"{best_name} - CNPJ {format_cnpj(best_cnpj)}"

    return None

