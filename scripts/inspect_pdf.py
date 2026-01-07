"""
Inspeção rápida de PDFs para debug.

Script simples e direto para debugar extração de campos de PDFs.
Mais prático que debug_pdf.py - mostra os campos extraídos de forma clara.

Uso:
    # Passa só o nome do arquivo - busca em failed_cases_pdf/ e temp_email/
    python scripts/inspect_pdf.py exemplo.pdf

    # Passa caminho completo
    python scripts/inspect_pdf.py failed_cases_pdf/pasta/exemplo.pdf

    # Com campos específicos
    python scripts/inspect_pdf.py exemplo.pdf --fields fornecedor valor vencimento

    # Mostra texto bruto completo
    python scripts/inspect_pdf.py exemplo.pdf --raw

Dica: Se passar só o nome do arquivo, ele busca recursivamente em:
      - failed_cases_pdf/ (modo legado)
      - temp_email/ (modo novo/batch)
"""
import sys
from pathlib import Path
from typing import List, Optional

from _init_env import setup_project_path

PROJECT_ROOT = setup_project_path()

from config.settings import DIR_DEBUG_INPUT, DIR_TEMP
from core.processor import BaseInvoiceProcessor

# Pastas onde buscar PDFs (ordem de prioridade)
SEARCH_DIRS = [
    DIR_DEBUG_INPUT,  # failed_cases_pdf
    DIR_TEMP,         # temp_email
]

# Campos comuns a todos os tipos de documento
COMMON_FIELDS = [
    'doc_type',
    'arquivo_origem',
    'fornecedor_nome',
    'empresa',
    'data_emissao',
    'vencimento',
    'data_processamento',
]

# Campos específicos por tipo
DANFE_FIELDS = [
    'numero_nota',
    'serie_nf',
    'valor_total',
    'cnpj_emitente',
    'numero_pedido',
    'numero_fatura',
    'chave_acesso',
    'forma_pagamento',
]

BOLETO_FIELDS = [
    'valor_documento',
    'cnpj_beneficiario',
    'linha_digitavel',
    'nosso_numero',
    'numero_documento',
    'referencia_nfse',
    'banco_nome',
    'agencia',
    'conta_corrente',
]

NFSE_FIELDS = [
    'numero_nota',
    'valor_total',
    'cnpj_prestador',
    'numero_pedido',
    'forma_pagamento',
    'valor_ir',
    'valor_inss',
    'valor_csll',
    'valor_iss',
]

OUTROS_FIELDS = [
    'numero_documento',
    'numero_nota',
    'valor_total',
    'cnpj_fornecedor',
    'subtipo',
]


def find_pdf(filename: str) -> Optional[Path]:
    """
    Busca um PDF pelo nome nas pastas padrão.

    Se filename já é um path válido, retorna direto.
    Se não, busca recursivamente em failed_cases_pdf/ e temp_email/.

    Args:
        filename: Nome do arquivo ou caminho completo

    Returns:
        Path do arquivo encontrado ou None
    """
    # Se já é um path válido, usa direto
    path = Path(filename)
    if path.exists():
        return path

    # Se tem separador de diretório, tenta relativo ao projeto
    if '/' in filename or '\\' in filename:
        full_path = PROJECT_ROOT / filename
        if full_path.exists():
            return full_path
        return None

    # Busca recursiva nas pastas padrão
    filename_lower = filename.lower()

    for search_dir in SEARCH_DIRS:
        if not search_dir.exists():
            continue

        # Busca exata primeiro
        for pdf_path in search_dir.rglob("*.pdf"):
            if pdf_path.name.lower() == filename_lower:
                return pdf_path

        # Busca parcial (contém o nome)
        for pdf_path in search_dir.rglob("*.pdf"):
            if filename_lower in pdf_path.name.lower():
                return pdf_path

    return None


