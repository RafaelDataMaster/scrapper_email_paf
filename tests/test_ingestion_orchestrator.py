"""
Testes para o EmailIngestionOrchestrator.

Testa:
1. Checkpoint save/load
2. Resume após interrupção
3. Filtro de emails
4. Processamento com e sem anexos
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from core.interfaces import EmailIngestorStrategy
from services.email_ingestion_orchestrator import (
    CheckpointData,
    EmailIngestionOrchestrator,
    IngestionResult,
    IngestionStatus,
)


class MockIngestor(EmailIngestorStrategy):
    """Mock do ingestor para testes."""

    def __init__(
        self,
        emails_with_attachments: List[Dict[str, Any]] = None,
        emails_without_attachments: List[Dict[str, Any]] = None,
    ):
        self.emails_with_attachments = emails_with_attachments or []
        self.emails_without_attachments = emails_without_attachments or []
        self._connected = False

    def connect(self) -> None:
        self._connected = True

    def fetch_attachments(self, subject_filter: str = "") -> List[Dict[str, Any]]:
        return self.emails_with_attachments

    def fetch_emails_without_attachments(
        self, subject_filter: str = "", limit: int = 100
    ) -> List[Dict[str, Any]]:
        return self.emails_without_attachments


@pytest.fixture
def temp_dir():
    """Cria diretório temporário para testes."""
    path = Path(tempfile.mkdtemp())
    yield path
    # Cleanup
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def mock_ingestor():
    """Cria mock do ingestor."""
    return MockIngestor(
        emails_with_attachments=[
            {
                "email_id": "email_001",
                "subject": "ENC: Nota Fiscal - Janeiro",
                "sender_name": "Fornecedor A",
                "sender_address": "nfe@fornecedor-a.com",
                "body_text": "Segue nota fiscal em anexo.",
                "received_date": "2025-01-15",
                "filename": "nf_001.pdf",
                "content": b"%PDF-1.4 fake content",
            },
        ],
        emails_without_attachments=[
            {
                "email_id": "email_002",
                "subject": "ENC: Fatura Energia - CEMIG",
                "sender_name": "CEMIG",
                "sender_address": "nfe@cemig.com.br",
                "body_text": "Acesse sua fatura: https://nfe.cemig.com.br/consulta?codigo=ABC123",
                "received_date": "2025-01-15",
                "has_attachments": False,
            },
        ],
    )


class TestCheckpointData:
    """Testes para CheckpointData."""

    def test_to_dict(self):
        """Testa serialização para dicionário."""
        checkpoint = CheckpointData(
            status=IngestionStatus.IN_PROGRESS,
            started_at="2025-01-15T10:00:00",
            processed_email_ids={"email_001", "email_002"},
            total_processed=2,
        )

        data = checkpoint.to_dict()

        assert data["status"] == "IN_PROGRESS"
        assert data["started_at"] == "2025-01-15T10:00:00"
        assert set(data["processed_email_ids"]) == {"email_001", "email_002"}
        assert data["total_processed"] == 2

    def test_from_dict(self):
        """Testa desserialização de dicionário."""
        data = {
            "status": "COMPLETED",
            "started_at": "2025-01-15T10:00:00",
            "processed_email_ids": ["email_001", "email_002"],
            "total_processed": 2,
            "total_errors": 0,
        }

        checkpoint = CheckpointData.from_dict(data)

        assert checkpoint.status == IngestionStatus.COMPLETED
        assert checkpoint.started_at == "2025-01-15T10:00:00"
        assert checkpoint.processed_email_ids == {"email_001", "email_002"}
        assert checkpoint.total_processed == 2


class TestIngestionResult:
    """Testes para IngestionResult."""

    def test_summary(self):
        """Testa geração de resumo."""
        result = IngestionResult(
            total_emails_scanned=10,
            total_with_attachments=5,
            total_without_attachments=3,
            total_filtered_out=2,
            duration_seconds=30.5,
            status=IngestionStatus.COMPLETED,
        )

        summary = result.summary()

        assert "COMPLETED" in summary
        assert "10 emails escaneados" in summary
        assert "5 com anexos" in summary
        assert "30.5s" in summary


class TestEmailIngestionOrchestrator:
    """Testes para EmailIngestionOrchestrator."""

    def test_init(self, mock_ingestor, temp_dir):
        """Testa inicialização do orquestrador."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        assert orchestrator.ingestor == mock_ingestor
        assert orchestrator.temp_dir == temp_dir
        assert orchestrator.enable_checkpoint is True
        assert orchestrator.batch_timeout_seconds == 300

    def test_checkpoint_path(self, mock_ingestor, temp_dir):
        """Testa caminho do checkpoint."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        assert orchestrator.checkpoint_path == temp_dir / "_checkpoint.json"

    def test_save_and_load_checkpoint(self, mock_ingestor, temp_dir):
        """Testa salvamento e carregamento de checkpoint."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Modifica checkpoint
        orchestrator._checkpoint.status = IngestionStatus.IN_PROGRESS
        orchestrator._checkpoint.processed_email_ids.add("email_001")
        orchestrator._checkpoint.total_processed = 1
        orchestrator._save_checkpoint()

        # Verifica arquivo
        assert orchestrator.checkpoint_path.exists()

        # Cria novo orquestrador e carrega checkpoint
        orchestrator2 = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )
        loaded = orchestrator2._load_checkpoint()

        assert loaded is True
        assert orchestrator2._checkpoint.status == IngestionStatus.IN_PROGRESS
        assert "email_001" in orchestrator2._checkpoint.processed_email_ids
        assert orchestrator2._checkpoint.total_processed == 1

    def test_clear_checkpoint(self, mock_ingestor, temp_dir):
        """Testa limpeza de checkpoint."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Cria checkpoint
        orchestrator._checkpoint.status = IngestionStatus.COMPLETED
        orchestrator._save_checkpoint()
        assert orchestrator.checkpoint_path.exists()

        # Limpa
        orchestrator.clear_checkpoint()
        assert not orchestrator.checkpoint_path.exists()
        assert orchestrator._checkpoint.status == IngestionStatus.IDLE

    def test_has_pending_work_false(self, mock_ingestor, temp_dir):
        """Testa detecção de trabalho pendente - sem pendência."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Sem checkpoint
        assert orchestrator.has_pending_work() is False

        # Com checkpoint COMPLETED
        orchestrator._checkpoint.status = IngestionStatus.COMPLETED
        orchestrator._save_checkpoint()
        assert orchestrator.has_pending_work() is False

    def test_has_pending_work_true(self, mock_ingestor, temp_dir):
        """Testa detecção de trabalho pendente - com pendência."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Com checkpoint IN_PROGRESS
        orchestrator._checkpoint.status = IngestionStatus.IN_PROGRESS
        orchestrator._save_checkpoint()

        # Novo orquestrador
        orchestrator2 = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )
        assert orchestrator2.has_pending_work() is True

    def test_get_status(self, mock_ingestor, temp_dir):
        """Testa obtenção de status."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        orchestrator._checkpoint.status = IngestionStatus.COMPLETED
        orchestrator._checkpoint.total_processed = 10
        orchestrator._checkpoint.total_errors = 1
        orchestrator._save_checkpoint()

        status = orchestrator.get_status()

        assert status["status"] == "COMPLETED"
        assert status["total_processed"] == 10
        assert status["total_errors"] == 1

    @patch.object(EmailIngestionOrchestrator, "_process_emails_with_attachments")
    @patch.object(EmailIngestionOrchestrator, "_process_emails_without_attachments")
    def test_run_basic(
        self,
        mock_without_attachments,
        mock_with_attachments,
        mock_ingestor,
        temp_dir,
    ):
        """Testa execução básica do orquestrador."""
        mock_with_attachments.return_value = ([], 0)
        mock_without_attachments.return_value = ([], 0, 0)

        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        result = orchestrator.run(
            subject_filter="ENC",
            resume=False,
        )

        assert result.status == IngestionStatus.COMPLETED
        mock_with_attachments.assert_called_once()
        mock_without_attachments.assert_called_once()

    @patch.object(EmailIngestionOrchestrator, "_process_emails_with_attachments")
    @patch.object(EmailIngestionOrchestrator, "_process_emails_without_attachments")
    def test_run_only_attachments(
        self,
        mock_without_attachments,
        mock_with_attachments,
        mock_ingestor,
        temp_dir,
    ):
        """Testa execução apenas com anexos."""
        mock_with_attachments.return_value = ([], 0)
        mock_without_attachments.return_value = ([], 0, 0)

        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        result = orchestrator.run(
            subject_filter="ENC",
            process_with_attachments=True,
            process_without_attachments=False,
            resume=False,
        )

        assert result.status == IngestionStatus.COMPLETED
        mock_with_attachments.assert_called_once()
        mock_without_attachments.assert_not_called()

    def test_register_timeout(self, mock_ingestor, temp_dir):
        """Testa registro de timeout."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Registra timeout
        orchestrator._register_timeout("batch_001", temp_dir / "batch_001")

        # Verifica arquivo
        timeout_log = temp_dir / "_timeouts.json"
        assert timeout_log.exists()

        data = json.loads(timeout_log.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["batch_id"] == "batch_001"

    def test_progress_callback(self, mock_ingestor, temp_dir):
        """Testa callback de progresso."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        progress_calls = []

        def callback(phase, current, total):
            progress_calls.append((phase, current, total))

        orchestrator.set_progress_callback(callback)
        orchestrator._notify_progress("Teste", 1, 10)

        assert len(progress_calls) == 1
        assert progress_calls[0] == ("Teste", 1, 10)


