"""
Orquestrador de Ingestão de E-mails com Checkpoint e Resume.

Este módulo implementa um serviço robusto de ingestão que:
1. Processa emails COM e SEM anexos de forma unificada
2. Mantém checkpoints para resume após interrupções
3. Suporta processamento em lotes com timeout
4. Aplica filtros inteligentes para evitar falsos positivos
5. Exporta CSVs incrementais para não perder dados em interrupções

Estrutura de checkpoint:
    temp_email/
    ├── _checkpoint.json           # Estado atual da ingestão
    ├── _partial_batches.jsonl     # Resultados parciais de lotes
    └── _partial_avisos.jsonl      # Resultados parciais de avisos

Autor: Sistema de Ingestão
Versão: 1.1.0
"""

import atexit
import json
import logging
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core.batch_processor import BatchProcessor
from core.batch_result import BatchResult
from core.filters import EmailFilter, FilterResult, get_default_filter
from core.interfaces import EmailIngestorStrategy
from core.metrics import IngestionMetrics
from core.models import EmailAvisoData
from services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTES DE ARQUIVOS PARCIAIS
# =============================================================================
PARTIAL_BATCHES_FILE = "_partial_batches.jsonl"
PARTIAL_AVISOS_FILE = "_partial_avisos.jsonl"


class IngestionStatus(Enum):
    """Status da ingestão."""
    IDLE = "IDLE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"


@dataclass
class CheckpointData:
    """Dados do checkpoint de ingestão."""
    status: IngestionStatus = IngestionStatus.IDLE
    started_at: Optional[str] = None
    last_updated: Optional[str] = None

    # E-mails processados (conjunto de email_ids)
    processed_email_ids: Set[str] = field(default_factory=set)

    # Lotes criados (caminhos relativos)
    created_batches: List[str] = field(default_factory=list)

    # Avisos criados (emails sem anexo)
    created_avisos: List[Dict[str, Any]] = field(default_factory=list)

    # Contadores
    total_emails_found: int = 0
    total_processed: int = 0
    total_skipped: int = 0
    total_errors: int = 0

    # Lote atual sendo processado
    current_batch_idx: int = 0

    # Filtro de assunto usado
    subject_filter: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "status": self.status.value,
            "started_at": self.started_at,
            "last_updated": self.last_updated,
            "processed_email_ids": list(self.processed_email_ids),
            "created_batches": self.created_batches,
            "created_avisos": self.created_avisos,
            "total_emails_found": self.total_emails_found,
            "total_processed": self.total_processed,
            "total_skipped": self.total_skipped,
            "total_errors": self.total_errors,
            "current_batch_idx": self.current_batch_idx,
            "subject_filter": self.subject_filter,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointData":
        """Cria instância a partir de dicionário."""
        return cls(
            status=IngestionStatus(data.get("status", "IDLE")),
            started_at=data.get("started_at"),
            last_updated=data.get("last_updated"),
            processed_email_ids=set(data.get("processed_email_ids", [])),
            created_batches=data.get("created_batches", []),
            created_avisos=data.get("created_avisos", []),
            total_emails_found=data.get("total_emails_found", 0),
            total_processed=data.get("total_processed", 0),
            total_skipped=data.get("total_skipped", 0),
            total_errors=data.get("total_errors", 0),
            current_batch_idx=data.get("current_batch_idx", 0),
            subject_filter=data.get("subject_filter", ""),
        )


@dataclass
class IngestionResult:
    """Resultado consolidado da ingestão."""
    # Lotes de e-mails com anexos processados
    batch_results: List[BatchResult] = field(default_factory=list)

    # Avisos de e-mails sem anexos (links/códigos)
    avisos: List[EmailAvisoData] = field(default_factory=list)

    # Estatísticas
    total_emails_scanned: int = 0
    total_with_attachments: int = 0
    total_without_attachments: int = 0
    total_filtered_out: int = 0
    total_errors: int = 0

    # Tempo de execução
    duration_seconds: float = 0.0

    # Status final
    status: IngestionStatus = IngestionStatus.COMPLETED

    @property
    def total_documents(self) -> int:
        """Total de documentos extraídos dos lotes."""
        return sum(br.total_documents for br in self.batch_results)

    @property
    def total_avisos(self) -> int:
        """Total de avisos de email sem anexo."""
        return len(self.avisos)

    def summary(self) -> str:
        """Retorna resumo textual do resultado."""
        return (
            f"Ingestão {self.status.value}: "
            f"{self.total_emails_scanned} emails escaneados, "
            f"{self.total_with_attachments} com anexos, "
            f"{self.total_without_attachments} sem anexos, "
            f"{self.total_filtered_out} filtrados, "
            f"{self.total_documents} documentos extraídos, "
            f"{self.total_avisos} avisos criados "
            f"em {self.duration_seconds:.1f}s"
        )


