"""
Testes de validação da refatoração SOLID.

Testa que os princípios SOLID foram implementados corretamente:
- LSP: Todas as estratégias têm comportamento uniforme em falhas
- OCP: Modelos têm doc_type correto
- DIP: Injeção de dependências funciona
"""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile

from core.models import InvoiceData, BoletoData, DocumentData
from strategies.native import NativePdfStrategy
from strategies.ocr import TesseractOcrStrategy
from strategies.table import TablePdfStrategy
from strategies.fallback import SmartExtractionStrategy
from core.exceptions import ExtractionError
from core.processor import BaseInvoiceProcessor
from core.interfaces import TextExtractionStrategy


class TestLSPCompliance(unittest.TestCase):
    """Testa que todas as estratégias respeitam o Liskov Substitution Principle."""
    
    def test_all_strategies_return_string_on_failure(self):
        """Todas as estratégias devem retornar string (vazia ou não) em falhas recuperáveis."""
        fake_path = "arquivo_inexistente.pdf"
        
        strategies = [
            NativePdfStrategy(),
            TablePdfStrategy(),
            # OCR precisa de arquivo real para testar, pulamos aqui
        ]
        
        for strategy in strategies:
            with self.subTest(strategy=strategy.__class__.__name__):
                result = strategy.extract(fake_path)
                # Deve retornar string, não lançar exceção
                self.assertIsInstance(result, str, 
                    f"{strategy.__class__.__name__} deve retornar string em falhas")
    
    def test_fallback_catches_all_exceptions(self):
        """SmartExtractionStrategy deve capturar exceções de estratégias individuais."""
        # Cria estratégia mock que lança exceção
        mock_strategy = Mock(spec=TextExtractionStrategy)
        mock_strategy.extract.side_effect = Exception("Erro simulado")
        
        fallback = SmartExtractionStrategy()
        # Substitui estratégias por uma que falha sempre
        fallback.strategies = [mock_strategy, mock_strategy, mock_strategy]
        
        # Deve lançar ExtractionError após todas falharem, não propagar a exceção original
        with self.assertRaises(ExtractionError) as ctx:
            fallback.extract("fake.pdf")
        
        self.assertIn("Nenhuma estratégia conseguiu", str(ctx.exception))
    
    def test_extraction_error_only_for_critical_failures(self):
        """ExtractionError deve ser usada apenas para falhas críticas."""
        fallback = SmartExtractionStrategy()
        
        # Arquivo inexistente deve eventualmente lançar ExtractionError
        with self.assertRaises(ExtractionError):
            fallback.extract("arquivo_totalmente_inexistente_xyz.pdf")


class TestOCPCompliance(unittest.TestCase):
    """Testa que os modelos seguem Open/Closed Principle com doc_type."""
    
    def test_invoice_has_doc_type(self):
        """InvoiceData deve ter doc_type = 'NFSE'."""
        invoice = InvoiceData(
            arquivo_origem="test.pdf",
            texto_bruto="Texto teste"
        )
        
        self.assertEqual(invoice.doc_type, 'NFSE')
        self.assertIsInstance(invoice, DocumentData)
    
    def test_boleto_has_doc_type(self):
        """BoletoData deve ter doc_type = 'BOLETO'."""
        boleto = BoletoData(
            arquivo_origem="test.pdf",
            texto_bruto="Texto teste"
        )
        
        self.assertEqual(boleto.doc_type, 'BOLETO')
        self.assertIsInstance(boleto, DocumentData)
    
    def test_all_models_have_to_dict(self):
        """Todos os modelos devem implementar to_dict()."""
        invoice = InvoiceData(
            arquivo_origem="test.pdf",
            texto_bruto="Texto teste",
            numero_nota="12345"
        )
        boleto = BoletoData(
            arquivo_origem="test.pdf",
            texto_bruto="Texto teste",
            valor_documento=100.50
        )
        
        invoice_dict = invoice.to_dict()
        boleto_dict = boleto.to_dict()
        
        # Verifica estrutura básica
        self.assertIn('tipo_documento', invoice_dict)
        self.assertIn('tipo_documento', boleto_dict)
        self.assertEqual(invoice_dict['tipo_documento'], 'NFSE')
        self.assertEqual(boleto_dict['tipo_documento'], 'BOLETO')
    
    def test_doc_type_enables_polymorphism(self):
        """doc_type permite tratamento polimórfico de documentos."""
        documentos = [
            InvoiceData(arquivo_origem="nfse.pdf", texto_bruto="teste"),
            BoletoData(arquivo_origem="boleto.pdf", texto_bruto="teste"),
        ]
        
        # Pode agrupar por tipo sem usar hasattr ou isinstance
        tipos_encontrados = {doc.doc_type for doc in documentos}
        self.assertEqual(tipos_encontrados, {'NFSE', 'BOLETO'})


