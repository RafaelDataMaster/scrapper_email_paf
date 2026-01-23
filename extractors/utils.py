"""
Módulo de utilidades compartilhadas para extratores.

Contém funções de parsing e normalização usadas por múltiplos extratores:
- Parsing de valores monetários brasileiros (R$ 1.234,56)
- Parsing de datas brasileiras (dd/mm/yyyy, dd-mm-yyyy)
- Extração e formatação de CNPJ/CPF
- Normalização de texto (acentos, espaços, entidades, caracteres OCR)

Princípio DRY: Estas funções eram duplicadas em boleto.py, danfe.py,
nfse_generic.py e outros.py. Centralizá-las aqui evita inconsistências
e facilita manutenção.
"""

import re
import unicodedata
from datetime import datetime
from typing import Optional

# =============================================================================
# REGEX COMPILADOS (evita recompilação a cada chamada)
# =============================================================================

# Valor monetário brasileiro: 1.234,56 ou 1234,56
BR_MONEY_RE = re.compile(r"\b(\d{1,3}(?:\.\d{3})*,\d{2})\b")

# CNPJ formatado: 00.000.000/0000-00
CNPJ_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")

# CNPJ sem formatação (14 dígitos)
CNPJ_DIGITS_RE = re.compile(
    r"(?<!\d)(\d{2})\D?(\d{3})\D?(\d{3})\D?(\d{4})\D?(\d{2})(?!\d)"
)

# CPF formatado: 000.000.000-00
CPF_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")

# Data brasileira: dd/mm/yyyy ou dd-mm-yyyy ou dd/mm/yy
BR_DATE_RE = re.compile(r"\b(\d{2})[/\-](\d{2})[/\-](\d{2,4})\b")


# =============================================================================
# PARSING DE VALORES MONETÁRIOS
# =============================================================================


def parse_br_money(value: str) -> float:
    """
    Converte valor monetário brasileiro para float.

    Formatos suportados:
    - "1.234,56" -> 1234.56
    - "1234,56" -> 1234.56
    - "1.234.567,89" -> 1234567.89

    Args:
        value: String com valor monetário no formato brasileiro

    Returns:
        float: Valor numérico ou 0.0 se inválido

    Examples:
        >>> parse_br_money("1.234,56")
        1234.56
        >>> parse_br_money("352,08")
        352.08
        >>> parse_br_money("")
        0.0
    """
    if not value:
        return 0.0
    try:
        # Remove pontos de milhar e troca vírgula decimal por ponto
        cleaned = value.replace(".", "").replace(",", ".")
        return float(cleaned)
    except (ValueError, AttributeError):
        return 0.0


def extract_br_money_values(text: str) -> list[float]:
    """
    Extrai todos os valores monetários de um texto.

    Args:
        text: Texto contendo valores monetários

    Returns:
        Lista de floats com valores encontrados (> 0)

    Example:
        >>> extract_br_money_values("Total: R$ 1.234,56 + R$ 100,00")
        [1234.56, 100.0]
    """
    if not text:
        return []

    values = []
    for match in BR_MONEY_RE.findall(text):
        val = parse_br_money(match.replace(" ", ""))
        if val > 0:
            values.append(val)
    return values


def extract_best_money_from_segment(segment: str) -> float:
    """
    Extrai o maior valor monetário de um segmento de texto.

    Útil quando uma linha contém múltiplos valores e queremos o principal
    (geralmente o maior, que representa o total).

    Args:
        segment: Trecho de texto a analisar

    Returns:
        Maior valor encontrado ou 0.0

    Example:
        >>> extract_best_money_from_segment("0,00 0,00 4.800,00")
        4800.0
    """
    values = extract_br_money_values(segment)
    return max(values) if values else 0.0


# =============================================================================
# PARSING DE DATAS
# =============================================================================


