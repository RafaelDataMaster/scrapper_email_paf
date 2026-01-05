import os
import sys

# Adicionar o diretório pai ao path para importar módulos do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from core.batch_processor import BatchProcessor
from core.processor import BaseInvoiceProcessor


class DebugInvoiceProcessor(BaseInvoiceProcessor):
    """Processador de debug que mostra detalhes do processamento."""
    pass


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    batch_dir = os.path.join(base_dir, "temp_email", "email_20260105_125519_9b0b0752")

    print(f"=" * 80)
    print(f"DEBUG - Processamento do Batch Problemático")
    print(f"=" * 80)
    print(f"Diretório: {batch_dir}")
    print()

    # Listar arquivos
    print("Arquivos no diretório:")
    for f in os.listdir(batch_dir):
        file_path = os.path.join(batch_dir, f)
        size = os.path.getsize(file_path)
        print(f"  - {f} ({size:,} bytes)")
    print()

    # Carregar metadata
    metadata_path = os.path.join(batch_dir, "metadata.json")
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        print("Metadata:")
        print(f"  Assunto: {metadata.get('email_subject')}")
        print(f"  Anexos: {metadata.get('attachments')}")
        print()

    # Processar cada PDF individualmente
    print("=" * 80)
    print("PROCESSAMENTO INDIVIDUAL DE CADA PDF")
    print("=" * 80)

    processor = DebugInvoiceProcessor()

    pdf_files = [f for f in os.listdir(batch_dir) if f.lower().endswith('.pdf')]

    for pdf_file in sorted(pdf_files):
        file_path = os.path.join(batch_dir, pdf_file)
        print(f"\n{'='*60}")
        print(f"Processando: {pdf_file}")
        print(f"{'='*60}")

        try:
            result = processor.process(file_path)

            print(f"Tipo de documento detectado: {type(result).__name__}")
            print(f"Extrator usado: {processor.last_extractor}")
            print()
            print("Dados extraídos:")

            # Mostrar todos os campos do resultado
            for key, value in vars(result).items():
                if value is not None and key != 'texto_bruto':
                    print(f"  {key}: {value}")

            # Destacar campos críticos
            print()
            print("CAMPOS CRÍTICOS:")
            print(f"  valor_documento/valor_total: {getattr(result, 'valor_documento', None) or getattr(result, 'valor_total', None)}")
            print(f"  vencimento: {getattr(result, 'vencimento', None)}")
            print(f"  fornecedor_nome: {getattr(result, 'fornecedor_nome', None)}")

        except Exception as e:
            print(f"ERRO: {e}")
            import traceback
            traceback.print_exc()

    # Processar como batch
    print()
    print("=" * 80)
    print("PROCESSAMENTO COMO BATCH (BatchProcessor)")
    print("=" * 80)

    batch_processor = BatchProcessor()
    batch_result = batch_processor.process_batch(batch_dir)

    print(f"\nResultado do Batch:")
    print(f"  batch_id: {batch_result.batch_id}")
    print(f"  total_documents: {batch_result.total_documents}")
    print(f"  total_errors: {batch_result.total_errors}")

    if batch_result.correlation_result:
        cr = batch_result.correlation_result
        print()
        print("Correlação:")
        print(f"  status: {cr.status}")
        print(f"  divergencia: {cr.divergencia}")
        print(f"  diferenca: {cr.diferenca}")
        print(f"  valor_compra: {cr.valor_compra}")
        print(f"  valor_boleto: {cr.valor_boleto}")
        print(f"  vencimento_herdado: {cr.vencimento_herdado}")
        print(f"  numero_nota_herdado: {cr.numero_nota_herdado}")
        print(f"  sem_vencimento: {cr.sem_vencimento}")

    print()
    print("Documentos processados:")
    for doc in batch_result.documents:
        print(f"\n  Arquivo: {doc.arquivo_origem}")
        print(f"    Tipo: {type(doc).__name__}")
        if hasattr(doc, 'valor_documento'):
            print(f"    Valor: {doc.valor_documento}")
        elif hasattr(doc, 'valor_total'):
            print(f"    Valor: {doc.valor_total}")
        if hasattr(doc, 'vencimento'):
            print(f"    Vencimento: {doc.vencimento}")
        if hasattr(doc, 'fornecedor_nome'):
            print(f"    Fornecedor: {doc.fornecedor_nome}")


if __name__ == "__main__":
    main()
