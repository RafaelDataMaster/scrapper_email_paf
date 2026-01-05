"""
Exemplo de processamento em lote (Batch Processing).

Este script demonstra como usar a nova estrutura de processamento
de e-mails em lote, com correlação entre documentos e enriquecimento
de dados.

MODOS DE USO:

1. Processar uma pasta de lote específica:
   python scripts/example_batch_processing.py --batch-folder temp_email/email_20250101_abc123

2. Processar todas as pastas de lote em um diretório:
   python scripts/example_batch_processing.py --root-folder temp_email

3. Processar arquivos legados (failed_cases_pdf):
   python scripts/example_batch_processing.py --legacy --folder failed_cases_pdf

4. Criar um lote de teste simulado:
   python scripts/example_batch_processing.py --create-test-batch

Princípios SOLID aplicados:
- SRP: Cada função tem uma única responsabilidade
- DIP: Usa abstrações (BatchProcessor, CorrelationService)
"""
import argparse
import sys
from pathlib import Path
from typing import List

from _init_env import setup_project_path

# Inicializa o ambiente do projeto
setup_project_path()

from config.settings import DIR_DEBUG_INPUT, DIR_TEMP
from core.batch_processor import (
    BatchProcessor,
    process_email_batch,
    process_legacy_folder,
)
from core.batch_result import BatchResult
from core.correlation_service import CorrelationService
from core.metadata import EmailMetadata
from services.ingestion_service import create_batch_folder


def print_batch_summary(batch: BatchResult) -> None:
    """Imprime resumo de um lote processado."""
    print("\n" + "=" * 60)
    print(f"📦 LOTE: {batch.batch_id}")
    print("=" * 60)

    if batch.source_folder:
        print(f"📂 Pasta: {batch.source_folder}")

    if batch.email_subject:
        print(f"📧 Assunto: {batch.email_subject}")

    if batch.email_sender:
        print(f"👤 Remetente: {batch.email_sender}")

    print(f"\n📊 Documentos processados: {batch.total_documents}")
    print(f"   - DANFEs: {len(batch.danfes)}")
    print(f"   - Boletos: {len(batch.boletos)}")
    print(f"   - NFSes: {len(batch.nfses)}")
    print(f"   - Outros: {len(batch.outros)}")

    if batch.total_errors > 0:
        print(f"❌ Erros: {batch.total_errors}")

    # Valores
    valor_compra = batch.get_valor_compra()
    if valor_compra > 0:
        print(f"\n💰 Valor da compra: R$ {valor_compra:,.2f}")

        if batch.has_danfe:
            print(f"   - DANFEs: R$ {batch.get_valor_total_danfes():,.2f}")

        if batch.has_boleto:
            print(f"   - Boletos: R$ {batch.get_valor_total_boletos():,.2f}")

    # Detalhes de cada documento
    print("\n📄 DETALHES DOS DOCUMENTOS:")
    print("-" * 40)

    for i, doc in enumerate(batch.documents, start=1):
        doc_type = doc.doc_type
        fornecedor = getattr(doc, 'fornecedor_nome', None) or "N/A"

        if doc_type == 'DANFE':
            valor = getattr(doc, 'valor_total', 0) or 0
            numero = getattr(doc, 'numero_nota', None) or "N/A"
            print(f"  {i}. [{doc_type}] NF {numero} - {fornecedor} - R$ {valor:,.2f}")

        elif doc_type == 'BOLETO':
            valor = getattr(doc, 'valor_documento', 0) or 0
            venc = getattr(doc, 'vencimento', None) or "N/A"
            print(f"  {i}. [{doc_type}] Venc: {venc} - {fornecedor} - R$ {valor:,.2f}")

        elif doc_type == 'NFSE':
            valor = getattr(doc, 'valor_total', 0) or 0
            numero = getattr(doc, 'numero_nota', None) or "N/A"
            print(f"  {i}. [{doc_type}] NF {numero} - {fornecedor} - R$ {valor:,.2f}")

        else:
            valor = getattr(doc, 'valor_total', 0) or 0
            print(f"  {i}. [{doc_type}] {fornecedor} - R$ {valor:,.2f}")

    print("-" * 40)


def process_single_batch(folder_path: str, apply_correlation: bool = True) -> None:
    """Processa uma única pasta de lote."""
    print(f"\n🔄 Processando lote: {folder_path}")

    batch = process_email_batch(folder_path, apply_correlation=apply_correlation)

    if batch.is_empty:
        print("⚠️ Nenhum documento processado no lote.")
        return

    print_batch_summary(batch)


