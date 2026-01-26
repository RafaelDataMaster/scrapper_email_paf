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

Modo batch:
    python scripts/inspect_pdf.py --batch email_20250126_100120_cac5a27d
    python scripts/inspect_pdf.py --batch temp_email/email_20250126_100120_cac5a27d
"""

import sys
from pathlib import Path
from typing import List, Optional

from _init_env import setup_project_path

PROJECT_ROOT = setup_project_path()

from config.settings import DIR_DEBUG_INPUT, DIR_TEMP
from core.processor import BaseInvoiceProcessor
from core.extractors import EXTRACTOR_REGISTRY

# Pastas onde buscar PDFs (ordem de prioridade) e batch padrão
BATCH_BASE_DIR = DIR_TEMP
SEARCH_DIRS = [
    DIR_DEBUG_INPUT,  # failed_cases_pdf
    DIR_TEMP,  # temp_email
]

# Campos comuns a todos os tipos de documento
COMMON_FIELDS = [
    "doc_type",
    "arquivo_origem",
    "fornecedor_nome",
    "empresa",
    "data_emissao",
    "vencimento",
    "data_processamento",
]

# Campos específicos por tipo
DANFE_FIELDS = [
    "numero_nota",
    "serie_nf",
    "valor_total",
    "cnpj_emitente",
    "numero_pedido",
    "numero_fatura",
    "chave_acesso",
    "forma_pagamento",
]

BOLETO_FIELDS = [
    "valor_documento",
    "cnpj_beneficiario",
    "linha_digitavel",
    "nosso_numero",
    "numero_documento",
    "referencia_nfse",
    "banco_nome",
    "agencia",
    "conta_corrente",
]

NFSE_FIELDS = [
    "numero_nota",
    "valor_total",
    "cnpj_prestador",
    "numero_pedido",
    "forma_pagamento",
    "valor_ir",
    "valor_inss",
    "valor_csll",
    "valor_iss",
]

OUTROS_FIELDS = [
    "numero_documento",
    "numero_nota",
    "valor_total",
    "cnpj_fornecedor",
    "subtipo",
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
    if "/" in filename or "\\" in filename:
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


def get_batch_info(pdf_path: Path) -> dict:
    """
    Extrai informações do batch a partir do caminho do PDF.

    Args:
        pdf_path: Path do arquivo PDF

    Returns:
        Dicionário com informações do batch:
        - batch_id: ID do batch (nome da pasta)
        - batch_path: Caminho da pasta do batch
        - is_from_batch: True se veio de temp_email/
        - batch_date: Data estimada do batch
    """
    path_str = str(pdf_path)

    info = {
        "batch_id": None,
        "batch_path": None,
        "is_from_batch": False,
        "batch_date": None,
    }

    # Verifica se está dentro de temp_email
    if "temp_email" in path_str:
        info["is_from_batch"] = True
        # Encontra a pasta do batch (imediatamente após temp_email)
        parts = Path(pdf_path).parts
        try:
            temp_email_idx = parts.index("temp_email")
            if len(parts) > temp_email_idx + 1:
                batch_folder = parts[temp_email_idx + 1]
                info["batch_id"] = batch_folder
                info["batch_path"] = str(Path(*parts[: temp_email_idx + 2]))

                # Tenta extrair data do nome do batch
                if batch_folder.startswith("email_"):
                    # Formato: email_YYYYMMDD_HHMMSS_xxxx
                    date_part = batch_folder[6:14]  # YYYYMMDD
                    if date_part.isdigit() and len(date_part) == 8:
                        year = date_part[0:4]
                        month = date_part[4:6]
                        day = date_part[6:8]
                        info["batch_date"] = f"{day}/{month}/{year}"
        except (ValueError, IndexError):
            pass

    return info


def test_all_extractors(text: str) -> List[dict]:
    """
    Testa todos os extratores registrados no texto.

    Args:
        text: Texto do documento

    Returns:
        Lista de dicionários com resultados de cada extrator:
        - name: Nome da classe do extrator
        - can_handle: Resultado do can_handle
        - priority: Posição no registro (0 = mais prioritário)
    """
    results = []
    for i, extractor_cls in enumerate(EXTRACTOR_REGISTRY):
        try:
            can_handle = extractor_cls.can_handle(text)
            results.append(
                {
                    "name": extractor_cls.__name__,
                    "can_handle": can_handle,
                    "priority": i,
                }
            )
        except Exception as e:
            results.append(
                {
                    "name": extractor_cls.__name__,
                    "can_handle": False,
                    "priority": i,
                    "error": str(e),
                }
            )
    return results


def get_relatorio_lotes_fields(doc) -> dict:
    """
    Extrai campos que seriam usados no relatorio_lotes.csv.

    Args:
        doc: Documento processado

    Returns:
        Dicionário com campos para relatório de lotes
    """
    # Campos do relatorio_lotes.csv baseado em run_ingestion.py
    campos = {}

    # Campos básicos que sempre existem
    campos["batch_id"] = None  # Será preenchido externamente
    campos["data"] = getattr(doc, "data_emissao", None) or getattr(
        doc, "data_processamento", None
    )
    campos["status_conciliacao"] = "N/A"  # Seria calculado no processamento batch
    campos["divergencia"] = "N/A"
    campos["diferenca_valor"] = "N/A"
    campos["fornecedor"] = getattr(doc, "fornecedor_nome", None)
    campos["vencimento"] = getattr(doc, "vencimento", None)
    campos["numero_nota"] = getattr(doc, "numero_nota", None) or getattr(
        doc, "numero_documento", None
    )

    # Campos de valor dependem do tipo
    if hasattr(doc, "valor_total"):
        campos["valor_compra"] = getattr(doc, "valor_total", 0.0)
    elif hasattr(doc, "valor_documento"):
        campos["valor_compra"] = getattr(doc, "valor_documento", 0.0)
    else:
        campos["valor_compra"] = getattr(doc, "valor_total", 0.0)

    campos["valor_boleto"] = (
        getattr(doc, "valor_documento", 0.0) if hasattr(doc, "valor_documento") else 0.0
    )
    campos["empresa"] = getattr(doc, "empresa", None)

    return campos


def get_fields_for_doc(doc) -> List[str]:
    """Retorna lista de campos relevantes baseado no tipo do documento."""
    doc_type = getattr(doc, "doc_type", "UNKNOWN")

    fields = COMMON_FIELDS.copy()

    if doc_type == "DANFE":
        fields.extend(DANFE_FIELDS)
    elif doc_type == "BOLETO":
        fields.extend(BOLETO_FIELDS)
    elif doc_type == "NFSE":
        fields.extend(NFSE_FIELDS)
    elif doc_type == "OUTRO":
        fields.extend(OUTROS_FIELDS)
    else:
        # Mostra todos os campos possíveis
        fields.extend(DANFE_FIELDS + BOLETO_FIELDS + NFSE_FIELDS + OUTROS_FIELDS)

    # Remove duplicatas mantendo ordem
    seen = set()
    return [f for f in fields if not (f in seen or seen.add(f))]


def inspect(
    pdf_path: Path, fields: Optional[List[str]] = None, show_raw: bool = False
) -> None:
    """Processa e exibe campos extraídos do PDF."""

    print(f"\n{'=' * 80}")
    print(f"📄 ARQUIVO: {pdf_path.name}")
    print(f"📁 PATH:    {pdf_path}")

    # Informações do batch
    batch_info = get_batch_info(pdf_path)
    if batch_info["is_from_batch"]:
        print(f"📦 BATCH:   {batch_info['batch_id']}")
        if batch_info["batch_date"]:
            print(f"📅 DATA:    {batch_info['batch_date']}")
        print(f"📂 PASTA:   {batch_info['batch_path']}")

    print(f"{'=' * 80}")

    # Processa
    p = BaseInvoiceProcessor()
    doc = p.process(str(pdf_path))

    # Texto bruto para testes de extratores
    texto_bruto = getattr(doc, "texto_bruto", "")

    # Testa todos os extratores
    print("\n🔍 TESTE DE EXTRATORES (Ordem de prioridade):")
    print("-" * 60)
    test_results = test_all_extractors(texto_bruto)

    for result in test_results:
        status = (
            "✅ SELECIONADO"
            if result["can_handle"]
            and result["name"] == getattr(p, "last_extractor", "")
            else ("✓ Compatível" if result["can_handle"] else "✗ Não compatível")
        )
        error_info = f" - ERRO: {result['error']}" if "error" in result else ""
        print(f"{result['priority']:2d}. {result['name']:<35} {status}{error_info}")

    print("-" * 60)
    print(f"🎯 EXTRATOR SELECIONADO: {getattr(p, 'last_extractor', 'N/A')}")
    print(f"📄 TIPO DO DOCUMENTO:    {getattr(doc, 'doc_type', 'N/A')}")

    # Campos para relatorio_lotes.csv
    print("\n📋 CAMPOS PARA RELATÓRIO_LOTES.CSV:")
    print("-" * 60)
    lotes_fields = get_relatorio_lotes_fields(doc)
    for key, value in lotes_fields.items():
        if value is None or value == "":
            display = "(vazio)"
        elif isinstance(value, float):
            display = (
                f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
        else:
            display = str(value)
        print(f"{key:<20} = {display}")

    print("\n📊 CAMPOS EXTRÍDOS DO DOCUMENTO:")
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
        if value is None or value == "":
            display = "(vazio)"
        elif isinstance(value, float):
            display = (
                f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
        else:
            display = str(value)

        print(f"{field:<22} = {display}")

    # Texto bruto (truncado ou completo)
    print("-" * 40)
    texto_bruto = getattr(doc, "texto_bruto", "")

    if show_raw:
        print(f"\n📝 TEXTO BRUTO COMPLETO:\n{texto_bruto}")
    else:
        preview = texto_bruto[:500] + "..." if len(texto_bruto) > 500 else texto_bruto
        print(f"📝 TEXTO BRUTO (primeiros 500 chars):\n{preview}")

    print(f"\n{'=' * 80}")
    print("✅ INSPEÇÃO CONCLUÍDA")
    print(f"{'=' * 80}")
    print()


def inspect_batch(batch_path: Path) -> None:
    """
    Inspeciona todos os PDFs de um batch (pasta do temp_email).

    Args:
        batch_path: Path da pasta do batch
    """
    if not batch_path.exists():
        print(f"❌ Pasta do batch não encontrada: {batch_path}")
        return

    if not batch_path.is_dir():
        print(f"❌ O caminho não é uma pasta: {batch_path}")
        return

    # Lista todos os PDFs
    pdf_files = list(batch_path.glob("*.pdf"))
    if not pdf_files:
        print(f"ℹ️  Nenhum PDF encontrado no batch: {batch_path}")
        return

    print(f"\n{'=' * 80}")
    print("🔍 INSPEÇÃO DE BATCH: " + batch_path.name)
    print(f"📂 PASTA: {batch_path}")
    print(f"📄 TOTAL DE PDFs: {len(pdf_files)}")
    print(f"{'=' * 80}")

    batch_summary = []

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] Processando: {pdf_path.name}")
        print("-" * 40)

        # Processa o PDF
        p = BaseInvoiceProcessor()
        doc = p.process(str(pdf_path))

        # Coleta informações para sumário
        summary = {
            "arquivo": pdf_path.name,
            "extrator": getattr(p, "last_extractor", "N/A"),
            "tipo": getattr(doc, "doc_type", "N/A"),
            "fornecedor": getattr(doc, "fornecedor_nome", ""),
            "valor": getattr(doc, "valor_total", getattr(doc, "valor_documento", 0.0)),
            "vencimento": getattr(doc, "vencimento", ""),
            "numero_nota": getattr(
                doc, "numero_nota", getattr(doc, "numero_documento", "")
            ),
            "empresa": getattr(doc, "empresa", ""),
        }
        batch_summary.append(summary)

        # Exibe informações resumidas
        print(f"🎯 Extrator: {summary['extrator']}")
        print(f"📄 Tipo: {summary['tipo']}")
        print(f"🏢 Fornecedor: {summary['fornecedor'] or '(vazio)'}")
        print(
            f"💰 Valor: R$ {summary['valor']:,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
        print(f"📅 Vencimento: {summary['vencimento'] or '(vazio)'}")
        print(f"🔢 Número: {summary['numero_nota'] or '(vazio)'}")
        print(f"🏭 Empresa: {summary['empresa'] or '(vazio)'}")

    # Resumo consolidado do batch
    print("\n" + "=" * 80)
    print(f"📊 RESUMO DO BATCH: {batch_path.name}")
    print("=" * 80)

    # Estatísticas
    extratores = {}
    tipos = {}
    empresas = {}

    for summary in batch_summary:
        extrator = summary["extrator"]
        tipo = summary["tipo"]
        empresa = summary["empresa"]

        extratores[extrator] = extratores.get(extrator, 0) + 1
        tipos[tipo] = tipos.get(tipo, 0) + 1
        if empresa:
            empresas[empresa] = empresas.get(empresa, 0) + 1

    print("\n📈 ESTATÍSTICAS:")
    print("📄 Total de documentos: " + str(len(batch_summary)))

    print("\n🎯 DISTRIBUIÇÃO POR EXTRATOR:")
    for extrator, count in sorted(extratores.items(), key=lambda x: x[1], reverse=True):
        percent = (count / len(batch_summary)) * 100
        print(f"  {extrator:<35} {count:3d} ({percent:.1f}%)")

    print("\n📄 DISTRIBUIÇÃO POR TIPO:")
    for tipo, count in sorted(tipos.items(), key=lambda x: x[1], reverse=True):
        percent = (count / len(batch_summary)) * 100
        print(f"  {tipo:<35} {count:3d} ({percent:.1f}%)")

    if empresas:
        print("\n🏭 DISTRIBUIÇÃO POR EMPRESA:")
        for empresa, count in sorted(
            empresas.items(), key=lambda x: x[1], reverse=True
        ):
            percent = (count / len(batch_summary)) * 100
            print(f"  {empresa:<35} {count:3d} ({percent:.1f}%)")

    # Lista de documentos para relatorio_lotes.csv
    print("\n📋 LISTA PARA RELATÓRIO_LOTES.CSV:")
    print("-" * 80)
    print(
        f"{'Arquivo':<30} {'Extrator':<25} {'Tipo':<10} {'Fornecedor':<30} {'Valor':>12} {'Vencimento':<12} {'Número':<15}"
    )
    print("-" * 80)

    for summary in batch_summary:
        arquivo = (
            summary["arquivo"][:27] + "..."
            if len(summary["arquivo"]) > 30
            else summary["arquivo"]
        )
        extrator = (
            summary["extrator"][:22] + "..."
            if len(summary["extrator"]) > 25
            else summary["extrator"]
        )
        tipo = summary["tipo"][:8] if summary["tipo"] else "N/A"
        fornecedor = (
            summary["fornecedor"][:27] + "..."
            if len(summary["fornecedor"]) > 30
            else summary["fornecedor"] or "(vazio)"
        )
        valor_str = (
            f"R$ {summary['valor']:,.2f}".replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
            if summary["valor"]
            else "R$ 0,00"
        )
        vencimento = summary["vencimento"][:10] if summary["vencimento"] else "(vazio)"
        numero = summary["numero_nota"][:12] if summary["numero_nota"] else "(vazio)"

        print(
            f"{arquivo:<30} {extrator:<25} {tipo:<10} {fornecedor:<30} {valor_str:>12} {vencimento:<12} {numero:<15}"
        )

    print("\n" + "=" * 80)
    print("✅ INSPEÇÃO DE BATCH CONCLUÍDA")
    print(f"{'=' * 80}")
    print()


def main():
    args = sys.argv[1:]

    # Help
    if "--help" in args or "-h" in args or not args:
        print(__doc__)
        print("Argumentos:")
        print("  <arquivo.pdf>       Nome ou caminho do PDF")
        print(
            "  --batch <batch_id>  Analisa todos os PDFs de um batch (pasta do temp_email)"
        )
        print("  --fields <campos>   Lista de campos específicos para mostrar")
        print("  --raw               Mostra texto bruto completo (não truncado)")
        print("  --help, -h          Mostra esta ajuda")
        print()
        print("Exemplos:")
        print("  python scripts/inspect_pdf.py NF3595.pdf")
        print("  python scripts/inspect_pdf.py failed_cases_pdf/pasta/boleto.pdf")
        print("  python scripts/inspect_pdf.py --batch email_20250126_100120_cac5a27d")
        print(
            "  python scripts/inspect_pdf.py --batch temp_email/email_20250126_100120_cac5a27d"
        )
        print("  python scripts/inspect_pdf.py danfe.pdf --fields fornecedor valor")
        print("  python scripts/inspect_pdf.py nota.pdf --raw")
        print()
        print(f"Pastas de busca: {', '.join(str(d) for d in SEARCH_DIRS)}")
        return

    # Modo batch
    batch_mode = False
    batch_id = None
    if "--batch" in args:
        batch_mode = True
        idx = args.index("--batch")
        args.pop(idx)  # remove --batch
        if idx < len(args) and not args[idx].startswith("--"):
            batch_id = args.pop(idx)
        else:
            print("ERRO: Especifique o ID do batch após --batch")
            print("Exemplo: --batch email_20250126_100120_cac5a27d")
            return

    # Flags
    show_raw = "--raw" in args
    if show_raw:
        args.remove("--raw")

    show_fields = None
    if "--fields" in args:
        idx = args.index("--fields")
        args.pop(idx)  # remove --fields
        # Pega campos até o próximo argumento que começa com -- ou fim
        show_fields = []
        while idx < len(args) and not args[idx].startswith("--"):
            show_fields.append(args.pop(idx))

    # Modo batch
    if batch_mode:
        if not batch_id:
            print("ERRO: ID do batch não especificado")
            return

        # Tenta encontrar a pasta do batch
        batch_path = None

        # Se já é um caminho completo ou relativo
        candidate = Path(batch_id)
        if candidate.exists() and candidate.is_dir():
            batch_path = candidate
        else:
            # Tenta dentro de temp_email
            candidate = BATCH_BASE_DIR / batch_id
            if candidate.exists() and candidate.is_dir():
                batch_path = candidate
            else:
                # Busca por nome parcial
                if BATCH_BASE_DIR.exists():
                    for folder in BATCH_BASE_DIR.iterdir():
                        if folder.is_dir() and batch_id in folder.name:
                            batch_path = folder
                            break

        if not batch_path:
            print(f"❌ Batch não encontrado: {batch_id}")
            print("\nBuscado em:")
            print(f"  - {BATCH_BASE_DIR}")
            print(f"\nBatches disponíveis em {BATCH_BASE_DIR}:")
            if BATCH_BASE_DIR.exists():
                batches = [f.name for f in BATCH_BASE_DIR.iterdir() if f.is_dir()]
                for batch in sorted(batches)[:20]:  # Mostra primeiros 20
                    print(f"  - {batch}")
                if len(batches) > 20:
                    print(f"  ... e mais {len(batches) - 20} batches")
            else:
                print(f"  (pasta não existe: {BATCH_BASE_DIR})")
            return

        inspect_batch(batch_path)
        return

    # Modo arquivo único
    if not args:
        print("ERRO: Especifique o nome ou caminho do PDF.")
        print("Use --help para ver exemplos.")
        return

    filename = args[0]

    # Busca o arquivo
    pdf_path = find_pdf(filename)

    if not pdf_path:
        print(f"ERRO: Arquivo não encontrado: {filename}")
        print("\nBuscado em:")
        for d in SEARCH_DIRS:
            print(f"  - {d}")
        print(
            "\nDica: Passe o caminho completo ou coloque o PDF em uma das pastas acima."
        )
        return

    inspect(pdf_path, fields=show_fields, show_raw=show_raw)


if __name__ == "__main__":
    main()