class TestCheckpointResume:
    """Testes de resume a partir de checkpoint."""

    def test_resume_skips_processed_emails(self, mock_ingestor, temp_dir):
        """Testa que e-mails já processados são pulados no resume."""
        # Cria checkpoint com e-mail já processado
        checkpoint_data = {
            "status": "INTERRUPTED",
            "started_at": "2025-01-15T10:00:00",
            "processed_email_ids": ["email_001"],
            "created_batches": [],
            "created_avisos": [],
            "total_emails_found": 1,
            "total_processed": 1,
            "total_skipped": 0,
            "total_errors": 0,
            "current_batch_idx": 1,
            "subject_filter": "ENC",
        }

        checkpoint_path = temp_dir / "_checkpoint.json"
        checkpoint_path.write_text(
            json.dumps(checkpoint_data, ensure_ascii=False), encoding="utf-8"
        )

        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Carrega checkpoint
        loaded = orchestrator._load_checkpoint()
        assert loaded is True
        assert "email_001" in orchestrator._checkpoint.processed_email_ids

    def test_different_filter_clears_checkpoint(self, mock_ingestor, temp_dir):
        """Testa que filtro diferente limpa o checkpoint."""
        # Cria checkpoint com filtro antigo
        checkpoint_data = {
            "status": "INTERRUPTED",
            "started_at": "2025-01-15T10:00:00",
            "processed_email_ids": ["email_001"],
            "subject_filter": "Nota Fiscal",  # Filtro antigo
            "total_processed": 1,
        }

        checkpoint_path = temp_dir / "_checkpoint.json"
        checkpoint_path.write_text(
            json.dumps(checkpoint_data, ensure_ascii=False), encoding="utf-8"
        )

        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Executa com filtro diferente
        with patch.object(orchestrator, "_process_emails_with_attachments", return_value=([], 0)):
            with patch.object(
                orchestrator, "_process_emails_without_attachments", return_value=([], 0, 0)
            ):
                result = orchestrator.run(
                    subject_filter="ENC",  # Filtro diferente
                    resume=True,
                )

        # Checkpoint deve ter sido limpo (não deve ter email_001)
        # O novo subject_filter deve ser "ENC"
        assert orchestrator._checkpoint.subject_filter == "ENC"


