"""
Módulo de Métricas e Observabilidade para Ingestão de E-mails.

Este módulo fornece classes e funções para coletar, armazenar e exportar
métricas sobre o processo de ingestão de e-mails.

Features:
- Contadores para e-mails processados, ignorados, erros
- Histogramas de latência por operação
- Exportação para JSON, logs estruturados ou Prometheus (opcional)
- Thread-safe para uso em ambientes concorrentes

Uso:
    from core.metrics import IngestionMetrics, MetricsCollector

    # Uso simples com contexto
    metrics = IngestionMetrics()
    with metrics.measure("fetch_emails"):
        emails = fetch_emails()

    metrics.increment("emails_processed", len(emails))
    metrics.export_json("metrics.json")

Autor: Sistema de Ingestão
Versão: 1.0.0
"""

import json
import logging
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Tipos de métricas suportadas."""
    COUNTER = "counter"      # Contagem incremental
    GAUGE = "gauge"          # Valor instantâneo
    HISTOGRAM = "histogram"  # Distribuição de valores (latência)
    SUMMARY = "summary"      # Resumo estatístico


@dataclass
class MetricValue:
    """Valor de uma métrica com metadados."""
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário serializável."""
        return {
            "name": self.name,
            "type": self.type.value,
            "value": self.value,
            "labels": self.labels,
            "timestamp": self.timestamp,
            "description": self.description,
        }


@dataclass
class HistogramBucket:
    """Bucket de histograma para distribuição de latências."""
    le: float  # less than or equal
    count: int = 0


class Histogram:
    """
    Histograma para medir distribuição de latências.

    Buckets padrão otimizados para operações de I/O (em segundos):
    0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, +Inf
    """

    DEFAULT_BUCKETS = [0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float('inf')]

    def __init__(self, name: str, buckets: Optional[List[float]] = None):
        self.name = name
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._counts = [0] * len(self.buckets)
        self._sum = 0.0
        self._count = 0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        """Registra uma observação no histograma."""
        with self._lock:
            self._sum += value
            self._count += 1
            for i, bucket in enumerate(self.buckets):
                if value <= bucket:
                    self._counts[i] += 1

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do histograma."""
        with self._lock:
            return {
                "count": self._count,
                "sum": self._sum,
                "avg": self._sum / self._count if self._count > 0 else 0,
                "buckets": {
                    f"le_{b}": c for b, c in zip(self.buckets, self._counts)
                }
            }


class MetricsCollector:
    """
    Coletor central de métricas.

    Thread-safe e singleton-friendly para coleta de métricas
    em toda a aplicação.
    """

    _instance: Optional["MetricsCollector"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "MetricsCollector":
        """Singleton pattern para coletor global."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._labels: Dict[str, Dict[str, str]] = {}
        self._descriptions: Dict[str, str] = {}
        self._data_lock = threading.Lock()
        self._start_time = time.time()
        self._initialized = True

    def increment(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
        description: str = ""
    ) -> None:
        """Incrementa um contador."""
        key = self._make_key(name, labels)
        with self._data_lock:
            self._counters[key] += value
            if labels:
                self._labels[key] = labels
            if description:
                self._descriptions[name] = description

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        description: str = ""
    ) -> None:
        """Define valor de um gauge."""
        key = self._make_key(name, labels)
        with self._data_lock:
            self._gauges[key] = value
            if labels:
                self._labels[key] = labels
            if description:
                self._descriptions[name] = description

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        description: str = ""
    ) -> None:
        """Registra observação em um histograma."""
        key = self._make_key(name, labels)
        with self._data_lock:
            if key not in self._histograms:
                self._histograms[key] = Histogram(name)
            self._histograms[key].observe(value)
            if labels:
                self._labels[key] = labels
            if description:
                self._descriptions[name] = description

    @contextmanager
    def measure(self, name: str, labels: Optional[Dict[str, str]] = None):
        """
        Context manager para medir latência de uma operação.

        Uso:
            with collector.measure("fetch_emails"):
                emails = fetch_emails()
        """
        start = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - start
            self.observe_histogram(f"{name}_duration_seconds", elapsed, labels)
            self.increment(f"{name}_total", 1, labels)

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Cria chave única para métrica com labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_all_metrics(self) -> Dict[str, Any]:
        """Retorna todas as métricas coletadas."""
        with self._data_lock:
            return {
                "uptime_seconds": time.time() - self._start_time,
                "collected_at": datetime.now().isoformat(),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: v.get_stats() for k, v in self._histograms.items()
                },
                "labels": dict(self._labels),
                "descriptions": dict(self._descriptions),
            }

    def reset(self) -> None:
        """Reseta todas as métricas."""
        with self._data_lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._labels.clear()
            self._start_time = time.time()

    def export_json(self, path: Union[str, Path]) -> None:
        """Exporta métricas para arquivo JSON."""
        path = Path(path)
        metrics = self.get_all_metrics()

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)

        logger.info(f"📊 Métricas exportadas para {path}")

    def export_prometheus(self) -> str:
        """
        Exporta métricas no formato Prometheus.

        Retorna string formatada para /metrics endpoint.
        """
        lines = []

        with self._data_lock:
            # Counters
            for key, value in self._counters.items():
                name = key.split('{')[0]
                desc = self._descriptions.get(name, "")
                if desc:
                    lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{key} {value}")

            # Gauges
            for key, value in self._gauges.items():
                name = key.split('{')[0]
                desc = self._descriptions.get(name, "")
                if desc:
                    lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{key} {value}")

            # Histograms
            for key, histogram in self._histograms.items():
                name = key.split('{')[0]
                stats = histogram.get_stats()
                desc = self._descriptions.get(name, "")
                if desc:
                    lines.append(f"# HELP {name} {desc}")
                lines.append(f"# TYPE {name} histogram")

                for bucket, count in stats["buckets"].items():
                    le = bucket.replace("le_", "")
                    lines.append(f'{name}_bucket{{le="{le}"}} {count}')

                lines.append(f"{name}_sum {stats['sum']}")
                lines.append(f"{name}_count {stats['count']}")

        return "\n".join(lines)

    def log_summary(self, level: int = logging.INFO) -> None:
        """Loga resumo das métricas."""
        metrics = self.get_all_metrics()

        logger.log(level, "=" * 60)
        logger.log(level, "📊 RESUMO DE MÉTRICAS")
        logger.log(level, "=" * 60)
        logger.log(level, f"   Uptime: {metrics['uptime_seconds']:.1f}s")

        if metrics['counters']:
            logger.log(level, "\n   Contadores:")
            for name, value in metrics['counters'].items():
                logger.log(level, f"      {name}: {value}")

        if metrics['gauges']:
            logger.log(level, "\n   Gauges:")
            for name, value in metrics['gauges'].items():
                logger.log(level, f"      {name}: {value}")

        if metrics['histograms']:
            logger.log(level, "\n   Latências:")
            for name, stats in metrics['histograms'].items():
                logger.log(
                    level,
                    f"      {name}: count={stats['count']}, avg={stats['avg']:.3f}s"
                )

        logger.log(level, "=" * 60)


