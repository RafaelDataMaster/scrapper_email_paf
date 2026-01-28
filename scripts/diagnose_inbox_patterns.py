"""
Script de Diagnóstico de Padrões de E-mail na Caixa de Entrada.

Este script varre os últimos N e-mails da caixa de entrada (sem filtro de assunto)
e gera um relatório JSON classificando cada e-mail para identificar padrões úteis
para ingestão de Notas Fiscais e Boletos.

Objetivo: Identificar quais assuntos (subjects) de e-mail valem a pena ser
processados e quais devem ser ignorados no scrapper de NFs/Boletos.

Características:
- Processamento em STREAMING para evitar estouro de memória
- Escreve incrementalmente no arquivo (não acumula tudo em RAM)
- Seguro para caixas de entrada com milhares de e-mails
- Suporte a RESUME para continuar de onde parou

Usage:
    python scripts/diagnose_inbox_patterns.py
    python scripts/diagnose_inbox_patterns.py --limit 200
    python scripts/diagnose_inbox_patterns.py --limit 500 --output meu_diagnostico.json
    python scripts/diagnose_inbox_patterns.py --all  # Processa TODOS os e-mails
    python scripts/diagnose_inbox_patterns.py --all --resume  # Continua de onde parou
"""

from __future__ import annotations

import argparse
import imaplib
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
# datetime imported via email.utils
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

# Adiciona o diretório raiz ao path para importar config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings

# =============================================================================
# REGEX E KEYWORDS (Reutilizados do analyze_emails_no_attachment.py)
# =============================================================================

# Extensões de arquivos válidos (que indicam anexo relevante)
VALID_EXTENSIONS = {'.pdf', '.xml'}

# Regex SIMPLES para extrair URLs (eficiente, sem backtracking)
# Depois filtramos as URLs extraídas
REGEX_URL_SIMPLE = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)

# Keywords para identificar URLs de NF-e (aplicadas nas URLs já extraídas)
URL_KEYWORDS_NFE = [
    'nf', 'nfe', 'nfs', 'nfse', 'nota', 'fiscal', 'danfe',
    'prefeitura', 'gov.br', 'issnet', 'ginfes', 'betha',
    'download', 'baixar', 'visualizar', '.pdf', '.xml'
]

# Regex para códigos de autenticação/verificação (simplificados para evitar backtracking)
REGEX_CODIGOS = [
    # Chave de acesso NFe (44 dígitos) - mais específico primeiro
    (re.compile(r'\b(\d{44})\b'), 'chave_nfe'),
    # Códigos explícitos com palavra-chave
    (re.compile(r'(?:código|codigo|cód|cod)[\s:]+([A-Z0-9\-]{6,30})\b', re.IGNORECASE), 'codigo'),
    # Verificação/Autenticação
    (re.compile(r'(?:verificação|verificacao|autenticação|autenticacao)[\s:]+([A-Z0-9\-]{4,20})', re.IGNORECASE), 'verificacao'),
    # Protocolo
    (re.compile(r'protocolo[\s:]+([A-Z0-9\-\/]{6,30})', re.IGNORECASE), 'protocolo'),
    # Token em URL (padrão simples)
    (re.compile(r'token=([A-Za-z0-9\-_]{8,50})', re.IGNORECASE), 'token'),
]

# Palavras-chave para contexto
KEYWORDS_NF = ['nota fiscal', 'nf-e', 'nfse', 'nfs-e', 'danfe', 'xml', 'nota eletrônica', 'nfe']
KEYWORDS_BOLETO = ['boleto', 'fatura', 'cobrança', 'pagamento', 'vencimento', 'duplicata']
KEYWORDS_DOWNLOAD = ['download', 'baixar', 'clique', 'acesse', 'visualizar', 'acessar', 'clique aqui']
KEYWORDS_PORTAL = ['portal', 'sistema', 'plataforma', 'site', 'acesso']
KEYWORDS_PREFEITURA = ['prefeitura', 'município', 'secretaria', 'fazenda', 'issqn', 'iss']
KEYWORDS_VERIFICACAO = ['código de verificação', 'código de autenticação', 'autenticidade',
                         'verificar', 'validar', 'autenticar', 'chave de acesso']

