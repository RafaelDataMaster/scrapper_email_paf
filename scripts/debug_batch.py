#!/usr/bin/env python3
"""
Script de Debug para Batch Processing

Processa uma pasta de email e mostra exatamente quais valores
apareceriam no relatorio_lotes.csv, aplicando a lógica de pairing
quando necessário.

Uso:
    python debug_batch.py <caminho_da_pasta>
    python debug_batch.py temp_email/email_20260105_125518_4e51c5e2

Autor: Sistema de Processamento de Documentos
"""

import sys
from pathlib import Path
from typing import Any, Dict, List

# Adiciona o diretório raiz ao path para imports funcionarem
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.batch_processor import BatchProcessor
from core.document_pairing import DocumentPairingService


def format_value(value: Any) -> str:
    """Formata um valor para exibição."""
    if value is None:
        return "(vazio)"
    if isinstance(value, float):
        return f"{value:.2f}".replace(".", ",")
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    return str(value)


def print_header(title: str, width: int = 80):
    """Imprime um cabeçalho formatado."""
    print("\n" + "=" * width)
    print(f"  {title}")
    print("=" * width)


def print_section(title: str, width: int = 80):
    """Imprime uma seção formatada."""
    print("\n" + "-" * width)
    print(f"  {title}")
    print("-" * width)


def print_field(label: str, value: Any, indent: int = 0):
    """Imprime um campo formatado."""
    spaces = "  " * indent
    formatted = format_value(value)
    print(f"{spaces}{label:<30} {formatted}")


def analyze_document(doc: Any, index: int) -> Dict[str, Any]:
    """Analisa um documento e extrai informações relevantes."""
    doc_type = type(doc).__name__

    info = {
        "index": index,
        "tipo": doc_type,
        "arquivo": getattr(doc, "arquivo_origem", None),
        "numero_nota": getattr(doc, "numero_nota", None),
        "numero_documento": getattr(doc, "numero_documento", None),
        "numero_pedido": getattr(doc, "numero_pedido", None),
        "numero_fatura": getattr(doc, "numero_fatura", None),
        "referencia_nfse": getattr(doc, "referencia_nfse", None),
        "fornecedor": getattr(doc, "fornecedor_nome", None),
        "cnpj": getattr(doc, "cnpj_prestador", None) or getattr(doc, "cnpj_emitente", None) or getattr(doc, "cnpj_beneficiario", None),
        "valor_total": getattr(doc, "valor_total", None),
        "valor_documento": getattr(doc, "valor_documento", None),
        "vencimento": getattr(doc, "vencimento", None),
        "data_emissao": getattr(doc, "data_emissao", None),
    }

    return info


def print_document_details(doc_info: Dict[str, Any]):
    """Imprime detalhes de um documento."""
    print(f"\n  Documento #{doc_info['index']}: {doc_info['tipo']}")
    print(f"  {'─' * 76}")

    print_field("Arquivo:", doc_info["arquivo"], indent=1)

    # Campos de número
    if any([doc_info["numero_nota"], doc_info["numero_documento"],
            doc_info["numero_pedido"], doc_info["numero_fatura"],
            doc_info["referencia_nfse"]]):
        print(f"\n  {'Campos de Número:':<30}")
        if doc_info["numero_nota"]:
            print_field("numero_nota:", doc_info["numero_nota"], indent=2)
        if doc_info["numero_documento"]:
            print_field("numero_documento:", doc_info["numero_documento"], indent=2)
        if doc_info["numero_pedido"]:
            print_field("numero_pedido:", doc_info["numero_pedido"], indent=2)
        if doc_info["numero_fatura"]:
            print_field("numero_fatura:", doc_info["numero_fatura"], indent=2)
        if doc_info["referencia_nfse"]:
            print_field("referencia_nfse:", doc_info["referencia_nfse"], indent=2)

    # Outros campos importantes
    print(f"\n  {'Outros Campos:':<30}")
    print_field("fornecedor:", doc_info["fornecedor"], indent=2)
    print_field("CNPJ:", doc_info["cnpj"], indent=2)
    print_field("valor_total:", doc_info["valor_total"], indent=2)
    print_field("valor_documento:", doc_info["valor_documento"], indent=2)
    print_field("vencimento:", doc_info["vencimento"], indent=2)
    print_field("data_emissao:", doc_info["data_emissao"], indent=2)


