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
            subject="NF 12345 - Empresa XYZ",
            sender_name="Fornecedor ABC",
            sender_address="nf@fornecedor.com.br",
            body_text="Segue NF referente ao pedido 98765",
            attachments=["danfe.pdf", "boleto.pdf"],
        )

        self.assertEqual(metadata.batch_id, "email_20251231_abc123")
        self.assertEqual(metadata.email_subject, "NF 12345 - Empresa XYZ")
        self.assertEqual(metadata.email_sender_name, "Fornecedor ABC")
        self.assertEqual(metadata.email_sender_address, "nf@fornecedor.com.br")
        self.assertEqual(len(metadata.attachments), 2)

    def test_create_legacy(self):
        """Testa criação de metadata para arquivos legados."""
        metadata = EmailMetadata.create_legacy(
            batch_id="legacy_test",
            file_paths=["file1.pdf", "file2.pdf"],
        )

        self.assertEqual(metadata.batch_id, "legacy_test")
        self.assertTrue(metadata.is_legacy())
        self.assertEqual(len(metadata.attachments), 2)

    def test_save_and_load(self):
        """Testa salvar e carregar metadata de arquivo JSON."""
        batch_folder = Path(self.temp_dir) / "test_batch"
        batch_folder.mkdir()

        # Salva
        original = EmailMetadata.create_for_batch(
            batch_id="test_batch",
            subject="Test Subject",
            sender_name="Test Sender",
        )
        original.save(batch_folder)

        # Carrega
        loaded = EmailMetadata.load(batch_folder)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.batch_id, "test_batch")
        self.assertEqual(loaded.email_subject, "Test Subject")
        self.assertEqual(loaded.email_sender_name, "Test Sender")

    def test_load_nonexistent(self):
        """Testa carregar de pasta sem metadata.json."""
        result = EmailMetadata.load(Path(self.temp_dir))
        self.assertIsNone(result)

    def test_extract_cnpj_from_body(self):
        """Testa extração de CNPJ do corpo do e-mail."""
        metadata = EmailMetadata(
            batch_id="test",
            email_body_text="Prezados, segue NF do CNPJ 12.345.678/0001-90 para pagamento.",
        )

        cnpj = metadata.extract_cnpj_from_body()
        self.assertEqual(cnpj, "12.345.678/0001-90")

    def test_extract_cnpj_from_body_not_found(self):
        """Testa quando não há CNPJ no corpo."""
        metadata = EmailMetadata(
            batch_id="test",
            email_body_text="Prezados, segue NF para pagamento.",
        )

        cnpj = metadata.extract_cnpj_from_body()
        self.assertIsNone(cnpj)

    def test_extract_numero_pedido_from_context(self):
        """Testa extração de número de pedido do assunto/corpo."""
        metadata = EmailMetadata(
            batch_id="test",
            email_subject="NF ref. PEDIDO: 12345",
            email_body_text="Conforme pedido acima",
        )

        pedido = metadata.extract_numero_pedido_from_context()
        self.assertEqual(pedido, "12345")

    def test_extract_numero_pedido_ordem(self):
        """Testa extração de OC (ordem de compra)."""
        metadata = EmailMetadata(
            batch_id="test",
            email_subject="Faturamento OC 98765",
        )

        pedido = metadata.extract_numero_pedido_from_context()
        self.assertEqual(pedido, "98765")

    def test_get_fallback_fornecedor(self):
        """Testa fallback de fornecedor via sender_name."""
        metadata = EmailMetadata(
            batch_id="test",
            email_sender_name="Distribuidora XYZ",
        )

        self.assertEqual(metadata.get_fallback_fornecedor(), "Distribuidora XYZ")

    def test_to_dict_and_json(self):
        """Testa serialização para dict e JSON."""
        metadata = EmailMetadata.create_for_batch(
            batch_id="test",
            subject="Test",
        )

        # to_dict
        data = metadata.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["batch_id"], "test")

        # to_json
        json_str = metadata.to_json()
        self.assertIsInstance(json_str, str)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["batch_id"], "test")