# Consolidação de todas as keywords para busca
ALL_KEYWORDS = {
    'nf': KEYWORDS_NF,
    'boleto': KEYWORDS_BOLETO,
    'download': KEYWORDS_DOWNLOAD,
    'portal': KEYWORDS_PORTAL,
    'prefeitura': KEYWORDS_PREFEITURA,
    'verificacao': KEYWORDS_VERIFICACAO,
}


# =============================================================================
# ESTRUTURA DE DADOS
# =============================================================================

@dataclass
class EmailPattern:
    """Padrão identificado em um e-mail."""
    email_id: str  # ID do e-mail para suporte a resume
    subject: str
    sender_name: str
    sender_address: str
    has_attachment: bool
    has_links_nfe: bool
    has_verification_code: bool
    content_type: str
    keywords_found: List[str]
    date: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StreamingStats:
    """Estatísticas acumuladas durante o streaming (usa pouca memória)."""
    total_processed: int = 0
    errors: int = 0
    last_email_id: str = ""  # Para suporte a resume

    # Contadores por tipo
    count_com_anexo: int = 0
    count_link_com_codigo: int = 0
    count_link_download: int = 0
    count_apenas_codigo: int = 0
    count_irrelevante: int = 0

    # Contadores de flags
    count_with_attachment: int = 0
    count_with_nfe_links: int = 0
    count_with_verification_code: int = 0

    # Para keywords e remetentes, usamos Counter (memória controlada)
    keyword_counter: Optional[Counter] = None
    sender_counter: Optional[Counter] = None

    # Exemplos de subjects por tipo (limitados a 10 cada)
    examples_link_com_codigo: Optional[List[str]] = None
    examples_link_download: Optional[List[str]] = None
    examples_apenas_codigo: Optional[List[str]] = None

    def __post_init__(self):
        if self.keyword_counter is None:
            self.keyword_counter = Counter()
        if self.sender_counter is None:
            self.sender_counter = Counter()
        if self.examples_link_com_codigo is None:
            self.examples_link_com_codigo = []
        if self.examples_link_download is None:
            self.examples_link_download = []
        if self.examples_apenas_codigo is None:
            self.examples_apenas_codigo = []

    def update(self, pattern: EmailPattern) -> None:
        """Atualiza estatísticas com um novo padrão."""
        self.total_processed += 1
        self.last_email_id = pattern.email_id

        # Atualiza contadores de tipo
        if pattern.content_type == "COM_ANEXO":
            self.count_com_anexo += 1
        elif pattern.content_type == "LINK_COM_CODIGO":
            self.count_link_com_codigo += 1
            if self.examples_link_com_codigo is not None and len(self.examples_link_com_codigo) < 10:
                self.examples_link_com_codigo.append(pattern.subject)
        elif pattern.content_type == "LINK_DOWNLOAD":
            self.count_link_download += 1
            if self.examples_link_download is not None and len(self.examples_link_download) < 10:
                self.examples_link_download.append(pattern.subject)
        elif pattern.content_type == "APENAS_CODIGO":
            self.count_apenas_codigo += 1
            if self.examples_apenas_codigo is not None and len(self.examples_apenas_codigo) < 10:
                self.examples_apenas_codigo.append(pattern.subject)
        else:
            self.count_irrelevante += 1

        # Atualiza flags
        if pattern.has_attachment:
            self.count_with_attachment += 1
        if pattern.has_links_nfe:
            self.count_with_nfe_links += 1
        if pattern.has_verification_code:
            self.count_with_verification_code += 1

        # Atualiza contadores
        if self.keyword_counter is not None:
            for keyword in pattern.keywords_found:
                self.keyword_counter[keyword] += 1
        if self.sender_counter is not None:
            self.sender_counter[pattern.sender_address] += 1

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário para salvar como JSON."""
        return {
            "total_analisado": self.total_processed,
            "erros": self.errors,
            "last_email_id": self.last_email_id,
            "por_tipo": {
                "COM_ANEXO": self.count_com_anexo,
                "LINK_COM_CODIGO": self.count_link_com_codigo,
                "LINK_DOWNLOAD": self.count_link_download,
                "APENAS_CODIGO": self.count_apenas_codigo,
                "IRRELEVANTE": self.count_irrelevante,
            },
            "com_anexo": self.count_with_attachment,
            "com_links_nfe": self.count_with_nfe_links,
            "com_codigo_verificacao": self.count_with_verification_code,
            "keywords_frequentes": dict(self.keyword_counter.most_common(20)) if self.keyword_counter else {},
            "remetentes_frequentes": dict(self.sender_counter.most_common(15)) if self.sender_counter else {},
            "exemplos_subjects_por_tipo": {
                "LINK_COM_CODIGO": self.examples_link_com_codigo,
                "LINK_DOWNLOAD": self.examples_link_download,
                "APENAS_CODIGO": self.examples_apenas_codigo,
            },
            "potenciais_nfs_sem_anexo": self.count_link_com_codigo + self.count_link_download,
        }


# =============================================================================
# ANALISADOR DE INBOX (STREAMING)
# =============================================================================

class InboxDiagnosticAnalyzer:
    """Analisador de padrões da caixa de entrada com suporte a streaming."""

    def __init__(self, host: str, user: str, password: str, folder: str = "INBOX"):
        self.host = host
        self.user = user
        self.password = password
        self.folder = folder
        self.connection: Optional[imaplib.IMAP4_SSL] = None

    def connect(self) -> None:
        """Estabelece conexão SSL com o servidor IMAP."""
        self.connection = imaplib.IMAP4_SSL(self.host)
        self.connection.login(self.user, self.password)
        self.connection.select(self.folder)
        print(f"✅ Conectado a {self.host} - Pasta: {self.folder}")

    def disconnect(self) -> None:
        """Fecha conexão com o servidor."""
        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
            except Exception:
                pass
            self.connection = None

    def _decode_text(self, text: str) -> str:
        """Decodifica cabeçalhos de e-mail com tratamento robusto de encoding."""
        if not text:
            return ""

        decoded_list = decode_header(text)
        final_text = ""

        for content, encoding in decoded_list:
            if isinstance(content, bytes):
                # Tenta o encoding informado, senão fallback para utf-8 e latin-1
                encodings_to_try = []
                if encoding:
                    encodings_to_try.append(encoding)
                encodings_to_try.extend(['utf-8', 'latin-1', 'iso-8859-1', 'cp1252'])

                decoded = None
                for enc in encodings_to_try:
                    try:
                        decoded = content.decode(enc)
                        break
                    except (LookupError, UnicodeDecodeError):
                        continue

                if decoded is None:
                    decoded = content.decode('latin-1', errors='replace')

                final_text += decoded
            else:
                final_text += str(content)

        return final_text

    def _has_valid_attachment(self, msg: Message) -> bool:
        """Verifica se o e-mail tem anexo PDF ou XML."""
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue

            filename = part.get_filename()
            if filename:
                filename_decoded = self._decode_text(filename).lower()
                if any(filename_decoded.endswith(ext) for ext in VALID_EXTENSIONS):
                    return True
        return False

    def _extract_body(self, msg: Message) -> Tuple[str, str]:
        """Extrai corpo do e-mail (texto e HTML) com tratamento robusto de encoding."""
        body_text = ""
        body_html = ""

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    continue

                try:
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue

                    # Tenta múltiplos encodings
                    charset = part.get_content_charset()
                    encodings_to_try = []
                    if charset:
                        encodings_to_try.append(charset)
                    encodings_to_try.extend(['utf-8', 'latin-1', 'iso-8859-1', 'cp1252'])

                    decoded = None
                    if isinstance(payload, bytes):
                        for enc in encodings_to_try:
                            try:
                                decoded = payload.decode(enc)
                                break
                            except (LookupError, UnicodeDecodeError):
                                continue

                        if decoded is None:
                            decoded = payload.decode('latin-1', errors='replace')

                    if decoded is not None:
                        if content_type == "text/plain":
                            body_text += decoded
                        elif content_type == "text/html":
                            body_html += decoded
                except Exception:
                    pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset()
                    encodings_to_try = []
                    if charset:
                        encodings_to_try.append(charset)
                    encodings_to_try.extend(['utf-8', 'latin-1', 'iso-8859-1', 'cp1252'])

                    decoded = None
                    if isinstance(payload, bytes):
                        for enc in encodings_to_try:
                            try:
                                decoded = payload.decode(enc)
                                break
                            except (LookupError, UnicodeDecodeError):
                                continue

                        if decoded is None:
                            decoded = payload.decode('latin-1', errors='replace')

                    if decoded is not None:
                        if msg.get_content_type() == "text/plain":
                            body_text = decoded if decoded else ""
                        else:
                            body_html = decoded if decoded else ""
            except Exception:
                pass

        return body_text, body_html

    def _extract_sender_info(self, msg: Message) -> Dict[str, str]:
        """Extrai informações do remetente."""
        from_header = msg.get("From", "")
        decoded_from = self._decode_text(from_header)

        sender_name = ""
        sender_address = ""

        if "<" in decoded_from and ">" in decoded_from:
            parts = decoded_from.rsplit("<", 1)
            sender_name = parts[0].strip().strip('"\'')
            sender_address = parts[1].rstrip(">").strip()
        else:
            sender_address = decoded_from.strip()

        return {"name": sender_name, "address": sender_address}

    def _extract_date(self, msg: Message) -> str:
        """Extrai data do e-mail no formato YYYY-MM-DD."""
        date_header = msg.get("Date", "")
        if not date_header:
            return ""

        try:
            # Tenta parsear formatos comuns de data de e-mail
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_header)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            # Fallback: extrai o que puder
            try:
                # Tenta extrair padrão DD Mon YYYY ou similar
                match = re.search(r'(\d{1,2})\s+(\w{3})\s+(\d{4})', date_header)
                if match:
                    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
            except Exception:
                pass
            return date_header[:10] if len(date_header) >= 10 else date_header

    def _has_nfe_links(self, text: str) -> bool:
        """
        Verifica se o texto contém links relacionados a NF-e.
        Usa abordagem eficiente: extrai URLs primeiro, depois filtra por keywords.
        """
        # Extrai todas as URLs de uma vez (regex simples, sem backtracking)
        urls = REGEX_URL_SIMPLE.findall(text)

        # Verifica se alguma URL contém keywords de NF-e
        for url in urls:
            url_lower = url.lower()
            for keyword in URL_KEYWORDS_NFE:
                if keyword in url_lower:
                    return True
        return False

    def _has_verification_code(self, text: str) -> bool:
        """Verifica se o texto contém códigos de verificação/autenticação."""
        for regex, _ in REGEX_CODIGOS:
            if regex.search(text):
                return True
        return False

    def _find_keywords(self, text: str) -> List[str]:
        """Encontra todas as keywords presentes no texto."""
        text_lower = text.lower()
        found = []

        for _, keywords in ALL_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    if keyword not in found:
                        found.append(keyword)

        return found

    def _classify_content_type(self, has_attachment: bool, has_links_nfe: bool,
                                has_verification_code: bool) -> str:
        """Classifica o tipo de conteúdo do e-mail."""
        if has_attachment:
            return "COM_ANEXO"
        elif has_links_nfe and has_verification_code:
            return "LINK_COM_CODIGO"
        elif has_links_nfe:
            return "LINK_DOWNLOAD"
        elif has_verification_code:
            return "APENAS_CODIGO"
        else:
            return "IRRELEVANTE"

    def _analyze_email(self, msg: Message, email_id: str) -> EmailPattern:
        """Analisa um e-mail e extrai padrões."""
        # Extrai informações básicas
        subject = self._decode_text(msg.get("Subject", ""))
        sender_info = self._extract_sender_info(msg)
        body_text, body_html = self._extract_body(msg)
        date = self._extract_date(msg)

        # Verifica anexos
        has_attachment = self._has_valid_attachment(msg)

        # Texto combinado para análise (usa body completo)
        full_text = f"{subject} {body_text} {body_html}"

        # Análise de conteúdo
        has_links_nfe = self._has_nfe_links(full_text)
        has_verification_code = self._has_verification_code(full_text)

        # Encontra keywords
        keywords_found = self._find_keywords(full_text)

        # Classifica tipo de conteúdo
        content_type = self._classify_content_type(
            has_attachment, has_links_nfe, has_verification_code
        )

        return EmailPattern(
            email_id=email_id,
            subject=subject,
            sender_name=sender_info['name'],
            sender_address=sender_info['address'],
            has_attachment=has_attachment,
            has_links_nfe=has_links_nfe,
            has_verification_code=has_verification_code,
            content_type=content_type,
            keywords_found=keywords_found,
            date=date,
        )

    def iter_emails(self, limit: int = 200, skip_ids: Optional[Set[str]] = None) -> Iterator[Tuple[EmailPattern, int, int, Message]]:
        """
        Itera sobre os e-mails como um generator (não carrega tudo em memória).

        Args:
            limit: Máximo de e-mails a analisar. Se 0 ou negativo, processa TODOS.
            skip_ids: Set de IDs de e-mails já processados (para resume)

        Yields:
            Tupla (EmailPattern, índice_atual, total_a_processar, msg)
        """
        if not self.connection:
            self.connect()

        if skip_ids is None:
            skip_ids = set()

        # Busca TODOS os e-mails (sem filtro de subject)
        if self.connection is None:
            return
        _status, messages = self.connection.search(None, 'ALL')

        if not messages or messages[0] == b'':
            print("⚠️ Nenhum e-mail encontrado na caixa de entrada.")
            return

        email_ids = messages[0].split()
        total_emails = len(email_ids)

        # Ordena do mais recente para o mais antigo (IDs maiores são mais recentes)
        email_ids_sorted = sorted(email_ids, key=lambda x: int(x), reverse=True)

        # Se limit <= 0, processa todos; caso contrário, limita
        if limit > 0:
            email_ids_to_process = email_ids_sorted[:limit]
        else:
            email_ids_to_process = email_ids_sorted

        total_to_process = len(email_ids_to_process)
        skipped_resume = 0

        print(f"📧 {total_emails} e-mails na caixa de entrada")
        if limit > 0:
            print(f"📊 Analisando os últimos {total_to_process} e-mails...")
        else:
            print(f"📊 Analisando TODOS os {total_to_process} e-mails...")

        if skip_ids:
            print(f"⏭️  Modo resume: pulando {len(skip_ids)} e-mails já processados")
        print()

        for idx, num in enumerate(email_ids_to_process):
            email_id_str = num.decode('utf-8') if isinstance(num, bytes) else str(num)

            # Pula e-mails já processados (resume)
            if email_id_str in skip_ids:
                skipped_resume += 1
                continue

            try:
                if self.connection is None:
                    continue
                num_str = num.decode('utf-8') if isinstance(num, bytes) else str(num)
                _, msg_data = self.connection.fetch(num_str, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                raw_bytes = msg_data[0][1]
                if isinstance(raw_bytes, int):
                    continue
                msg = message_from_bytes(raw_bytes)

                # Analisa o e-mail e retorna imediatamente (não acumula)
                pattern = self._analyze_email(msg, email_id_str)
                yield pattern, idx + 1 - skipped_resume, total_to_process - len(skip_ids), msg

                # Libera referência explicitamente
                del msg
                del msg_data

            except Exception:
                # Skip on error (estatísticas contabilizam)
                continue

    def fetch_and_diagnose_streaming(
        self,
        limit: int,
        output_path: Path,
        resume: bool = False
    ) -> StreamingStats:
        """
        Busca e-mails com processamento em streaming.
        Escreve cada e-mail diretamente no arquivo, não acumula em memória.

        Args:
            limit: Máximo de e-mails (0 = todos)
            output_path: Caminho do arquivo de saída
            resume: Se True, continua de onde parou

        Returns:
            Estatísticas consolidadas
        """
        import json

        stats = StreamingStats()
        skip_ids: Set[str] = set()
        existing_patterns: List[Dict] = []

        # Para armazenar corpos e anexos dos e-mails
        email_bodies = []

        # Se resume, carrega IDs já processados
        if resume and output_path.exists():
            print(f"📂 Carregando progresso anterior de {output_path}...")
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    existing_patterns = json.load(f)
                    skip_ids = {p['email_id'] for p in existing_patterns}
                    print(f"   Encontrados {len(skip_ids)} e-mails já processados")
            except Exception as e:
                print(f"⚠️ Erro ao carregar arquivo anterior: {e}")
                print("   Iniciando do zero...")
                existing_patterns = []
                skip_ids = set()

        # Cria diretório se não existir
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Abre arquivo para escrita incremental
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('[\n')  # Início do array JSON
            first = True

            # Se resume, escreve os padrões existentes primeiro
            for existing in existing_patterns:
                if not first:
                    f.write(',\n')
                first = False
                json_line = json.dumps(existing, ensure_ascii=False)
                f.write('  ' + json_line)

                # Atualiza stats com dados existentes (recria contadores)
                stats.total_processed += 1
                content_type = existing.get('content_type', 'IRRELEVANTE')
                if content_type == "COM_ANEXO":
                    stats.count_com_anexo += 1
                elif content_type == "LINK_COM_CODIGO":
                    stats.count_link_com_codigo += 1
                elif content_type == "LINK_DOWNLOAD":
                    stats.count_link_download += 1
                elif content_type == "APENAS_CODIGO":
                    stats.count_apenas_codigo += 1
                else:
                    stats.count_irrelevante += 1

                if existing.get('has_attachment'):
                    stats.count_with_attachment += 1
                if existing.get('has_links_nfe'):
                    stats.count_with_nfe_links += 1
                if existing.get('has_verification_code'):
                    stats.count_with_verification_code += 1

                for kw in existing.get('keywords_found', []):
                    if stats.keyword_counter is not None:
                        stats.keyword_counter[kw] += 1
                if stats.sender_counter is not None:
                    stats.sender_counter[existing.get('sender_address', '')] += 1

            if existing_patterns:
                print(f"✅ {len(existing_patterns)} e-mails anteriores mantidos")
                print()

            # Processa novos e-mails
            new_count = 0
            for result in self.iter_emails(limit=limit, skip_ids=skip_ids):
                pattern, _, _, msg = result

                if pattern is None or msg is None:
                    stats.errors += 1
                    continue

                # Atualiza estatísticas (usa pouca memória)
                stats.update(pattern)
                new_count += 1

                # Escreve diretamente no arquivo (não acumula em memória)
                if not first:
                    f.write(',\n')
                first = False

                json_line = json.dumps(pattern.to_dict(), ensure_ascii=False)
                f.write('  ' + json_line)

                # --------- NOVO: Salva corpo e anexos ----------
                # Extrai corpo
                body_text, body_html = self._extract_body(msg)
                # Conta anexos
                attachment_count = sum(
                    1 for part in msg.walk()
                    if part.get_content_maintype() != 'multipart'
                    and part.get('Content-Disposition') is not None
                    and 'attachment' in part.get('Content-Disposition', '').lower()
                )
                email_bodies.append({
                    "uid": pattern.email_id,
                    "subject": self._decode_text(msg.get("Subject") or ""),
                    "from": self._decode_text(msg.get("From") or ""),
                    "date": self._decode_text(msg.get("Date") or ""),
                    "body_text": body_text,
                    "body_html": body_html,
                    "quantidade_anexos": attachment_count,
                })
                # ------------------------------------------------

                # Flush periódico para garantir escrita e permitir resume
                if new_count % 50 == 0:
                    f.flush()

                # Log de progresso a cada 10 e-mails
                if new_count % 10 == 0:
                    print(f"   Analisados: {new_count} novos ({stats.total_processed} total) "
                          f"(📎{stats.count_com_anexo} 🥇{stats.count_link_com_codigo} "
                          f"🥈{stats.count_link_download})")

            f.write('\n]')  # Fim do array JSON

        # Salva o corpo dos e-mails analisados em inbox_body.json
        with open("data/output/inbox_body.json", "w", encoding="utf-8") as fbody:
            json.dump(email_bodies, fbody, ensure_ascii=False, indent=2)

        print("\n✅ Análise concluída:")
        print(f"   - E-mails analisados (total): {stats.total_processed}")
        print(f"   - Novos nesta execução: {new_count}")
        if stats.errors > 0:
            print(f"   - Erros: {stats.errors}")
        print(f"   - Último ID processado: {stats.last_email_id}")

        return stats


# =============================================================================
# FUNÇÕES DE RELATÓRIO
# =============================================================================

def print_summary(stats: StreamingStats) -> None:
    """Imprime resumo estatístico no console."""
    stats_dict = stats.to_dict()

    print("\n" + "=" * 60)
    print("📊 RESUMO DO DIAGNÓSTICO DE PADRÕES")
    print("=" * 60)

    print(f"\n📧 Total analisado: {stats_dict['total_analisado']}")
    print()

    print("📁 Classificação por Tipo:")
    tipo_order = ['COM_ANEXO', 'LINK_COM_CODIGO', 'LINK_DOWNLOAD', 'APENAS_CODIGO', 'IRRELEVANTE']
    tipo_emoji = {
        'COM_ANEXO': '📎',
        'LINK_COM_CODIGO': '🥇',
        'LINK_DOWNLOAD': '🥈',
        'APENAS_CODIGO': '🔍',
        'IRRELEVANTE': '🗑️',
    }
    tipo_desc = {
        'COM_ANEXO': 'Com anexo PDF/XML',
        'LINK_COM_CODIGO': 'Link + Código (Alta prioridade)',
        'LINK_DOWNLOAD': 'Apenas link (Média prioridade)',
        'APENAS_CODIGO': 'Apenas código (Investigar)',
        'IRRELEVANTE': 'Sem padrão relevante',
    }

    total = stats_dict['total_analisado']
    for tipo in tipo_order:
        count = stats_dict['por_tipo'].get(tipo, 0)
        pct = (count / total * 100) if total > 0 else 0
        emoji = tipo_emoji.get(tipo, '❓')
        desc = tipo_desc.get(tipo, tipo)
        print(f"   {emoji} {desc}: {count} ({pct:.1f}%)")

    print()
    print(f"🎯 Potenciais NFs sem anexo (Link+Código ou Link): {stats_dict['potenciais_nfs_sem_anexo']}")

    print()
    print("🔑 Keywords mais frequentes:")
    for keyword, count in list(stats_dict['keywords_frequentes'].items())[:10]:
        print(f"   • {keyword}: {count}")

    print()
    print("📤 Remetentes mais frequentes:")
    for sender, count in list(stats_dict['remetentes_frequentes'].items())[:10]:
        sender_display = sender[:45] + "..." if len(sender) > 45 else sender
        print(f"   • {sender_display}: {count}")

    # Exemplos de subjects interessantes
    print()
    print("📋 Exemplos de Subjects por Tipo (para análise):")
    for tipo in ['LINK_COM_CODIGO', 'LINK_DOWNLOAD', 'APENAS_CODIGO']:
        subjects = stats_dict['exemplos_subjects_por_tipo'].get(tipo, [])
        if subjects:
            print(f"\n   [{tipo}]:")
            for subj in subjects[:5]:
                subj_display = subj[:60] + "..." if len(subj) > 60 else subj
                print(f"      • {subj_display}")

    print("\n" + "=" * 60)


# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='Diagnóstico de padrões de e-mail na caixa de entrada para identificar NFs/Boletos'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=200,
        help='Máximo de e-mails a analisar, do mais recente ao mais antigo (default: 200). Use 0 para TODOS.'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        dest='process_all',
        help='Processa TODOS os e-mails da caixa de entrada (ignora --limit)'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Continua de onde parou (usa arquivo de saída existente)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Caminho alternativo para salvar o JSON (default: data/output/inbox_patterns.json)'
    )

    args = parser.parse_args()

    # Se --all foi passado, define limit como 0 (sem limite)
    effective_limit = 0 if args.process_all else args.limit

    # Verifica configuração
    if not settings.EMAIL_PASS:
        print("❌ Erro: Configure as credenciais de e-mail no arquivo .env")
        print("   EMAIL_HOST, EMAIL_USER, EMAIL_PASS")
        return 1

    print("🔍 Iniciando diagnóstico de padrões da caixa de entrada...")
    print(f"   Servidor: {settings.EMAIL_HOST}")
    print(f"   Usuário: {settings.EMAIL_USER}")
    print(f"   Pasta: {settings.EMAIL_FOLDER}")
    if effective_limit > 0:
        print(f"   Limite: {effective_limit} e-mails")
    else:
        print("   Limite: TODOS os e-mails (modo streaming ativado)")
    if args.resume:
        print("   Modo: RESUME (continua de onde parou)")
    print()

    # Cria analisador e conecta
    analyzer = InboxDiagnosticAnalyzer(
        host=settings.EMAIL_HOST,
        user=settings.EMAIL_USER,
        password=settings.EMAIL_PASS,
        folder=settings.EMAIL_FOLDER
    )

    try:
        # Determina caminho de saída
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = Path("data/output/inbox_patterns.json")

        # Processa em modo streaming (escreve direto no arquivo)
        stats = analyzer.fetch_and_diagnose_streaming(
            limit=effective_limit,
            output_path=output_path,
            resume=args.resume
        )

        if stats.total_processed == 0:
            print("\n⚠️ Nenhum e-mail foi analisado.")
            return 1

        # Imprime resumo
        print_summary(stats)

        print(f"\n💾 Relatório detalhado salvo em: {output_path}")

        # Salva também as estatísticas em arquivo separado
        stats_path = output_path.parent / "inbox_patterns_stats.json"
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats.to_dict(), f, ensure_ascii=False, indent=2)

        print(f"📊 Estatísticas salvas em: {stats_path}")

        return 0

    except Exception as e:
        print(f"\n❌ Erro durante diagnóstico: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        analyzer.disconnect()


if __name__ == "__main__":
    sys.exit(main())