class IngestionMetrics:
    """
    Métricas específicas para o processo de ingestão de e-mails.

    Fornece uma API de alto nível para as métricas mais comuns
    do processo de ingestão.
    """

    # Nomes de métricas padronizados
    EMAILS_SCANNED = "ingestion_emails_scanned_total"
    EMAILS_PROCESSED = "ingestion_emails_processed_total"
    EMAILS_SKIPPED = "ingestion_emails_skipped_total"
    EMAILS_ERRORS = "ingestion_emails_errors_total"
    BATCHES_CREATED = "ingestion_batches_created_total"
    BATCHES_PROCESSED = "ingestion_batches_processed_total"
    DOCUMENTS_EXTRACTED = "ingestion_documents_extracted_total"
    ATTACHMENTS_DOWNLOADED = "ingestion_attachments_downloaded_total"
    AVISOS_CREATED = "ingestion_avisos_created_total"
    FETCH_DURATION = "ingestion_fetch_duration_seconds"
    PROCESS_DURATION = "ingestion_process_duration_seconds"
    BATCH_DURATION = "ingestion_batch_duration_seconds"

    def __init__(self, collector: Optional[MetricsCollector] = None):
        """
        Inicializa métricas de ingestão.

        Args:
            collector: Coletor de métricas. Se None, usa singleton global.
        """
        self._collector = collector or MetricsCollector()
        self._session_start = time.time()
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    @property
    def collector(self) -> MetricsCollector:
        """Retorna o coletor de métricas."""
        return self._collector

    @property
    def session_id(self) -> str:
        """ID único desta sessão de ingestão."""
        return self._session_id

    def record_email_scanned(self, labels: Optional[Dict[str, str]] = None) -> None:
        """Registra um e-mail varrido/analisado."""
        self._collector.increment(
            self.EMAILS_SCANNED, 1, labels,
            "Total de e-mails analisados"
        )

    def record_email_processed(
        self,
        has_attachment: bool = False,
        filter_result: Optional[str] = None
    ) -> None:
        """Registra um e-mail processado com sucesso."""
        labels = {
            "has_attachment": str(has_attachment).lower(),
        }
        if filter_result:
            labels["filter_result"] = filter_result

        self._collector.increment(
            self.EMAILS_PROCESSED, 1, labels,
            "Total de e-mails processados com sucesso"
        )

    def record_email_skipped(
        self,
        reason: str,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Registra um e-mail ignorado."""
        skip_labels = {"reason": reason}
        if labels:
            skip_labels.update(labels)

        self._collector.increment(
            self.EMAILS_SKIPPED, 1, skip_labels,
            "Total de e-mails ignorados"
        )

    def record_email_error(
        self,
        error_type: str,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Registra um erro no processamento de e-mail."""
        error_labels = {"error_type": error_type}
        if labels:
            error_labels.update(labels)

        self._collector.increment(
            self.EMAILS_ERRORS, 1, error_labels,
            "Total de erros no processamento de e-mails"
        )

    def record_batch_created(self, num_attachments: int = 1) -> None:
        """Registra criação de um lote."""
        self._collector.increment(
            self.BATCHES_CREATED, 1,
            description="Total de lotes criados"
        )
        self._collector.increment(
            self.ATTACHMENTS_DOWNLOADED, num_attachments,
            description="Total de anexos baixados"
        )

    def record_batch_processed(
        self,
        num_documents: int,
        duration_seconds: float,
        status: str = "ok"
    ) -> None:
        """Registra processamento de um lote."""
        self._collector.increment(
            self.BATCHES_PROCESSED, 1, {"status": status},
            "Total de lotes processados"
        )
        self._collector.increment(
            self.DOCUMENTS_EXTRACTED, num_documents,
            description="Total de documentos extraídos"
        )
        self._collector.observe_histogram(
            self.BATCH_DURATION, duration_seconds,
            description="Duração do processamento de lote"
        )

    def record_aviso_created(self, has_link: bool = True) -> None:
        """Registra criação de um aviso (e-mail sem anexo)."""
        self._collector.increment(
            self.AVISOS_CREATED, 1,
            {"type": "link" if has_link else "code"},
            "Total de avisos criados"
        )

    @contextmanager
    def measure_fetch(self, operation: str = "generic"):
        """Mede duração de operação de fetch."""
        with self._collector.measure(f"{self.FETCH_DURATION}_{operation}"):
            yield

    @contextmanager
    def measure_process(self, operation: str = "generic"):
        """Mede duração de operação de processamento."""
        with self._collector.measure(f"{self.PROCESS_DURATION}_{operation}"):
            yield

    def set_current_progress(
        self,
        phase: str,
        current: int,
        total: int
    ) -> None:
        """Define progresso atual (gauge)."""
        self._collector.set_gauge(
            f"ingestion_progress_{phase}",
            current,
            description=f"Progresso atual na fase {phase}"
        )
        self._collector.set_gauge(
            f"ingestion_total_{phase}",
            total,
            description=f"Total de itens na fase {phase}"
        )

        percent = (current / total * 100) if total > 0 else 0
        self._collector.set_gauge(
            f"ingestion_percent_{phase}",
            percent,
            description=f"Percentual concluído na fase {phase}"
        )

    def get_session_summary(self) -> Dict[str, Any]:
        """Retorna resumo da sessão atual."""
        metrics = self._collector.get_all_metrics()

        return {
            "session_id": self._session_id,
            "session_duration_seconds": time.time() - self._session_start,
            "emails_scanned": metrics["counters"].get(self.EMAILS_SCANNED, 0),
            "emails_processed": metrics["counters"].get(self.EMAILS_PROCESSED, 0),
            "emails_skipped": sum(
                v for k, v in metrics["counters"].items()
                if k.startswith(self.EMAILS_SKIPPED)
            ),
            "emails_errors": sum(
                v for k, v in metrics["counters"].items()
                if k.startswith(self.EMAILS_ERRORS)
            ),
            "batches_created": metrics["counters"].get(self.BATCHES_CREATED, 0),
            "batches_processed": sum(
                v for k, v in metrics["counters"].items()
                if k.startswith(self.BATCHES_PROCESSED)
            ),
            "documents_extracted": metrics["counters"].get(self.DOCUMENTS_EXTRACTED, 0),
            "avisos_created": sum(
                v for k, v in metrics["counters"].items()
                if k.startswith(self.AVISOS_CREATED)
            ),
        }

    def log_session_summary(self, level: int = logging.INFO) -> None:
        """Loga resumo da sessão."""
        summary = self.get_session_summary()

        logger.log(level, "\n" + "=" * 60)
        logger.log(level, "📊 MÉTRICAS DA SESSÃO")
        logger.log(level, "=" * 60)
        logger.log(level, f"   Session ID: {summary['session_id']}")
        logger.log(level, f"   Duração: {summary['session_duration_seconds']:.1f}s")
        logger.log(level, f"   E-mails analisados: {summary['emails_scanned']}")
        logger.log(level, f"   E-mails processados: {summary['emails_processed']}")
        logger.log(level, f"   E-mails ignorados: {summary['emails_skipped']}")
        logger.log(level, f"   Erros: {summary['emails_errors']}")
        logger.log(level, f"   Lotes criados: {summary['batches_created']}")
        logger.log(level, f"   Lotes processados: {summary['batches_processed']}")
        logger.log(level, f"   Documentos extraídos: {summary['documents_extracted']}")
        logger.log(level, f"   Avisos criados: {summary['avisos_created']}")
        logger.log(level, "=" * 60)

    def export_session(self, output_dir: Union[str, Path]) -> Path:
        """
        Exporta métricas da sessão para arquivo JSON.

        Returns:
            Path do arquivo gerado
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"metrics_{self._session_id}.json"
        filepath = output_dir / filename

        data = {
            "session": self.get_session_summary(),
            "metrics": self._collector.get_all_metrics(),
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"📊 Métricas da sessão exportadas para {filepath}")
        return filepath


# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def get_global_metrics() -> IngestionMetrics:
    """Retorna instância global de métricas de ingestão."""
    return IngestionMetrics()


def reset_global_metrics() -> None:
    """Reseta métricas globais."""
    MetricsCollector().reset()