def print_csv_row(summary: Dict[str, Any], use_colors: bool = True):
    """Imprime uma linha do CSV de forma formatada."""
    # Cores ANSI (se suportado)
    GREEN = "\033[92m" if use_colors else ""
    YELLOW = "\033[93m" if use_colors else ""
    RED = "\033[91m" if use_colors else ""
    RESET = "\033[0m" if use_colors else ""
    BOLD = "\033[1m" if use_colors else ""

    # Determina cor do status
    status = summary.get("status_conciliacao", "")
    if status == "OK":
        status_color = GREEN
    elif status == "DIVERGENTE":
        status_color = RED
    else:
        status_color = YELLOW

    print(f"\n  {BOLD}batch_id:{RESET}")
    print(f"    {summary.get('batch_id')}")

    print(f"\n  {BOLD}status_conciliacao:{RESET}")
    print(f"    {status_color}{status}{RESET}")

    if summary.get("divergencia"):
        print(f"\n  {BOLD}divergencia:{RESET}")
        print(f"    {YELLOW}{summary.get('divergencia')}{RESET}")

    print(f"\n  {BOLD}diferenca_valor:{RESET}")
    print(f"    {format_value(summary.get('diferenca_valor'))}")

    print(f"\n  {BOLD}fornecedor:{RESET}")
    print(f"    {summary.get('fornecedor')}")

    print(f"\n  {BOLD}vencimento:{RESET}")
    print(f"    {summary.get('vencimento')}")

    print(f"\n  {BOLD}numero_nota:{RESET}")
    nota = summary.get('numero_nota')
    if nota:
        print(f"    {GREEN}{nota}{RESET}")
    else:
        print(f"    {RED}(vazio){RESET}")

    print(f"\n  {BOLD}valor_compra:{RESET}")
    print(f"    {format_value(summary.get('valor_compra'))}")

    print(f"\n  {BOLD}valor_boleto:{RESET}")
    print(f"    {format_value(summary.get('valor_boleto'))}")

    print(f"\n  {BOLD}total_documents:{RESET}")
    print(f"    {summary.get('total_documents')}")

    print(f"\n  {BOLD}total_errors:{RESET}")
    print(f"    {summary.get('total_errors')}")

    print(f"\n  {BOLD}Contadores:{RESET}")
    print(f"    DANFEs:  {summary.get('danfes', 0)}")
    print(f"    Boletos: {summary.get('boletos', 0)}")
    print(f"    NFSes:   {summary.get('nfses', 0)}")
    print(f"    Outros:  {summary.get('outros', 0)}")

    print(f"\n  {BOLD}email_subject:{RESET}")
    print(f"    {summary.get('email_subject')}")

    print(f"\n  {BOLD}email_sender:{RESET}")
    print(f"    {summary.get('email_sender')}")

    print(f"\n  {BOLD}avisos:{RESET}")
    print(f"    {summary.get('avisos', 0)}")

    print(f"\n  {BOLD}source_folder:{RESET}")
    print(f"    {summary.get('source_folder')}")


