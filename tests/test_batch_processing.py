"""
Testes unitários para os módulos de processamento em lote (batch processing).

Este arquivo testa os novos módulos da refatoração:
- core/batch_processor.py (BatchProcessor)
- core/batch_result.py (BatchResult, CorrelationResult)
- core/correlation_service.py (CorrelationService)
- core/metadata.py (EmailMetadata)
- services/ingestion_service.py (IngestionService)

Princípios de teste:
- Cada teste é isolado e não depende de arquivos reais
- Usa mocks para simular PDFs e processamento
- Testa casos de sucesso e de falha
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.batch_processor import (
    BatchProcessor,
    process_email_batch,
    process_legacy_folder,
)
from core.batch_result import BatchResult, CorrelationResult
from core.correlation_service import CorrelationService, correlate_batch
from core.metadata import EmailMetadata
from core.models import BoletoData, DanfeData, InvoiceData, OtherDocumentData
from services.ingestion_service import IngestionService, create_batch_folder


class TestEmailMetadata(unittest.TestCase):
    """Testes para a classe EmailMetadata."""

    def setUp(self):
        """Cria diretório temporário para testes."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove diretório temporário."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_for_batch(self):
        """Testa criação de metadata para um lote."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="email_20251231_abc123",
            subject="NF 12345 - Pedido 98765",
            sender_name="Fornecedor XYZ",
            sender_address="nf@fornecedor.com",
        )

        self.assertEqual(metadata.batch_id, "email_20251231_abc123")
        self.assertEqual(metadata.email_subject, "NF 12345 - Pedido 98765")
        self.assertEqual(metadata.email_sender_name, "Fornecedor XYZ")
        self.assertEqual(metadata.email_sender_address, "nf@fornecedor.com")

    def test_save_and_load(self):
        """Testa salvar e carregar metadata."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test_batch",
            subject="Test Subject",
            sender_name="Test Sender",
        )

        # Salva
        folder = Path(self.temp_dir)
        metadata.save(folder)

        # Verifica que arquivo foi criado
        self.assertTrue((folder / "metadata.json").exists())

        # Carrega
        loaded = EmailMetadata.load(folder)

        self.assertEqual(loaded.batch_id, "test_batch")
        self.assertEqual(loaded.email_subject, "Test Subject")

    def test_load_nonexistent(self):
        """Testa carregar metadata de pasta sem arquivo."""
        folder = Path(self.temp_dir)
        loaded = EmailMetadata.load(folder)

        self.assertIsNone(loaded)

    def test_to_dict_and_json(self):
        """Testa conversão para dicionário e JSON."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Test",
        )

        d = metadata.to_dict()
        self.assertIn("batch_id", d)
        self.assertIn("email_subject", d)

        j = metadata.to_json()
        self.assertIn("batch_id", j)

    def test_create_legacy(self):
        """Testa criação de metadata legado."""
        metadata = EmailMetadata.create_legacy(
            batch_id="legacy_test",
            file_paths=["file1.pdf", "file2.pdf"],
        )

        self.assertEqual(metadata.batch_id, "legacy_test")
        self.assertTrue(metadata.is_legacy)
        self.assertEqual(len(metadata.attachments), 2)

    def test_get_fallback_fornecedor(self):
        """Testa fallback de fornecedor usando email_sender_name."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            sender_name="Distribuidora ABC LTDA",
        )

        fallback = metadata.get_fallback_fornecedor()
        self.assertEqual(fallback, "Distribuidora ABC LTDA")

    def test_extract_cnpj_from_body(self):
        """Testa extração de CNPJ do corpo do e-mail."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Prezados, segue NF referente ao CNPJ 12.345.678/0001-90",
        )

        cnpj = metadata.extract_cnpj_from_body()
        self.assertEqual(cnpj, "12.345.678/0001-90")

    def test_extract_cnpj_from_body_not_found(self):
        """Testa extração de CNPJ quando não existe."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Prezados, segue a nota fiscal.",
        )

        cnpj = metadata.extract_cnpj_from_body()
        self.assertIsNone(cnpj)

    def test_extract_numero_pedido_from_context(self):
        """Testa extração de número de pedido do contexto."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="NF 12345 - Pedido 98765",
        )

        pedido = metadata.extract_numero_pedido_from_context()
        self.assertEqual(pedido, "98765")

    def test_extract_numero_pedido_ordem(self):
        """Testa extração de número de pedido com 'OC' ou 'Ordem'."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Fatura ref. OC 54321",
        )

        pedido = metadata.extract_numero_pedido_from_context()
        self.assertEqual(pedido, "54321")

    def test_extract_vencimento_from_context_basic(self):
        """Testa extração de vencimento do corpo do e-mail."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Segue nota fiscal. Vencimento: 15/01/2025. Att.",
        )

        vencimento = metadata.extract_vencimento_from_context()
        self.assertEqual(vencimento, "15/01/2025")

    def test_extract_vencimento_from_context_vencimento_em(self):
        """Testa extração com 'vencimento em DD/MM/YYYY' (padrão Asaas/Power Tuning)."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="A POWER TUNING - COBRANÇA gerou uma fatura no valor de R$ 4.748,86 com vencimento em 18/12/2025.",
        )

        vencimento = metadata.extract_vencimento_from_context()
        self.assertEqual(vencimento, "18/12/2025")

    def test_extract_vencimento_from_context_vencto(self):
        """Testa extração de vencimento com abreviação 'Vencto'."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Boleto anexo. Vencto: 20-02-2025",
        )

        vencimento = metadata.extract_vencimento_from_context()
        self.assertEqual(vencimento, "20/02/2025")

    def test_extract_vencimento_from_context_data_vencimento(self):
        """Testa extração com 'Data de vencimento'."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Data de vencimento: 05.03.2025",
        )

        vencimento = metadata.extract_vencimento_from_context()
        self.assertEqual(vencimento, "05/03/2025")

    def test_extract_vencimento_from_context_vence_em(self):
        """Testa extração com 'Vence em'."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Fatura - Vence em 10/04/2025",
        )

        vencimento = metadata.extract_vencimento_from_context()
        self.assertEqual(vencimento, "10/04/2025")

    def test_extract_vencimento_from_context_pagar_ate(self):
        """Testa extração com 'Pagar até'."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Favor pagar até 25/12/2025",
        )

        vencimento = metadata.extract_vencimento_from_context()
        self.assertEqual(vencimento, "25/12/2025")

    def test_extract_vencimento_from_context_ano_curto(self):
        """Testa extração com ano de 2 dígitos."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Vencimento: 15/06/25",
        )

        vencimento = metadata.extract_vencimento_from_context()
        self.assertEqual(vencimento, "15/06/2025")

    def test_extract_vencimento_from_context_not_found(self):
        """Testa quando não há vencimento no contexto."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Segue nota fiscal em anexo. Atenciosamente.",
        )

        vencimento = metadata.extract_vencimento_from_context()
        self.assertIsNone(vencimento)

    def test_normalize_date_various_formats(self):
        """Testa normalização de diferentes formatos de data."""
        metadata = EmailMetadata.create_for_batch(batch_id="test")

        # DD/MM/YYYY
        self.assertEqual(metadata._normalize_date("15/01/2025"), "15/01/2025")
        # DD-MM-YYYY
        self.assertEqual(metadata._normalize_date("15-01-2025"), "15/01/2025")
        # DD.MM.YYYY
        self.assertEqual(metadata._normalize_date("15.01.2025"), "15/01/2025")
        # D/M/YYYY (sem zeros)
        self.assertEqual(metadata._normalize_date("5/1/2025"), "05/01/2025")
        # DD/MM/YY
        self.assertEqual(metadata._normalize_date("15/01/25"), "15/01/2025")
        # Ano antigo (ex: 99 -> 1999)
        self.assertEqual(metadata._normalize_date("15/01/99"), "15/01/1999")

    def test_normalize_date_invalid(self):
        """Testa normalização com datas inválidas."""
        metadata = EmailMetadata.create_for_batch(batch_id="test")

        # Dia inválido
        self.assertIsNone(metadata._normalize_date("32/01/2025"))
        # Mês inválido
        self.assertIsNone(metadata._normalize_date("15/13/2025"))
        # Formato errado
        self.assertIsNone(metadata._normalize_date("2025-01-15"))
        # Vazio
        self.assertIsNone(metadata._normalize_date(""))
        # None
        self.assertIsNone(metadata._normalize_date(None))

    def test_extract_numero_nota_from_context_fatura(self):
        """Testa extração de número de fatura do assunto."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Fatura 50446 - EMC Tecnologia",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertEqual(numero, "50446")

    def test_extract_numero_nota_from_context_fatura_com_numero(self):
        """Testa extração de fatura com 'Nº'."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Fatura Nº 12345 - Empresa XYZ",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertEqual(numero, "12345")

    def test_extract_numero_nota_from_context_nf(self):
        """Testa extração de NF do assunto."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="NF 123456789 emitida",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertEqual(numero, "123456789")

    def test_extract_numero_nota_from_context_nfe(self):
        """Testa extração de NF-e do assunto."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="NF-e 987654321 disponível",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertEqual(numero, "987654321")

    def test_extract_numero_nota_from_context_nfse(self):
        """Testa extração de NFS-e do assunto."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="NFS-e 54321 - Serviços",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertEqual(numero, "54321")

    def test_extract_numero_nota_from_context_nota_fiscal(self):
        """Testa extração de 'Nota Fiscal' do assunto."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Nota Fiscal 99999 emitida",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertEqual(numero, "99999")

    def test_extract_numero_nota_from_context_padrao_composto(self):
        """Testa extração de padrão composto ano/sequencial (2025/44)."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Referente à nota 2025/44",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertEqual(numero, "2025/44")

    def test_extract_numero_nota_from_context_padrao_composto_hifen(self):
        """Testa extração de padrão composto ano-sequencial (2025-44)."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Segue NFS-e referente à nota fatura 2025-123. Att.",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertEqual(numero, "2025-123")

    def test_extract_numero_nota_from_context_numero_simbolo(self):
        """Testa extração de 'Nº: 50446' do corpo."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Documento Nº: 50446 disponível para download.",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertEqual(numero, "50446")

    def test_extract_numero_nota_from_context_prioriza_assunto(self):
        """Testa que assunto tem prioridade sobre corpo."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Fatura 11111 - Empresa",
            body_text="Segue fatura. Nº: 22222. Att.",
        )

        numero = metadata.extract_numero_nota_from_context()
        # Deve pegar do assunto (11111), não do corpo (22222)
        self.assertEqual(numero, "11111")

    def test_extract_numero_nota_from_context_not_found(self):
        """Testa quando não há número de nota no contexto."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Documentos anexos",
            body_text="Segue documentos. Att.",
        )

        numero = metadata.extract_numero_nota_from_context()
        self.assertIsNone(numero)

    def test_extract_numero_nota_from_context_ignora_ano_isolado(self):
        """Testa que ano isolado (2025) não é extraído como número de nota."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Documentos 2025",
            body_text="Referente ao ano de 2025.",
        )

        numero = metadata.extract_numero_nota_from_context()
        # Não deve retornar "2025" como número de nota
        self.assertIsNone(numero)

    def test_extract_numero_nota_from_context_ignora_urls_imagem(self):
        """Testa que URLs de imagem não geram falsos positivos (caso Locaweb)."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="A sua fatura Locaweb já está disponível!",
            body_text="""
            <https://locaweb.com.br/>
            Central do Cliente <http://assets.locaweb.com.br/geradoremailmkt/images/2017-01-20-b.png>
            A sua fatura Locaweb já está disponível!
            Olá, CSC GESTAO INTEGRADA S/A!
            fatura da sua conta Locaweb, com vencimento para o dia 01/09/2025
            <http://assets.locaweb.com.br/geradoremailmkt/images/2017-01-24-f.png>
            """,
        )

        numero = metadata.extract_numero_nota_from_context()
        # Não deve retornar "2017-01" de URLs de imagem
        self.assertIsNone(numero)

    def test_extract_numero_nota_from_context_locaweb_sem_numero(self):
        """Testa que fatura Locaweb sem número retorna None (não tem NF tradicional)."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="ENC: A sua fatura Locaweb já está disponível!",
            body_text="Gostaríamos de informar que a fatura da sua conta Locaweb está disponível.",
        )

        numero = metadata.extract_numero_nota_from_context()
        # Locaweb não tem número de NF tradicional
        self.assertIsNone(numero)


