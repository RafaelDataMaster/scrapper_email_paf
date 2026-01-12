"""
Serviço de Ingestão de E-mails.

Este módulo implementa a "Camada de Ingestão (Bronze)" do plano de refatoração,
responsável por organizar anexos de e-mail em pastas estruturadas com metadados.

Estrutura de saída:
    temp/
    └── email_20251231_uniqueID/
        ├── metadata.json
        ├── anexo_01.xml
        ├── anexo_02_danfe.pdf
        └── anexo_03_boleto.pdf

Também suporta ingestão de e-mails SEM anexos, gerando registros de "aviso"
com link de NF-e e código de verificação para a coluna de observações.

Princípios SOLID aplicados:
- SRP: Classe focada apenas em ingestão e organização de arquivos
- OCP: Extensível via herança sem modificar código existente
- DIP: Depende de abstrações (EmailIngestorStrategy), não de implementações
"""
import os
import re
import uuid
from datetime import datetime
from email.header import decode_header
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.empresa_matcher_email import find_empresa_in_email
from core.filters import (
    EmailFilter,
    FilterResult,
    get_default_filter,
    should_process_email,
)
from core.interfaces import EmailIngestorStrategy
from core.metadata import EmailMetadata
from core.models import EmailAvisoData


class IngestionService:
    """
    Serviço de ingestão e organização de e-mails.

    Responsável por:
    1. Baixar anexos de e-mails via ingestor (IMAP/API)
    2. Criar estrutura de pastas por lote (e-mail)
    3. Gerar metadata.json com contexto do e-mail
    4. Filtrar arquivos não relevantes (assinaturas, imagens)

    Attributes:
        ingestor: Implementação de EmailIngestorStrategy
        temp_dir: Diretório temporário para lotes
        ignored_extensions: Extensões de arquivo a ignorar

    Usage:
        service = IngestionService(ingestor, temp_dir=Path("temp"))
        batches = service.ingest_emails(subject_filter="Nota Fiscal")
    """

    # Extensões de arquivos a serem ignorados
    DEFAULT_IGNORED_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.gif', '.bmp',  # Imagens (assinaturas de e-mail)
        '.p7s', '.smime',  # Assinaturas digitais
        '.ics',  # Convites de calendário
        '.vcf',  # Cartões de visita
    }

    # Padrões de nomes de arquivo a ignorar (assinaturas de e-mail)
    IGNORED_NAME_PATTERNS = [
        r'^image\d{3}\.',  # image001.png, image002.jpg
        r'^logo',  # logo.png, logo_empresa.jpg
        r'^assinatura',
        r'^signature',
    ]

    def __init__(
        self,
        ingestor: EmailIngestorStrategy,
        temp_dir: Union[str, Path],
        ignored_extensions: Optional[set] = None,
        email_filter: Optional[EmailFilter] = None,
    ):
        """
        Inicializa o serviço de ingestão.

        Args:
            ingestor: Estratégia de ingestão de e-mail (IMAP, Graph API, etc.)
            temp_dir: Diretório raiz para criar pastas de lote
            ignored_extensions: Extensões de arquivo a ignorar (opcional)
            email_filter: Filtro de e-mails customizado (opcional)
        """
        self.ingestor = ingestor
        self.temp_dir = Path(temp_dir)
        self.ignored_extensions = ignored_extensions or self.DEFAULT_IGNORED_EXTENSIONS
        self.email_filter = email_filter or get_default_filter()

    def ingest_emails(
        self,
        subject_filter: str = "Nota Fiscal",
        create_ignored_folder: bool = False,
    ) -> List[Path]:
        """
        Baixa e organiza e-mails em pastas de lote.

        Args:
            subject_filter: Filtro de assunto para busca
            create_ignored_folder: Se True, cria pasta 'ignored/' para arquivos descartados

        Returns:
            Lista de caminhos das pastas de lote criadas
        """
        # Garante conexão
        self.ingestor.connect()

        # Busca anexos
        raw_attachments = self.ingestor.fetch_attachments(subject_filter)

        if not raw_attachments:
            return []

        # Agrupa anexos por e-mail de origem usando email_id
        emails_grouped = self._group_attachments_by_email(raw_attachments)

        batches_created = []

        # Processa cada e-mail como um lote único (com todos os seus anexos)
        for email_data in emails_grouped.values():
            batch_path = self.ingest_single_email(
                email_data,
                create_ignored_folder=create_ignored_folder
            )
            if batch_path and batch_path not in batches_created:
                batches_created.append(batch_path)

        return batches_created

    def _group_attachments_by_email(
        self,
        attachments: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Agrupa anexos pelo email_id para criar um lote único por e-mail.

        Args:
            attachments: Lista de anexos individuais com email_id

        Returns:
            Dict mapeando email_id para dados do e-mail com todos os anexos
        """
        emails_map: Dict[str, Dict[str, Any]] = {}

        for att in attachments:
            # Usa email_id se disponível, senão gera um ID único por anexo (modo legado)
            email_id = att.get('email_id', self._generate_batch_id())

            if email_id not in emails_map:
                emails_map[email_id] = {
                    'subject': att.get('subject', ''),
                    'sender_name': att.get('sender_name', ''),
                    'sender_address': att.get('sender_address', att.get('source', '')),
                    'body_text': att.get('body_text', ''),
                    'received_date': att.get('received_date', ''),
                    'attachments': [],
                }

            emails_map[email_id]['attachments'].append({
                'filename': att.get('filename', ''),
                'content': att.get('content', b''),
            })

        return emails_map

    def ingest_single_email(
        self,
        email_data: Dict[str, Any],
        create_ignored_folder: bool = False,
    ) -> Optional[Path]:
        """
        Processa um único e-mail e cria pasta de lote.

        Args:
            email_data: Dicionário com dados do e-mail:
                - subject: Assunto
                - sender_name: Nome do remetente
                - sender_address: E-mail do remetente
                - body_text: Corpo do e-mail (texto)
                - received_date: Data de recebimento
                - attachments: Lista de dicts com 'filename' e 'content'
            create_ignored_folder: Se True, cria pasta 'ignored/'

        Returns:
            Path da pasta de lote criada ou None se não houver anexos válidos
        """
        attachments = email_data.get('attachments', [])

        if not attachments:
            return None

        # Gera ID único para o lote
        batch_id = self._generate_batch_id()
        batch_folder = self.temp_dir / batch_id

        # Filtra anexos
        valid_attachments = []
        ignored_attachments = []

        for att in attachments:
            filename = att.get('filename', '')
            if self._should_ignore_file(filename):
                ignored_attachments.append(att)
            else:
                valid_attachments.append(att)

        # Se não há anexos válidos, não cria o lote
        if not valid_attachments:
            return None

        # Cria pasta do lote
        batch_folder.mkdir(parents=True, exist_ok=True)

        # Salva anexos válidos
        saved_files = []
        for idx, att in enumerate(valid_attachments, start=1):
            filename = att.get('filename', f'anexo_{idx:02d}.pdf')
            safe_filename = self._sanitize_filename(filename)

            # Adiciona prefixo numérico para ordenação
            numbered_filename = f"{idx:02d}_{safe_filename}"

            file_path = batch_folder / numbered_filename
            file_path.write_bytes(att.get('content', b''))
            saved_files.append(numbered_filename)

        # Salva anexos ignorados (se configurado)
        if create_ignored_folder and ignored_attachments:
            ignored_folder = batch_folder / "ignored"
            ignored_folder.mkdir(exist_ok=True)

            for att in ignored_attachments:
                filename = att.get('filename', 'unknown')
                safe_filename = self._sanitize_filename(filename)
                file_path = ignored_folder / safe_filename
                file_path.write_bytes(att.get('content', b''))

        # Cria metadata.json
        metadata = EmailMetadata.create_for_batch(
            batch_id=batch_id,
            subject=email_data.get('subject'),
            sender_name=email_data.get('sender_name'),
            sender_address=email_data.get('sender_address'),
            body_text=email_data.get('body_text'),
            received_date=email_data.get('received_date'),
            attachments=saved_files,
        )
        metadata.save(batch_folder)

        return batch_folder

    def _create_batch_from_attachment(
        self,
        attachment: Dict[str, Any],
        create_ignored_folder: bool = False,
    ) -> Optional[Path]:
        """
        Cria lote a partir de um anexo individual.

        Modo de compatibilidade com a estrutura atual do ingestor
        que retorna anexos sem agrupamento por e-mail.

        Args:
            attachment: Dicionário com dados do anexo
            create_ignored_folder: Se True, cria pasta 'ignored/'

        Returns:
            Path da pasta do lote ou None
        """
        filename = attachment.get('filename', '')
        content = attachment.get('content', b'')
        source = attachment.get('source', '')
        subject = attachment.get('subject', '')

        # Ignora arquivos inválidos
        if self._should_ignore_file(filename):
            return None

        # Gera ID único para o lote
        batch_id = self._generate_batch_id()
        batch_folder = self.temp_dir / batch_id

        # Cria pasta
        batch_folder.mkdir(parents=True, exist_ok=True)

        # Salva arquivo
        safe_filename = self._sanitize_filename(filename)
        numbered_filename = f"01_{safe_filename}"
        file_path = batch_folder / numbered_filename
        file_path.write_bytes(content)

        # Cria metadata
        metadata = EmailMetadata.create_for_batch(
            batch_id=batch_id,
            subject=subject,
            sender_address=source,
            attachments=[numbered_filename],
        )
        metadata.save(batch_folder)

        return batch_folder

    def _generate_batch_id(self) -> str:
        """
        Gera ID único para o lote.

        Formato: email_YYYYMMDD_HHMMSS_shortUUID
        Exemplo: email_20251231_143052_a1b2c3d4

        Returns:
            String com ID único
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        short_uuid = uuid.uuid4().hex[:8]
        return f"email_{timestamp}_{short_uuid}"

    def _should_ignore_file(self, filename: str) -> bool:
        """
        Verifica se um arquivo deve ser ignorado.

        Args:
            filename: Nome do arquivo

        Returns:
            True se deve ser ignorado
        """
        if not filename:
            return True

        # Verifica extensão
        ext = Path(filename).suffix.lower()
        if ext in self.ignored_extensions:
            return True

        # Verifica padrões de nome
        name_lower = filename.lower()
        for pattern in self.IGNORED_NAME_PATTERNS:
            if re.match(pattern, name_lower):
                return True

        return False

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitiza nome de arquivo removendo caracteres inválidos.

        Args:
            filename: Nome original

        Returns:
            Nome sanitizado
        """
        if not filename:
            return "unnamed_file"

        # Remove caracteres inválidos para Windows/Linux
        invalid_chars = r'<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        # Remove espaços múltiplos
        filename = re.sub(r'\s+', ' ', filename).strip()

        # Limita tamanho
        if len(filename) > 200:
            name, ext = os.path.splitext(filename)
            filename = name[:200-len(ext)] + ext

        return filename or "unnamed_file"

    def ingest_emails_without_attachments(
        self,
        subject_filter: str = "*",
        limit: int = 0,
        apply_filter: bool = True,
    ) -> List[EmailAvisoData]:
        """
        Ingere e-mails SEM anexos PDF/XML e cria registros de aviso.

        Para cada e-mail sem anexo que contenha link de NF-e ou código
        de verificação, cria um EmailAvisoData com os dados extraídos.

        IMPORTANTE: Usa o módulo de filtros (core/filters.py) para decidir
        se cada e-mail deve ser processado, evitando falsos positivos como
        e-mails com código de verificação no rodapé mas assunto de SPAM.

        Args:
            subject_filter: Filtro de assunto para busca IMAP ("*" = todos)
            limit: Máximo de e-mails a processar (0 = sem limite)
            apply_filter: Se True, aplica regras de filtragem inteligente

        Returns:
            Lista de EmailAvisoData com links/códigos extraídos
        """
        # Garante conexão
        self.ingestor.connect()

        # Verifica se o ingestor suporta busca sem anexos
        if not hasattr(self.ingestor, 'fetch_emails_without_attachments'):
            raise NotImplementedError(
                "Ingestor não suporta fetch_emails_without_attachments"
            )

        # Busca e-mails sem anexo
        raw_emails = self.ingestor.fetch_emails_without_attachments(
            subject_filter=subject_filter,
            limit=limit
        )

        if not raw_emails:
            return []

        avisos: List[EmailAvisoData] = []
        skipped_count = 0

        for email_data in raw_emails:
            # ================================================================
            # FILTRO INTELIGENTE: Decide se o e-mail deve ser processado
            # ================================================================
            if apply_filter:
                filter_metadata = self._build_filter_metadata(email_data)
                filter_result = self.email_filter.should_process_email(filter_metadata)

                if not filter_result.should_process:
                    skipped_count += 1
                    continue
            # Cria metadata temporário para extração
            metadata = EmailMetadata.create_for_batch(
                batch_id=email_data.get('email_id', 'unknown'),
                subject=email_data.get('subject'),
                sender_name=email_data.get('sender_name'),
                sender_address=email_data.get('sender_address'),
                body_text=email_data.get('body_text'),
                received_date=email_data.get('received_date'),
                attachments=[],
            )

            # Extrai link e código
            link = metadata.extract_link_nfe_from_context()
            codigo = (
                metadata.extract_codigo_verificacao_from_link(link)
                or metadata.extract_codigo_verificacao_from_body()
            )

            # Só cria aviso se tiver link OU código
            if not link and not codigo:
                continue

            # Cria registro de aviso
            aviso = EmailAvisoData.from_metadata(
                metadata=metadata,
                email_id=email_data.get('email_id', 'unknown')
            )

            # Detecta empresa usando o texto COMPLETO do e-mail
            texto_completo = f"{email_data.get('subject', '')} {email_data.get('body_text', '')}"
            codigo_empresa, metodo, matches = find_empresa_in_email(texto_completo)
            if codigo_empresa:
                aviso.empresa = codigo_empresa

            avisos.append(aviso)

        if skipped_count > 0:
            import logging
            logging.getLogger(__name__).info(
                f"Filtro ignorou {skipped_count} e-mails sem conteúdo fiscal relevante"
            )

        return avisos

    def _build_filter_metadata(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Constrói metadados para o filtro de e-mail.

        Extrai indicadores do corpo do e-mail para alimentar o filtro
        de decisão inteligente.

        Args:
            email_data: Dados brutos do e-mail

        Returns:
            Dicionário formatado para EmailFilter.should_process_email()
        """
        body_text = email_data.get('body_text', '') or ''
        subject = email_data.get('subject', '') or ''

        # Detecta links de NF-e no corpo
        has_links_nfe = self._detect_nfe_links(body_text)

        # Detecta códigos de verificação no corpo
        has_verification_code = self._detect_verification_codes(body_text)

        # Verifica se há anexos válidos (PDF/XML)
        attachments = email_data.get('attachments', [])
        has_attachment = any(
            att.get('filename', '').lower().endswith(('.pdf', '.xml'))
            for att in attachments
        ) if attachments else False

        return {
            'subject': subject,
            'has_attachment': has_attachment,
            'has_links_nfe': has_links_nfe,
            'has_verification_code': has_verification_code,
            'sender_address': email_data.get('sender_address', ''),
            'attachments': [att.get('filename', '') for att in attachments] if attachments else [],
        }

    def _detect_nfe_links(self, body_text: str) -> bool:
        """
        Detecta links de NF-e no corpo do e-mail.

        Procura por URLs que contenham padrões típicos de portais
        de nota fiscal eletrônica.

        Args:
            body_text: Corpo do e-mail em texto

        Returns:
            True se encontrar links de NF-e
        """
        if not body_text:
            return False

        # Padrões de URLs de NF-e (simplificados para performance)
        nfe_url_patterns = [
            # === PORTAIS DE NF-e DIRETOS ===
            r'https?://[^\s]*nf[es]?\.',           # nfe., nfs., nfse.
            r'https?://[^\s]*nota[^\s]*fiscal',    # notafiscal, nota-fiscal
            r'https?://[^\s]*danfe',               # danfe
            r'https?://[^\s]*sefaz',               # sefaz (estadual)

            # === PREFEITURAS E PORTAIS MUNICIPAIS ===
            r'https?://[^\s]*prefeitura',          # qualquer link de prefeitura
            r'https?://[^\s]*\.gov\.br',           # qualquer .gov.br
            r'https?://[^\s]*pmf\.',               # pmf. (prefeitura municipal)
            r'https?://[^\s]*issqn',               # ISSQN (imposto municipal)
            r'https?://[^\s]*iss[.\-]',            # iss. ou iss- (imposto sobre serviços)
            r'https?://[^\s]*nfse',                # nfse (nota fiscal de serviço)
            r'https?://[^\s]*ginfes',              # GINFES (sistema de NFS-e)
            r'https?://[^\s]*abrasf',              # ABRASF (padrão nacional)
            r'https?://[^\s]*webiss',              # WebISS (sistema comum)
            r'https?://[^\s]*tributosmunicipais',  # tributos municipais
            r'https?://[^\s]*tributos\.',          # tributos.cidade.gov.br

            # === REDIRECIONADORES DE SISTEMAS ERP/CRM ===
            # Esses sistemas enviam e-mails com links de tracking que redirecionam para NF
            r'https?://[^\s]*\.omie\.com',         # Omie ERP
            r'https?://[^\s]*\.bling\.com',        # Bling ERP
            r'https?://[^\s]*\.tiny\.com',         # Tiny ERP
            r'https?://[^\s]*\.conta\.azul',       # ContaAzul
            r'https?://[^\s]*\.nibo\.com',         # Nibo
            r'https?://[^\s]*\.enotas\.com',       # eNotas
            r'https?://[^\s]*\.nfe\.io',           # NFe.io
            r'https?://[^\s]*\.focusnfe\.com',     # Focus NFe
            r'https?://[^\s]*\.webmaniabr\.com',   # WebmaniaBR
            r'https?://[^\s]*\.plugnotas\.com',    # PlugNotas
            r'https?://[^\s]*\.tecnospeed\.com',   # TecnoSpeed
            r'https?://[^\s]*\.senior\.com',       # Senior Sistemas
            r'https?://[^\s]*\.totvs\.com',        # TOTVS
            r'https?://[^\s]*\.sankhya\.com',      # Sankhya

            # === REDIRECIONADORES DE EMAIL MARKETING ===
            # Links de tracking que podem conter NF no destino
            r'https?://[^\s]*click\.[^\s]+/track', # Padrão genérico de tracking
            r'https?://[^\s]*\.rdstation\.com',    # RD Station
            r'https?://[^\s]*\.mailchimp\.com',    # Mailchimp (raro, mas possível)
            r'https?://[^\s]*sendgrid\.',          # SendGrid

            # === CONSULTAS E DOWNLOADS ===
            r'https?://[^\s]*/consulta[^\s]*nf',   # consulta de NF
            r'https?://[^\s]*/download[^\s]*xml',  # download de XML
            r'https?://[^\s]*/validar',            # validar NF
            r'https?://[^\s]*/verificar',          # verificar autenticidade

            # === CONCESSIONÁRIAS E UTILITIES ===
            r'https?://[^\s]*2via',                # segunda via (comum em contas)
            r'https?://[^\s]*fatura',              # fatura online
            r'https?://[^\s]*conta[^\s]*digital',  # conta digital
            r'https?://[^\s]*boleto',              # boleto online
        ]

        for pattern in nfe_url_patterns:
            if re.search(pattern, body_text, re.IGNORECASE):
                return True

        return False

    def _detect_verification_codes(self, body_text: str) -> bool:
        """
        Detecta códigos de verificação no corpo do e-mail.

        Procura por padrões típicos de códigos de verificação
        de notas fiscais (44 dígitos, códigos alfanuméricos, etc.)

        Args:
            body_text: Corpo do e-mail em texto

        Returns:
            True se encontrar código de verificação
        """
        if not body_text:
            return False

        # Padrões de códigos de verificação
        code_patterns = [
            # Chave NFe: 44 dígitos
            r'\b\d{44}\b',
            # Código de verificação alfanumérico (8-12 chars)
            r'(?:código|codigo|chave)[^\n]{0,30}[:=]\s*([A-Z0-9]{8,12})',
            # Padrão "Verificação: XXXX-XXXX"
            r'verifica[çc][aã]o[^\n]{0,20}[:=]\s*[A-Z0-9\-]{6,}',
        ]

        for pattern in code_patterns:
            if re.search(pattern, body_text, re.IGNORECASE):
                return True

        return False

    def cleanup_old_batches(self, max_age_hours: int = 48) -> int:
        """
        Remove pastas de lote antigas.

        Args:
            max_age_hours: Idade máxima em horas

        Returns:
            Número de pastas removidas
        """
        import shutil
        from datetime import timedelta

        if not self.temp_dir.exists():
            return 0

        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        removed_count = 0

        for item in self.temp_dir.iterdir():
            if not item.is_dir():
                continue

            # Verifica idade pela data de modificação
            try:
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                if mtime < cutoff:
                    shutil.rmtree(item)
                    removed_count += 1
            except (OSError, PermissionError):
                continue

        return removed_count


def create_batch_folder(
    temp_dir: Union[str, Path],
    subject: Optional[str] = None,
    sender_name: Optional[str] = None,
    sender_address: Optional[str] = None,
    body_text: Optional[str] = None,
    files: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    """
    Função utilitária para criar uma pasta de lote manualmente.

    Útil para testes e para criar lotes simulados.

    Args:
        temp_dir: Diretório raiz
        subject: Assunto do e-mail
        sender_name: Nome do remetente
        sender_address: E-mail do remetente
        body_text: Corpo do e-mail
        files: Lista de dicts com 'filename' e 'content'

    Returns:
        Path da pasta criada
    """
    temp_dir = Path(temp_dir)

    # Gera ID
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    short_uuid = uuid.uuid4().hex[:8]
    batch_id = f"email_{timestamp}_{short_uuid}"

    batch_folder = temp_dir / batch_id
    batch_folder.mkdir(parents=True, exist_ok=True)

    # Salva arquivos
    saved_files = []
    if files:
        for idx, file_data in enumerate(files, start=1):
            filename = file_data.get('filename', f'file_{idx:02d}.pdf')
            content = file_data.get('content', b'')

            # Sanitiza nome
            safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
            numbered_name = f"{idx:02d}_{safe_name}"

            file_path = batch_folder / numbered_name
            file_path.write_bytes(content)
            saved_files.append(numbered_name)

    # Cria metadata
    metadata = EmailMetadata.create_for_batch(
        batch_id=batch_id,
        subject=subject,
        sender_name=sender_name,
        sender_address=sender_address,
        body_text=body_text,
        attachments=saved_files,
    )
    metadata.save(batch_folder)

    return batch_folder
