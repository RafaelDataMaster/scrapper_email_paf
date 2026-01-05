"""
Script para analisar todos os batches e identificar problemas similares.

Este script processa todos os batches em temp_email e gera um relatório
comparando os resultados de extração com os esperados.
"""

import os
import sys

# Adicionar o diretório pai ao path para importar módulos do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from pathlib import Path

from core.batch_processor import BatchProcessor


def analyze_batch(batch_dir: Path) -> dict:
    """Analisa um batch individual e retorna um resumo."""
    result = {
        "batch_id": batch_dir.name,
        "status": None,
        "divergencia": None,
        "diferenca": None,
        "valor_compra": None,
        "valor_boleto": None,
        "fornecedor": None,
        "vencimento": None,
        "total_documents": 0,
        "total_errors": 0,
        "extractors_used": [],
        "pdf_files": [],
        "has_multi_page_pdf": False,
        "error": None,
    }

    try:
        # Listar PDFs
        pdf_files = list(batch_dir.glob("*.pdf"))
        result["pdf_files"] = [f.name for f in pdf_files]

        # Verificar se há PDFs com múltiplas páginas
        import pdfplumber

        for pdf_file in pdf_files:
            try:
                with pdfplumber.open(pdf_file) as pdf:
                    if len(pdf.pages) > 1:
                        result["has_multi_page_pdf"] = True
                        break
            except Exception:
                pass

        # Processar batch
        processor = BatchProcessor()
        batch_result = processor.process_batch(str(batch_dir))

        result["total_documents"] = batch_result.total_documents
        result["total_errors"] = batch_result.total_errors

        # Coletar extratores usados
        for doc in batch_result.documents:
            doc_type = type(doc).__name__
            if doc_type not in result["extractors_used"]:
                result["extractors_used"].append(doc_type)

        # Extrair dados de correlação
        if batch_result.correlation_result:
            cr = batch_result.correlation_result
            result["status"] = cr.status
            result["divergencia"] = cr.divergencia
            result["diferenca"] = cr.diferenca
            result["valor_compra"] = cr.valor_compra
            result["valor_boleto"] = cr.valor_boleto

        # Extrair fornecedor e vencimento do summary
        summary = batch_result.to_summary()
        result["fornecedor"] = summary.get("fornecedor")
        result["vencimento"] = summary.get("vencimento")

    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    base_dir = Path(__file__).parent.parent
    temp_email_dir = base_dir / "temp_email"

    print("=" * 80)
    print("ANÁLISE DE TODOS OS BATCHES")
    print("=" * 80)
    print(f"Diretório: {temp_email_dir}")
    print()

    # Listar todos os batches
    batch_dirs = sorted(
        [d for d in temp_email_dir.iterdir() if d.is_dir()],
        key=lambda x: x.name,
    )

    print(f"Total de batches encontrados: {len(batch_dirs)}")
    print()

    # Análise de cada batch
    results = []
    problematic_batches = []

    for batch_dir in batch_dirs:
        print(f"Processando: {batch_dir.name}...", end=" ")
        result = analyze_batch(batch_dir)
        results.append(result)

        # Identificar problemas
        is_problematic = False
        problem_reasons = []

        if result["status"] == "DIVERGENTE":
            is_problematic = True
            problem_reasons.append(f"DIVERGENTE (diff={result['diferenca']:.2f})")

        if result["error"]:
            is_problematic = True
            problem_reasons.append(f"ERRO: {result['error']}")

        if result["has_multi_page_pdf"] and result["status"] != "OK":
            is_problematic = True
            problem_reasons.append("PDF multi-página com problema")

        if is_problematic:
            problematic_batches.append((result, problem_reasons))
            print(f"⚠️  {', '.join(problem_reasons)}")
        else:
            print(f"✅ {result['status']}")

    # Resumo final
    print()
    print("=" * 80)
    print("RESUMO")
    print("=" * 80)

    status_counts = {}
    for r in results:
        status = r["status"] or "UNKNOWN"
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\nContagem por status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")

    print(f"\nBatches com problemas: {len(problematic_batches)}")

    if problematic_batches:
        print("\n" + "=" * 80)
        print("BATCHES PROBLEMÁTICOS")
        print("=" * 80)

        for result, reasons in problematic_batches:
            print(f"\n{result['batch_id']}:")
            print(f"  Problemas: {', '.join(reasons)}")
            print(f"  PDFs: {result['pdf_files']}")
            print(f"  Multi-página: {result['has_multi_page_pdf']}")
            print(f"  Valor compra: R$ {result['valor_compra']:.2f}" if result["valor_compra"] else "  Valor compra: N/A")
            print(f"  Valor boleto: R$ {result['valor_boleto']:.2f}" if result["valor_boleto"] else "  Valor boleto: N/A")
            print(f"  Diferença: R$ {result['diferenca']:.2f}" if result["diferenca"] else "  Diferença: N/A")
            print(f"  Fornecedor: {result['fornecedor']}")
            print(f"  Extratores: {result['extractors_used']}")

    # Batches com PDFs multi-página
    multi_page_batches = [r for r in results if r["has_multi_page_pdf"]]
    if multi_page_batches:
        print("\n" + "=" * 80)
        print("BATCHES COM PDFs MULTI-PÁGINA")
        print("=" * 80)

        for result in multi_page_batches:
            status_emoji = "✅" if result["status"] == "OK" else "⚠️"
            print(f"\n{status_emoji} {result['batch_id']}:")
            print(f"  Status: {result['status']}")
            print(f"  PDFs: {result['pdf_files']}")
            print(f"  Extratores: {result['extractors_used']}")


if __name__ == "__main__":
    main()
