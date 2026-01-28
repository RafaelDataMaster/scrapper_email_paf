"""
Módulo de identificação de empresas do cadastro interno.

Este módulo implementa a lógica para detectar qual empresa do cadastro
está mencionada em um documento (PDF/XML), utilizando múltiplas estratégias:

1. **Match por CNPJ** (preferencial): Busca CNPJs no texto e verifica se
   pertencem ao cadastro de empresas.
2. **Match por Nome/Código**: Fallback usando o código da empresa (ex: CSC, RBC)
   quando CNPJ não é encontrado.
3. **Match por Domínio**: Último recurso, verifica domínios de email no texto.

Funções principais:
    - find_empresa_no_texto: Detecta empresa do cadastro no documento
    - is_cnpj_nosso: Verifica se um CNPJ pertence ao cadastro
    - is_nome_nosso: Verifica se um nome corresponde a uma empresa cadastrada
    - pick_first_non_our_cnpj: Retorna o primeiro CNPJ que NÃO é do cadastro

Example:
    >>> from core.empresa_matcher import find_empresa_no_texto
    >>> match = find_empresa_no_texto(texto_documento)
    >>> if match:
    ...     print(f"Empresa: {match.codigo} - {match.razao_social}")
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple


# Match CNPJ even when PDF extraction inserts spaces between separators.
# Examples: "12.345.678/0001-90", "12 . 345 . 678 / 0001 - 90", "12345678000190"
_CNPJ_ANY_RE = re.compile(
    r"(?<!\d)(?:"
    r"\d{2}\s*\.\s*\d{3}\s*\.\s*\d{3}\s*/\s*\d{4}\s*-\s*\d{2}"
    r"|\d{14}"
    r")(?!\d)",
    flags=re.MULTILINE,
)


_EMAIL_DOMAIN_RE = re.compile(
    r"\b[a-z0-9._%+\-]+@([a-z0-9\-]+(?:\.[a-z0-9\-]+)+)\b",
    flags=re.IGNORECASE,
)

# Captura domínios comuns quando aparecem sem @ (ex.: "soumaster.com.br")
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9\-]+\.)+(?:[a-z]{2,})(?:\.[a-z]{2,})?\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class EmpresaMatch:
    cnpj_digits: str
    razao_social: str
    codigo: str
    method: str
    score: int


def normalize_cnpj_to_digits(value: str) -> Optional[str]:
    """Normaliza um CNPJ para apenas dígitos (14 caracteres).
    
    Args:
        value: CNPJ em qualquer formato (com ou sem pontuação).
        
    Returns:
        String com 14 dígitos ou None se inválido.
        
    Example:
        >>> normalize_cnpj_to_digits("12.345.678/0001-90")
        '12345678000190'
    """
    if not value:
        return None
    digits = re.sub(r"\D+", "", value)
    if len(digits) != 14:
        return None
    return digits


def format_cnpj(digits: str) -> str:
    """Formata dígitos de CNPJ para o padrão XX.XXX.XXX/XXXX-XX.
    
    Args:
        digits: String com 14 dígitos do CNPJ.
        
    Returns:
        CNPJ formatado ou string vazia se inválido.
        
    Example:
        >>> format_cnpj("12345678000190")
        '12.345.678/0001-90'
    """
    d = normalize_cnpj_to_digits(digits)
    if not d:
        return ""
    return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"


def empresa_codigo_from_razao(razao_social: str) -> str:
    """Extrai o código/sigla da empresa a partir da razão social.
    
    O código é o primeiro token alfanumérico da razão social,
    geralmente uma sigla como CSC, MASTER, OP11, RBC.
    
    Args:
        razao_social: Razão social da empresa.
        
    Returns:
        Código da empresa em maiúsculas ou string vazia.
        
    Example:
        >>> empresa_codigo_from_razao("CSC GESTAO INTEGRADA S/A")
        'CSC'
    """
    if not razao_social:
        return ""
    # pega o primeiro token alfanumérico (ex: CSC, MASTER, OP11, RBC)
    cleaned = re.sub(r"\([^)]*\)", " ", razao_social)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    m = re.search(r"\b([A-Z0-9]{2,15})\b", cleaned.upper())
    return m.group(1) if m else cleaned[:20].upper()


def _load_empresas_cadastro() -> Dict[str, Dict[str, str]]:
    """Carrega o cadastro de empresas normalizado por CNPJ.
    
    Realiza import local de config.empresas para evitar carga
    em caminhos que não usam a feature de detecção de empresa.
    
    Returns:
        Dicionário onde chave é CNPJ (14 dígitos) e valor é payload
        com 'razao_social' e outros dados da empresa.
    """
    # Import local para não forçar carga em caminhos que não usam a feature
    try:
        from config.empresas import EMPRESAS_CADASTRO  # type: ignore

        # Normaliza chaves para dígitos
        normalized: Dict[str, Dict[str, str]] = {}
        for cnpj, payload in (EMPRESAS_CADASTRO or {}).items():
            cnpj_digits = normalize_cnpj_to_digits(str(cnpj))
            if not cnpj_digits:
                continue
            normalized[cnpj_digits] = payload
        return normalized
    except Exception:
        return {}


def iter_cnpjs_in_text(text: str) -> Iterable[Tuple[str, int, int, str]]:
    """Itera sobre todos os CNPJs encontrados no texto.
    
    Detecta CNPJs em vários formatos:
    - Formatado: 12.345.678/0001-90
    - Com espaços: 12 . 345 . 678 / 0001 - 90
    - Apenas dígitos: 12345678000190
    
    Args:
        text: Texto onde buscar CNPJs.
        
    Yields:
        Tupla (cnpj_digits, start, end, raw_match) onde:
        - cnpj_digits: CNPJ normalizado (14 dígitos)
        - start: Posição inicial no texto
        - end: Posição final no texto
        - raw_match: Texto original encontrado
        
    Example:
        >>> for cnpj, start, end, raw in iter_cnpjs_in_text(texto):
        ...     print(f"CNPJ {cnpj} encontrado na posição {start}")
    """
    if not text:
        return []

    for m in _CNPJ_ANY_RE.finditer(text):
        raw = m.group(0)
        digits = normalize_cnpj_to_digits(raw)
        if not digits:
            continue
        yield (digits, m.start(), m.end(), raw)


def iter_domains_in_text(text: str) -> Iterable[str]:
    """Itera sobre domínios encontrados no texto.
    
    Detecta domínios a partir de:
    - Endereços de e-mail (usuario@dominio.com)
    - Domínios soltos (soumaster.com.br)
    
    Args:
        text: Texto onde buscar domínios.
        
    Yields:
        Domínios encontrados em minúsculas (sem duplicatas).
        
    Example:
        >>> list(iter_domains_in_text("Contato: nf@soumaster.com.br"))
        ['soumaster.com.br']
    """
    if not text:
        return []

    seen = set()

    for m in _EMAIL_DOMAIN_RE.finditer(text):
        dom = (m.group(1) or "").strip().lower()
        if dom and dom not in seen:
            seen.add(dom)
            yield dom

    for m in _DOMAIN_RE.finditer(text):
        dom = (m.group(0) or "").strip().lower()
        # Evita capturar coisas tipo "r$" etc; já filtrado por regex.
        if dom and dom not in seen:
            seen.add(dom)
            yield dom


def find_empresa_no_texto(text: str) -> Optional[EmpresaMatch]:
    """Detecta qual empresa do cadastro está mencionada no documento.
    
    Aplica estratégias em ordem de prioridade:
    1. Match por CNPJ (score base: 10)
    2. Match por nome/código (score base: 5)
    3. Match por domínio de e-mail (score base: 7)
    
    O score é incrementado por contexto (ex: "PAGADOR", "TOMADOR").
    
    Args:
        text: Texto do documento (PDF extraído ou XML).
        
    Returns:
        EmpresaMatch com dados da empresa encontrada ou None.
        
    Example:
        >>> match = find_empresa_no_texto(texto_boleto)
        >>> if match:
        ...     print(f"{match.codigo}: {match.razao_social} (via {match.method})")
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
        codigo = empresa_codigo_from_razao(razao)

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
        codigo = empresa_codigo_from_razao(razao)
        if codigo and re.search(rf"\b{re.escape(codigo)}\b", upper):
            return EmpresaMatch(
                cnpj_digits=cnpj_digits,
                razao_social=razao,
                codigo=codigo,
                method="nome",
                score=5,
            )

    # 3) Fallback por domínio/e-mail: útil quando o documento não traz nosso CNPJ,
    # mas traz e-mail/dominio corporativo (ex.: fatura Locaweb com "soumaster.com.br").
    domains = list(iter_domains_in_text(text))
    if domains:
        best_domain: Optional[EmpresaMatch] = None
        domains_up = [d.upper() for d in domains]

        for cnpj_digits, payload in cadastro.items():
            razao = (payload.get("razao_social") or "").strip()
            if not razao:
                continue
            codigo = empresa_codigo_from_razao(razao)
            codigo_up = (codigo or "").upper().strip()
            if not codigo_up:
                continue

            # Conservador: só usa códigos curtos/distintivos (mesma regra do is_nome_nosso)
            if len(codigo_up) < 2 or len(codigo_up) > 10:
                continue

            score = 0
            for dom_up in domains_up:
                # Extrai a parte principal do domínio (ex.: "soumaster" de "soumaster.com.br")
                dom_main = dom_up.split(".")[0] if "." in dom_up else dom_up

                # Exige match exato do código com o início do domínio principal,
                # ou que o código seja palavra isolada (evita "MASTER" em "SOUMASTER")
                is_prefix_match = dom_main.startswith(codigo_up)
                is_word_boundary = bool(re.search(rf"(?<![A-Z0-9]){re.escape(codigo_up)}(?![A-Z0-9])", dom_up))

                if is_prefix_match or is_word_boundary:
                    # pontua por match no domínio; quanto mais "limpo" o match, maior o score
                    score = max(score, 7 + min(3, len(codigo_up)))

            if score <= 0:
                continue

            cand = EmpresaMatch(
                cnpj_digits=cnpj_digits,
                razao_social=razao,
                codigo=codigo_up,
                method="domain",
                score=score,
            )
            if best_domain is None or cand.score > best_domain.score:
                best_domain = cand

        if best_domain:
            return best_domain

    return None