class EmailIngestionOrchestrator:
    """
    Orquestrador de Ingestão de E-mails.

    Gerencia todo o fluxo de ingestão de e-mails, incluindo:
    - E-mails COM anexos (PDFs/XMLs)
    - E-mails SEM anexos (links de NF-e, códigos de verificação)
    - Checkpointing para resume após interrupções
    - Tratamento graceful de sinais de interrupção
    - Processamento em lotes com timeout
    - Exportação incremental de resultados (JSONL)

    Uso:
        orchestrator = EmailIngestionOrchestrator(
            ingestor=ImapIngestor(...),
            temp_dir=Path("temp_email")
        )
        result = orchestrator.run(subject_filter="ENC")

    Segurança de Dados:
        - Cada lote processado é salvo imediatamente em arquivo JSONL
        - Em caso de interrupção, os dados parciais são preservados
        - Na próxima execução, os dados parciais são carregados automaticamente
    """

    CHECKPOINT_FILENAME = "_checkpoint.json"

    def __init__(
        self,
        ingestor: EmailIngestorStrategy,
        temp_dir: Path,
        email_filter: Optional[EmailFilter] = None,
        batch_timeout_seconds: int = 300,
        enable_checkpoint: bool = True,
        metrics: Optional[IngestionMetrics] = None,
    ):
        """
        Inicializa o orquestrador.

        Args:
            ingestor: Estratégia de ingestão (IMAP, Graph API, etc.)
            temp_dir: Diretório para armazenar lotes e checkpoints
            email_filter: Filtro de emails customizado (opcional)
            batch_timeout_seconds: Timeout por lote em segundos
            enable_checkpoint: Se True, salva checkpoints para resume
            metrics: Coletor de métricas (opcional, cria novo se não fornecido)
        """
        self.ingestor = ingestor
        self.temp_dir = Path(temp_dir)
        self.email_filter = email_filter or get_default_filter()
        self.batch_timeout_seconds = batch_timeout_seconds
        self.enable_checkpoint = enable_checkpoint

        # Métricas de telemetria
        self._metrics = metrics or IngestionMetrics()

        # Serviços internos
        self._ingestion_service = IngestionService(
            ingestor=ingestor,
            temp_dir=temp_dir,
            email_filter=self.email_filter,
        )
        self._batch_processor = BatchProcessor()

        # Estado de execução
        self._checkpoint: CheckpointData = CheckpointData()
        self._interrupted = False
        self._original_sigint_handler = None
        self._original_sigterm_handler = None

        # Callbacks de progresso
        self._progress_callback: Optional[Callable[[str, int, int], None]] = None

        # Armazena resultados parciais em memória (para retorno)
        self._partial_batch_results: List[BatchResult] = []
        self._partial_avisos: List[EmailAvisoData] = []

        # Garante que diretório existe
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @property
    def checkpoint_path(self) -> Path:
        """Caminho do arquivo de checkpoint."""
        return self.temp_dir / self.CHECKPOINT_FILENAME

    @property
    def partial_batches_path(self) -> Path:
        """Caminho do arquivo de lotes parciais."""
        return self.temp_dir / PARTIAL_BATCHES_FILE

    @property
    def partial_avisos_path(self) -> Path:
        """Caminho do arquivo de avisos parciais."""
        return self.temp_dir / PARTIAL_AVISOS_FILE

    def set_progress_callback(
        self,
        callback: Callable[[str, int, int], None]
    ) -> None:
        """
        Define callback de progresso.

        Args:
            callback: Função (fase, atual, total) chamada em cada etapa
        """
        self._progress_callback = callback

    def _notify_progress(self, phase: str, current: int, total: int) -> None:
        """Notifica progresso se callback definido."""
        if self._progress_callback:
            try:
                self._progress_callback(phase, current, total)
            except Exception:
                pass  # Ignora erros no callback

    def _setup_signal_handlers(self) -> None:
        """Configura handlers para capturar interrupções."""
        def signal_handler(signum, frame):
            logger.warning(f"\n⚠️ Sinal de interrupção recebido ({signum}). Salvando checkpoint...")
            self._interrupted = True

        # Salva handlers originais
        self._original_sigint_handler = signal.signal(signal.SIGINT, signal_handler)

        # SIGTERM pode não existir no Windows
        if hasattr(signal, 'SIGTERM'):
            self._original_sigterm_handler = signal.signal(signal.SIGTERM, signal_handler)

        # Registra callback de saída
        atexit.register(self._on_exit)

    def _restore_signal_handlers(self) -> None:
        """Restaura handlers originais de sinais."""
        if self._original_sigint_handler is not None:
            signal.signal(signal.SIGINT, self._original_sigint_handler)

        if hasattr(signal, 'SIGTERM') and self._original_sigterm_handler is not None:
            signal.signal(signal.SIGTERM, self._original_sigterm_handler)

        # Remove callback de saída
        try:
            atexit.unregister(self._on_exit)
        except Exception:
            pass

    def _on_exit(self) -> None:
        """Callback chamado na saída do programa."""
        if self._checkpoint.status == IngestionStatus.IN_PROGRESS:
            self._checkpoint.status = IngestionStatus.INTERRUPTED
            self._save_checkpoint()

    def _load_checkpoint(self) -> bool:
        """
        Carrega checkpoint existente se houver.

        Returns:
            True se checkpoint foi carregado com sucesso
        """
        if not self.enable_checkpoint:
            return False

        if not self.checkpoint_path.exists():
            return False

        try:
            data = json.loads(self.checkpoint_path.read_text(encoding='utf-8'))
            self._checkpoint = CheckpointData.from_dict(data)

            logger.info(
                f"📁 Checkpoint carregado: {self._checkpoint.total_processed} "
                f"e-mails processados anteriormente, "
                f"status: {self._checkpoint.status.value}"
            )
            return True

        except Exception as e:
            logger.warning(f"⚠️ Erro ao carregar checkpoint: {e}. Iniciando do zero.")
            return False

    def _save_checkpoint(self) -> None:
        """Salva checkpoint atual para disco."""
        if not self.enable_checkpoint:
            return

        try:
            self._checkpoint.last_updated = datetime.now().isoformat()

            self.checkpoint_path.write_text(
                json.dumps(self._checkpoint.to_dict(), indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"❌ Erro ao salvar checkpoint: {e}")

    def clear_checkpoint(self) -> None:
        """Remove checkpoint e arquivos parciais para forçar nova ingestão."""
        files_to_remove = [
            self.checkpoint_path,
            self.partial_batches_path,
            self.partial_avisos_path,
        ]

        for filepath in files_to_remove:
            if filepath.exists():
                try:
                    filepath.unlink()
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao remover {filepath.name}: {e}")

        logger.info("🗑️ Checkpoint e arquivos parciais removidos")
        self._checkpoint = CheckpointData()
        self._partial_batch_results = []
        self._partial_avisos = []

    def has_pending_work(self) -> bool:
        """
        Verifica se há trabalho pendente de execução anterior.

        Returns:
            True se checkpoint indica trabalho incompleto
        """
        self._load_checkpoint()
        return self._checkpoint.status in (
            IngestionStatus.IN_PROGRESS,
            IngestionStatus.INTERRUPTED
        )

    def _save_partial_batch(self, batch_result: BatchResult) -> None:
        """
        Salva um BatchResult parcial em arquivo JSONL (append).

        Isso garante que mesmo em caso de interrupção, os dados
        já processados não serão perdidos.

        Args:
            batch_result: Resultado do lote a salvar
        """
        try:
            # Converte para dict serializável
            batch_dict = {
                "batch_id": batch_result.batch_id,
                "source_folder": batch_result.source_folder,
                "status": batch_result.status,
                "processing_time": batch_result.processing_time,
                "email_subject": batch_result.email_subject,
                "email_sender": batch_result.email_sender,
                "total_documents": batch_result.total_documents,
                "total_errors": batch_result.total_errors,
                "documents": [doc.to_dict() for doc in batch_result.documents],
                "saved_at": datetime.now().isoformat(),
            }

            # Append ao arquivo JSONL
            with open(self.partial_batches_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(batch_dict, ensure_ascii=False) + "\n")

        except Exception as e:
            logger.warning(f"⚠️ Erro ao salvar lote parcial: {e}")

    def _save_partial_aviso(self, aviso: EmailAvisoData) -> None:
        """
        Salva um EmailAvisoData parcial em arquivo JSONL (append).

        Salva todos os campos necessários para reconstrução completa,
        garantindo compatibilidade com export_to_sheets.py.

        Args:
            aviso: Aviso a salvar
        """
        try:
            aviso_dict = {
                "email_id": aviso.email_id,
                "subject": aviso.subject,
                "sender_name": aviso.sender_name,
                "sender_address": aviso.sender_address,
                "link_nfe": aviso.link_nfe,
                "codigo_verificacao": aviso.codigo_verificacao,
                "empresa": aviso.empresa,
                "saved_at": datetime.now().isoformat(),
                # Campos adicionais para integração Google Sheets
                "data_processamento": aviso.data_processamento,
                "email_date": aviso.email_date,  # Data do email (não do processamento)
                "numero_nota": aviso.numero_nota,
                "dominio_portal": aviso.dominio_portal,
                "vencimento": aviso.vencimento,
                "observacoes": aviso.observacoes,
                "email_subject_full": aviso.email_subject_full,
                "source_email_subject": aviso.source_email_subject,
                "status_conciliacao": aviso.status_conciliacao,
            }

            with open(self.partial_avisos_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(aviso_dict, ensure_ascii=False) + "\n")

        except Exception as e:
            logger.warning(f"⚠️ Erro ao salvar aviso parcial: {e}")

    def _load_partial_results(self) -> Tuple[List[Dict], List[Dict]]:
        """
        Carrega resultados parciais de execuções anteriores.

        Returns:
            Tupla (lista de batches dict, lista de avisos dict)
        """
        batches = []
        avisos = []

        # Carrega lotes parciais
        if self.partial_batches_path.exists():
            try:
                with open(self.partial_batches_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            batches.append(json.loads(line))
                logger.info(f"📂 Carregados {len(batches)} lotes parciais anteriores")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao carregar lotes parciais: {e}")

        # Carrega avisos parciais
        if self.partial_avisos_path.exists():
            try:
                with open(self.partial_avisos_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            avisos.append(json.loads(line))
                logger.info(f"📂 Carregados {len(avisos)} avisos parciais anteriores")
            except Exception as e:
                logger.warning(f"⚠️ Erro ao carregar avisos parciais: {e}")

        return batches, avisos

    def get_partial_results_count(self) -> Tuple[int, int]:
        """
        Retorna contagem de resultados parciais salvos.

        Returns:
            Tupla (qtd lotes, qtd avisos)
        """
        batches_count = 0
        avisos_count = 0

        if self.partial_batches_path.exists():
            try:
                with open(self.partial_batches_path, "r", encoding="utf-8") as f:
                    batches_count = sum(1 for line in f if line.strip())
            except Exception:
                pass

        if self.partial_avisos_path.exists():
            try:
                with open(self.partial_avisos_path, "r", encoding="utf-8") as f:
                    avisos_count = sum(1 for line in f if line.strip())
            except Exception:
                pass

        return batches_count, avisos_count

    def run(
        self,
        subject_filter: str = "*",
        process_with_attachments: bool = True,
        process_without_attachments: bool = True,
        apply_filter: bool = True,
        apply_correlation: bool = True,
        resume: bool = True,
        limit_emails: Optional[int] = None,
        links_first: bool = False,
    ) -> IngestionResult:
        """
        Executa ingestão completa de e-mails.

        Esta é a função principal que orquestra todo o processo de ingestão,
        incluindo:
        1. Verificação de checkpoint para resume
        2. Busca de e-mails no servidor
        3. Filtro inteligente para evitar falsos positivos
        4. Download de anexos e criação de lotes
        5. Captura de links/códigos de e-mails sem anexo
        6. Processamento de lotes com timeout
        7. Salvamento de checkpoint em cada etapa

        Args:
            subject_filter: Filtro de assunto para busca IMAP
            process_with_attachments: Processar e-mails COM anexos
            process_without_attachments: Processar e-mails SEM anexos
            apply_filter: Aplicar filtro inteligente
            apply_correlation: Aplicar correlação entre documentos
            resume: Se True, resume de checkpoint existente
            limit_emails: Limite de e-mails a processar (None = sem limite)
            links_first: Se True, processa e-mails SEM anexo ANTES dos COM anexo

        Returns:
            IngestionResult com resultados consolidados
        """
        start_time = time.time()
        result = IngestionResult()

        # Configura handlers de sinal
        self._setup_signal_handlers()

        try:
            # Tenta carregar checkpoint se resume habilitado
            if resume:
                has_checkpoint = self._load_checkpoint()

                # Se checkpoint indica trabalho pendente, resume
                if has_checkpoint and self._checkpoint.status in (
                    IngestionStatus.IN_PROGRESS,
                    IngestionStatus.INTERRUPTED
                ):
                    # Verifica se o filtro é o mesmo
                    if self._checkpoint.subject_filter != subject_filter:
                        logger.warning(
                            f"⚠️ Filtro diferente do checkpoint "
                            f"('{subject_filter}' vs '{self._checkpoint.subject_filter}'). "
                            f"Iniciando nova ingestão."
                        )
                        self.clear_checkpoint()
                    else:
                        logger.info(f"▶️ Resumindo ingestão de checkpoint...")
            else:
                self.clear_checkpoint()

            # Inicia nova ingestão
            self._checkpoint.status = IngestionStatus.IN_PROGRESS
            self._checkpoint.subject_filter = subject_filter

            if not self._checkpoint.started_at:
                self._checkpoint.started_at = datetime.now().isoformat()

            self._save_checkpoint()

            # Carrega resultados parciais se estiver resumindo
            if resume and self.has_pending_work():
                partial_batches, partial_avisos = self._load_partial_results()
                # Os parciais já estão salvos, apenas contabilizamos
                logger.info(
                    f"   📊 Resultados parciais: {len(partial_batches)} lotes, "
                    f"{len(partial_avisos)} avisos já salvos"
                )

            # Conecta ao servidor
            logger.info(f"📧 Conectando ao servidor de e-mail...")
            self.ingestor.connect()

            # Define ordem de processamento
            if links_first:
                # ================================================================
                # FASE 1: E-mails SEM anexos (links e códigos) - PRIMEIRO
                # ================================================================
                if process_without_attachments and not self._interrupted:
                    logger.info(f"\n🔗 Fase 1: Processando e-mails SEM anexos...")

                    avisos, without_att_count, filtered_count = self._process_emails_without_attachments(
                        subject_filter=subject_filter,
                        apply_filter=apply_filter,
                        limit=limit_emails,
                    )

                    result.avisos.extend(avisos)
                    result.total_without_attachments = without_att_count
                    result.total_filtered_out = filtered_count

                # ================================================================
                # FASE 2: E-mails COM anexos - DEPOIS
                # ================================================================
                if process_with_attachments and not self._interrupted:
                    logger.info(f"\n📎 Fase 2: Processando e-mails COM anexos...")

                    batch_results, with_att_count = self._process_emails_with_attachments(
                        subject_filter=subject_filter,
                        apply_correlation=apply_correlation,
                        limit=limit_emails,
                    )

                    result.batch_results.extend(batch_results)
                    result.total_with_attachments = with_att_count
            else:
                # ================================================================
                # FASE 1: E-mails COM anexos - PRIMEIRO (padrão)
                # ================================================================
                if process_with_attachments and not self._interrupted:
                    logger.info(f"\n📎 Fase 1: Processando e-mails COM anexos...")

                    batch_results, with_att_count = self._process_emails_with_attachments(
                        subject_filter=subject_filter,
                        apply_correlation=apply_correlation,
                        limit=limit_emails,
                    )

                    result.batch_results.extend(batch_results)
                    result.total_with_attachments = with_att_count

                # ================================================================
                # FASE 2: E-mails SEM anexos (links e códigos) - DEPOIS
                # ================================================================
                if process_without_attachments and not self._interrupted:
                    logger.info(f"\n🔗 Fase 2: Processando e-mails SEM anexos...")

                    avisos, without_att_count, filtered_count = self._process_emails_without_attachments(
                        subject_filter=subject_filter,
                        apply_filter=apply_filter,
                        limit=limit_emails,
                    )

                    result.avisos.extend(avisos)
                    result.total_without_attachments = without_att_count
                    result.total_filtered_out = filtered_count

            # Atualiza estatísticas finais
            result.total_emails_scanned = (
                result.total_with_attachments +
                result.total_without_attachments +
                result.total_filtered_out
            )
            result.total_errors = self._checkpoint.total_errors

            # Define status final
            if self._interrupted:
                result.status = IngestionStatus.INTERRUPTED
                self._checkpoint.status = IngestionStatus.INTERRUPTED
            else:
                result.status = IngestionStatus.COMPLETED
                self._checkpoint.status = IngestionStatus.COMPLETED

            self._save_checkpoint()

        except Exception as e:
            logger.error(f"❌ Erro na ingestão: {e}")
            result.status = IngestionStatus.FAILED
            self._checkpoint.status = IngestionStatus.FAILED
            self._checkpoint.total_errors += 1
            self._save_checkpoint()
            raise

        finally:
            # Restaura handlers de sinal
            self._restore_signal_handlers()

            # Calcula duração
            result.duration_seconds = time.time() - start_time

            # ================================================================
            # SEMPRE carrega e mescla resultados parciais salvos no disco
            # Isso garante que o CSV final tenha TODOS os dados, mesmo em resume
            # ================================================================
            result = self._merge_partial_results_into_result(result)

        return result

    def _process_emails_with_attachments(
        self,
        subject_filter: str,
        apply_correlation: bool = True,
        limit: Optional[int] = None,
    ) -> Tuple[List[BatchResult], int]:
        """
        Processa e-mails COM anexos.

        Args:
            subject_filter: Filtro de assunto
            apply_correlation: Se aplica correlação
            limit: Limite de e-mails

        Returns:
            Tupla (lista de BatchResult, contagem de e-mails)
        """
        batch_results: List[BatchResult] = []
        email_count = 0
        processed_in_session = 0
        skipped_already_done = 0

        try:
            # Usa IngestionService para baixar e organizar anexos
            with self._metrics.measure_fetch("attachments"):
                batch_folders = self._ingestion_service.ingest_emails(
                    subject_filter=subject_filter,
                    create_ignored_folder=True,
                )

            if not batch_folders:
                logger.info("   ℹ️ Nenhum e-mail com anexos encontrado.")
                return batch_results, email_count

            logger.info(f"   📦 {len(batch_folders)} lote(s) para processar...")
            self._metrics.record_batch_created(len(batch_folders))

            # Processa cada lote
            total_batches = len(batch_folders)

            for idx, folder in enumerate(batch_folders):
                if self._interrupted:
                    logger.warning(f"   ⚠️ Interrompido após {idx} de {total_batches} lotes")
                    break

                batch_id = folder.name

                # Verifica se já foi processado (resume)
                if batch_id in self._checkpoint.processed_email_ids:
                    skipped_already_done += 1
                    continue

                processed_in_session += 1
                percent = ((idx + 1) / total_batches) * 100
                self._notify_progress("Processando lotes", idx + 1, total_batches)

                try:
                    # Log de progresso detalhado
                    logger.info(
                        f"   [{idx + 1}/{total_batches}] ({percent:.1f}%) {batch_id}..."
                    )

                    # Processa com timeout
                    batch_start = time.time()
                    batch_result = self._process_batch_with_timeout(
                        folder,
                        apply_correlation,
                    )
                    batch_duration = time.time() - batch_start

                    if batch_result:
                        batch_results.append(batch_result)
                        email_count += 1

                        # Registra métricas
                        self._metrics.record_batch_processed(
                            num_documents=batch_result.total_documents,
                            duration_seconds=batch_duration,
                            status="ok"
                        )
                        self._metrics.record_email_processed(has_attachment=True)

                        # Salva resultado parcial IMEDIATAMENTE (segurança)
                        self._save_partial_batch(batch_result)
                        self._partial_batch_results.append(batch_result)

                        # Atualiza checkpoint
                        self._checkpoint.processed_email_ids.add(batch_id)
                        self._checkpoint.created_batches.append(str(folder))
                        self._checkpoint.total_processed += 1

                        logger.info(
                            f"      ✓ {batch_result.total_documents} doc(s) | "
                            f"Valor: R$ {batch_result.get_valor_compra():,.2f}"
                        )
                    else:
                        logger.warning(f"      ⚠️ Nenhum documento extraído")
                        self._metrics.record_batch_processed(0, batch_duration, "empty")

                    self._save_checkpoint()

                    # Log de progresso a cada 10 lotes
                    if processed_in_session % 10 == 0:
                        logger.info(
                            f"   📊 Progresso: {processed_in_session} processados nesta sessão, "
                            f"{skipped_already_done} já feitos anteriormente"
                        )

                except FuturesTimeoutError:
                    logger.error(f"      ⏱️ TIMEOUT após {self.batch_timeout_seconds}s")
                    self._checkpoint.total_errors += 1
                    self._metrics.record_email_error("timeout", {"batch_id": batch_id})

                    # Registra timeout para reprocessamento posterior
                    self._register_timeout(batch_id, folder)

                except Exception as e:
                    logger.error(f"      ❌ Erro: {e}")
                    self._checkpoint.total_errors += 1
                    self._metrics.record_email_error("exception", {"error": str(e)[:50]})

        except Exception as e:
            logger.error(f"   ❌ Erro ao processar e-mails com anexos: {e}")
            self._checkpoint.total_errors += 1

        # Log final da fase
        if processed_in_session > 0 or skipped_already_done > 0:
            logger.info(
                f"   ✅ Fase 1 concluída: {processed_in_session} novos, "
                f"{skipped_already_done} já processados anteriormente"
            )

        return batch_results, email_count

    def _process_emails_without_attachments(
        self,
        subject_filter: str,
        apply_filter: bool = True,
        limit: Optional[int] = None,
    ) -> Tuple[List[EmailAvisoData], int, int]:
        """
        Processa e-mails SEM anexos (links e códigos de verificação).

        Args:
            subject_filter: Filtro de assunto
            apply_filter: Se aplica filtro inteligente
            limit: Limite de e-mails

        Returns:
            Tupla (lista de avisos, contagem processada, contagem filtrada)
        """
        avisos: List[EmailAvisoData] = []
        processed_count = 0
        filtered_count = 0

        try:
            # Usa IngestionService para buscar e-mails sem anexo
            # limit=0 significa sem limite (processa todos)
            with self._metrics.measure_fetch("links"):
                raw_avisos = self._ingestion_service.ingest_emails_without_attachments(
                    subject_filter=subject_filter,
                    limit=limit or 0,
                    apply_filter=apply_filter,
                )

            if not raw_avisos:
                logger.info("   ℹ️ Nenhum e-mail sem anexo relevante encontrado.")
                return avisos, processed_count, filtered_count

            total_avisos = len(raw_avisos)
            logger.info(f"   📋 {total_avisos} aviso(s) de link/código após filtro...")

            skipped_already_done = 0
            for idx, aviso in enumerate(raw_avisos):
                if self._interrupted:
                    logger.warning(f"   ⚠️ Interrompido após {idx} de {total_avisos} avisos")
                    break

                # Verifica se já foi processado
                if aviso.email_id in self._checkpoint.processed_email_ids:
                    skipped_already_done += 1
                    continue

                avisos.append(aviso)
                processed_count += 1

                # Log de progresso a cada 50 avisos
                if processed_count % 50 == 0:
                    percent = ((idx + 1) / total_avisos) * 100
                    logger.info(
                        f"   📊 Progresso avisos: {processed_count}/{total_avisos} ({percent:.1f}%)"
                    )

                # Salva aviso parcial IMEDIATAMENTE (segurança)
                self._save_partial_aviso(aviso)
                self._partial_avisos.append(aviso)

                # Registra métricas
                self._metrics.record_aviso_created(has_link=bool(aviso.link_nfe))
                self._metrics.record_email_processed(has_attachment=False)

                # Atualiza checkpoint
                self._checkpoint.processed_email_ids.add(aviso.email_id)
                self._checkpoint.created_avisos.append({
                    "email_id": aviso.email_id,
                    "subject": aviso.subject,
                    "link_nfe": aviso.link_nfe,
                    "codigo_verificacao": aviso.codigo_verificacao,
                })
                self._checkpoint.total_processed += 1

            self._save_checkpoint()

            # Log final da fase
            logger.info(
                f"   ✅ Fase 2 concluída: {processed_count} novos avisos, "
                f"{skipped_already_done} já processados anteriormente"
            )

        except Exception as e:
            logger.error(f"   ❌ Erro ao processar e-mails sem anexos: {e}")
            self._checkpoint.total_errors += 1

        return avisos, processed_count, filtered_count

    def _process_batch_with_timeout(
        self,
        folder: Path,
        apply_correlation: bool,
    ) -> Optional[BatchResult]:
        """
        Processa lote com timeout.

        Args:
            folder: Pasta do lote
            apply_correlation: Se aplica correlação

        Returns:
            BatchResult ou None se falhar
        """
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self._batch_processor.process_batch,
                folder,
                apply_correlation,
            )

            result = future.result(timeout=self.batch_timeout_seconds)
            return result if result and result.total_documents > 0 else None

    def _register_timeout(self, batch_id: str, folder: Path) -> None:
        """
        Registra lote que deu timeout para reprocessamento posterior.

        Args:
            batch_id: ID do lote
            folder: Pasta do lote
        """
        timeout_log_path = self.temp_dir / "_timeouts.json"

        try:
            # Carrega timeouts existentes
            if timeout_log_path.exists():
                timeouts = json.loads(timeout_log_path.read_text(encoding='utf-8'))
            else:
                timeouts = []

            # Adiciona novo timeout
            timeouts.append({
                "batch_id": batch_id,
                "folder": str(folder),
                "timestamp": datetime.now().isoformat(),
                "timeout_seconds": self.batch_timeout_seconds,
            })

            # Salva
            timeout_log_path.write_text(
                json.dumps(timeouts, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )

        except Exception as e:
            logger.warning(f"⚠️ Erro ao registrar timeout: {e}")

    def get_status(self) -> Dict[str, Any]:
        """
        Retorna status atual da ingestão.

        Returns:
            Dicionário com informações de status
        """
        self._load_checkpoint()

        # Conta resultados parciais salvos
        partial_batches, partial_avisos = self.get_partial_results_count()

        return {
            "status": self._checkpoint.status.value,
            "started_at": self._checkpoint.started_at,
            "last_updated": self._checkpoint.last_updated,
            "total_processed": self._checkpoint.total_processed,
            "total_skipped": self._checkpoint.total_skipped,
            "total_errors": self._checkpoint.total_errors,
            "batches_created": len(self._checkpoint.created_batches),
            "avisos_created": len(self._checkpoint.created_avisos),
            "partial_batches_saved": partial_batches,
            "partial_avisos_saved": partial_avisos,
            "has_pending_work": self.has_pending_work(),
        }

    def _merge_partial_results_into_result(self, result: IngestionResult) -> IngestionResult:
        """
        Mescla resultados parciais salvos em disco com o resultado atual.

        Isso garante que, mesmo em resume (quando avisos/batches são pulados
        por já estarem processados), o resultado final contenha TODOS os dados
        para exportação correta dos CSVs.

        Args:
            result: Resultado atual da ingestão

        Returns:
            Resultado com dados parciais mesclados
        """
        try:
            # Carrega resultados parciais do disco
            partial_batches, partial_avisos = self._load_partial_results()

            if not partial_batches and not partial_avisos:
                return result

            # IDs já presentes no resultado atual
            current_batch_ids = {b.batch_id for b in result.batch_results}
            current_aviso_ids = {a.email_id for a in result.avisos}

            # Mescla batches parciais que não estão no resultado
            batches_added = 0
            for batch_dict in partial_batches:
                batch_id = batch_dict.get("batch_id")
                if batch_id and batch_id not in current_batch_ids:
                    # Reconstrói BatchResult a partir do dict
                    try:
                        batch = BatchResult.from_dict(batch_dict)
                        result.batch_results.append(batch)
                        current_batch_ids.add(batch_id)
                        batches_added += 1
                    except Exception as e:
                        logger.warning(f"Erro ao reconstruir batch {batch_id}: {e}")

            # Mescla avisos parciais que não estão no resultado
            avisos_added = 0
            for aviso_dict in partial_avisos:
                email_id = aviso_dict.get("email_id")
                if email_id and email_id not in current_aviso_ids:
                    # Reconstrói EmailAvisoData a partir do dict
                    try:
                        aviso = EmailAvisoData(
                            arquivo_origem=email_id,
                            email_subject_full=aviso_dict.get("email_subject_full") or aviso_dict.get("subject"),
                            link_nfe=aviso_dict.get("link_nfe"),
                            codigo_verificacao=aviso_dict.get("codigo_verificacao"),
                            empresa=aviso_dict.get("empresa"),
                            fornecedor_nome=aviso_dict.get("sender_name"),
                            source_email_sender=aviso_dict.get("sender_address"),
                            # Campos adicionais para compatibilidade Google Sheets
                            data_processamento=aviso_dict.get("data_processamento"),
                            email_date=aviso_dict.get("email_date"),  # Data do email (não do processamento)
                            numero_nota=aviso_dict.get("numero_nota"),
                            dominio_portal=aviso_dict.get("dominio_portal"),
                            vencimento=aviso_dict.get("vencimento"),
                            observacoes=aviso_dict.get("observacoes"),
                            source_email_subject=aviso_dict.get("source_email_subject") or aviso_dict.get("subject"),
                            status_conciliacao=aviso_dict.get("status_conciliacao"),
                        )
                        result.avisos.append(aviso)
                        current_aviso_ids.add(email_id)
                        avisos_added += 1
                    except Exception as e:
                        logger.warning(f"Erro ao reconstruir aviso {email_id}: {e}")

            if batches_added > 0 or avisos_added > 0:
                logger.info(
                    f"   📦 Mesclados do histórico: {batches_added} lotes, {avisos_added} avisos"
                )

        except Exception as e:
            logger.warning(f"Erro ao mesclar resultados parciais: {e}")

        return result

    def export_metrics(self, output_dir: Path) -> Optional[Path]:
        """
        Exporta métricas da sessão para arquivo JSON.

        Args:
            output_dir: Diretório de saída

        Returns:
            Path do arquivo gerado ou None se falhar
        """
        try:
            return self._metrics.export_session(output_dir)
        except Exception as e:
            logger.error(f"Erro ao exportar métricas: {e}")
            return None

    def log_metrics_summary(self) -> None:
        """Loga resumo das métricas da sessão."""
        self._metrics.log_session_summary()

    def export_partial_results_to_csv(self, output_dir: Path) -> Tuple[int, int]:
        """
        Exporta resultados parciais salvos para CSV.

        Útil para recuperar dados após uma interrupção sem precisar
        reprocessar tudo.

        Args:
            output_dir: Diretório de saída para os CSVs

        Returns:
            Tupla (qtd lotes exportados, qtd avisos exportados)
        """
        import pandas as pd

        output_dir.mkdir(parents=True, exist_ok=True)

        batches_exported = 0
        avisos_exported = 0

        # Exporta lotes parciais
        if self.partial_batches_path.exists():
            try:
                batches = []
                with open(self.partial_batches_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            batches.append(json.loads(line))

                if batches:
                    # Achata documentos para CSV
                    all_docs = []
                    for batch in batches:
                        for doc in batch.get("documents", []):
                            doc["batch_id"] = batch["batch_id"]
                            doc["email_subject"] = batch.get("email_subject", "")
                            all_docs.append(doc)

                    if all_docs:
                        df = pd.DataFrame(all_docs)
                        output_path = output_dir / "parcial_documentos.csv"
                        df.to_csv(output_path, index=False, sep=";", encoding="utf-8-sig")
                        batches_exported = len(batches)
                        logger.info(f"✅ {len(all_docs)} documentos parciais -> {output_path.name}")

            except Exception as e:
                logger.error(f"❌ Erro ao exportar lotes parciais: {e}")

        # Exporta avisos parciais
        if self.partial_avisos_path.exists():
            try:
                avisos_raw = []
                with open(self.partial_avisos_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            avisos_raw.append(json.loads(line))

                if avisos_raw:
                    # Converte para formato compatível com Google Sheets (load_avisos_from_csv)
                    avisos_sheets = []
                    for aviso_dict in avisos_raw:
                        avisos_sheets.append({
                            'tipo_documento': 'AVISO',
                            'arquivo_origem': aviso_dict.get('email_id', ''),
                            'data_processamento': aviso_dict.get('data_processamento'),
                            'email_date': aviso_dict.get('email_date'),  # Data do email (não do processamento)
                            'empresa': aviso_dict.get('empresa'),
                            'fornecedor_nome': aviso_dict.get('sender_name'),
                            'numero_nota': aviso_dict.get('numero_nota'),
                            'link_nfe': aviso_dict.get('link_nfe'),
                            'codigo_verificacao': aviso_dict.get('codigo_verificacao'),
                            'dominio_portal': aviso_dict.get('dominio_portal'),
                            'email_subject': aviso_dict.get('email_subject_full') or aviso_dict.get('subject'),
                            'vencimento': aviso_dict.get('vencimento'),
                            'observacoes': aviso_dict.get('observacoes'),
                            'status_conciliacao': aviso_dict.get('status_conciliacao'),
                        })

                    df = pd.DataFrame(avisos_sheets)
                    # Exporta para o nome esperado pelo export_to_sheets.py
                    output_path = output_dir / "avisos_emails_sem_anexo_latest.csv"
                    df.to_csv(output_path, index=False, sep=";", encoding="utf-8-sig")
                    avisos_exported = len(avisos_sheets)
                    logger.info(f"✅ {len(avisos_sheets)} avisos parciais -> {output_path.name}")

                    # Também exporta versão simplificada para leitura rápida
                    output_path_simple = output_dir / "parcial_avisos.csv"
                    df_simple = pd.DataFrame(avisos_raw)
                    df_simple.to_csv(output_path_simple, index=False, sep=";", encoding="utf-8-sig")

            except Exception as e:
                logger.error(f"❌ Erro ao exportar avisos parciais: {e}")

        return batches_exported, avisos_exported


def create_orchestrator_from_config(
    temp_dir: Optional[Path] = None,
    batch_timeout_seconds: int = 300,
) -> EmailIngestionOrchestrator:
    """
    Factory para criar orquestrador a partir das configurações.

    Args:
        temp_dir: Diretório temporário (opcional, usa settings se None)
        batch_timeout_seconds: Timeout por lote

    Returns:
        EmailIngestionOrchestrator configurado

    Raises:
        ValueError: Se credenciais estiverem faltando
    """
    from config import settings
    from ingestors.imap import ImapIngestor

    if not settings.EMAIL_PASS:
        raise ValueError("Por favor, configure o arquivo .env com suas credenciais.")

    ingestor = ImapIngestor(
        host=settings.EMAIL_HOST,
        user=settings.EMAIL_USER,
        password=settings.EMAIL_PASS,
        folder=settings.EMAIL_FOLDER,
    )

    return EmailIngestionOrchestrator(
        ingestor=ingestor,
        temp_dir=temp_dir or settings.DIR_TEMP,
        batch_timeout_seconds=batch_timeout_seconds,
    )