class TestBatchResult(unittest.TestCase):
    """Testes para a classe BatchResult."""

    def test_create_empty(self):
        """Testa criação de resultado vazio."""
        result = BatchResult(batch_id="test_batch")

        self.assertEqual(result.batch_id, "test_batch")
        self.assertEqual(len(result.documents), 0)
        self.assertEqual(len(result.errors), 0)
        self.assertTrue(result.is_empty)

    def test_add_document(self):
        """Testa adição de documentos."""
        result = BatchResult(batch_id="test")

        danfe = DanfeData(arquivo_origem="test.pdf")
        result.add_document(danfe)

        self.assertEqual(result.total_documents, 1)
        self.assertFalse(result.is_empty)

    def test_add_error(self):
        """Testa registro de erros."""
        result = BatchResult(batch_id="test")

        result.add_error("file.pdf", "Erro de processamento")

        self.assertEqual(result.total_errors, 1)
        self.assertEqual(result.errors[0]["file"], "file.pdf")

    def test_filter_by_type(self):
        """Testa filtros por tipo de documento."""
        result = BatchResult(batch_id="test")

        result.add_document(DanfeData(arquivo_origem="d1.pdf"))
        result.add_document(DanfeData(arquivo_origem="d2.pdf"))
        result.add_document(BoletoData(arquivo_origem="b1.pdf"))
        result.add_document(InvoiceData(arquivo_origem="n1.pdf"))

        self.assertEqual(len(result.danfes), 2)
        self.assertEqual(len(result.boletos), 1)
        self.assertEqual(len(result.nfses), 1)

    def test_has_danfe_boleto(self):
        """Testa verificação de presença de tipos."""
        result = BatchResult(batch_id="test")

        self.assertFalse(result.has_danfe)
        self.assertFalse(result.has_boleto)

        result.add_document(DanfeData(arquivo_origem="d.pdf"))
        self.assertTrue(result.has_danfe)

        result.add_document(BoletoData(arquivo_origem="b.pdf"))
        self.assertTrue(result.has_boleto)

    def test_get_valor_total_danfes(self):
        """Testa soma de valores das DANFEs."""
        result = BatchResult(batch_id="test")

        result.add_document(DanfeData(arquivo_origem="d1.pdf", valor_total=1000.0))
        result.add_document(DanfeData(arquivo_origem="d2.pdf", valor_total=500.0))

        self.assertAlmostEqual(result.get_valor_total_danfes(), 1500.0, places=2)

    def test_get_valor_total_boletos(self):
        """Testa soma de valores dos Boletos."""
        result = BatchResult(batch_id="test")

        result.add_document(BoletoData(arquivo_origem="b1.pdf", valor_documento=200.0))
        result.add_document(BoletoData(arquivo_origem="b2.pdf", valor_documento=300.0))

        self.assertAlmostEqual(result.get_valor_total_boletos(), 500.0, places=2)

    def test_get_valor_compra_prioriza_nfse(self):
        """Testa que valor_compra prioriza NFS-e sobre outros tipos."""
        result = BatchResult(batch_id="test")

        # Adiciona na ordem inversa de prioridade
        result.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=500.0))
        result.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        result.add_document(InvoiceData(arquivo_origem="n.pdf", valor_total=1500.0))

        # Deve pegar o valor da NFS-e (maior prioridade)
        self.assertAlmostEqual(result.get_valor_compra(), 1500.0, places=2)

    def test_get_valor_compra_usa_boleto_quando_nao_tem_nota(self):
        """Testa que valor_compra usa boleto quando não há notas."""
        result = BatchResult(batch_id="test")

        result.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=800.0))

        # Sem notas, usa boleto
        self.assertAlmostEqual(result.get_valor_compra(), 800.0, places=2)

    def test_to_summary(self):
        """Testa geração de resumo."""
        result = BatchResult(
            batch_id="test",
            source_folder="/path/to/batch",
            email_subject="Test Subject",
            email_sender="Sender Name",
        )
        result.add_document(DanfeData(
            arquivo_origem="d.pdf",
            valor_total=1000.0,
            fornecedor_nome="Fornecedor Teste LTDA",
            vencimento="2024-12-31",
            numero_nota="12345",
        ))
        result.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        summary = result.to_summary()

        self.assertEqual(summary["batch_id"], "test")
        self.assertEqual(summary["total_documents"], 2)
        self.assertEqual(summary["danfes"], 1)
        self.assertEqual(summary["boletos"], 1)
        self.assertEqual(summary["email_subject"], "Test Subject")
        # Novos campos para integração com Google Sheets
        self.assertEqual(summary["fornecedor"], "Fornecedor Teste LTDA")
        self.assertEqual(summary["vencimento"], "2024-12-31")
        self.assertEqual(summary["numero_nota"], "12345")

    def test_to_summary_prioriza_nfse_para_numero_nota(self):
        """Testa se numero_nota prioriza NFS-e sobre DANFE e Boleto."""
        result = BatchResult(batch_id="test_prioridade")

        # Adiciona boleto primeiro (menor prioridade)
        result.add_document(BoletoData(
            arquivo_origem="b.pdf",
            valor_documento=500.0,
            numero_documento="BOL-999",
        ))
        # Adiciona DANFE (prioridade média)
        result.add_document(DanfeData(
            arquivo_origem="d.pdf",
            valor_total=1000.0,
            numero_nota="DANFE-456",
        ))
        # Adiciona NFS-e (maior prioridade)
        result.add_document(InvoiceData(
            arquivo_origem="n.pdf",
            valor_total=1500.0,
            numero_nota="NFSE-123",
        ))

        summary = result.to_summary()

        # Deve priorizar NFS-e
        self.assertEqual(summary["numero_nota"], "NFSE-123")