class TestBatchResult(unittest.TestCase):
    """Testes para a classe BatchResult."""

    def test_create_empty(self):
        """Testa criação de resultado vazio."""
        result = BatchResult(batch_id="test_batch")

        self.assertEqual(result.batch_id, "test_batch")
        self.assertEqual(result.total_documents, 0)
        self.assertEqual(result.total_errors, 0)
        self.assertTrue(result.is_empty)

    def test_add_document(self):
        """Testa adição de documentos."""
        result = BatchResult(batch_id="test")

        danfe = DanfeData(arquivo_origem="test.pdf", numero_nota="12345", valor_total=1000.0)
        boleto = BoletoData(arquivo_origem="boleto.pdf", valor_documento=1000.0)

        result.add_document(danfe)
        result.add_document(boleto)

        self.assertEqual(result.total_documents, 2)
        self.assertFalse(result.is_empty)

    def test_add_error(self):
        """Testa registro de erros."""
        result = BatchResult(batch_id="test")
        result.add_error("file.pdf", "Erro de leitura")

        self.assertEqual(result.total_errors, 1)
        self.assertEqual(result.errors[0]["file"], "file.pdf")

    def test_filter_by_type(self):
        """Testa filtros por tipo de documento."""
        result = BatchResult(batch_id="test")

        result.add_document(DanfeData(arquivo_origem="d1.pdf"))
        result.add_document(DanfeData(arquivo_origem="d2.pdf"))
        result.add_document(BoletoData(arquivo_origem="b1.pdf"))
        result.add_document(InvoiceData(arquivo_origem="n1.pdf"))
        result.add_document(OtherDocumentData(arquivo_origem="o1.pdf"))

        self.assertEqual(len(result.danfes), 2)
        self.assertEqual(len(result.boletos), 1)
        self.assertEqual(len(result.nfses), 1)
        self.assertEqual(len(result.outros), 1)

    def test_has_danfe_boleto(self):
        """Testa propriedades has_danfe e has_boleto."""
        result = BatchResult(batch_id="test")

        self.assertFalse(result.has_danfe)
        self.assertFalse(result.has_boleto)

        result.add_document(DanfeData(arquivo_origem="d.pdf"))
        self.assertTrue(result.has_danfe)
        self.assertFalse(result.has_boleto)

        result.add_document(BoletoData(arquivo_origem="b.pdf"))
        self.assertTrue(result.has_boleto)

    def test_get_valor_total_danfes(self):
        """Testa soma de valores das DANFEs."""
        result = BatchResult(batch_id="test")

        result.add_document(DanfeData(arquivo_origem="d1.pdf", valor_total=1000.0))
        result.add_document(DanfeData(arquivo_origem="d2.pdf", valor_total=500.50))

        self.assertAlmostEqual(result.get_valor_total_danfes(), 1500.50, places=2)

    def test_get_valor_total_boletos(self):
        """Testa soma de valores dos Boletos."""
        result = BatchResult(batch_id="test")

        result.add_document(BoletoData(arquivo_origem="b1.pdf", valor_documento=200.0))
        result.add_document(BoletoData(arquivo_origem="b2.pdf", valor_documento=300.0))

        self.assertAlmostEqual(result.get_valor_total_boletos(), 500.0, places=2)

    def test_get_valor_total_lote(self):
        """Testa soma total do lote (todos os tipos)."""
        result = BatchResult(batch_id="test")

        result.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        result.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=500.0))
        result.add_document(InvoiceData(arquivo_origem="n.pdf", valor_total=300.0))

        self.assertAlmostEqual(result.get_valor_total_lote(), 1800.0, places=2)

    def test_to_summary(self):
        """Testa geração de resumo."""
        result = BatchResult(
            batch_id="test",
            source_folder="/path/to/batch",
            email_subject="Test Subject",
            email_sender="Sender Name",
        )
        result.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=1000.0))
        result.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        summary = result.to_summary()

        self.assertEqual(summary["batch_id"], "test")
        self.assertEqual(summary["total_documents"], 2)
        self.assertEqual(summary["danfes"], 1)
        self.assertEqual(summary["boletos"], 1)
        self.assertEqual(summary["email_subject"], "Test Subject")


class TestCorrelationResult(unittest.TestCase):
    """Testes para a classe CorrelationResult."""

    def test_create_ok(self):
        """Testa criação com status OK."""
        result = CorrelationResult(batch_id="test", status="OK")

        self.assertTrue(result.is_ok())
        self.assertFalse(result.is_divergente())
        self.assertFalse(result.is_orfao())

    def test_create_divergente(self):
        """Testa status DIVERGENTE."""
        result = CorrelationResult(
            batch_id="test",
            status="DIVERGENTE",
            divergencia="Valor nota: R$ 1000.00 | Valor boletos: R$ 900.00",
        )

        self.assertFalse(result.is_ok())
        self.assertTrue(result.is_divergente())

    def test_create_orfao(self):
        """Testa status ORFAO."""
        result = CorrelationResult(batch_id="test", status="ORFAO")

        self.assertTrue(result.is_orfao())


