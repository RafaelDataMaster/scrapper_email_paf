import email
import imaplib
import logging
from email.header import decode_header
from typing import Any, Dict, List

from core.interfaces import EmailIngestorStrategy

logger = logging.getLogger(__name__)


class ImapIngestor(EmailIngestorStrategy):
    """
    Implementação de ingestão de e-mails via protocolo IMAP.

    Esta classe gerencia a conexão segura (SSL) com servidores de e-mail,
    realiza buscas filtradas por assunto e extrai anexos PDF e XML.

    Attributes:
        host (str): Endereço do servidor IMAP (ex: imap.gmail.com).
        user (str): Usuário para autenticação.
        password (str): Senha ou App Password.
        folder (str): Pasta do e-mail a ser monitorada (Padrão: INBOX).
    """

    # Extensões de arquivos válidos para extração
    VALID_EXTENSIONS = {'.pdf', '.xml'}

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

    def _is_valid_attachment(self, filename: str) -> bool:
        """
        Verifica se o arquivo é um anexo válido (PDF ou XML).

        Args:
            filename: Nome do arquivo

        Returns:
            True se for PDF ou XML
        """
        if not filename:
            return False

        ext = filename.lower()
        return any(ext.endswith(valid_ext) for valid_ext in self.VALID_EXTENSIONS)

    def _extract_email_body(self, msg: email.message.Message) -> str:
        """
        Extrai o corpo do e-mail em texto plano E HTML combinados.

        Combina texto plano e HTML para garantir que links e códigos
        presentes apenas no HTML também sejam capturados.

        Args:
            msg: Objeto Message do email

        Returns:
            Texto combinado do corpo do e-mail (plain + HTML)
        """
        body_text = ""
        body_html = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # Pula anexos
                if "attachment" in content_disposition:
                    continue

                try:
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue

                    charset = part.get_content_charset() or 'utf-8'
                    decoded = payload.decode(charset, errors='replace')

                    if content_type == "text/plain":
                        body_text += decoded
                    elif content_type == "text/html":
                        body_html += decoded
                except Exception:
                    pass
        else:
            content_type = msg.get_content_type()
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    decoded = payload.decode(charset, errors='replace')

                    if content_type == "text/plain":
                        body_text = decoded
                    elif content_type == "text/html":
                        body_html = decoded
            except Exception:
                pass

        # Combina texto plano e HTML (HTML pode conter links não presentes no texto)
        # Separa com marcador para facilitar debug
        combined = body_text
        if body_html:
            combined += "\n\n--- HTML CONTENT ---\n\n" + body_html

        return combined

    def _extract_sender_info(self, msg: email.message.Message) -> Dict[str, str]:
        """
        Extrai informações do remetente do e-mail.

        Args:
            msg: Objeto Message do email

        Returns:
            Dict com 'name' e 'address' do remetente
        """
        from_header = msg.get("From", "")
        decoded_from = self._decode_text(from_header)

        sender_name = ""
        sender_address = ""

        # Tenta extrair nome e email do formato "Nome <email@domain.com>"
        if "<" in decoded_from and ">" in decoded_from:
            parts = decoded_from.rsplit("<", 1)
            sender_name = parts[0].strip().strip('"\'')
            sender_address = parts[1].rstrip(">").strip()
        else:
            sender_address = decoded_from.strip()

        return {"name": sender_name, "address": sender_address}

    def fetch_attachments(self, subject_filter: str = "") -> List[Dict[str, Any]]:
        """
        Busca e-mails pelo assunto e extrai anexos PDF e XML.

        Cada anexo retornado inclui um 'email_id' para permitir
        agrupamento de múltiplos anexos do mesmo e-mail.

        Args:
            subject_filter (str): Texto para filtrar o assunto dos e-mails.
                                  Se vazio ou "*", busca TODOS os e-mails.

        Returns:
            List[Dict[str, Any]]: Lista de dicionários contendo:
                - filename (str): Nome do arquivo decodificado.
                - content (bytes): Conteúdo binário do arquivo.
                - source (str): E-mail de origem (usuário).
                - subject (str): Assunto do e-mail.
                - email_id (str): Identificador único do e-mail de origem.
                - sender_name (str): Nome do remetente.
                - sender_address (str): E-mail do remetente.
                - body_text (str): Corpo do e-mail (texto).
                - received_date (str): Data de recebimento.
        """
        if not self.connection:
            self.connect()

        # Busca no servidor - se filtro vazio ou "*", busca TODOS
        if not subject_filter or subject_filter == "*":
            status, messages = self.connection.search(None, 'ALL')
        else:
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

                # Gera um email_id único baseado no Message-ID ou número sequencial
                message_id = msg.get("Message-ID", "")
                if message_id:
                    # Limpa o Message-ID para usar como identificador
                    email_id = message_id.strip("<>").replace("@", "_").replace(".", "_")
                else:
                    # Fallback: usa o número do email no servidor
                    email_id = f"email_{num.decode('utf-8')}"

                # Extrai metadados do e-mail
                subject = self._decode_text(msg["Subject"])
                sender_info = self._extract_sender_info(msg)
                body_text = self._extract_email_body(msg)
                received_date = msg.get("Date", "")

                # Navegar pela árvore MIME para achar anexos
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    if part.get('Content-Disposition') is None:
                        continue

                    filename = part.get_filename()

                    # Aceita PDF e XML
                    if self._is_valid_attachment(filename):
                        # Uso do método seguro
                        filename = self._decode_text(filename)

                        results.append({
                            'filename': filename,
                            'content': part.get_payload(decode=True),
                            'source': self.user,
                            'subject': subject,
                            'email_id': email_id,
                            'sender_name': sender_info['name'],
                            'sender_address': sender_info['address'],
                            'body_text': body_text,
                            'received_date': received_date,
                        })

            except Exception as e:
                logger.warning(f"Erro ao ler e-mail ID {num}: {e}")
                continue

        return results

    def fetch_emails_grouped(self, subject_filter: str = "Nota Fiscal") -> List[Dict[str, Any]]:
        """
        Busca e-mails pelo assunto e retorna agrupados (um dict por e-mail).

        Diferente de fetch_attachments que retorna um item por anexo,
        este método retorna um item por e-mail com todos os anexos juntos.

        Args:
            subject_filter (str): Texto para filtrar o assunto dos e-mails.

        Returns:
            List[Dict[str, Any]]: Lista de dicionários (um por e-mail) contendo:
                - email_id (str): Identificador único do e-mail.
                - subject (str): Assunto do e-mail.
                - sender_name (str): Nome do remetente.
                - sender_address (str): E-mail do remetente.
                - body_text (str): Corpo do e-mail (texto).
                - received_date (str): Data de recebimento.
                - attachments (List[Dict]): Lista de anexos com 'filename' e 'content'.
        """
        # Busca anexos individuais
        attachments = self.fetch_attachments(subject_filter)

        # Agrupa por email_id
        emails_map: Dict[str, Dict[str, Any]] = {}

        for att in attachments:
            email_id = att['email_id']

            if email_id not in emails_map:
                emails_map[email_id] = {
                    'email_id': email_id,
                    'subject': att['subject'],
                    'sender_name': att['sender_name'],
                    'sender_address': att['sender_address'],
                    'body_text': att['body_text'],
                    'received_date': att['received_date'],
                    'attachments': [],
                }

            emails_map[email_id]['attachments'].append({
                'filename': att['filename'],
                'content': att['content'],
            })

        return list(emails_map.values())

    def fetch_emails_without_attachments(
        self,
        subject_filter: str = "",
        limit: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Busca e-mails SEM anexos PDF/XML válidos.

        Útil para capturar e-mails que contêm apenas links de download
        ou códigos de verificação para acessar notas fiscais em portais.

        Args:
            subject_filter (str): Texto para filtrar o assunto dos e-mails.
                                  Se vazio ou "*", busca TODOS os e-mails.
            limit (int): Máximo de e-mails a retornar (0 = sem limite).

        Returns:
            List[Dict[str, Any]]: Lista de dicionários (um por e-mail) contendo:
                - email_id (str): Identificador único do e-mail.
                - subject (str): Assunto do e-mail.
                - sender_name (str): Nome do remetente.
                - sender_address (str): E-mail do remetente.
                - body_text (str): Corpo do e-mail (texto).
                - received_date (str): Data de recebimento.
                - has_attachments (bool): False (sem anexos válidos).
        """
        if not self.connection:
            self.connect()

        # Busca no servidor - se filtro vazio ou "*", busca TODOS
        if not subject_filter or subject_filter == "*":
            status, messages = self.connection.search(None, 'ALL')
        else:
            status, messages = self.connection.search(None, f'(SUBJECT "{subject_filter}")')

        results = []
        count = 0

        if not messages or messages[0] == b'':
            return results

        for num in messages[0].split():
            if limit > 0 and count >= limit:
                break

            try:
                _, msg_data = self.connection.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                msg = email.message_from_bytes(msg_data[0][1])

                # Verifica se tem anexo válido - se tiver, pula
                has_valid_attachment = False
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    if part.get('Content-Disposition') is None:
                        continue

                    filename = part.get_filename()
                    if self._is_valid_attachment(filename):
                        has_valid_attachment = True
                        break

                # Só processa e-mails SEM anexos válidos
                if has_valid_attachment:
                    continue

                # Gera email_id único
                message_id = msg.get("Message-ID", "")
                if message_id:
                    email_id = message_id.strip("<>").replace("@", "_").replace(".", "_")
                else:
                    email_id = f"email_{num.decode('utf-8')}"

                # Extrai metadados
                subject = self._decode_text(msg["Subject"])
                sender_info = self._extract_sender_info(msg)
                body_text = self._extract_email_body(msg)
                received_date = msg.get("Date", "")

                results.append({
                    'email_id': email_id,
                    'subject': subject,
                    'sender_name': sender_info['name'],
                    'sender_address': sender_info['address'],
                    'body_text': body_text,
                    'received_date': received_date,
                    'has_attachments': False,
                })

                count += 1

            except Exception as e:
                logger.warning(f"Erro ao ler e-mail ID {num}: {e}")
                continue

        return results