class TestCorrelationServicePropagation(unittest.TestCase):
    """Testes para propagação de status_conciliacao e valor_compra."""

    def test_propagate_status_conciliacao_ok(self):
        """Testa propagação de status OK para documentos."""
        batch = BatchResult(batch_id="test_prop_ok")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        service = CorrelationService()
        result = service.correlate(batch)

        # Verifica propagação para todos os documentos
        for doc in batch.documents:
            self.assertEqual(doc.status_conciliacao, "CONCILIADO")
            # valor_compra é o valor da nota (1000.0)
            self.assertEqual(doc.valor_compra, 1000.0)

    def test_propagate_status_conciliacao_divergente(self):
        """Testa propagação de status DIVERGENTE para documentos."""
        batch = BatchResult(batch_id="test_prop_div")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1500.0))

        service = CorrelationService()
        result = service.correlate(batch)

        # Verifica propagação para todos os documentos
        for doc in batch.documents:
            self.assertEqual(doc.status_conciliacao, "DIVERGENTE")
            # valor_compra é o valor da nota (1000.0)
            self.assertEqual(doc.valor_compra, 1000.0)

    def test_propagate_status_conciliacao_conferir(self):
        """Testa propagação de status CONFERIR para nota sem boleto."""
        batch = BatchResult(batch_id="test_prop_conferir")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=500.0))

        service = CorrelationService()
        result = service.correlate(batch)

        danfe = batch.danfes[0]
        self.assertEqual(danfe.status_conciliacao, "CONFERIR")
        self.assertEqual(danfe.valor_compra, 500.0)

    def test_to_dict_includes_new_fields(self):
        """Testa que to_dict inclui os novos campos."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        service = CorrelationService()
        service.correlate(batch)

        danfe = batch.danfes[0]
        d = danfe.to_dict()

        self.assertIn("status_conciliacao", d)
        self.assertIn("valor_compra", d)

    def test_to_summary_includes_correlation_data(self):
        """Testa que to_summary inclui dados de correlação."""
        batch = BatchResult(batch_id="test_summary")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        service = CorrelationService()
        result = service.correlate(batch)
        batch.correlation_result = result

        summary = batch.to_summary()

        self.assertIn("status_conciliacao", summary)
        self.assertEqual(summary["status_conciliacao"], "CONCILIADO")

    def test_batch_result_stores_correlation_result(self):
        """Testa que BatchResult armazena CorrelationResult."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        service = CorrelationService()
        result = service.correlate(batch)

        batch.correlation_result = result

        self.assertIsNotNone(batch.correlation_result)
        self.assertEqual(batch.correlation_result.status, "CONCILIADO")