class TestCorrelationService(unittest.TestCase):
    """Testes para a classe CorrelationService."""

    def test_correlate_empty_batch(self):
        """Testa correlação de lote vazio."""
        service = CorrelationService()
        batch = BatchResult(batch_id="test")

        result = service.correlate(batch)

        self.assertEqual(result.status, "OK")

    def test_correlate_danfe_boleto_valores_iguais(self):
        """Testa correlação com valores iguais (OK)."""
        service = CorrelationService()
        batch = BatchResult(batch_id="test")

        batch.add_document(DanfeData(arquivo_origem="d.pdf", numero_nota="123", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0))

        result = service.correlate(batch)

        self.assertEqual(result.status, "OK")
        self.assertAlmostEqual(result.diferenca, 0.0, places=2)

    def test_correlate_danfe_boleto_valores_divergentes(self):
        """Testa correlação com valores divergentes."""
        service = CorrelationService()
        batch = BatchResult(batch_id="test")

        batch.add_document(DanfeData(arquivo_origem="d.pdf", numero_nota="123", valor_total=1000.0))
        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=800.0))

        result = service.correlate(batch)

        self.assertEqual(result.status, "DIVERGENTE")
        self.assertAlmostEqual(result.diferenca, 200.0, places=2)

    def test_correlate_boleto_orfao(self):
        """Testa boleto sem nota fiscal (órfão)."""
        service = CorrelationService()
        batch = BatchResult(batch_id="test")

        batch.add_document(BoletoData(arquivo_origem="b.pdf", valor_documento=500.0))

        result = service.correlate(batch)

        self.assertEqual(result.status, "ORFAO")
        self.assertIsNotNone(result.divergencia)

    def test_heranca_numero_nota(self):
        """Testa herança de numero_nota da DANFE para Boleto."""
        service = CorrelationService()
        batch = BatchResult(batch_id="test")

        danfe = DanfeData(arquivo_origem="d.pdf", numero_nota="12345", valor_total=1000.0)
        boleto = BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0)

        batch.add_document(danfe)
        batch.add_document(boleto)

        result = service.correlate(batch)

        # Boleto deve herdar o numero_nota
        self.assertEqual(boleto.referencia_nfse, "12345")
        self.assertEqual(result.numero_nota_herdado, "12345")

    def test_heranca_vencimento(self):
        """Testa herança de vencimento do Boleto para DANFE."""
        service = CorrelationService()
        batch = BatchResult(batch_id="test")

        danfe = DanfeData(arquivo_origem="d.pdf", numero_nota="123", valor_total=1000.0)
        boleto = BoletoData(arquivo_origem="b.pdf", valor_documento=1000.0, vencimento="2025-01-15")

        batch.add_document(danfe)
        batch.add_document(boleto)

        result = service.correlate(batch)

        # DANFE deve herdar o vencimento
        self.assertEqual(danfe.vencimento, "2025-01-15")
        self.assertEqual(result.vencimento_herdado, "2025-01-15")

    def test_enrich_from_metadata_fallback_fornecedor(self):
        """Testa enriquecimento com fallback de fornecedor."""
        service = CorrelationService()
        batch = BatchResult(batch_id="test")

        # Documento sem fornecedor
        danfe = DanfeData(arquivo_origem="d.pdf", numero_nota="123", fornecedor_nome=None)
        batch.add_document(danfe)

        # Metadata com sender_name
        metadata = EmailMetadata(
            batch_id="test",
            email_sender_name="Distribuidora XYZ",
        )

        service.correlate(batch, metadata)

        # Deve usar sender_name como fallback
        self.assertEqual(danfe.fornecedor_nome, "Distribuidora XYZ")

    def test_enrich_from_metadata_cnpj(self):
        """Testa enriquecimento com CNPJ do corpo do e-mail."""
        service = CorrelationService()
        batch = BatchResult(batch_id="test")

        # Documento sem CNPJ
        danfe = DanfeData(arquivo_origem="d.pdf", numero_nota="123", cnpj_emitente=None)
        batch.add_document(danfe)

        # Metadata com CNPJ no corpo
        metadata = EmailMetadata(
            batch_id="test",
            email_body_text="Nota fiscal do CNPJ 12.345.678/0001-90",
        )

        service.correlate(batch, metadata)

        # Deve extrair CNPJ do corpo
        self.assertEqual(danfe.cnpj_emitente, "12.345.678/0001-90")

    def test_correlate_batch_utility_function(self):
        """Testa função utilitária correlate_batch."""
        batch = BatchResult(batch_id="test")
        batch.add_document(DanfeData(arquivo_origem="d.pdf", valor_total=500.0))

        result = correlate_batch(batch)

        self.assertIsInstance(result, CorrelationResult)
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
        pdf_file = batch_folder / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test content")

        # Mock retorna DanfeData
        mock_process.return_value = DanfeData(arquivo_origem="test.pdf", numero_nota="123")

        processor = BatchProcessor()
        result = processor.process_batch(batch_folder)

        self.assertEqual(result.total_documents, 1)
        mock_process.assert_called_once()

    def test_is_processable_ignores_metadata(self):
        """Testa que metadata.json é ignorado."""
        processor = BatchProcessor()

        self.assertFalse(processor._is_processable(Path("metadata.json")))
        self.assertFalse(processor._is_processable(Path(".gitkeep")))
        self.assertFalse(processor._is_processable(Path("thumbs.db")))
        self.assertFalse(processor._is_processable(Path(".hidden")))

    def test_is_processable_accepts_pdf_xml(self):
        """Testa que PDF e XML são aceitos."""
        processor = BatchProcessor()

        self.assertTrue(processor._is_processable(Path("doc.pdf")))
        self.assertTrue(processor._is_processable(Path("doc.PDF")))
        self.assertTrue(processor._is_processable(Path("doc.xml")))
        self.assertTrue(processor._is_processable(Path("doc.XML")))

    def test_is_processable_rejects_ignored_folder(self):
        """Testa que arquivos na pasta 'ignored' são ignorados."""
        processor = BatchProcessor()

        self.assertFalse(processor._is_processable(Path("batch/ignored/file.pdf")))

    @patch.object(BatchProcessor, '_process_single_file')
    def test_process_legacy_files(self, mock_process):
        """Testa processamento de arquivos legados (sem metadata)."""
        legacy_folder = Path(self.temp_dir) / "legacy"
        legacy_folder.mkdir()

        # Cria PDFs
        (legacy_folder / "file1.pdf").write_bytes(b"%PDF test1")
        (legacy_folder / "file2.pdf").write_bytes(b"%PDF test2")

        mock_process.return_value = DanfeData(arquivo_origem="test.pdf")

        processor = BatchProcessor()
        result = processor.process_legacy_files(legacy_folder, recursive=False)

        self.assertTrue(result.batch_id.startswith("legacy_"))
        self.assertEqual(mock_process.call_count, 2)

    @patch.object(BatchProcessor, 'process_batch')
    def test_process_multiple_batches(self, mock_process_batch):
        """Testa processamento de múltiplos lotes."""
        root = Path(self.temp_dir)
        (root / "batch1").mkdir()
        (root / "batch2").mkdir()
        (root / ".hidden").mkdir()  # Deve ser ignorado

        mock_process_batch.return_value = BatchResult(batch_id="test")

        processor = BatchProcessor()
        results = processor.process_multiple_batches(root)

        self.assertEqual(len(results), 2)
        self.assertEqual(mock_process_batch.call_count, 2)

    def test_process_email_batch_utility(self):
        """Testa função utilitária process_email_batch."""
        batch_folder = Path(self.temp_dir) / "util_batch"
        batch_folder.mkdir()

        result = process_email_batch(batch_folder)

        self.assertIsInstance(result, BatchResult)

    def test_process_legacy_folder_utility(self):
        """Testa função utilitária process_legacy_folder."""
        legacy_folder = Path(self.temp_dir) / "util_legacy"
        legacy_folder.mkdir()

        result = process_legacy_folder(legacy_folder)

        self.assertIsInstance(result, BatchResult)
        self.assertTrue(result.batch_id.startswith("legacy_"))


