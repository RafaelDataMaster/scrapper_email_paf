import os
import shutil
import unittest
import uuid
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

from ingestors.imap import ImapIngestor
from services.ingestion_service import IngestionService


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

class TestImapIngestorXmlSupport(unittest.TestCase):
    """Testa suporte a arquivos XML além de PDF."""

    def setUp(self):
        self.host = "imap.test.com"
        self.user = "user@test.com"
        self.password = "pass"
        self.ingestor = ImapIngestor(self.host, self.user, self.password)

    @patch('ingestors.imap.imaplib.IMAP4_SSL')
    def test_fetch_attachments_includes_xml(self, mock_imap):
        """Testa que arquivos XML são baixados junto com PDFs."""
        mock_conn = mock_imap.return_value
        self.ingestor.connection = mock_conn

        mock_conn.search.return_value = ('OK', [b'1'])

        msg = EmailMessage()
        msg['Subject'] = 'NFS-e + Boleto'
        msg['From'] = 'fornecedor@empresa.com'
        msg['Message-ID'] = '<test123@example.com>'
        msg.set_content('Segue NFS-e e boleto em anexo.')

        # Adiciona PDF
        pdf_content = b'%PDF-1.4 boleto content'
        msg.add_attachment(pdf_content, maintype='application', subtype='pdf', filename='boleto.pdf')

        # Adiciona XML
        xml_content = b'<?xml version="1.0"?><NFSe>...</NFSe>'
        msg.add_attachment(xml_content, maintype='application', subtype='xml', filename='nfse.xml')

        raw_email = msg.as_bytes()
        mock_conn.fetch.return_value = ('OK', [(b'1 (RFC822)', raw_email)])

        results = self.ingestor.fetch_attachments(subject_filter="NFS-e")

        # Deve retornar AMBOS os anexos (PDF e XML)
        self.assertEqual(len(results), 2)
        filenames = [r['filename'] for r in results]
        self.assertIn('boleto.pdf', filenames)
        self.assertIn('nfse.xml', filenames)

    @patch('ingestors.imap.imaplib.IMAP4_SSL')
    def test_fetch_attachments_includes_email_id(self, mock_imap):
        """Testa que cada anexo inclui email_id para agrupamento."""
        mock_conn = mock_imap.return_value
        self.ingestor.connection = mock_conn

        mock_conn.search.return_value = ('OK', [b'1'])

        msg = EmailMessage()
        msg['Subject'] = 'Teste'
        msg['Message-ID'] = '<unique123@domain.com>'
        msg.set_content('Corpo do email.')

        msg.add_attachment(b'%PDF', maintype='application', subtype='pdf', filename='doc1.pdf')
        msg.add_attachment(b'%PDF', maintype='application', subtype='pdf', filename='doc2.pdf')

        raw_email = msg.as_bytes()
        mock_conn.fetch.return_value = ('OK', [(b'1 (RFC822)', raw_email)])

        results = self.ingestor.fetch_attachments(subject_filter="Teste")

        # Ambos os anexos devem ter o mesmo email_id
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['email_id'], results[1]['email_id'])
        self.assertIn('email_id', results[0])
        self.assertIn('sender_address', results[0])

    @patch('ingestors.imap.imaplib.IMAP4_SSL')
    def test_fetch_emails_grouped(self, mock_imap):
        """Testa o método fetch_emails_grouped que agrupa por email."""
        mock_conn = mock_imap.return_value
        self.ingestor.connection = mock_conn

        mock_conn.search.return_value = ('OK', [b'1'])

        msg = EmailMessage()
        msg['Subject'] = 'Fatura Completa'
        msg['Message-ID'] = '<msg123@test.com>'
        msg['From'] = 'Fornecedor <fornecedor@empresa.com>'
        msg.set_content('Segue NFS-e, boleto e XML.')

        msg.add_attachment(b'%PDF-nfse', maintype='application', subtype='pdf', filename='nfse.pdf')
        msg.add_attachment(b'%PDF-boleto', maintype='application', subtype='pdf', filename='boleto.pdf')
        msg.add_attachment(b'<?xml', maintype='application', subtype='xml', filename='nfse.xml')

        raw_email = msg.as_bytes()
        mock_conn.fetch.return_value = ('OK', [(b'1 (RFC822)', raw_email)])

        results = self.ingestor.fetch_emails_grouped(subject_filter="Fatura")

        # Deve retornar 1 email com 3 anexos agrupados
        self.assertEqual(len(results), 1)
        email_data = results[0]
        self.assertEqual(email_data['subject'], 'Fatura Completa')
        self.assertEqual(len(email_data['attachments']), 3)


