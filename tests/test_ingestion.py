import unittest
import os
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch
from email.message import EmailMessage
from ingestors.imap import ImapIngestor
from config import settings

class TestImapIngestor(unittest.TestCase):
    def setUp(self):
        self.host = "imap.test.com"
        self.user = "user@test.com"
        self.password = "pass"
        self.ingestor = ImapIngestor(self.host, self.user, self.password)

    @patch('ingestors.imap.imaplib.IMAP4_SSL')
    def test_connect(self, mock_imap):
        """Testa a conexão e login no servidor IMAP."""
        self.ingestor.connect()
        
        mock_imap.assert_called_with(self.host)
        instance = mock_imap.return_value
        instance.login.assert_called_with(self.user, self.password)
        instance.select.assert_called_with("INBOX")

    @patch('ingestors.imap.imaplib.IMAP4_SSL')
    def test_fetch_attachments_success(self, mock_imap):
        """Testa a busca e extração de anexos PDF."""
        # 1. Configurar Mock do Servidor
        mock_conn = mock_imap.return_value
        self.ingestor.connection = mock_conn
        
        # Mock SEARCH: Retorna IDs dos e-mails (ex: '1 2')
        mock_conn.search.return_value = ('OK', [b'1'])
        
        # Mock FETCH: Retorna o conteúdo bruto do e-mail
        # Vamos criar um e-mail real em memória para o teste ser fiel
        msg = EmailMessage()
        msg['Subject'] = 'Nota Fiscal Teste'
        msg.set_content('Segue anexo.')
        
        # Adiciona anexo PDF simulado
        pdf_content = b'%PDF-1.4 test content'
        msg.add_attachment(pdf_content, maintype='application', subtype='pdf', filename='nota.pdf')
        
        # O retorno do fetch é complexo: (status, [(header, body), closing])
        raw_email = msg.as_bytes()
        mock_conn.fetch.return_value = ('OK', [(b'1 (RFC822)', raw_email)])

        # 2. Executar
        results = self.ingestor.fetch_attachments(subject_filter="Nota Fiscal")

        # 3. Asserções
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['filename'], 'nota.pdf')
        self.assertEqual(results[0]['content'], pdf_content)
        self.assertEqual(results[0]['source'], self.user)

class TestIngestionIntegration(unittest.TestCase):
    """
    Testa a lógica de integração 'Bytes -> Disco' usada no run_ingestion.py.
    """
    def setUp(self):
        # Cria diretório temporário de teste
        self.test_dir = Path("tests/temp_ingestion_test")
        os.makedirs(self.test_dir, exist_ok=True)
        
        # Patch no settings para usar nosso diretório de teste
        self.patcher = patch('config.settings.DIR_TEMP', self.test_dir)
        self.mock_settings_dir = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_save_bytes_to_disk_with_unique_name(self):
        """Simula o loop principal do run_ingestion.py para garantir que arquivos são salvos corretamente."""
        
        # Dados simulados vindos do Ingestor
        mock_anexos = [
            {'filename': 'invoice.pdf', 'content': b'PDF1'},
            {'filename': 'invoice.pdf', 'content': b'PDF2'} # Nome repetido intencional
        ]
        
        saved_files = []
        
        # Lógica copiada/adaptada do run_ingestion.py
        for item in mock_anexos:
            filename = item['filename']
            content_bytes = item['content']
            
            # GERA UM NOME ÚNICO
            unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
            file_path = self.test_dir / unique_filename
            
            with open(file_path, 'wb') as f:
                f.write(content_bytes)
            
            saved_files.append(file_path)

        # Verificações
        self.assertEqual(len(saved_files), 2)
        
        # Garante que ambos existem (não houve sobrescrita)
        self.assertTrue(os.path.exists(saved_files[0]))
        self.assertTrue(os.path.exists(saved_files[1]))
        
        # Garante que os conteúdos são diferentes
        with open(saved_files[0], 'rb') as f:
            self.assertEqual(f.read(), b'PDF1')
            
        with open(saved_files[1], 'rb') as f:
            self.assertEqual(f.read(), b'PDF2')

        # Garante que os nomes são diferentes apesar do filename original ser igual
        self.assertNotEqual(saved_files[0].name, saved_files[1].name)

if __name__ == '__main__':
    unittest.main()
