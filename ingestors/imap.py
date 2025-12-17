import imaplib
import email
from email.header import decode_header
from typing import List, Dict, Any
from core.interfaces import EmailIngestorStrategy

class ImapIngestor(EmailIngestorStrategy):
    """
    Implementação de ingestão de e-mails via protocolo IMAP.

    Esta classe gerencia a conexão segura (SSL) com servidores de e-mail,
    realiza buscas filtradas por assunto e extrai anexos PDF.

    Attributes:
        host (str): Endereço do servidor IMAP (ex: imap.gmail.com).
        user (str): Usuário para autenticação.
        password (str): Senha ou App Password.
        folder (str): Pasta do e-mail a ser monitorada (Padrão: INBOX).
    """

    def __init__(self, host: str, user: str, password: str, folder: str = "INBOX"):
        self.host = host
        self.user = user
        self.password = password
        self.folder = folder
        self.connection = None

    def connect(self) -> None:
        """
        Estabelece conexão SSL com o servidor IMAP e realiza login.

        Raises:
            imaplib.IMAP4.error: Se houver falha na conexão ou autenticação.
        """
        # Conexão SSL padrão (Porta 993)
        self.connection = imaplib.IMAP4_SSL(self.host)
        self.connection.login(self.user, self.password)
        self.connection.select(self.folder) # Seleciona caixa de entrada

    def _decode_text(self, text: str) -> str:
        """
        Decodifica cabeçalhos de e-mail (Assunto, Nome de arquivo) de forma segura.
        Trata diferentes encodings e evita falhas de 'utf-8 codec error'.
        """
        if not text:
            return ""
            
        decoded_list = decode_header(text)
        final_text = ""
        
        for content, encoding in decoded_list:
            if isinstance(content, bytes):
                if not encoding:
                    # Se não vier encoding, tenta utf-8, se falhar vai de latin-1
                    encoding = "utf-8"
                
                try:
                    final_text += content.decode(encoding, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    # Fallback agressivo para latin-1 se o encoding informado estiver errado
                    final_text += content.decode("latin-1", errors="replace")
            else:
                final_text += str(content)
                
        return final_text

    def fetch_attachments(self, subject_filter: str = "Nota Fiscal") -> List[Dict[str, Any]]:
        """
        Busca e-mails pelo assunto e extrai anexos PDF.

        Args:
            subject_filter (str): Texto para filtrar o assunto dos e-mails.

        Returns:
            List[Dict[str, Any]]: Lista de dicionários contendo:
                - filename (str): Nome do arquivo decodificado.
                - content (bytes): Conteúdo binário do arquivo.
                - source (str): E-mail de origem (usuário).
                - subject (str): Assunto do e-mail.
        """
        if not self.connection:
            self.connect()
            
        # Busca no servidor (Filtering Server-side é limitado no IMAP)
        # IMAP search é verboso
        status, messages = self.connection.search(None, f'(SUBJECT "{subject_filter}")')
        
        results = []
        if not messages or messages[0] == b'':
            return results

        for num in messages[0].split():
            try:
                _, msg_data = self.connection.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                msg = email.message_from_bytes(msg_data[0][1])
                
                # Uso do método seguro
                subject = self._decode_text(msg["Subject"])
                
                # Navegar pela árvore MIME para achar anexos 
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    if part.get('Content-Disposition') is None:
                        continue
                        
                    filename = part.get_filename()
                    if filename and filename.lower().endswith('.pdf'):
                        # Uso do método seguro
                        filename = self._decode_text(filename)
                        
                        results.append({
                            'filename': filename,
                            'content': part.get_payload(decode=True),
                            'source': self.user,
                            'subject': subject
                        })
            except Exception as e:
                print(f"⚠️ Erro ao ler e-mail ID {num}: {e}")
                continue

        return results