class TestIngestionServiceGrouping(unittest.TestCase):
    """Testa o agrupamento de anexos por email no IngestionService."""

    def setUp(self):
        self.test_dir = Path("tests/temp_grouping_test")
        os.makedirs(self.test_dir, exist_ok=True)

        # Mock do ingestor
        self.mock_ingestor = MagicMock()
        self.service = IngestionService(self.mock_ingestor, self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_group_attachments_by_email(self):
        """Testa que anexos com mesmo email_id são agrupados."""
        attachments = [
            {
                'filename': 'nfse.pdf',
                'content': b'%PDF-nfse',
                'email_id': 'email_001',
                'subject': 'Fatura Empresa X',
                'sender_name': 'Empresa X',
                'sender_address': 'empresa@x.com',
                'body_text': 'Segue fatura',
                'received_date': '2025-01-01',
            },
            {
                'filename': 'boleto.pdf',
                'content': b'%PDF-boleto',
                'email_id': 'email_001',  # Mesmo email_id
                'subject': 'Fatura Empresa X',
                'sender_name': 'Empresa X',
                'sender_address': 'empresa@x.com',
                'body_text': 'Segue fatura',
                'received_date': '2025-01-01',
            },
            {
                'filename': 'nfse.xml',
                'content': b'<?xml>',
                'email_id': 'email_001',  # Mesmo email_id
                'subject': 'Fatura Empresa X',
                'sender_name': 'Empresa X',
                'sender_address': 'empresa@x.com',
                'body_text': 'Segue fatura',
                'received_date': '2025-01-01',
            },
        ]

        grouped = self.service._group_attachments_by_email(attachments)

        # Deve ter apenas 1 grupo (1 email)
        self.assertEqual(len(grouped), 1)

        # O grupo deve ter 3 anexos
        email_data = grouped['email_001']
        self.assertEqual(len(email_data['attachments']), 3)
        self.assertEqual(email_data['subject'], 'Fatura Empresa X')

    def test_ingest_single_email_with_multiple_attachments(self):
        """Testa que um email com múltiplos anexos cria 1 lote com todos os arquivos."""
        email_data = {
            'subject': 'Fatura Completa',
            'sender_name': 'Fornecedor LTDA',
            'sender_address': 'nf@fornecedor.com',
            'body_text': 'Segue NFS-e e boleto.',
            'received_date': '2025-06-15',
            'attachments': [
                {'filename': 'nfse.pdf', 'content': b'%PDF-nfse-content'},
                {'filename': 'boleto.pdf', 'content': b'%PDF-boleto-content'},
                {'filename': 'nfse.xml', 'content': b'<?xml version="1.0"?>'},
            ],
        }

        batch_path = self.service.ingest_single_email(email_data)

        # Deve criar pasta do lote
        self.assertIsNotNone(batch_path)
        self.assertTrue(batch_path.exists())

        # Deve ter 3 arquivos + metadata.json
        files = list(batch_path.glob('*'))
        # Filtra só arquivos (não diretórios)
        files = [f for f in files if f.is_file()]
        self.assertEqual(len(files), 4)  # 3 anexos + metadata.json

        # Verifica que os arquivos foram salvos
        pdf_files = list(batch_path.glob('*.pdf'))
        xml_files = list(batch_path.glob('*.xml'))
        self.assertEqual(len(pdf_files), 2)
        self.assertEqual(len(xml_files), 1)


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