def process_all_batches(root_folder: str, apply_correlation: bool = True) -> None:
    """Processa todas as pastas de lote em um diretório."""
    root_path = Path(root_folder)

    if not root_path.exists():
        print(f"❌ Pasta não encontrada: {root_folder}")
        return

    print(f"\n🔄 Processando lotes em: {root_folder}")

    processor = BatchProcessor()
    batches = processor.process_multiple_batches(root_path, apply_correlation=apply_correlation)

    if not batches:
        print("⚠️ Nenhum lote encontrado.")
        return

    print(f"\n📦 {len(batches)} lote(s) processado(s)")

    total_docs = 0
    total_erros = 0

    for batch in batches:
        print_batch_summary(batch)
        total_docs += batch.total_documents
        total_erros += batch.total_errors

    print("\n" + "=" * 60)
    print("📊 RESUMO GERAL")
    print("=" * 60)
    print(f"   Lotes processados: {len(batches)}")
    print(f"   Total de documentos: {total_docs}")
    print(f"   Total de erros: {total_erros}")


def process_legacy(folder_path: str) -> None:
    """Processa arquivos legados (PDFs soltos)."""
    print(f"\n🔄 Processando arquivos legados em: {folder_path}")

    batch = process_legacy_folder(folder_path, recursive=True)

    if batch.is_empty:
        print("⚠️ Nenhum documento processado.")
        return

    print_batch_summary(batch)


def create_test_batch() -> None:
    """Cria um lote de teste simulado para demonstração."""
    print("\n🧪 Criando lote de teste simulado...")

    # Cria pasta de lote com metadata
    batch_folder = create_batch_folder(
        temp_dir=DIR_TEMP,
        subject="[NF] Nota Fiscal #12345 - Fornecedor Exemplo LTDA",
        sender_name="Fornecedor Exemplo LTDA",
        sender_address="nf@fornecedor.com.br",
        body_text="Segue em anexo a Nota Fiscal 12345. CNPJ: 12.345.678/0001-90. Pedido: PC-2025-001.",
        files=[]  # Sem arquivos reais (só demonstração)
    )

    print(f"✅ Lote criado: {batch_folder}")

    # Mostra o metadata criado
    metadata = EmailMetadata.load(batch_folder)
    if metadata:
        print("\n📋 Metadata gerado:")
        print(f"   batch_id: {metadata.batch_id}")
        print(f"   email_subject: {metadata.email_subject}")
        print(f"   email_sender_name: {metadata.email_sender_name}")
        print(f"   email_sender_address: {metadata.email_sender_address}")
        print(f"   created_at: {metadata.created_at}")

        # Demonstra extração de dados do contexto
        cnpj = metadata.extract_cnpj_from_body()
        pedido = metadata.extract_numero_pedido_from_context()

        print("\n🔍 Dados extraídos do contexto:")
        print(f"   CNPJ encontrado no corpo: {cnpj or 'N/A'}")
        print(f"   Número pedido encontrado: {pedido or 'N/A'}")

    print(f"\n💡 Adicione PDFs na pasta '{batch_folder}' e execute:")
    print(f"   python scripts/example_batch_processing.py --batch-folder {batch_folder}")


def main() -> None:
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='Exemplo de processamento em lote',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Processar uma pasta de lote específica
  python scripts/example_batch_processing.py --batch-folder temp_email/email_123

  # Processar todas as pastas de lote
  python scripts/example_batch_processing.py --root-folder temp_email

  # Processar arquivos legados
  python scripts/example_batch_processing.py --legacy --folder failed_cases_pdf

  # Criar lote de teste
  python scripts/example_batch_processing.py --create-test-batch
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--batch-folder',
        type=str,
        help='Pasta de lote específica para processar'
    )
    group.add_argument(
        '--root-folder',
        type=str,
        help='Pasta raiz contendo múltiplos lotes'
    )
    group.add_argument(
        '--legacy',
        action='store_true',
        help='Processar arquivos legados (PDFs soltos)'
    )
    group.add_argument(
        '--create-test-batch',
        action='store_true',
        help='Criar lote de teste simulado'
    )

    parser.add_argument(
        '--folder',
        type=str,
        default=str(DIR_DEBUG_INPUT),
        help='Pasta para modo legado (default: failed_cases_pdf)'
    )
    parser.add_argument(
        '--no-correlation',
        action='store_true',
        help='Desabilitar correlação entre documentos'
    )

    args = parser.parse_args()

    apply_correlation = not args.no_correlation

    if args.batch_folder:
        process_single_batch(args.batch_folder, apply_correlation)

    elif args.root_folder:
        process_all_batches(args.root_folder, apply_correlation)

    elif args.legacy:
        process_legacy(args.folder)

    elif args.create_test_batch:
        create_test_batch()


if __name__ == "__main__":
    main()