class TestDIPCompliance(unittest.TestCase):
    """Testa que a injeção de dependências funciona corretamente."""
    
    def test_processor_accepts_custom_reader(self):
        """BaseInvoiceProcessor deve aceitar estratégia customizada."""
        # Cria mock de estratégia
        mock_reader = Mock(spec=TextExtractionStrategy)
        mock_reader.extract.return_value = "Texto mockado de teste"
        
        # Injeta dependência
        processor = BaseInvoiceProcessor(reader=mock_reader)
        
        # Verifica que o mock foi usado
        self.assertIs(processor.reader, mock_reader)
    
    def test_processor_uses_default_if_no_reader(self):
        """BaseInvoiceProcessor deve usar SmartExtractionStrategy por padrão."""
        processor = BaseInvoiceProcessor()
        
        self.assertIsInstance(processor.reader, SmartExtractionStrategy)
    
    def test_processor_calls_injected_reader(self):
        """Processor deve usar a estratégia injetada ao processar arquivos."""
        # Cria estratégia mock que retorna texto específico
        mock_reader = Mock(spec=TextExtractionStrategy)
        mock_reader.extract.return_value = "NOTA FISCAL Nº 123\nCNPJ: 12.345.678/0001-90\nValor: R$ 1.500,00"
        
        processor = BaseInvoiceProcessor(reader=mock_reader)
        
        # Cria arquivo temporário fake
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Processa (vai usar o mock)
            result = processor.process(tmp_path)
            
            # Verifica que o mock foi chamado
            mock_reader.extract.assert_called_once_with(tmp_path)
            
            # Verifica que retornou um documento válido
            self.assertIsInstance(result, DocumentData)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestSRPCompliance(unittest.TestCase):
    """Testa que as responsabilidades estão bem separadas."""
    
    def test_file_system_manager_exists(self):
        """FileSystemManager deve existir e ter métodos de gerenciamento."""
        from core.exporters import FileSystemManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FileSystemManager(
                temp_dir=Path(tmpdir) / "temp",
                output_dir=Path(tmpdir) / "output"
            )
            
            # Testa métodos
            manager.setup_directories()
            self.assertTrue(manager.temp_dir.exists())
            self.assertTrue(manager.output_dir.exists())
    
    def test_attachment_downloader_exists(self):
        """AttachmentDownloader deve existir e salvar arquivos."""
        from core.exporters import FileSystemManager, AttachmentDownloader
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = FileSystemManager(
                temp_dir=Path(tmpdir) / "temp",
                output_dir=Path(tmpdir) / "output"
            )
            manager.setup_directories()
            
            downloader = AttachmentDownloader(manager)
            
            # Testa download
            content = b"PDF fake content"
            path = downloader.save_attachment("test.pdf", content)
            
            self.assertTrue(path.exists())
            self.assertEqual(path.read_bytes(), content)
    
    def test_csv_exporter_exists(self):
        """CsvExporter deve existir e implementar DataExporter."""
        from core.exporters import CsvExporter, DataExporter
        
        exporter = CsvExporter()
        self.assertIsInstance(exporter, DataExporter)


class TestIntegrationAfterRefactoring(unittest.TestCase):
    """Testes de integração para garantir que tudo funciona junto."""
    
    def test_processor_with_mock_produces_correct_doc_type(self):
        """Fluxo completo com mock deve produzir documento com doc_type correto."""
        # Mock que simula texto de boleto
        mock_reader = Mock(spec=TextExtractionStrategy)
        mock_reader.extract.return_value = (
            "ITAÚ\n"
            "Linha Digitável: 12345.67890 12345.678901 12345.678901 1 23450000012345\n"
            "Vencimento: 15/01/2025\n"
            "Valor do Documento: R$ 2.500,00\n"
            "CNPJ Beneficiário: 12.345.678/0001-90"
        )
        
        processor = BaseInvoiceProcessor(reader=mock_reader)
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            result = processor.process(tmp_path)
            
            # Deve ter identificado como boleto
            self.assertEqual(result.doc_type, 'BOLETO')
            self.assertIsInstance(result, BoletoData)
            
            # Deve ter to_dict funcionando
            data_dict = result.to_dict()
            self.assertEqual(data_dict['tipo_documento'], 'BOLETO')
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