class TestCorrelationResult(unittest.TestCase):
    """Testes para a classe CorrelationResult."""

    def test_create_ok(self):
        """Testa criação de resultado OK."""
        result = CorrelationResult(
            batch_id="test",
            status="CONCILIADO",
            valor_compra=1000.0,
            valor_boleto=1000.0,
            diferenca=0.0,
        )

        self.assertTrue(result.is_ok())
        self.assertFalse(result.is_divergente())
        self.assertFalse(result.is_conferir())

    def test_create_divergente(self):
        """Testa criação de resultado DIVERGENTE."""
        result = CorrelationResult(
            batch_id="test",
            status="DIVERGENTE",
            divergencia="Valores não batem",
            valor_compra=1000.0,
            valor_boleto=800.0,
            diferenca=200.0,
        )

        self.assertFalse(result.is_ok())
        self.assertTrue(result.is_divergente())
        self.assertEqual(result.divergencia, "Valores não batem")

    def test_create_conferir(self):
        """Testa criação de resultado CONFERIR (sem boleto)."""
        result = CorrelationResult(
            batch_id="test",
            status="CONFERIR",
            divergencia="Conferir valor - sem boleto para comparação",
            valor_compra=1000.0,
            valor_boleto=0.0,
        )

        self.assertFalse(result.is_ok())
        self.assertTrue(result.is_conferir())