def get_fields_for_doc(doc) -> List[str]:
    """Retorna lista de campos relevantes baseado no tipo do documento."""
    doc_type = getattr(doc, 'doc_type', 'UNKNOWN')

    fields = COMMON_FIELDS.copy()

    if doc_type == 'DANFE':
        fields.extend(DANFE_FIELDS)
    elif doc_type == 'BOLETO':
        fields.extend(BOLETO_FIELDS)
    elif doc_type == 'NFSE':
        fields.extend(NFSE_FIELDS)
    elif doc_type == 'OUTRO':
        fields.extend(OUTROS_FIELDS)
    else:
        # Mostra todos os campos possíveis
        fields.extend(DANFE_FIELDS + BOLETO_FIELDS + NFSE_FIELDS + OUTROS_FIELDS)

    # Remove duplicatas mantendo ordem
    seen = set()
    return [f for f in fields if not (f in seen or seen.add(f))]


def inspect(pdf_path: Path, fields: Optional[List[str]] = None, show_raw: bool = False) -> None:
    """Processa e exibe campos extraídos do PDF."""

    print(f"\n{'='*60}")
    print(f"ARQUIVO: {pdf_path.name}")
    print(f"PATH:    {pdf_path}")
    print(f"{'='*60}")

    # Processa
    p = BaseInvoiceProcessor()
    doc = p.process(str(pdf_path))

    # Extrator usado
    print(f"\n[extrator] {getattr(p, 'last_extractor', 'N/A')}")
    print(f"[tipo]     {getattr(doc, 'doc_type', 'N/A')}")
    print("-" * 40)

    # Campos a mostrar
    if fields:
        show_fields = fields
    else:
        show_fields = get_fields_for_doc(doc)

    # Exibe campos
    for field in show_fields:
        value = getattr(doc, field, None)

        # Formatação
        if value is None or value == '':
            display = "(vazio)"
        elif isinstance(value, float):
            display = f"R$ {value:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        else:
            display = str(value)

        print(f"{field:<22} = {display}")

    # Texto bruto (truncado ou completo)
    print("-" * 40)
    texto_bruto = getattr(doc, 'texto_bruto', '')

    if show_raw:
        print(f"\n[texto_bruto completo]\n{texto_bruto}")
    else:
        preview = texto_bruto[:300] + "..." if len(texto_bruto) > 300 else texto_bruto
        print(f"[texto_bruto] {preview}")

    print()


def main():
    args = sys.argv[1:]

    # Help
    if '--help' in args or '-h' in args or not args:
        print(__doc__)
        print("Argumentos:")
        print("  <arquivo.pdf>       Nome ou caminho do PDF")
        print("  --fields <campos>   Lista de campos específicos para mostrar")
        print("  --raw               Mostra texto bruto completo (não truncado)")
        print("  --help, -h          Mostra esta ajuda")
        print()
        print("Exemplos:")
        print("  python scripts/inspect_pdf.py NF3595.pdf")
        print("  python scripts/inspect_pdf.py failed_cases_pdf/pasta/boleto.pdf")
        print("  python scripts/inspect_pdf.py danfe.pdf --fields fornecedor valor")
        print("  python scripts/inspect_pdf.py nota.pdf --raw")
        print()
        print(f"Pastas de busca: {', '.join(str(d) for d in SEARCH_DIRS)}")
        return

    # Flags
    show_raw = '--raw' in args
    if show_raw:
        args.remove('--raw')

    show_fields = None
    if '--fields' in args:
        idx = args.index('--fields')
        args.pop(idx)  # remove --fields
        # Pega campos até o próximo argumento que começa com -- ou fim
        show_fields = []
        while idx < len(args) and not args[idx].startswith('--'):
            show_fields.append(args.pop(idx))

    # PDF path
    if not args:
        print("ERRO: Especifique o nome ou caminho do PDF.")
        print("Use --help para ver exemplos.")
        return

    filename = args[0]

    # Busca o arquivo
    pdf_path = find_pdf(filename)

    if not pdf_path:
        print(f"ERRO: Arquivo não encontrado: {filename}")
        print(f"\nBuscado em:")
        for d in SEARCH_DIRS:
            print(f"  - {d}")
        print("\nDica: Passe o caminho completo ou coloque o PDF em uma das pastas acima.")
        return

    inspect(pdf_path, fields=show_fields, show_raw=show_raw)


if __name__ == "__main__":
    main()
