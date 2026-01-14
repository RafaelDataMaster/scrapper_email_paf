"""
Testes para as estratégias de extração de texto de PDFs.

Testa:
    - NativePdfStrategy: extração de texto nativo
    - TablePdfStrategy: extração de tabelas
    - TesseractOcrStrategy: extração via OCR
    - Funções utilitárias de tratamento de senha
"""
import unittest
from unittest.mock import MagicMock, patch


class TestNativePdfStrategy(unittest.TestCase):
    """Testes para a estratégia de extração nativa de PDFs."""

    def setUp(self):
        from strategies.native import NativePdfStrategy
        self.strategy = NativePdfStrategy()

    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_extract_success(self, mock_pdf_open):
        """Testa se a extração retorna texto quando o PDF é legível."""
        # Configura o Mock para simular um PDF com texto
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Nota Fiscal de Serviço Eletrônica - Valor R$ 100,00 - Prestador XYZ"
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value = mock_pdf

        texto = self.strategy.extract("caminho/falso.pdf")

        self.assertIn("Nota Fiscal", texto)
        self.assertIn("100,00", texto)

    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_extract_fallback_empty_text(self, mock_pdf_open):
        """Testa se retorna vazio (gatilho para OCR) quando o PDF tem pouco texto."""
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        # Simula texto insuficiente (< 50 caracteres)
        mock_page.extract_text.return_value = "   "
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value = mock_pdf

        texto = self.strategy.extract("caminho/falso.pdf")

        # Deve retornar string vazia para ativar o fallback
        self.assertEqual(texto, "")

    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_extract_file_error(self, mock_pdf_open):
        """Testa resiliência a erros de arquivo."""
        mock_pdf_open.side_effect = Exception("Arquivo corrompido")

        texto = self.strategy.extract("arquivo_ruim.pdf")
        self.assertEqual(texto, "")

    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_extract_password_protected_success(self, mock_pdf_open):
        """Testa se consegue extrair de PDF protegido por senha conhecida."""
        # Primeira chamada falha com erro de senha
        # Segunda chamada (com senha) funciona
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Conteúdo do PDF protegido - Valor R$ 500,00 - Empresa XYZ"
        mock_pdf.pages = [mock_page]

        def open_side_effect(path, password=None):
            if password is None:
                raise Exception("File is password protected")
            return mock_pdf

        mock_pdf_open.side_effect = open_side_effect

        texto = self.strategy.extract("protegido.pdf")

        self.assertIn("Conteúdo do PDF protegido", texto)
        self.assertIn("500,00", texto)


class TestTablePdfStrategy(unittest.TestCase):
    """Testes para a estratégia de extração de tabelas de PDFs."""

    def setUp(self):
        from strategies.table import TablePdfStrategy
        self.strategy = TablePdfStrategy()

    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_extract_with_tables(self, mock_pdf_open):
        """Testa extração de PDF com tabelas estruturadas."""
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Texto base do documento"
        # Formato: [headers], [row1], [row2]...
        # A saída será "Header1: Value1\nHeader2: Value2\n" para cada row
        mock_page.extract_tables.return_value = [
            [["CNPJ", "Valor"], ["12.345.678/0001-90", "100,00"]]
        ]
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value = mock_pdf

        texto = self.strategy.extract("tabela.pdf")

        self.assertIn("DADOS ESTRUTURADOS", texto)
        self.assertIn("CNPJ: 12.345.678/0001-90", texto)
        self.assertIn("Valor: 100,00", texto)

    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_extract_no_tables(self, mock_pdf_open):
        """Testa retorno vazio quando não há tabelas."""
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Texto sem tabelas"
        mock_page.extract_tables.return_value = []
        mock_pdf.pages = [mock_page]
        mock_pdf_open.return_value = mock_pdf

        texto = self.strategy.extract("sem_tabela.pdf")

        # Deve retornar vazio se não encontrou tabelas
        self.assertEqual(texto, "")

    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_extract_password_protected(self, mock_pdf_open):
        """Testa extração de tabelas de PDF protegido por senha."""
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Documento protegido"
        # Formato: primeira linha é header, demais são dados
        mock_page.extract_tables.return_value = [
            [["Campo", "Vencimento"], ["Valor", "15/01/2025"]]
        ]
        mock_pdf.pages = [mock_page]

        def open_side_effect(path, password=None):
            if password is None:
                raise Exception("encrypted")
            return mock_pdf

        mock_pdf_open.side_effect = open_side_effect

        texto = self.strategy.extract("tabela_protegida.pdf")

        self.assertIn("DADOS ESTRUTURADOS", texto)
        self.assertIn("Vencimento: 15/01/2025", texto)


class TestGerarCandidatosSenha(unittest.TestCase):
    """Testes para a função de geração de candidatos de senha."""

    @patch('strategies.pdf_utils.EMPRESAS_CADASTRO', {
        "12345678000190": {"razao_social": "Empresa Teste"},
        "98765432000155": {"razao_social": "Outra Empresa"},
    })
    def test_gerar_candidatos(self):
        """Testa geração de candidatos baseados em CNPJs."""
        from strategies.pdf_utils import gerar_candidatos_senha

        candidatos = gerar_candidatos_senha()

        # Deve incluir CNPJs completos
        self.assertIn("12345678000190", candidatos)
        self.assertIn("98765432000155", candidatos)

        # Deve incluir 4 primeiros dígitos
        self.assertIn("1234", candidatos)
        self.assertIn("9876", candidatos)

        # Deve incluir 5 primeiros dígitos
        self.assertIn("12345", candidatos)
        self.assertIn("98765", candidatos)

        # Deve incluir 8 primeiros dígitos (raiz do CNPJ)
        self.assertIn("12345678", candidatos)
        self.assertIn("98765432", candidatos)

    @patch('strategies.pdf_utils.EMPRESAS_CADASTRO', {})
    def test_gerar_candidatos_vazio(self):
        """Testa que retorna lista vazia quando não há empresas."""
        from strategies.pdf_utils import gerar_candidatos_senha

        candidatos = gerar_candidatos_senha()

        self.assertEqual(candidatos, [])