def parse_date_br(value: str) -> Optional[str]:
    """
    Converte data brasileira para formato ISO (YYYY-MM-DD).

    Formatos suportados:
    - dd/mm/yyyy (ex: 24/03/2025)
    - dd-mm-yyyy (ex: 24-03-2025)
    - dd/mm/yy (ex: 24/03/25 -> 2025-03-24)

    Args:
        value: String com data no formato brasileiro

    Returns:
        Data no formato ISO ou None se inválida

    Examples:
        >>> parse_date_br("24/03/2025")
        '2025-03-24'
        >>> parse_date_br("24-03-25")
        '2025-03-24'
        >>> parse_date_br("invalid")
        None
    """
    if not value:
        return None

    # Remove espaços extras que podem aparecer em PDFs mal extraídos
    value = re.sub(r"\s+", "", value.strip())

    # Normaliza separadores: hífen -> barra para parsing uniforme
    normalized = value.replace("-", "/")

    # Tenta diferentes formatos
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            dt = datetime.strptime(normalized, fmt)
            # Para anos de 2 dígitos, ajusta século se necessário
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def extract_first_date_br(text: str) -> Optional[str]:
    """
    Extrai a primeira data brasileira encontrada no texto.

    Args:
        text: Texto a ser analisado

    Returns:
        Data no formato ISO ou None

    Example:
        >>> extract_first_date_br("Emitido em 24/03/2025 com vencimento 24/04/2025")
        '2025-03-24'
    """
    if not text:
        return None

    match = BR_DATE_RE.search(text)
    if match:
        return parse_date_br(match.group(0))
    return None


# =============================================================================
# EXTRAÇÃO DE CNPJ/CPF
# =============================================================================


def extract_cnpj(text: str) -> Optional[str]:
    """
    Extrai o primeiro CNPJ formatado do texto.

    Args:
        text: Texto contendo CNPJ

    Returns:
        CNPJ formatado (00.000.000/0000-00) ou None

    Example:
        >>> extract_cnpj("Empresa XYZ - CNPJ: 12.345.678/0001-90")
        '12.345.678/0001-90'
    """
    if not text:
        return None

    match = CNPJ_RE.search(text)
    return match.group(0) if match else None


def extract_cnpj_flexible(text: str) -> Optional[str]:
    """
    Extrai CNPJ mesmo sem formatação padrão e retorna formatado.

    Útil para PDFs onde a formatação foi perdida na extração.

    Args:
        text: Texto contendo CNPJ (formatado ou não)

    Returns:
        CNPJ formatado (00.000.000/0000-00) ou None

    Example:
        >>> extract_cnpj_flexible("CNPJ 12345678000190")
        '12.345.678/0001-90'
    """
    if not text:
        return None

    match = CNPJ_DIGITS_RE.search(text)
    if match:
        return f"{match.group(1)}.{match.group(2)}.{match.group(3)}/{match.group(4)}-{match.group(5)}"
    return None


def extract_cpf(text: str) -> Optional[str]:
    """
    Extrai o primeiro CPF formatado do texto.

    Args:
        text: Texto contendo CPF

    Returns:
        CPF formatado (000.000.000-00) ou None
    """
    if not text:
        return None

    match = CPF_RE.search(text)
    return match.group(0) if match else None


def format_cnpj(digits: str) -> str:
    """
    Formata 14 dígitos como CNPJ.

    Args:
        digits: String com 14 dígitos

    Returns:
        CNPJ formatado ou string original se inválido

    Example:
        >>> format_cnpj("12345678000190")
        '12.345.678/0001-90'
    """
    digits = re.sub(r"\D", "", digits or "")
    if len(digits) != 14:
        return digits
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


# =============================================================================
# NORMALIZAÇÃO DE TEXTO
# =============================================================================


def strip_accents(value: str) -> str:
    """
    Remove acentos de uma string.

    Útil para comparações case-insensitive e matching de palavras-chave.

    Args:
        value: String com possíveis acentos

    Returns:
        String sem acentos

    Example:
        >>> strip_accents("Código Eletrônico")
        'Codigo Eletronico'
    """
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_whitespace(text: str) -> str:
    """
    Normaliza espaços em branco (tabs, múltiplos espaços, nbsp).

    Args:
        text: Texto a normalizar

    Returns:
        Texto com espaços normalizados

    Example:
        >>> normalize_whitespace("Nome    da   Empresa")
        'Nome da Empresa'
    """
    if not text:
        return ""
    # Substitui caracteres especiais de espaço
    text = text.replace("\u00a0", " ")  # nbsp
    text = text.replace("\t", " ")
    # Colapsa múltiplos espaços
    return re.sub(r" +", " ", text).strip()


