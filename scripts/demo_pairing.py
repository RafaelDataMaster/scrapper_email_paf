#!/usr/bin/env python
"""
Demo: Pareamento de Documentos NF↔Boleto

Este script demonstra a funcionalidade de pareamento que resolve
o problema de múltiplas NFs no mesmo email e XMLs duplicados.

Casos testados:
1. MAIS CONSULTORIA - Múltiplas NFs com boletos (XML + PDF da mesma nota)
2. LOCAWEB - Pareamento por valor (sem número de nota)
3. MATRIXGO - XML + PDF demonstrativo (devem agrupar)
4. REPROMAQ - Documentos de locação com boleto
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.batch_result import BatchResult
from core.document_pairing import pair_batch_documents
from core.models import BoletoData, InvoiceData, OtherDocumentData


def demo_caso_mais_consultoria():
    """Demonstra o caso da MAIS CONSULTORIA com XMLs + PDFs da mesma nota."""
    print("=" * 70)
    print("DEMO: Caso MAIS CONSULTORIA (XMLs + PDFs duplicados)")
    print("=" * 70)
    print()

    batch = BatchResult(batch_id="email_20260105_125517_cc334d1b")
    batch.email_subject = "ENC: Mais Consultoria - NF 2025.119 e NF 2025.122"
    batch.email_sender = "rafael.ferreira@soumaster.com.br"

    # NF 2025.119 - XML
    xml1 = InvoiceData(
        arquivo_origem="01_nfse_202500000000119.xml",
        numero_nota="202500000000119",
        valor_total=9290.71,
        fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA",
        cnpj_prestador="18.363.307/0001-12",
        vencimento="2025-08-18",
        data_emissao="2025-08-01",
    )
    # NF 2025.119 - PDF
    pdf1 = InvoiceData(
        arquivo_origem="02_NF 2025.119.pdf",
        numero_nota="2025/119",
        valor_total=9290.71,
        fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA ed",
        cnpj_prestador="18.363.307/0001-12",
        vencimento="2025-08-18",
        data_emissao="2025-08-01",
    )
    # Boleto NF 2025.119
    boleto1 = BoletoData(
        arquivo_origem="03_BOLETO NF 2025.119.pdf",
        numero_documento="2025.119",
        valor_documento=9290.71,
        fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA",
        cnpj_beneficiario="18.363.307/0001-12",
        vencimento="2025-08-18",
    )

    # NF 2025.122 - XML
    xml2 = InvoiceData(
        arquivo_origem="04_nfse_202500000000122.xml",
        numero_nota="202500000000122",
        valor_total=6250.00,
        fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA",
        cnpj_prestador="18.363.307/0001-12",
        vencimento="2025-08-10",
        data_emissao="2025-08-01",
    )
    # NF 2025.122 - PDF
    pdf2 = InvoiceData(
        arquivo_origem="05_NF 2025.122.pdf",
        numero_nota="2025/122",
        valor_total=6250.00,
        fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA ed",
        cnpj_prestador="18.363.307/0001-12",
        vencimento="2025-08-10",
        data_emissao="2025-08-01",
    )
    # Boleto NF 2025.122
    boleto2 = BoletoData(
        arquivo_origem="06_BOLETO NF 2025.122.pdf",
        numero_documento="2025.122",
        valor_documento=6250.00,
        fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA",
        cnpj_beneficiario="18.363.307/0001-12",
        vencimento="2025-08-10",
    )

    # Adiciona documentos ao batch (6 documentos no total)
    batch.add_document(xml1)
    batch.add_document(pdf1)
    batch.add_document(boleto1)
    batch.add_document(xml2)
    batch.add_document(pdf2)
    batch.add_document(boleto2)

    print("📧 Email:", batch.email_subject)
    print("📄 Documentos no lote (6 arquivos):")
    for doc in batch.documents:
        tipo = "XML" if ".xml" in doc.arquivo_origem else "PDF"
        print(f"   - {doc.arquivo_origem} ({tipo})")
    print()

    # ANTES: Método antigo (to_summary)
    print("❌ ANTES (comportamento antigo gerava 4-6 linhas):")
    print("-" * 50)
    old_summary = batch.to_summary()
    print(f"   batch_id: {old_summary['batch_id']}")
    print(f"   valor_compra: R$ {old_summary['valor_compra']:,.2f} (só 1ª NF)")
    print(f"   valor_boleto: R$ {old_summary['valor_boleto']:,.2f} (soma todos)")
    diferenca = old_summary['valor_compra'] - old_summary['valor_boleto']
    print(f"   diferença: R$ {diferenca:,.2f}")
    print(f"   → Gerava múltiplas linhas divergentes!")
    print()

    # DEPOIS: Método novo (to_summaries)
    print("✅ DEPOIS (to_summaries) - Comportamento corrigido:")
    print("-" * 50)
    summaries = batch.to_summaries()
    print(f"   {len(summaries)} par(es) identificado(s) (deveria ser 2):\n")

    for i, summary in enumerate(summaries, 1):
        print(f"   PAR {i}:")
        print(f"      batch_id: {summary['batch_id']}")
        print(f"      numero_nota: {summary['numero_nota']}")
        print(f"      valor_compra: R$ {summary['valor_compra']:,.2f}")
        print(f"      valor_boleto: R$ {summary['valor_boleto']:,.2f}")
        print(f"      status: {summary['status_conciliacao']}")
        print()

    print("=" * 70)
    print()


def demo_caso_matrixgo():
    """Demonstra o caso MATRIXGO com XML + PDF demonstrativo."""
    print("=" * 70)
    print("DEMO: Caso MATRIXGO (XML + PDF demonstrativo)")
    print("=" * 70)
    print()

    batch = BatchResult(batch_id="email_20260105_125517_3253c973")
    batch.email_subject = "ENC: MATRIXGO - NFS-e + Boleto Nº 202500000002945"

    # XML da NFS-e
    xml = InvoiceData(
        arquivo_origem="02_202500000002945_20250812.xml",
        numero_nota="202500000002945",
        valor_total=45018.71,
        fornecedor_nome="MATRIXGO INTELIGENCIA ARTIFICIAL E SISTEMAS LTDA",
        cnpj_prestador="29.061.574/0001-51",
        vencimento="2025-08-28",
    )

    # PDF demonstrativo (mesmo valor, número diferente)
    pdf = InvoiceData(
        arquivo_origem="01_demonstrativo_nfse_202500000002945.pdf",
        numero_nota="01",  # Número errado extraído do PDF
        valor_total=11900.0,  # Valor parcial extraído
        fornecedor_nome="MATRIXGO INTELIGENCIA ARTIFICIAL E SISTEMAS LTDA",
        cnpj_prestador="29.061.574/0001-51",
        vencimento="2025-08-28",
    )

    # Boleto
    boleto = BoletoData(
        arquivo_origem="04_matrixgo_vencto_28_08_2025_doc_0000002945_bol_13503.pdf",
        numero_documento="109/00013503",
        referencia_nfse="202500000002945",
        valor_documento=45018.71,
        fornecedor_nome="SISTEMAS LTDA",
        vencimento="2025-08-28",
    )

    batch.add_document(xml)
    batch.add_document(pdf)
    batch.add_document(boleto)

    print("📧 Email:", batch.email_subject)
    print("📄 Documentos:")
    for doc in batch.documents:
        print(f"   - {doc.arquivo_origem}")
    print()

    summaries = batch.to_summaries()
    print(f"✅ Resultado: {len(summaries)} par(es)")
    print()

    for summary in summaries:
        print(f"   numero_nota: {summary['numero_nota']}")
        print(f"   valor_compra: R$ {summary['valor_compra']:,.2f}")
        print(f"   valor_boleto: R$ {summary['valor_boleto']:,.2f}")
        print(f"   status: {summary['status_conciliacao']}")

    print()
    print("=" * 70)
    print()


def demo_caso_repromaq():
    """Demonstra o caso REPROMAQ com documentos de locação."""
    print("=" * 70)
    print("DEMO: Caso REPROMAQ (Locação com documentos auxiliares)")
    print("=" * 70)
    print()

    batch = BatchResult(batch_id="email_20260105_125516_dd57f954")
    batch.email_subject = "ENC: Fechamento de Locação :11/2025 - CSC GESTAO INTEGRADA S/A"

    # Documento de locação (OUTRO)
    locacao = OtherDocumentData(
        arquivo_origem="01_A00003222.PDF",
        valor_total=2855.0,
        fornecedor_nome="REPROMAQ COMERCIO E SERVICOS DE TECNOLOGIA LTDA",
        vencimento="2025-07-31",
    )

    # Boleto
    boleto = BoletoData(
        arquivo_origem="02_BOLS081941_1_1.PDF",
        numero_documento="09",
        valor_documento=2855.0,
        fornecedor_nome="REPROMAQ COMERCIO E SERVICOS DE TECNOLOGIA LTDA",
        cnpj_beneficiario="22.527.311/0001-46",
        vencimento="2025-11-08",
    )

    # Atestado (documento auxiliar - deve ser ignorado)
    atestado = OtherDocumentData(
        arquivo_origem="03_RECS08194.PDF",
        valor_total=2855.0,
        fornecedor_nome="ATESTAMOS A REPROMAQ COMERCIO E SERVICOS DE TECNOLOGIA LTDA",
        vencimento=None,
    )

    batch.add_document(locacao)
    batch.add_document(boleto)
    batch.add_document(atestado)

    print("📧 Email:", batch.email_subject)
    print("📄 Documentos:")
    for doc in batch.documents:
        print(f"   - {doc.arquivo_origem}")
    print()

    summaries = batch.to_summaries()
    print(f"✅ Resultado: {len(summaries)} par(es) (atestado deve ser ignorado)")
    print()

    for summary in summaries:
        print(f"   fornecedor: {summary['fornecedor']}")
        print(f"   valor_compra: R$ {summary['valor_compra']:,.2f}")
        print(f"   valor_boleto: R$ {summary['valor_boleto']:,.2f}")
        print(f"   status: {summary['status_conciliacao']}")

    print()
    print("=" * 70)
    print()


def demo_caso_locaweb():
    """Demonstra o caso Locaweb (pareamento por valor)."""
    print("=" * 70)
    print("DEMO: Caso LOCAWEB (pareamento por valor)")
    print("=" * 70)
    print()

    batch = BatchResult(batch_id="email_20260105_125517_d6220072")
    batch.email_subject = "ENC: A sua fatura Locaweb já está disponível!"

    fatura = OtherDocumentData(
        arquivo_origem="02_Fatura Locaweb.pdf",
        valor_total=352.08,
        fornecedor_nome="LOCAWEB",
        vencimento="2025-09-01",
    )

    boleto = BoletoData(
        arquivo_origem="01_Boleto Locaweb.pdf",
        valor_documento=352.08,
        fornecedor_nome="Yapay a serviço de Locaweb S/A",
        cnpj_beneficiario="02.351.877/0001-52",
        vencimento="2025-09-01",
    )

    batch.add_document(fatura)
    batch.add_document(boleto)

    print("📧 Email:", batch.email_subject)
    print()

    summaries = batch.to_summaries()
    print(f"✅ Resultado: {len(summaries)} par identificado por VALOR")

    for summary in summaries:
        print(f"   valor_compra: R$ {summary['valor_compra']:,.2f}")
        print(f"   valor_boleto: R$ {summary['valor_boleto']:,.2f}")
        print(f"   status: {summary['status_conciliacao']}")

    print()
    print("=" * 70)


if __name__ == "__main__":
    print()
    print("🔄 DEMO: Sistema de Pareamento NF↔Boleto (Versão Corrigida)")
    print()

    demo_caso_mais_consultoria()
    demo_caso_matrixgo()
    demo_caso_repromaq()
    demo_caso_locaweb()

    print()
    print("✅ Demo concluída!")
    print()