class TestCorrelationService(unittest.TestCase):
    """Testes para a classe CorrelationService."""

    def test_correlate_danfe_boleto_valores_iguais(self):
        """Testa correlação com valores iguais (CONCILIADO)."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        service = CorrelationService()
        result = service.correlate(batch)

        self.assertEqual(result.status, "CONCILIADO")
        self.assertAlmostEqual(result.diferenca, 0.0, places=2)

    def test_correlate_danfe_boleto_valores_divergentes(self):
        """Testa correlação com valores divergentes."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=800.0))

        service = CorrelationService()
        result = service.correlate(batch)

        self.assertEqual(result.status, "DIVERGENTE")
        self.assertAlmostEqual(result.diferenca, 200.0, places=2)

    def test_correlate_nota_sem_boleto(self):
        """Testa correlação de nota sem boleto -> CONFERIR."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))

        service = CorrelationService()
        result = service.correlate(batch)

        self.assertEqual(result.status, "CONFERIR")
        self.assertIn("sem boleto", result.divergencia)

    def test_correlate_empty_batch(self):
        """Testa correlação de lote vazio."""
        batch = BatchResult(batch_id="test")

        service = CorrelationService()
        result = service.correlate(batch)

        # Lote vazio sem boleto = CONFERIR
        self.assertEqual(result.status, "CONFERIR")

    def test_heranca_numero_nota(self):
        """Testa herança de numero_nota para Boleto."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(
            arquivo_origem="d.pdf",
            numero_nota="12345",
            valor_total=1000.0,
        ))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        service = CorrelationService()
        service.correlate(batch)

        # Boleto deve ter herdado numero_nota
        boleto = batch.boletos[0]
        self.assertEqual(boleto.referencia_nfse, "12345")

    def test_heranca_vencimento(self):
        """Testa herança de vencimento para DANFE."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(
            arquivo_origem="b.pdf",
            valor_documento=1000.0,
            vencimento="2024-12-31",
        ))

        service = CorrelationService()
        service.correlate(batch)

        # DANFE deve ter herdado vencimento
        danfe = batch.danfes[0]
        self.assertEqual(danfe.vencimento, "2024-12-31")

    def test_enrich_from_metadata_fallback_fornecedor(self):
        """Testa enriquecimento com fallback de fornecedor."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            sender_name="Distribuidora ABC",
        )

        service = CorrelationService()
        service.correlate(batch, metadata)

        # Documentos sem fornecedor devem ter herdado do metadata
        danfe = batch.danfes[0]
        self.assertEqual(danfe.fornecedor_nome, "Distribuidora ABC")

    def test_enrich_from_metadata_cnpj(self):
        """Testa enriquecimento com CNPJ do corpo do e-mail."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Referente ao CNPJ 12.345.678/0001-90",
        )

        service = CorrelationService()
        service.correlate(batch, metadata)

        # Documentos sem CNPJ devem ter herdado do metadata
        danfe = batch.danfes[0]
        self.assertEqual(danfe.cnpj_emitente, "12.345.678/0001-90")

    def test_enrich_from_metadata_vencimento(self):
        """Testa enriquecimento com vencimento do corpo do e-mail."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Segue nota fiscal. Vencimento: 15/01/2025. Att.",
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # Documentos sem vencimento devem ter herdado do email (formato ISO)
        danfe = batch.danfes[0]
        self.assertEqual(danfe.vencimento, "2025-01-15")

        # Vencimento deve estar registrado no resultado (formato ISO)
        self.assertEqual(result.vencimento_herdado, "2025-01-15")

    def test_enrich_from_metadata_vencimento_subject(self):
        """Testa extração de vencimento do assunto do e-mail."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="NF 12345 - Vencto: 20/02/2025",
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # DANFE deve ter herdado vencimento do assunto (formato ISO)
        danfe = batch.danfes[0]
        self.assertEqual(danfe.vencimento, "2025-02-20")

    def test_vencimento_boleto_prioridade_sobre_email(self):
        """Testa que vencimento do boleto tem prioridade sobre email."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(
            arquivo_origem="b.pdf",
            valor_documento=1000.0,
            vencimento="31/12/2024"  # Vencimento do boleto
        ))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Vencimento: 15/01/2025",  # Vencimento do email (diferente)
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # DANFE deve ter herdado vencimento do BOLETO, não do email
        danfe = batch.danfes[0]
        self.assertEqual(danfe.vencimento, "31/12/2024")
        self.assertEqual(result.vencimento_herdado, "31/12/2024")

    def test_vencimento_email_fallback_quando_boleto_sem_vencimento(self):
        """Testa que vencimento do email é usado quando boleto não tem."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(
            arquivo_origem="b.pdf",
            valor_documento=1000.0,
            # Sem vencimento no boleto
        ))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Pagar até 25/03/2025",
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # DANFE deve ter herdado vencimento do EMAIL (fallback, formato ISO)
        danfe = batch.danfes[0]
        self.assertEqual(danfe.vencimento, "2025-03-25")
        self.assertEqual(result.vencimento_herdado, "2025-03-25")

    def test_vencimento_nao_sobrescreve_existente(self):
        """Testa que vencimento do email não sobrescreve valor já existente."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(
            arquivo_origem="d.pdf",
            valor_total=1000.0,
            vencimento="10/10/2024"  # Já tem vencimento
        ))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            body_text="Vencimento: 15/01/2025",  # Diferente do documento
        )

        service = CorrelationService()
        service.correlate(batch, metadata)

        # DANFE deve manter seu vencimento original
        danfe = batch.danfes[0]
        self.assertEqual(danfe.vencimento, "10/10/2024")

    def test_numero_nota_fallback_from_email_fatura(self):
        """Testa fallback de numero_nota do assunto do e-mail (Fatura)."""
        batch = BatchResult(batch_id="test")
        # Documento sem numero_nota
        batch.add_document(OtherDocumentData(
            arquivo_origem="fatura.pdf",
            valor_total=500.0
        ))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Fatura 50446 - EMC Tecnologia",
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # Documento deve ter herdado numero_nota do e-mail
        doc = batch.outros[0]
        self.assertEqual(doc.numero_documento, "50446")

        # Resultado deve registrar a herança e fonte
        self.assertEqual(result.numero_nota_herdado, "50446")
        self.assertEqual(result.numero_nota_fonte, "email")

    def test_numero_nota_fallback_from_email_nfse(self):
        """Testa fallback de numero_nota do assunto do e-mail (NFS-e)."""
        batch = BatchResult(batch_id="test")
        # InvoiceData (NFS-e) sem numero_nota
        batch.add_document(InvoiceData(
            arquivo_origem="nfse.pdf",
            valor_total=1500.0
        ))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="NFS-e 12345 emitida",
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # NFS-e deve ter herdado numero_nota do e-mail
        nfse = batch.nfses[0]
        self.assertEqual(nfse.numero_nota, "12345")

        self.assertEqual(result.numero_nota_herdado, "12345")
        self.assertEqual(result.numero_nota_fonte, "email")

    def test_numero_nota_documento_prioridade_sobre_email(self):
        """Testa que numero_nota do documento tem prioridade sobre e-mail."""
        batch = BatchResult(batch_id="test")
        # DANFE com numero_nota preenchido
        batch.add_document(DanfeData(
            arquivo_origem="danfe.pdf",
            valor_total=1000.0,
            numero_nota="999999"  # Número do documento
        ))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Fatura 11111 - Empresa",  # Número diferente no e-mail
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # DANFE deve manter seu numero_nota original
        danfe = batch.danfes[0]
        self.assertEqual(danfe.numero_nota, "999999")

        # Não deve ter usado fallback do e-mail
        self.assertIsNone(result.numero_nota_fonte)

    def test_numero_nota_fallback_padrao_composto(self):
        """Testa fallback de numero_nota com padrão composto (2025/44)."""
        batch = BatchResult(batch_id="test")
        batch.add_document(InvoiceData(
            arquivo_origem="nfse.pdf",
            valor_total=800.0
        ))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Nota Fatura - 2025/44",
            body_text="Referente ao documento. Att.",
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # Deve ter extraído o padrão composto
        nfse = batch.nfses[0]
        self.assertEqual(nfse.numero_nota, "2025/44")

        self.assertEqual(result.numero_nota_herdado, "2025/44")
        self.assertEqual(result.numero_nota_fonte, "email")

    def test_numero_nota_nao_sobrescreve_existente(self):
        """Testa que fallback não sobrescreve numero_nota existente em nenhum doc."""
        batch = BatchResult(batch_id="test")
        # DANFE com numero_nota
        batch.add_document(DanfeData(
            arquivo_origem="danfe.pdf",
            valor_total=1000.0,
            numero_nota="111111"
        ))
        # Boleto sem numero_documento
        batch.add_document(BoletoData(
            arquivo_origem="boleto.pdf",
            valor_documento=1000.0
        ))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Fatura 99999",
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # DANFE deve manter seu numero_nota
        danfe = batch.danfes[0]
        self.assertEqual(danfe.numero_nota, "111111")

        # Não deve ter usado fallback (já tinha numero_nota no lote)
        self.assertIsNone(result.numero_nota_fonte)

    def test_numero_nota_fallback_propaga_para_todos_docs(self):
        """Testa que fallback propaga numero_nota para todos os docs sem número."""
        batch = BatchResult(batch_id="test")
        # Múltiplos documentos sem numero_nota
        batch.add_document(InvoiceData(
            arquivo_origem="nfse.pdf",
            valor_total=500.0
        ))
        batch.add_document(BoletoData(
            arquivo_origem="boleto.pdf",
            valor_documento=500.0
        ))
        batch.add_document(OtherDocumentData(
            arquivo_origem="outro.pdf",
            valor_total=0.0
        ))

        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Fatura 77777 - Empresa",
        )

        service = CorrelationService()
        result = service.correlate(batch, metadata)

        # Todos os documentos devem ter recebido o numero_nota
        self.assertEqual(batch.nfses[0].numero_nota, "77777")
        self.assertEqual(batch.boletos[0].numero_documento, "77777")
        self.assertEqual(batch.outros[0].numero_documento, "77777")

        self.assertEqual(result.numero_nota_herdado, "77777")
        self.assertEqual(result.numero_nota_fonte, "email")

    def test_correlate_batch_utility_function(self):
        """Testa função utilitária correlate_batch."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        result = correlate_batch(batch)

        self.assertEqual(result.batch_id, "test")


class TestBatchProcessor(unittest.TestCase):
    """Testes para a classe BatchProcessor."""

    def setUp(self):
        """Cria diretório temporário para testes."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove diretório temporário."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_with_defaults(self):
        """Testa criação com valores padrão."""
        processor = BatchProcessor()

        self.assertIsNotNone(processor.processor)
        self.assertIsNotNone(processor.correlation_service)

    def test_create_with_custom_dependencies(self):
        """Testa injeção de dependências (DIP)."""
        mock_processor = MagicMock()
        mock_correlation = MagicMock()

        batch_processor = BatchProcessor(
            processor=mock_processor,
            correlation_service=mock_correlation,
        )

        self.assertEqual(batch_processor.processor, mock_processor)
        self.assertEqual(batch_processor.correlation_service, mock_correlation)

    def test_process_batch_empty_folder(self):
        """Testa processamento de pasta vazia."""
        batch_folder = Path(self.temp_dir) / "empty_batch"
        batch_folder.mkdir()

        processor = BatchProcessor()
        result = processor.process_batch(batch_folder)

        self.assertEqual(result.batch_id, "empty_batch")
        self.assertTrue(result.is_empty)

    def test_process_batch_with_metadata(self):
        """Testa processamento de pasta com metadata.json."""
        batch_folder = Path(self.temp_dir) / "test_batch"
        batch_folder.mkdir()

        # Cria metadata
        metadata = EmailMetadata.create_for_batch(
            batch_id="test_batch",
            subject="Test Subject",
            sender_name="Test Sender",
        )
        metadata.save(batch_folder)

        processor = BatchProcessor()
        result = processor.process_batch(batch_folder)

        self.assertEqual(result.email_subject, "Test Subject")
        self.assertEqual(result.email_sender, "Test Sender")

    @patch.object(BatchProcessor, '_process_single_file')
    def test_process_batch_with_pdf(self, mock_process):
        """Testa processamento de pasta com PDF."""
        batch_folder = Path(self.temp_dir) / "pdf_batch"
        batch_folder.mkdir()

        # Cria arquivo PDF fake
        (batch_folder / "test.pdf").write_bytes(b"%PDF-1.4 test")

        # Mock retorna um documento
        mock_process.return_value = DanfeData(arquivo_origem="test.pdf")

        processor = BatchProcessor()
        result = processor.process_batch(batch_folder)

        self.assertEqual(result.total_documents, 1)
        mock_process.assert_called_once()

    def test_is_processable_accepts_pdf_xml(self):
        """Testa que apenas PDF e XML são aceitos."""
        processor = BatchProcessor()

        self.assertTrue(processor._is_processable(Path("test.pdf")))
        self.assertTrue(processor._is_processable(Path("test.PDF")))
        self.assertTrue(processor._is_processable(Path("test.xml")))
        self.assertTrue(processor._is_processable(Path("test.XML")))

    def test_is_processable_ignores_metadata(self):
        """Testa que metadata.json é ignorado."""
        processor = BatchProcessor()

        self.assertFalse(processor._is_processable(Path("metadata.json")))

    def test_is_processable_rejects_ignored_folder(self):
        """Testa que arquivos na pasta 'ignored' são rejeitados."""
        processor = BatchProcessor()

        self.assertFalse(processor._is_processable(
            Path("batch/ignored/file.pdf")
        ))

    @patch.object(BatchProcessor, '_process_single_file')
    def test_process_multiple_batches(self, mock_process):
        """Testa processamento de múltiplos lotes."""
        root_folder = Path(self.temp_dir)

        # Cria 3 subpastas (lotes)
        for i in range(3):
            batch_folder = root_folder / f"batch_{i}"
            batch_folder.mkdir()
            (batch_folder / f"doc_{i}.pdf").write_bytes(b"%PDF")

        mock_process.return_value = DanfeData(arquivo_origem="doc.pdf")

        processor = BatchProcessor()
        results = processor.process_multiple_batches(root_folder)

        self.assertEqual(len(results), 3)

    @patch.object(BatchProcessor, '_process_single_file')
    def test_process_legacy_files(self, mock_process):
        """Testa processamento de arquivos legados."""
        legacy_folder = Path(self.temp_dir) / "legacy"
        legacy_folder.mkdir()

        # Cria PDFs em subpastas
        (legacy_folder / "sub1").mkdir()
        (legacy_folder / "sub1" / "doc1.pdf").write_bytes(b"%PDF")
        (legacy_folder / "doc2.pdf").write_bytes(b"%PDF")

        mock_process.return_value = DanfeData(arquivo_origem="doc.pdf")

        processor = BatchProcessor()
        result = processor.process_legacy_files(legacy_folder, recursive=True)

        self.assertEqual(result.total_documents, 2)

    def test_process_email_batch_utility(self):
        """Testa função utilitária process_email_batch."""
        batch_folder = Path(self.temp_dir) / "utility_test"
        batch_folder.mkdir()

        result = process_email_batch(batch_folder)

        self.assertEqual(result.batch_id, "utility_test")

    def test_process_legacy_folder_utility(self):
        """Testa função utilitária process_legacy_folder."""
        legacy_folder = Path(self.temp_dir) / "legacy_utility"
        legacy_folder.mkdir()

        result = process_legacy_folder(legacy_folder)

        self.assertIn("legacy_", result.batch_id)


