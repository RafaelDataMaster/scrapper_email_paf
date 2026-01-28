"""
Extrator de DANFE (Documento Auxiliar da Nota Fiscal Eletrônica).

Este módulo implementa a extração de dados de DANFEs em formato PDF,
seguindo o layout padrão estabelecido pela SEFAZ.

Campos extraídos:
    - chave_acesso: Chave de 44 dígitos da NF-e
    - numero_nota: Número da nota fiscal
    - serie: Série da nota fiscal
    - data_emissao: Data de emissão
    - valor_total: Valor total da nota (produtos + serviços)
    - cnpj_emitente: CNPJ do emitente
    - fornecedor_nome: Razão social do emitente
    - cnpj_destinatario: CNPJ do destinatário
    - duplicatas: Lista de parcelas (número, vencimento, valor)

Características do layout DANFE:
    - Chave de acesso em formato de código de barras 2D ou numérico
    - Dados do emitente no cabeçalho
    - Dados do destinatário em seção específica
    - Duplicatas/faturas quando há parcelamento

Example:
    >>> from extractors.danfe import DanfeExtractor
    >>> extractor = DanfeExtractor()
    >>> dados = extractor.extract(texto_pdf)
    >>> print(f"NF-e: {dados['numero_nota']} - R$ {dados['valor_total']:.2f}")
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from core.extractors import BaseExtractor, register_extractor
from extractors.utils import (
    extract_best_money_from_segment,
    normalize_digits,
    parse_br_money,
    parse_date_br,
)


def _extract_danfe_valor_total(text: str) -> float:
    """Extrai o valor total da nota fiscal do DANFE.
    
    Busca por rótulos como "VALOR TOTAL DA NOTA" e extrai o valor
    monetário mais significativo no segmento.
    
    Em DANFEs com layout tabular, os valores podem aparecer em sequência
    (0,00 0,00 ... 4.800,00), então usa heurística do maior valor.
    
    Args:
        text: Texto extraído do DANFE.
        
    Returns:
        Valor total em float ou 0.0 se não encontrado.
    """
    if not text:
        return 0.0

    # Em muitos DANFEs os campos vêm em uma "tabela" linearizada no texto,
    # onde a linha contém vários números (ex.: 0,00 0,00 ... 4.800,00).
    # Nesses casos, pegar o primeiro match falha; precisamos pegar o melhor (geralmente o último/maior).
    label_patterns = [
        r"(?i)\bVALOR\s+TOTAL\s+DA\s+NOTA\b",
        r"(?i)\bVALOR\s+TOTAL\s+(?:DOS\s+)?PRODUTOS\b",
        r"(?i)\bVALOR\s+TOTAL\s+PRODUTOS\b",
        r"(?i)\bV\.?\s*TOTAL\s+DA\s+NOTA\b",
        r"(?i)\bTOTAL\s+DA\s+NOTA\b",
    ]

    for lp in label_patterns:
        for m in re.finditer(lp, text):
            start = m.end()
            line_end = text.find("\n", start)
            if line_end == -1:
                line_end = min(len(text), start + 350)
            segment = text[start:line_end]
            best = extract_best_money_from_segment(segment)
            if best > 0:
                return best

            # Em alguns PDFs o valor pode cair na linha seguinte
            next_end = text.find("\n", line_end + 1)
            if next_end == -1:
                next_end = min(len(text), line_end + 350)
            segment2 = text[start:next_end]
            best2 = extract_best_money_from_segment(segment2)
            if best2 > 0:
                return best2

    # Fallback conservador: escolhe o maior valor monetário no documento.
    # Em DANFE, o maior valor quase sempre corresponde ao total da nota.
    best_overall = extract_best_money_from_segment(text)
    return best_overall


def _extract_chave_acesso(text: str) -> Optional[str]:
    """Extrai a chave de acesso de 44 dígitos do DANFE.
    
    A chave pode aparecer em vários formatos:
    - 44 dígitos consecutivos: 31250114169885000595550010000308381189120506
    - Espaçado em grupos de 4: 3125 0114 1698 8500 ...
    
    Args:
        text: Texto extraído do DANFE.
        
    Returns:
        Chave de acesso (44 dígitos) ou None se não encontrada.
    """
    if not text:
        return None

    # Primeiro, tenta encontrar 44 dígitos consecutivos
    # Alguns PDFs têm a chave no formato: 31250114169885000595550010000308381189120506
    digits = normalize_digits(text)
    m = re.search(r"(\d{44})", digits)
    if m:
        return m.group(1)

    # Tenta encontrar no formato espaçado: 3125 0114 1698 8500 ...
    # Procura padrões de 4 dígitos espaçados que somem 44
    spaced_pattern = re.compile(r"(\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4}\s+\d{4})")
    m = spaced_pattern.search(text)
    if m:
        chave = normalize_digits(m.group(1))
        if len(chave) == 44:
            return chave

    return None


def _extract_data_emissao(text: str) -> Optional[str]:
    """Extrai a data de emissão do DANFE.
    
    Usa múltiplos padrões para cobrir diferentes layouts:
    - "DATA DA EMISSÃO" seguido de data
    - "Emissão:" seguido de data
    - CNPJ seguido de data (layout tabular)
    
    Args:
        text: Texto extraído do DANFE.
        
    Returns:
        Data no formato ISO (YYYY-MM-DD) ou None.
    """
    if not text:
        return None

    # Regex para data brasileira: aceita tanto barra (/) quanto hífen (-)
    # Formatos: dd/mm/yyyy, dd-mm-yyyy, dd/mm/yy, dd-mm-yy
    DATE_PATTERN = r"(\d{2}[/-]\d{2}[/-]\d{2,4})"

    # Padrão 1: "DATA DA EMISSÃO" ou "DATA DE EMISSÃO" seguido de data
    # Considerando caracteres problemáticos (□ = caractere não renderizado)
    patterns = [
        # Padrão mais específico: DATA DA EMISSÃO no mesmo contexto que nome/CNPJ
        # Ex: "NOME RAZÃO SOCIAL CNPJ/CPF DATA DA EMISSÃO\nXXX 00.000.000/0000-00 24/03/2023"
        r"(?i)DATA\s*(?:DA|DE)?\s*EMISS[ÃA□]O[^\d]{0,30}" + DATE_PATTERN,

        # Padrão com caractere especial (□)
        r"(?i)DATA\s*(?:DA|DE)?\s*EMISS.O[^\d]{0,30}" + DATE_PATTERN,

        # Padrão em contexto de linha do destinatário
        r"(?i)CNPJ/CPF\s+DATA\s*(?:DA|DE)?\s*EMISS[ÃA□O]O?[^\d]*" + DATE_PATTERN,

        # Padrão genérico - EMISSÃO seguido de data na mesma linha ou próxima
        # Ex: "EMISSÃO: 24-02-2025" ou "EMISSÃO: 24/02/2025"
        r"(?i)\bEMISS[ÃA□O]O?\s*[:\-]?\s*" + DATE_PATTERN,

        # Padrão para formato "- EMISSÃO: dd-mm-yyyy -" comum em alguns DANFEs
        r"(?i)-\s*EMISS[ÃA]O\s*[:\-]?\s*" + DATE_PATTERN,

        # Padrão para "Emissão:" no início de linha ou após espaço
        r"(?i)(?:^|\s)Emiss[ãa]o\s*[:\-]?\s*" + DATE_PATTERN,
    ]

    for pat in patterns:
        m = re.search(pat, text)
        if m:
            date_str = m.group(1)
            parsed = parse_date_br(date_str)
            if parsed:
                return parsed

    # Fallback: Procura na estrutura típica do DANFE onde a data aparece após CNPJ
    # em formato de tabela linearizada
    # Ex: "... 38.323.230/0001-64 10/03/2025\n..."
    # Procura linha que contenha CNPJ seguido de data (aceita / ou -)
    cnpj_date_pattern = re.compile(
        r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\s+" + DATE_PATTERN
    )
    matches = cnpj_date_pattern.findall(text)

    # Retorna a primeira data encontrada (geralmente é a data de emissão)
    for date_str in matches:
        parsed = parse_date_br(date_str)
        if parsed:
            return parsed

    return None


def _extract_duplicatas(text: str) -> List[Tuple[str, str, float]]:
    """Extrai faturas/duplicatas do DANFE.
    
    Duplicatas são parcelas de pagamento com número, vencimento e valor.
    Padrão típico: "1/3 23/04/23 2.859,34"
    
    Args:
        text: Texto extraído do DANFE.
        
    Returns:
        Lista de tuplas (numero_parcela, vencimento_iso, valor).
        Ex: [("1/3", "2023-04-23", 2859.34), ("2/3", "2023-05-23", 2679.33)]
    """
    duplicatas = []
    if not text:
        return duplicatas

    # Padrão típico: "1/3 23/04/23 2.859,34" ou "1/6 19/01/25 626,65"
    # Número da parcela, data (dd/mm/aa ou dd/mm/aaaa), valor
    dup_pattern = re.compile(
        r"(\d{1,2}/\d{1,2})\s+(\d{2}/\d{2}/\d{2,4})\s+([\d\.]+,\d{2})"
    )

    for m in dup_pattern.finditer(text):
        parcela = m.group(1)
        data_str = m.group(2)
        valor_str = m.group(3)

        # Converte data
        data_iso = parse_date_br(data_str)
        valor = parse_br_money(valor_str)

        if data_iso and valor > 0:
            duplicatas.append((parcela, data_iso, valor))

    return duplicatas


def _extract_primeiro_vencimento(text: str) -> Optional[str]:
    """Extrai o vencimento da primeira parcela das duplicatas.
    
    Ordena as duplicatas por número da parcela e retorna o vencimento
    da primeira (ex: "1/3" vem antes de "2/3").
    
    Args:
        text: Texto extraído do DANFE.
        
    Returns:
        Data de vencimento no formato ISO ou None.
    """
    duplicatas = _extract_duplicatas(text)
    if duplicatas:
        # Ordena por número da parcela para garantir pegar a primeira
        duplicatas_sorted = sorted(duplicatas, key=lambda x: x[0])
        return duplicatas_sorted[0][1]
    return None


@register_extractor
class DanfeExtractor(BaseExtractor):
    """Extrator para DANFE (NF-e modelo 55)."""

    @classmethod
    def can_handle(cls, text: str) -> bool:
        if not text:
            return False

        t = text.upper()

        # Identificadores fortes
        if "DANFE" in t:
            return True

        if "DOCUMENTO AUXILIAR" in t and "NOTA FISCAL" in t and "ELETR" in t:
            return True

        # Chave de acesso (44 dígitos), muitas vezes espaçada
        digits = normalize_digits(text)
        if re.search(r"\b\d{44}\b", digits):
            return True

        # Algumas DANFEs vêm com 'NF-E' / 'NFE' + 'CHAVE DE ACESSO'
        if ("CHAVE DE ACESSO" in t) and ("NF-E" in t or "NFE" in t):
            return True

        return False

    def extract(self, text: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {"tipo_documento": "DANFE"}

        # Chave de acesso (44 dígitos)
        chave = _extract_chave_acesso(text)
        if chave:
            data["chave_acesso"] = chave

        # Número da NF (várias formas). Importante: em DANFE o número pode vir como
        # 'NF-E Nº000.084.653' (com pontos). Por isso capturamos também '.' e limpamos.
        # Também pode vir como 'N. 000003595' (com ponto e espaço).
        # Formato adicional: 'Nº. 000.006.941' (com ponto após º e pontos como separadores)
        patterns_num = [
            # Formato com ponto após Nº: "Nº. 000.006.941"
            r"(?i)\bN[º°o]\.?\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)*)",
            r"(?i)\bNF-?E\b[^\n]{0,120}?\bN[º°o\.]?\s*[:\-]?\s*([0-9\.]{1,20})",
            r"(?i)\bN[º°o\.]?\s*[:\-]?\s*([0-9\.]{1,20})\b\s*(?:S[ÉE]RIE|SERIE)\b",
            r"(?i)\bN[º°o\.]?\s*[:\-]?\s*([0-9\.]{1,20})\b",
        ]
        for pat in patterns_num:
            m = re.search(pat, text)
            if not m:
                continue
            numero = re.sub(r"\D", "", m.group(1))
            if numero:
                # Normaliza removendo zeros à esquerda só se ficar algo; mantém '0' se tudo zero
                data["numero_nota"] = numero.lstrip('0') or '0'
                break

        # Série
        m_serie = re.search(r"(?i)\bS[ÉE]RIE\s*[:\-]?\s*(\d{1,4})\b", text)
        if m_serie:
            data["serie_nf"] = m_serie.group(1)

        # Data de emissão - usando função melhorada
        data_emissao = _extract_data_emissao(text)
        if data_emissao:
            data["data_emissao"] = data_emissao

        # Valor total
        data["valor_total"] = _extract_danfe_valor_total(text)

        # CNPJ emitente (formato com pontuação)
        m_cnpj = re.search(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b", text)
        if m_cnpj:
            data["cnpj_emitente"] = m_cnpj.group(0)

        # Fornecedor/emitente (razão social)
        # 1) 'Recebemos de X os produtos...'
        m_recv = re.search(r"(?is)\bRECEBEMOS\s+DE\s+(.+?)\s+OS\s+PRODUTOS", text)
        if m_recv:
            name = re.sub(r"\s+", " ", m_recv.group(1)).strip()
            data["fornecedor_nome"] = name

        # 2) 'DANFE X DOCUMENTO AUXILIAR...'
        if not data.get("fornecedor_nome"):
            m_danfe = re.search(r"(?is)\bDANFE\b\s+(.+?)\s+DOCUMENTO\s+AUXILIAR", text)
            if m_danfe:
                name = re.sub(r"\s+", " ", m_danfe.group(1)).strip()
                # Evita capturar lixo muito longo
                if 4 <= len(name) <= 120:
                    data["fornecedor_nome"] = name

        # Extrai duplicatas/faturas
        duplicatas = _extract_duplicatas(text)
        if duplicatas:
            # Primeiro vencimento (da primeira parcela)
            primeiro_venc = _extract_primeiro_vencimento(text)
            if primeiro_venc:
                data["vencimento"] = primeiro_venc

            # Número da fatura (formato: "numero_nota/parcela")
            # Ex: "114906-1/3" ou apenas usa a referência da primeira
            if data.get("numero_nota") and duplicatas:
                data["numero_fatura"] = f"{data['numero_nota']}-{duplicatas[0][0]}"

            # Armazena todas as duplicatas para referência
            data["duplicatas"] = [
                {"parcela": d[0], "vencimento": d[1], "valor": d[2]}
                for d in duplicatas
            ]

        # Extração adicional: Número do pedido (comum em DANFEs)
        pedido_patterns = [
            r"(?i)\bPEDIDO\s*(?:DE\s*COMPRAS?)?\s*[:\-]?\s*(\d+)",
            r"(?i)\bNR\.?\s*PEDIDO\s*[:\-]?\s*(\d+)",
            r"(?i)\bORDEM\s*(?:DE\s*COMPRA)?\s*[:\-]?\s*(\d+)",
        ]
        for pat in pedido_patterns:
            m = re.search(pat, text)
            if m:
                data["numero_pedido"] = m.group(1)
                break

        # Extração: Natureza da operação
        m_nat = re.search(r"(?i)\bNATUREZA\s+(?:DA\s+)?OPERA[ÇC][ÃA]O\s*[:\-]?\s*([^\n]+)", text)
        if m_nat:
            natureza = re.sub(r"\s+", " ", m_nat.group(1)).strip()
            # Remove padrões que não são a natureza (como "DADOS DA NF-e")
            if not re.search(r"(?i)DADOS|NF-?E|INSCRI", natureza):
                data["natureza_operacao"] = natureza[:100]  # Limita tamanho

        return data