def normalize_text_for_extraction(text: str) -> str:
    """
    Normaliza texto para extração de dados.

    Trata problemas comuns em PDFs:
    - Hífens especiais (soft hyphen, en-dash, em-dash)
    - Espaços não-breaking
    - Múltiplos espaços/tabs
    - Caracteres OCR problemáticos (Ê, □, etc.)

    Args:
        text: Texto bruto extraído de PDF

    Returns:
        Texto normalizado
    """
    if not text:
        return ""

    # Normaliza hífens especiais
    text = text.replace("\u00ad", "-")  # soft hyphen
    text = text.replace("\u2013", "-")  # en-dash
    text = text.replace("\u2014", "-")  # em-dash

    # Normaliza caracteres OCR problemáticos
    # Caractere 'Ê' (circumflex accent) que aparece no lugar de espaços em alguns PDFs
    text = text.replace("Ê", " ")
    text = text.replace("ê", " ")

    # Outros caracteres problemáticos que podem aparecer em OCR
    problematic_chars = ["□", "▢", "■", "▭", "▯", "�"]
    for char in problematic_chars:
        text = text.replace(char, " ")

    # Normaliza espaços
    text = text.replace("\u00a0", " ")  # nbsp
    text = re.sub(r"[ \t]+", " ", text)

    return text


def normalize_entity_name(raw: str) -> str:
    """
    Normaliza nome de entidade (empresa/pessoa).

    Remove:
    - CNPJ/CPF embutidos
    - Números de documento
    - Espaços extras
    - Caracteres especiais de pontuação
    - Caracteres OCR problemáticos

    Args:
        raw: Nome bruto extraído

    Returns:
        Nome limpo e normalizado

    Example:
        >>> normalize_entity_name("EMPRESA XYZ LTDA   12.345.678/0001-90  ")
        'EMPRESA XYZ LTDA'
    """
    name = (raw or "").strip()

    # Normaliza espaços
    name = re.sub(r"\s+", " ", name)

    # Remove CNPJ
    name = re.sub(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", " ", name)

    # Remove CPF
    name = re.sub(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", " ", name)

    # Remove números de documento (ex: 2025.122, 1234/5678)
    name = re.sub(r"\b\d+[\./]\d+\b", " ", name)

    # Remove sequências numéricas longas (4+ dígitos)
    name = re.sub(r"\b\d{4,}\b", " ", name)

    # Remove caracteres OCR problemáticos (Ê, □, etc.)
    name = name.replace("Ê", " ")
    name = name.replace("ê", " ")
    problematic_chars = ["□", "▢", "■", "▭", "▯", "�"]
    for char in problematic_chars:
        name = name.replace(char, " ")

    # Limpa espaços e pontuação residual
    name = re.sub(r"\s+", " ", name).strip(" -:;")

    return name.strip()


def normalize_digits(value: str) -> str:
    """
    Remove todos os caracteres não-numéricos.

    Útil para comparar CNPJs, CPFs, chaves de acesso.

    Args:
        value: String com possíveis não-dígitos

    Returns:
        Apenas os dígitos

    Example:
        >>> normalize_digits("12.345.678/0001-90")
        '12345678000190'
    """
    return re.sub(r"\D", "", value or "")


# =============================================================================
# VALIDAÇÕES
# =============================================================================


def is_valid_cnpj_format(value: str) -> bool:
    """
    Verifica se string está no formato de CNPJ (não valida dígitos verificadores).

    Args:
        value: String a verificar

    Returns:
        True se formato válido
    """
    if not value:
        return False
    return bool(CNPJ_RE.fullmatch(value.strip()))


def is_valid_cpf_format(value: str) -> bool:
    """
    Verifica se string está no formato de CPF (não valida dígitos verificadores).

    Args:
        value: String a verificar

    Returns:
        True se formato válido
    """
    if not value:
        return False
    return bool(CPF_RE.fullmatch(value.strip()))