class TestIngestionService(unittest.TestCase):
    """Testes para a classe IngestionService."""

    def setUp(self):
        """Cria diretório temporário e mock do ingestor."""
        self.temp_dir = tempfile.mkdtemp()
        self.mock_ingestor = MagicMock()

    def tearDown(self):
        """Remove diretório temporário."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_service(self):
        """Testa criação do serviço."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertIsNotNone(service)

    def test_generate_batch_id_format(self):
        """Testa formato do batch_id gerado."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        batch_id = service._generate_batch_id()

        # Formato: email_YYYYMMDD_HHMMSS_XXXXX
        self.assertTrue(batch_id.startswith("email_"))
        parts = batch_id.split("_")
        self.assertEqual(len(parts), 4)

    def test_sanitize_filename(self):
        """Testa sanitização de nomes de arquivo."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        # Remove caracteres inválidos
        self.assertEqual(
            service._sanitize_filename("file<>:name.pdf"),
            "file___name.pdf"
        )

    def test_should_ignore_file_images(self):
        """Testa que imagens são ignoradas."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertTrue(service._should_ignore_file("image.png"))
        self.assertTrue(service._should_ignore_file("photo.jpg"))
        self.assertTrue(service._should_ignore_file("logo.gif"))

    def test_should_ignore_file_signatures(self):
        """Testa que assinaturas são ignoradas."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertTrue(service._should_ignore_file("assinatura.p7s"))
        self.assertTrue(service._should_ignore_file("smime.p7s"))

    def test_should_ignore_name_patterns(self):
        """Testa que padrões de nome são ignorados."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertTrue(service._should_ignore_file("image001.jpg"))
        self.assertTrue(service._should_ignore_file("logo_empresa.png"))

    def test_should_not_ignore_pdf_xml(self):
        """Testa que PDF e XML não são ignorados."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertFalse(service._should_ignore_file("nota.pdf"))
        self.assertFalse(service._should_ignore_file("nfe.xml"))

    def test_ingest_single_email_creates_folder(self):
        """Testa que ingestão cria pasta para o lote."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        email_data = {
            "subject": "Test Subject",
            "sender_name": "Test Sender",
            "attachments": [
                {"filename": "danfe.pdf", "content": b"%PDF test content"},
            ],
        }

        batch_folder = service.ingest_single_email(email_data)

        self.assertTrue(batch_folder.exists())
        self.assertTrue((batch_folder / "metadata.json").exists())

        # Verifica que arquivo foi salvo
        pdf_files = list(batch_folder.glob("*.pdf"))
        self.assertEqual(len(pdf_files), 1)

    def test_ingest_single_email_filters_images(self):
        """Testa que imagens são filtradas na ingestão."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        email_data = {
            "subject": "Test",
            "attachments": [
                {"filename": "danfe.pdf", "content": b"%PDF test"},
                {"filename": "logo.png", "content": b"PNG image"},
                {"filename": "image001.jpg", "content": b"JPG image"},
            ],
        }

        batch_folder = service.ingest_single_email(email_data)

        # Apenas PDF deve estar na pasta principal
        pdf_files = list(batch_folder.glob("*.pdf"))
        self.assertEqual(len(pdf_files), 1)

    def test_ingest_single_email_creates_ignored_folder(self):
        """Testa criação de pasta 'ignored' para arquivos descartados."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        email_data = {
            "subject": "Test",
            "attachments": [
                {"filename": "danfe.pdf", "content": b"%PDF test"},
                {"filename": "logo.png", "content": b"PNG image"},
            ],
        }

        batch_folder = service.ingest_single_email(email_data, create_ignored_folder=True)

        # Pasta ignored deve existir
        ignored_folder = batch_folder / "ignored"
        self.assertTrue(ignored_folder.exists())

        # Imagem deve estar na pasta ignored
        ignored_files = list(ignored_folder.glob("*"))
        self.assertEqual(len(ignored_files), 1)

    def test_ingest_single_email_no_valid_attachments(self):
        """Testa retorno None quando não há anexos válidos."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        email_data = {
            "subject": "Test",
            "attachments": [
                {"filename": "image.png", "content": b"PNG"},
            ],
        }

        batch_folder = service.ingest_single_email(email_data)

        self.assertIsNone(batch_folder)

    def test_ingest_single_email_no_attachments(self):
        """Testa retorno None quando não há anexos."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        email_data = {
            "subject": "Test",
            "attachments": [],
        }

        batch_folder = service.ingest_single_email(email_data)

        self.assertIsNone(batch_folder)

    def test_cleanup_old_batches(self):
        """Testa limpeza de lotes antigos."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        # Cria algumas pastas de lote
        for i in range(5):
            batch_folder = Path(self.temp_dir) / f"email_20240101_00000{i}_xxxxx"
            batch_folder.mkdir()

        # Limpa com max_age=0 (remove tudo)
        removed = service.cleanup_old_batches(max_age_hours=0)

        self.assertEqual(removed, 5)

    def test_ingest_emails_calls_ingestor(self):
        """Testa que ingest_emails chama o ingestor."""
        self.mock_ingestor.connect.return_value = None
        self.mock_ingestor.fetch_attachments.return_value = []

        service = IngestionService(self.mock_ingestor, self.temp_dir)

        service.ingest_emails(subject_filter="NF")

        self.mock_ingestor.connect.assert_called_once()
        self.mock_ingestor.fetch_attachments.assert_called_once_with("NF")