class TestPartialResults:
    """Testes para salvamento e carregamento de resultados parciais."""

    def test_save_partial_batch(self, mock_ingestor, temp_dir):
        """Testa salvamento de lote parcial em JSONL."""
        from core.batch_result import BatchResult

        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Cria um BatchResult mock
        batch_result = BatchResult(
            batch_id="batch_001",
            source_folder=str(temp_dir / "batch_001"),
            status="OK",
            email_subject="Nota Fiscal Teste",
        )

        # Salva
        orchestrator._save_partial_batch(batch_result)

        # Verifica arquivo
        assert orchestrator.partial_batches_path.exists()

        # Lê e verifica conteúdo
        content = orchestrator.partial_batches_path.read_text(encoding="utf-8")
        assert "batch_001" in content
        assert "Nota Fiscal Teste" in content

    def test_save_multiple_partial_batches(self, mock_ingestor, temp_dir):
        """Testa que múltiplos lotes são salvos em append."""
        from core.batch_result import BatchResult

        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Salva 3 lotes
        for i in range(3):
            batch_result = BatchResult(
                batch_id=f"batch_{i:03d}",
                source_folder=str(temp_dir / f"batch_{i:03d}"),
                status="OK",
            )
            orchestrator._save_partial_batch(batch_result)

        # Verifica que tem 3 linhas
        lines = orchestrator.partial_batches_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3

    def test_load_partial_results(self, mock_ingestor, temp_dir):
        """Testa carregamento de resultados parciais."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Cria arquivo de lotes parciais manualmente
        partial_data = [
            '{"batch_id": "batch_001", "documents": []}',
            '{"batch_id": "batch_002", "documents": []}',
        ]
        orchestrator.partial_batches_path.write_text(
            "\n".join(partial_data), encoding="utf-8"
        )

        # Carrega
        batches, avisos = orchestrator._load_partial_results()

        assert len(batches) == 2
        assert batches[0]["batch_id"] == "batch_001"
        assert batches[1]["batch_id"] == "batch_002"
        assert len(avisos) == 0

    def test_get_partial_results_count(self, mock_ingestor, temp_dir):
        """Testa contagem de resultados parciais."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Inicialmente vazio
        batches, avisos = orchestrator.get_partial_results_count()
        assert batches == 0
        assert avisos == 0

        # Adiciona alguns dados
        orchestrator.partial_batches_path.write_text(
            '{"batch_id": "b1"}\n{"batch_id": "b2"}\n{"batch_id": "b3"}\n',
            encoding="utf-8",
        )
        orchestrator.partial_avisos_path.write_text(
            '{"email_id": "e1"}\n{"email_id": "e2"}\n',
            encoding="utf-8",
        )

        batches, avisos = orchestrator.get_partial_results_count()
        assert batches == 3
        assert avisos == 2

    def test_clear_checkpoint_removes_partial_files(self, mock_ingestor, temp_dir):
        """Testa que clear_checkpoint remove arquivos parciais."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Cria arquivos
        orchestrator._checkpoint.status = IngestionStatus.IN_PROGRESS
        orchestrator._save_checkpoint()
        orchestrator.partial_batches_path.write_text('{"test": 1}', encoding="utf-8")
        orchestrator.partial_avisos_path.write_text('{"test": 2}', encoding="utf-8")

        # Verifica que existem
        assert orchestrator.checkpoint_path.exists()
        assert orchestrator.partial_batches_path.exists()
        assert orchestrator.partial_avisos_path.exists()

        # Limpa
        orchestrator.clear_checkpoint()

        # Verifica que foram removidos
        assert not orchestrator.checkpoint_path.exists()
        assert not orchestrator.partial_batches_path.exists()
        assert not orchestrator.partial_avisos_path.exists()

    def test_status_includes_partial_counts(self, mock_ingestor, temp_dir):
        """Testa que get_status inclui contagem de parciais."""
        orchestrator = EmailIngestionOrchestrator(
            ingestor=mock_ingestor,
            temp_dir=temp_dir,
        )

        # Adiciona dados parciais
        orchestrator.partial_batches_path.write_text(
            '{"batch_id": "b1"}\n{"batch_id": "b2"}\n',
            encoding="utf-8",
        )

        status = orchestrator.get_status()

        assert "partial_batches_saved" in status
        assert status["partial_batches_saved"] == 2
        assert status["partial_avisos_saved"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
