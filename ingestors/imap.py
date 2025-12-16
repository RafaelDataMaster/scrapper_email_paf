import imaplib
import email
from email.header import decode_header
from core.interfaces import EmailIngestorStrategy

class ImapIngestor(EmailIngestorStrategy):
    def __init__(self, host, user, password):
        self.host = host
        self.user = user
        self.password = password
        self.connection = None

    def connect(self):
        # Conexão SSL padrão (Porta 993)
        self.connection = imaplib.IMAP4_SSL(self.host)
        self.connection.login(self.user, self.password)
        self.connection.select("INBOX") # Seleciona caixa de entrada

    def fetch_attachments(self, subject_filter="Nota Fiscal"):
        if not self.connection:
            self.connect()
            
        # Busca no servidor (Filtering Server-side é limitado no IMAP)
        # [cite: 21] IMAP search é verboso
        status, messages = self.connection.search(None, f'(SUBJECT "{subject_filter}")')
        
        results = []
        for num in messages[0].split():
            _, msg_data = self.connection.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            
            # Navegar pela árvore MIME para achar anexos [cite: 27]
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue
                    
                filename = part.get_filename()
                if filename and filename.lower().endswith('.pdf'):
                    # Decodificar nome do arquivo (ex: =?utf-8?Q?...) [cite: 26]
                    decoded_list = decode_header(filename)
                    filename = "".join([t[0].decode(t[1] or 'utf-8') if isinstance(t[0], bytes) else t[0] for t in decoded_list])
                    
                    results.append({
                        'filename': filename,
                        'content': part.get_payload(decode=True),
                        'source': self.user
                    })
        return results