class TestCreateBatchFolderUtility(unittest.TestCase):
    """Testes para a função utilitária create_batch_folder."""

    def setUp(self):
        """Cria diretório temporário."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove diretório temporário."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_batch_folder_basic(self):
        """Testa criação básica de pasta de lote."""
        batch_folder = create_batch_folder(
            temp_dir=self.temp_dir,
            subject="Test Subject",
            sender_name="Test Sender",
        )

        self.assertTrue(batch_folder.exists())
        self.assertTrue((batch_folder / "metadata.json").exists())

    def test_create_batch_folder_with_files(self):
        """Testa criação com arquivos."""
        batch_folder = create_batch_folder(
            temp_dir=self.temp_dir,
            subject="Test",
            files=[
                {"filename": "doc1.pdf", "content": b"PDF1"},
                {"filename": "doc2.pdf", "content": b"PDF2"},
            ],
        )

        # Verifica arquivos salvos
        pdf_files = list(batch_folder.glob("*.pdf"))
        self.assertEqual(len(pdf_files), 2)

        # Verifica metadata
        metadata = EmailMetadata.load(batch_folder)
        self.assertEqual(len(metadata.attachments), 2)

    def test_create_batch_folder_generates_unique_id(self):
        """Testa que cada chamada gera ID único."""
        folder1 = create_batch_folder(self.temp_dir)
        folder2 = create_batch_folder(self.temp_dir)

        self.assertNotEqual(folder1.name, folder2.name)


class TestIntegrationBatchProcessing(unittest.TestCase):
    """Testes de integração do fluxo completo de batch processing."""

    def setUp(self):
        """Cria diretório temporário."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove diretório temporário."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch.object(BatchProcessor, '_process_single_file')
    def test_full_flow_danfe_boleto(self, mock_process):
        """Testa fluxo completo: ingestão -> processamento -> correlação."""
        # 1. Cria lote simulado
        batch_folder = create_batch_folder(
            temp_dir=self.temp_dir,
            subject="NF 12345 - Pedido 98765",
            sender_name="Distribuidora XYZ",
            sender_address="nf@distribuidora.com",
            body_text="Prezados, segue NF do CNPJ 12.345.678/0001-90",
            files=[
                {"filename": "danfe.pdf", "content": b"%PDF danfe"},
                {"filename": "boleto.pdf", "content": b"%PDF boleto"},
            ],
        )

        # 2. Mock do processador para retornar documentos
        danfe = DanfeData(arquivo_origem="danfe.pdf", numero_nota="12345", valor_total=1000.0)
        boleto = BoletoData(arquivo_origem="boleto.pdf", valor_documento=1000.0)

        mock_process.side_effect = [danfe, boleto]

        # 3. Processa o lote
        processor = BatchProcessor()
        result = processor.process_batch(batch_folder, apply_correlation=True)

        # 4. Verifica resultado
        self.assertEqual(result.total_documents, 2)
        self.assertTrue(result.has_danfe)
        self.assertTrue(result.has_boleto)

        # 5. Verifica que correlação foi aplicada
        # Boleto deve ter herdado numero_nota
        self.assertEqual(boleto.referencia_nfse, "12345")

        # 6. Verifica enriquecimento do metadata
        self.assertEqual(result.email_subject, "NF 12345 - Pedido 98765")
        self.assertEqual(result.email_sender, "Distribuidora XYZ")

    @patch.object(BatchProcessor, '_process_single_file')
    def test_flow_with_correlation_divergente(self, mock_process):
        """Testa fluxo com valores divergentes."""
        batch_folder = create_batch_folder(
            temp_dir=self.temp_dir,
            subject="NF Test",
            files=[
                {"filename": "danfe.pdf", "content": b"%PDF"},
                {"filename": "boleto.pdf", "content": b"%PDF"},
            ],
        )

        # Valores divergentes
        danfe = DanfeData(arquivo_origem="danfe.pdf", valor_total=1000.0)
        boleto = BoletoData(arquivo_origem="boleto.pdf", valor_documento=800.0)

        mock_process.side_effect = [danfe, boleto]

        processor = BatchProcessor()
        result = processor.process_batch(batch_folder, apply_correlation=True)

        # Cria correlação manualmente para verificar status
        correlation = CorrelationService().correlate(result)

        self.assertEqual(correlation.status, "DIVERGENTE")
        self.assertAlmostEqual(correlation.diferenca, 200.0, places=2)