class TestIngestionService(unittest.TestCase):
    """Testes para a classe IngestionService."""

    def setUp(self):
        """Cria diretório temporário para testes."""
        self.temp_dir = tempfile.mkdtemp()
        self.mock_ingestor = MagicMock()

    def tearDown(self):
        """Remove diretório temporário."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_service(self):
        """Testa criação do serviço."""
        service = IngestionService(
            ingestor=self.mock_ingestor,
            temp_dir=self.temp_dir,
        )

        self.assertEqual(service.temp_dir, Path(self.temp_dir))
        self.assertIsNotNone(service.ignored_extensions)

    def test_should_ignore_file_images(self):
        """Testa que imagens são ignoradas."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertTrue(service._should_ignore_file("logo.png"))
        self.assertTrue(service._should_ignore_file("image001.jpg"))
        self.assertTrue(service._should_ignore_file("photo.jpeg"))
        self.assertTrue(service._should_ignore_file("banner.gif"))

    def test_should_ignore_file_signatures(self):
        """Testa que assinaturas digitais são ignoradas."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertTrue(service._should_ignore_file("smime.p7s"))
        self.assertTrue(service._should_ignore_file("signature.smime"))

    def test_should_not_ignore_pdf_xml(self):
        """Testa que PDF e XML não são ignorados."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertFalse(service._should_ignore_file("danfe.pdf"))
        self.assertFalse(service._should_ignore_file("nfe.xml"))
        self.assertFalse(service._should_ignore_file("boleto.pdf"))

    def test_should_ignore_name_patterns(self):
        """Testa que padrões de nome são ignorados."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertTrue(service._should_ignore_file("image001.png"))
        self.assertTrue(service._should_ignore_file("image002.jpg"))
        self.assertTrue(service._should_ignore_file("logo_empresa.png"))
        self.assertTrue(service._should_ignore_file("assinatura.png"))
        self.assertTrue(service._should_ignore_file("signature.jpg"))

    def test_sanitize_filename(self):
        """Testa sanitização de nome de arquivo."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.assertEqual(service._sanitize_filename("normal.pdf"), "normal.pdf")
        self.assertEqual(service._sanitize_filename("with:invalid.pdf"), "with_invalid.pdf")
        self.assertEqual(service._sanitize_filename("with<>chars.pdf"), "with__chars.pdf")
        self.assertEqual(service._sanitize_filename(""), "unnamed_file")
        self.assertEqual(service._sanitize_filename(None), "unnamed_file")

    def test_generate_batch_id_format(self):
        """Testa formato do batch_id gerado."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        batch_id = service._generate_batch_id()

        self.assertTrue(batch_id.startswith("email_"))
        # Format: email_YYYYMMDD_HHMMSS_shortUUID
        parts = batch_id.split("_")
        self.assertEqual(len(parts), 4)
        self.assertEqual(len(parts[1]), 8)  # YYYYMMDD
        self.assertEqual(len(parts[2]), 6)  # HHMMSS
        self.assertEqual(len(parts[3]), 8)  # shortUUID

    def test_ingest_single_email_creates_folder(self):
        """Testa que ingest_single_email cria pasta e metadata."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        email_data = {
            "subject": "NF 12345",
            "sender_name": "Fornecedor ABC",
            "sender_address": "nf@fornecedor.com",
            "body_text": "Segue NF em anexo",
            "attachments": [
                {"filename": "danfe.pdf", "content": b"%PDF-1.4 test"},
            ],
        }

        batch_folder = service.ingest_single_email(email_data)

        self.assertIsNotNone(batch_folder)
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
                {"filename": "logo.png", "content": b"PNG"},
                {"filename": "image001.jpg", "content": b"JPG"},
            ],
        }

        result = service.ingest_single_email(email_data)
        self.assertIsNone(result)

    def test_ingest_single_email_no_attachments(self):
        """Testa retorno None quando não há anexos."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        email_data = {
            "subject": "Test",
            "attachments": [],
        }

        result = service.ingest_single_email(email_data)
        self.assertIsNone(result)

    def test_cleanup_old_batches(self):
        """Testa limpeza de lotes antigos."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        # Cria pasta "velha" (modifica mtime)
        old_batch = Path(self.temp_dir) / "old_batch"
        old_batch.mkdir()

        # Cria pasta "nova"
        new_batch = Path(self.temp_dir) / "new_batch"
        new_batch.mkdir()

        # Simula pasta antiga modificando mtime
        import time
        old_time = time.time() - (50 * 3600)  # 50 horas atrás
        os.utime(old_batch, (old_time, old_time))

        # Limpa com max_age de 48 horas
        removed = service.cleanup_old_batches(max_age_hours=48)

        self.assertEqual(removed, 1)
        self.assertFalse(old_batch.exists())
        self.assertTrue(new_batch.exists())

    def test_ingest_emails_calls_ingestor(self):
        """Testa que ingest_emails chama o ingestor."""
        service = IngestionService(self.mock_ingestor, self.temp_dir)

        self.mock_ingestor.fetch_attachments.return_value = []

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


if __name__ == "__main__":
    unittest.main()