class TestAbrirPdfplumberComSenha(unittest.TestCase):
    """Testes para a função de abertura de PDF com pdfplumber."""

    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_abrir_sem_senha(self, mock_open):
        """Testa abertura de PDF sem senha."""
        from strategies.pdf_utils import abrir_pdfplumber_com_senha

        mock_pdf = MagicMock()
        mock_pdf.pages = [MagicMock()]
        mock_open.return_value = mock_pdf

        result = abrir_pdfplumber_com_senha("teste.pdf")

        self.assertEqual(result, mock_pdf)
        mock_open.assert_called_once_with("teste.pdf")

    @patch('strategies.pdf_utils.gerar_candidatos_senha')
    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_abrir_com_senha_conhecida(self, mock_open, mock_candidatos):
        """Testa desbloqueio com senha conhecida."""
        from strategies.pdf_utils import abrir_pdfplumber_com_senha

        mock_candidatos.return_value = ["1234", "5678", "senha_certa"]
        mock_pdf = MagicMock()
        mock_pdf.pages = [MagicMock()]

        def open_side_effect(path, password=None):
            if password == "senha_certa":
                return mock_pdf
            raise Exception("password required" if password is None else "wrong password")

        mock_open.side_effect = open_side_effect

        result = abrir_pdfplumber_com_senha("protegido.pdf")

        self.assertEqual(result, mock_pdf)

    @patch('strategies.pdf_utils.gerar_candidatos_senha')
    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_abrir_senha_desconhecida(self, mock_open, mock_candidatos):
        """Testa falha quando nenhuma senha funciona."""
        from strategies.pdf_utils import abrir_pdfplumber_com_senha

        mock_candidatos.return_value = ["1234", "5678"]
        mock_open.side_effect = Exception("password required")

        result = abrir_pdfplumber_com_senha("senha_desconhecida.pdf")

        self.assertIsNone(result)

    @patch('strategies.pdf_utils.pdfplumber.open')
    def test_abrir_erro_nao_relacionado_senha(self, mock_open):
        """Testa que erros não relacionados a senha retornam None."""
        from strategies.pdf_utils import abrir_pdfplumber_com_senha

        mock_open.side_effect = Exception("arquivo corrompido")

        result = abrir_pdfplumber_com_senha("corrompido.pdf")

        self.assertIsNone(result)


class TestAbrirPypdfiumComSenha(unittest.TestCase):
    """Testes para a função de abertura de PDF com pypdfium2."""

    @patch('strategies.pdf_utils.pdfium.PdfDocument')
    def test_abrir_sem_senha(self, mock_pdf_class):
        """Testa abertura de PDF sem senha."""
        from strategies.pdf_utils import abrir_pypdfium_com_senha

        mock_pdf = MagicMock()
        mock_pdf_class.return_value = mock_pdf

        result = abrir_pypdfium_com_senha("teste.pdf")

        self.assertEqual(result, mock_pdf)
        mock_pdf_class.assert_called_once_with("teste.pdf")

    @patch('strategies.pdf_utils.gerar_candidatos_senha')
    @patch('strategies.pdf_utils.pdfium')
    def test_abrir_com_senha_conhecida(self, mock_pdfium, mock_candidatos):
        """Testa desbloqueio com senha conhecida."""
        from strategies.pdf_utils import abrir_pypdfium_com_senha

        mock_candidatos.return_value = ["1234", "5678", "senha_certa"]
        mock_pdf = MagicMock()

        # Simula erro de senha
        mock_pdfium.PdfiumError = Exception

        def pdf_side_effect(path, password=None):
            if password == "senha_certa":
                return mock_pdf
            error = Exception("password" if password is None else "wrong")
            raise error

        mock_pdfium.PdfDocument.side_effect = pdf_side_effect

        result = abrir_pypdfium_com_senha("protegido.pdf")

        self.assertEqual(result, mock_pdf)


class TestSmartExtractionStrategy(unittest.TestCase):
    """Testes para a estratégia de extração inteligente (fallback)."""

    def setUp(self):
        from strategies.fallback import SmartExtractionStrategy
        self.strategy = SmartExtractionStrategy()

    @patch('strategies.fallback.NativePdfStrategy.extract')
    def test_native_success(self, mock_native):
        """Testa que usa estratégia nativa quando funciona."""
        mock_native.return_value = "Texto extraído com sucesso - valor de 100,00 em 01/01/2025 CNPJ 12.345.678/0001-90"

        texto = self.strategy.extract("documento.pdf")

        self.assertIn("Texto extraído", texto)
        mock_native.assert_called_once()

    @patch('strategies.fallback.TesseractOcrStrategy.extract')
    @patch('strategies.fallback.TablePdfStrategy.extract')
    @patch('strategies.fallback.NativePdfStrategy.extract')
    def test_fallback_to_ocr(self, mock_native, mock_table, mock_ocr):
        """Testa fallback para OCR quando outras estratégias falham."""
        mock_native.return_value = ""
        mock_table.return_value = ""
        mock_ocr.return_value = "Texto extraído via OCR - valor de 200,00 em 15/02/2025"

        texto = self.strategy.extract("escaneado.pdf")

        self.assertIn("OCR", texto)
        mock_native.assert_called_once()
        mock_table.assert_called_once()
        mock_ocr.assert_called_once()


if __name__ == '__main__':
    unittest.main()