class TestDuplicateDetection(unittest.TestCase):
    """Testes para detecção de documentos duplicados (encaminhamentos duplicados)."""

    def test_detect_duplicate_by_numero_nota(self):
        """Testa detecção de duplicatas pelo número da nota."""
        batch = BatchResult(batch_id="test_dup")
        batch.add_document(DanfeData(arquivo_origem="d1.pdf", numero_nota="12345", valor_total=1000.0))
        batch.add_document(DanfeData(arquivo_origem="d2.pdf", numero_nota="12345", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        service = CorrelationService()
        duplicatas = service._detect_duplicate_documents(batch)

        self.assertIn("12345", duplicatas['numero_nota'])

    def test_detect_duplicate_by_fornecedor_valor(self):
        """Testa detecção de duplicatas pela combinação fornecedor+valor."""
        batch = BatchResult(batch_id="test_dup")
        batch.add_document(DanfeData(
            arquivo_origem="d1.pdf",
            fornecedor_nome="Empresa ABC",
            valor_total=1500.0
        ))
        batch.add_document(DanfeData(
            arquivo_origem="d2.pdf",
            fornecedor_nome="Empresa ABC",
            valor_total=1500.0
        ))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1500.0))

        service = CorrelationService()
        duplicatas = service._detect_duplicate_documents(batch)

        # Deve detectar duplicata por fornecedor+valor
        self.assertTrue(len(duplicatas['fornecedor_valor']) > 0)

    def test_no_duplicate_different_notas(self):
        """Testa que notas diferentes não são marcadas como duplicatas."""
        batch = BatchResult(batch_id="test_no_dup")
        batch.add_document(DanfeData(arquivo_origem="d1.pdf", numero_nota="12345", valor_total=1000.0))
        batch.add_document(DanfeData(arquivo_origem="d2.pdf", numero_nota="67890", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=2000.0))

        service = CorrelationService()
        duplicatas = service._detect_duplicate_documents(batch)

        self.assertEqual(len(duplicatas['numero_nota']), 0)

    def test_divergencia_includes_duplicate_warning(self):
        """Testa que aviso de duplicata aparece na divergência."""
        batch = BatchResult(batch_id="test_dup_warn")
        batch.add_document(DanfeData(arquivo_origem="d1.pdf", numero_nota="12345", valor_total=1000.0))
        batch.add_document(DanfeData(arquivo_origem="d2.pdf", numero_nota="12345", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        service = CorrelationService()
        result = service.correlate(batch)

        # Deve ter aviso de encaminhamento duplicado
        self.assertIn("ENCAMINHAMENTO DUPLICADO", result.divergencia or "")


class TestXmlPriority(unittest.TestCase):
    """Testes para lógica de XML como fonte prioritária quando completo."""

    def setUp(self):
        """Cria diretório temporário para testes."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove diretório temporário."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_is_xml_complete_all_fields(self):
        """Testa que XML com todos os campos é considerado completo."""
        processor = BatchProcessor()

        doc = InvoiceData(
            arquivo_origem="nota.xml",
            fornecedor_nome="Empresa Teste",
            vencimento="2024-12-31",
            numero_nota="12345",
            valor_total=1500.0
        )

        self.assertTrue(processor._is_xml_complete(doc))

    def test_is_xml_complete_missing_fornecedor(self):
        """Testa que XML sem fornecedor não é considerado completo."""
        processor = BatchProcessor()

        doc = InvoiceData(
            arquivo_origem="nota.xml",
            vencimento="2024-12-31",
            numero_nota="12345",
            valor_total=1500.0
        )

        self.assertFalse(processor._is_xml_complete(doc))

    def test_is_xml_complete_missing_vencimento(self):
        """Testa que XML sem vencimento não é considerado completo."""
        processor = BatchProcessor()

        doc = InvoiceData(
            arquivo_origem="nota.xml",
            fornecedor_nome="Empresa Teste",
            numero_nota="12345",
            valor_total=1500.0
        )

        self.assertFalse(processor._is_xml_complete(doc))

    def test_get_campos_faltantes(self):
        """Testa identificação de campos faltantes."""
        processor = BatchProcessor()

        doc = InvoiceData(
            arquivo_origem="nota.xml",
            fornecedor_nome="Empresa Teste",
            valor_total=1500.0
        )

        faltantes = processor._get_campos_faltantes(doc)

        self.assertIn('vencimento', faltantes)
        self.assertIn('numero_nota', faltantes)
        self.assertNotIn('fornecedor_nome', faltantes)
        self.assertNotIn('valor_total', faltantes)

    def test_normalize_fornecedor(self):
        """Testa normalização do nome do fornecedor."""
        processor = BatchProcessor()

        # Remove quebras de linha
        self.assertEqual(
            processor._normalize_fornecedor("Empresa\nTeste"),
            "EMPRESA TESTE"
        )

        # Remove espaços extras
        self.assertEqual(
            processor._normalize_fornecedor("  Empresa   Teste  "),
            "EMPRESA TESTE"
        )

    def test_list_files_by_type(self):
        """Testa separação de arquivos por tipo (XML vs PDF)."""
        batch_folder = Path(self.temp_dir) / "test_batch"
        batch_folder.mkdir()

        # Cria arquivos de teste
        (batch_folder / "nota.xml").write_text("<xml>test</xml>")
        (batch_folder / "danfe.pdf").write_bytes(b"%PDF test")
        (batch_folder / "boleto.pdf").write_bytes(b"%PDF test")
        (batch_folder / "metadata.json").write_text("{}")

        processor = BatchProcessor()
        xml_files, pdf_files = processor._list_files_by_type(batch_folder)

        self.assertEqual(len(xml_files), 1)
        self.assertEqual(len(pdf_files), 2)
        self.assertEqual(xml_files[0].name, "nota.xml")


class TestFornecedorNormalization(unittest.TestCase):
    """Testes para normalização do nome do fornecedor no BatchResult."""

    def test_normalize_removes_line_breaks(self):
        """Testa remoção de quebras de linha."""
        result = BatchResult(batch_id="test")
        normalized = result._normalize_fornecedor("Empresa\nTeste\nLTDA")
        self.assertEqual(normalized, "Empresa Teste LTDA")

    def test_normalize_removes_cnpj_prefix(self):
        """Testa remoção do prefixo CNPJ."""
        result = BatchResult(batch_id="test")
        normalized = result._normalize_fornecedor("CNPJ: Empresa Teste")
        self.assertEqual(normalized, "Empresa Teste")

    def test_normalize_removes_extra_spaces(self):
        """Testa remoção de espaços extras."""
        result = BatchResult(batch_id="test")
        normalized = result._normalize_fornecedor("  Empresa   Teste  ")
        self.assertEqual(normalized, "Empresa Teste")

    def test_get_primeiro_fornecedor_normalizes(self):
        """Testa que _get_primeiro_fornecedor aplica normalização."""
        result = BatchResult(batch_id="test")
        result.add_document(DanfeData(
            arquivo_origem="d.pdf",
            fornecedor_nome="CNPJ\nEmpresa Teste"
        ))

        fornecedor = result._get_primeiro_fornecedor()
        self.assertEqual(fornecedor, "Empresa Teste")


if __name__ == "__main__":
    unittest.main()