def is_cnpj_nosso(cnpj_value: Optional[str]) -> bool:
    """Verifica se um CNPJ pertence ao cadastro de empresas.
    
    Args:
        cnpj_value: CNPJ em qualquer formato (com ou sem pontuação).
        
    Returns:
        True se o CNPJ está no cadastro, False caso contrário.
        
    Example:
        >>> is_cnpj_nosso("38.323.227/0001-40")  # CSC
        True
        >>> is_cnpj_nosso("00.000.000/0000-00")  # Desconhecido
        False
    """
    if not cnpj_value:
        return False
    cadastro = _load_empresas_cadastro()
    digits = normalize_cnpj_to_digits(cnpj_value)
    return bool(digits and digits in cadastro)


def is_nome_nosso(nome: Optional[str]) -> bool:
    """Verifica se um nome corresponde a uma empresa do cadastro.
    
    Usa heurística de match por código/sigla (ex: CSC, RBC, OP11).
    Ignora tokens genéricos como SERVICOS, CONSULTORIA, LTDA.
    
    Args:
        nome: Nome ou razão social a verificar.
        
    Returns:
        True se o nome contém um código de empresa cadastrada.
        
    Example:
        >>> is_nome_nosso("CSC GESTAO INTEGRADA S/A")
        True
        >>> is_nome_nosso("EMPRESA DESCONHECIDA LTDA")
        False
    """
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
        codigo = empresa_codigo_from_razao(razao)
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
    """Retorna o primeiro CNPJ no texto que NÃO pertence ao cadastro.
    
    Útil para identificar o CNPJ do fornecedor/beneficiário em documentos
    onde o CNPJ da empresa (pagador) também aparece.
    
    Args:
        text: Texto do documento.
        
    Returns:
        CNPJ em formato de 14 dígitos ou None se não encontrado.
        
    Example:
        >>> # Texto com CNPJ da CSC e do fornecedor
        >>> pick_first_non_our_cnpj(texto_boleto)
        '12345678000190'  # CNPJ do fornecedor
    """
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
    empresa_cnpj_digits_norm = normalize_cnpj_to_digits(empresa_cnpj_digits or "")

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
            digits = normalize_cnpj_to_digits(m.group(0))
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

