import unittest
from unittest.mock import MagicMock, patch
from strategies.native import NativePdfStrategy

class TestNativePdfStrategy(unittest.TestCase):
    def setUp(self):
        self.strategy = NativePdfStrategy()

    @patch('strategies.native.pdfplumber.open')
    def test_extract_success(self, mock_pdf_open):
        """Testa se a extração retorna texto quando o PDF é legível."""
        # Configura o Mock para simular um PDF com texto
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Nota Fiscal de Serviço Eletrônica - Valor R$ 100,00 - Prestador XYZ"
        mock_pdf.pages = [mock_page]
        
        # O Context Manager (__enter__) deve retornar o objeto mock_pdf
        mock_pdf_open.return_value.__enter__.return_value = mock_pdf

        texto = self.strategy.extract("caminho/falso.pdf")
        
        self.assertIn("Nota Fiscal", texto)
        self.assertIn("100,00", texto)

    @patch('strategies.native.pdfplumber.open')
    def test_extract_fallback_empty_text(self, mock_pdf_open):
        """Testa se retorna vazio (gatilho para OCR) quando o PDF tem pouco texto."""
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        # Simula texto insuficiente (< 50 caracteres)
        mock_page.extract_text.return_value = "   " 
        mock_pdf.pages = [mock_page]
        
        mock_pdf_open.return_value.__enter__.return_value = mock_pdf

        texto = self.strategy.extract("caminho/falso.pdf")
        
        # Deve retornar string vazia para ativar o fallback
        self.assertEqual(texto, "")

    @patch('strategies.native.pdfplumber.open')
    def test_extract_file_error(self, mock_pdf_open):
        """Testa resiliência a erros de arquivo."""
        mock_pdf_open.side_effect = Exception("Arquivo corrompido")
        
        texto = self.strategy.extract("arquivo_ruim.pdf")
        self.assertEqual(texto, "")

if __name__ == '__main__':
    unittest.main()