def debug_batch(folder_path: str):
    """
    Processa um lote e mostra todos os detalhes do processamento.

    Args:
        folder_path: Caminho da pasta do lote (ex: temp_email/email_20260105_125518_4e51c5e2)
    """


    folder = Path(folder_path)

    if not folder.exists():
        print(f"❌ ERRO: Pasta não encontrada: {folder_path}")
        return 1

    if not folder.is_dir():
        print(f"❌ ERRO: O caminho não é uma pasta: {folder_path}")
        return 1

    print_header("DEBUG DE BATCH - Processamento de Documentos")
    print(f"\n📁 Pasta: {folder.absolute()}")

    # Processa o lote
    print("\n⏳ Processando lote...")
    processor = BatchProcessor()
    batch_result = processor.process_batch(folder)

    # Informações básicas do lote
    print_section("1. INFORMAÇÕES BÁSICAS DO LOTE")
    print_field("Batch ID:", batch_result.batch_id)
    print_field("Total de documentos:", batch_result.total_documents)
    print_field("Total de erros:", batch_result.total_errors)
    print_field("Assunto do email:", batch_result.email_subject)
    print_field("Remetente:", batch_result.email_sender)

    # Contadores por tipo
    print_section("2. DOCUMENTOS POR TIPO")
    print_field("DANFEs:", len(batch_result.danfes))
    print_field("NFSes:", len(batch_result.nfses))
    print_field("Boletos:", len(batch_result.boletos))
    print_field("Outros:", len(batch_result.outros))

    # Detalhes de cada documento
    print_section("3. DETALHES DOS DOCUMENTOS")
    all_docs_info = []
    for i, doc in enumerate(batch_result.documents, 1):
        doc_info = analyze_document(doc, i)
        all_docs_info.append(doc_info)
        print_document_details(doc_info)

    # Método 1: to_summary (antigo)
    print_section("4. MÉTODO 1: batch_result.to_summary() [LEGADO]")
    print("\n  ℹ️  Este é o método antigo que gera UMA linha por lote")
    print("      (usado quando não há múltiplas notas)")

    summary_legacy = batch_result.to_summary()
    print_csv_row(summary_legacy)

    # Método 2: Document Pairing (novo)
    print_section("5. MÉTODO 2: DocumentPairingService [NOVO - RECOMENDADO]")
    print("\n  ℹ️  Este método gera múltiplas linhas quando há múltiplas NFs")
    print("      e faz fallback correto do numero_nota")

    pairing_service = DocumentPairingService()
    pairs = pairing_service.pair_documents(batch_result)

    print(f"\n  📊 Total de pares gerados: {len(pairs)}")

    for i, pair in enumerate(pairs, 1):
        print(f"\n  {'─' * 76}")
        print(f"  Par #{i}")
        print(f"  {'─' * 76}")

        pair_summary = pair.to_summary()
        print_csv_row(pair_summary)

    # Comparação
    print_section("6. COMPARAÇÃO DOS MÉTODOS")

    print("\n  📌 Campos críticos:")
    print(f"\n  {'Campo':<25} {'Legado':<30} {'Pairing':<30}")
    print(f"  {'-' * 76}")

    pair_summary = pairs[0].to_summary() if pairs else {}

    fields_to_compare = [
        ("numero_nota", "Número da Nota"),
        ("fornecedor", "Fornecedor"),
        ("vencimento", "Vencimento"),
        ("valor_compra", "Valor Compra"),
        ("valor_boleto", "Valor Boleto"),
        ("status_conciliacao", "Status"),
    ]

    for field, label in fields_to_compare:
        legacy_val = format_value(summary_legacy.get(field))
        pairing_val = format_value(pair_summary.get(field))

        match = "✓" if legacy_val == pairing_val else "✗"
        print(f"  {label:<25} {legacy_val:<30} {pairing_val:<30} {match}")

    # Análise de fallbacks
    print_section("7. ANÁLISE DE FALLBACKS DE numero_nota")

    print("\n  🔍 Rastreamento de onde veio o numero_nota:")

    # Verifica cada documento
    for doc_info in all_docs_info:
        print(f"\n  Documento #{doc_info['index']} ({doc_info['tipo']}):")

        # Prioridade de campos
        fallback_chain = [
            ("numero_nota", doc_info["numero_nota"]),
            ("numero_pedido", doc_info["numero_pedido"]),
            ("numero_fatura", doc_info["numero_fatura"]),
            ("numero_documento", doc_info["numero_documento"]),
            ("referencia_nfse", doc_info["referencia_nfse"]),
        ]

        found = False
        for field_name, field_value in fallback_chain:
            if field_value:
                if not found:
                    print(f"    ✅ {field_name}: {field_value} [USADO]")
                    found = True
                else:
                    print(f"    ℹ️  {field_name}: {field_value} [ignorado]")
            else:
                print(f"    ❌ {field_name}: (vazio)")

        if not found:
            print(f"    ⚠️  Nenhum campo de número encontrado!")

    # Resultado final
    print(f"\n  {'─' * 76}")
    print(f"  📊 Resultado no CSV (numero_nota):")

    if pair_summary.get('numero_nota'):
        print(f"    ✅ {pair_summary.get('numero_nota')}")
    else:
        print(f"    ❌ (vazio) - ATENÇÃO: Verifique os documentos!")

    # Recomendações
    print_section("8. RECOMENDAÇÕES")

    warnings = []

    if not pair_summary.get('numero_nota'):
        warnings.append("⚠️  numero_nota está vazio! Verifique os extratores.")

    if summary_legacy.get('numero_nota') != pair_summary.get('numero_nota'):
        warnings.append("⚠️  Métodos legado e pairing retornam números diferentes!")

    if pair_summary.get('status_conciliacao') == 'DIVERGENTE':
        warnings.append("⚠️  Divergência de valores entre NF e Boleto!")

    if batch_result.total_errors > 0:
        warnings.append(f"⚠️  Há {batch_result.total_errors} erro(s) no processamento!")

    if warnings:
        print("\n  ⚠️  AVISOS:")
        for warning in warnings:
            print(f"    • {warning}")
    else:
        print("\n  ✅ Tudo OK! Nenhum aviso.")

    # Rodapé
    print_header("FIM DO DEBUG", 80)
    print("\n✅ Processamento concluído com sucesso!\n")

    return 0


def main():
    """Função principal do script."""
    if len(sys.argv) < 2:
        print("❌ ERRO: Você precisa fornecer o caminho da pasta!")
        print("\nUso:")
        print("  python debug_batch.py <caminho_da_pasta>")
        print("\nExemplos:")
        print("  python debug_batch.py temp_email/email_20260105_125518_4e51c5e2")
        print("  python debug_batch.py temp_email/email_20260105_125519_9b0b0752")
        print("  python debug_batch.py C:\\Users\\user\\Documents\\scrapper\\temp_email\\email_123")
        return 1

    folder_path = sys.argv[1]

    try:
        return debug_batch(folder_path)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrompido pelo usuário.")
        return 130
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
