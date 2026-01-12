"""
Testes para o módulo core/metrics.py

Testa a funcionalidade de métricas e observabilidade incluindo:
- Contadores
- Gauges
- Histogramas
- Medição de latência
- Exportação para JSON e Prometheus
- IngestionMetrics

Autor: Sistema de Ingestão
Versão: 1.0.0
"""

import json
import tempfile
import threading
import time
from pathlib import Path

import pytest

from core.metrics import (
    Histogram,
    IngestionMetrics,
    MetricsCollector,
    MetricType,
    MetricValue,
    get_global_metrics,
    reset_global_metrics,
)


class TestMetricValue:
    """Testes para a dataclass MetricValue."""

    def test_to_dict(self):
        """Testa conversão para dicionário."""
        metric = MetricValue(
            name="test_counter",
            type=MetricType.COUNTER,
            value=42.0,
            labels={"env": "test"},
            description="Test counter"
        )

        result = metric.to_dict()

        assert result["name"] == "test_counter"
        assert result["type"] == "counter"
        assert result["value"] == 42.0
        assert result["labels"] == {"env": "test"}
        assert result["description"] == "Test counter"
        assert "timestamp" in result

    def test_default_labels_empty(self):
        """Testa que labels padrão é dicionário vazio."""
        metric = MetricValue(
            name="test",
            type=MetricType.GAUGE,
            value=1.0
        )
        assert metric.labels == {}

    def test_timestamp_auto_generated(self):
        """Testa que timestamp é gerado automaticamente."""
        metric = MetricValue(
            name="test",
            type=MetricType.COUNTER,
            value=1.0
        )
        assert metric.timestamp is not None
        assert len(metric.timestamp) > 0


class TestHistogram:
    """Testes para a classe Histogram."""

    def test_observe_single_value(self):
        """Testa observação de um único valor."""
        histogram = Histogram("test_latency")
        histogram.observe(0.5)

        stats = histogram.get_stats()

        assert stats["count"] == 1
        assert stats["sum"] == 0.5
        assert stats["avg"] == 0.5

    def test_observe_multiple_values(self):
        """Testa observação de múltiplos valores."""
        histogram = Histogram("test_latency")

        values = [0.1, 0.2, 0.3, 0.4, 0.5]
        for v in values:
            histogram.observe(v)

        stats = histogram.get_stats()

        assert stats["count"] == 5
        assert abs(stats["sum"] - 1.5) < 0.001
        assert abs(stats["avg"] - 0.3) < 0.001

    def test_buckets_counting(self):
        """Testa contagem em buckets."""
        histogram = Histogram("test_latency")

        # Valores em diferentes buckets
        histogram.observe(0.05)   # <= 0.1
        histogram.observe(0.2)    # <= 0.25
        histogram.observe(3.0)    # <= 5.0
        histogram.observe(100.0)  # <= inf

        stats = histogram.get_stats()
        buckets = stats["buckets"]

        # Verificar contagens cumulativas
        assert buckets["le_0.1"] >= 1
        assert buckets["le_0.25"] >= 2
        assert buckets["le_5.0"] >= 3
        assert buckets["le_inf"] == 4

    def test_custom_buckets(self):
        """Testa buckets customizados."""
        custom_buckets = [1.0, 5.0, 10.0, float('inf')]
        histogram = Histogram("custom", buckets=custom_buckets)

        histogram.observe(0.5)
        histogram.observe(7.0)

        stats = histogram.get_stats()

        assert "le_1.0" in stats["buckets"]
        assert "le_5.0" in stats["buckets"]
        assert "le_10.0" in stats["buckets"]
        assert "le_inf" in stats["buckets"]

    def test_thread_safety(self):
        """Testa segurança em ambiente multithread."""
        histogram = Histogram("concurrent")

        def observe_values():
            for _ in range(100):
                histogram.observe(0.1)

        threads = [threading.Thread(target=observe_values) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        stats = histogram.get_stats()
        assert stats["count"] == 1000


class TestMetricsCollector:
    """Testes para a classe MetricsCollector."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reseta o singleton antes de cada teste."""
        MetricsCollector._instance = None
        yield
        MetricsCollector._instance = None

    def test_singleton_pattern(self):
        """Testa que MetricsCollector é singleton."""
        collector1 = MetricsCollector()
        collector2 = MetricsCollector()

        assert collector1 is collector2

    def test_increment_counter(self):
        """Testa incremento de contador."""
        collector = MetricsCollector()

        collector.increment("test_counter", 1)
        collector.increment("test_counter", 2)

        metrics = collector.get_all_metrics()
        assert metrics["counters"]["test_counter"] == 3

    def test_increment_with_labels(self):
        """Testa incremento com labels."""
        collector = MetricsCollector()

        collector.increment("requests", 1, {"method": "GET"})
        collector.increment("requests", 1, {"method": "POST"})
        collector.increment("requests", 2, {"method": "GET"})

        metrics = collector.get_all_metrics()

        assert metrics["counters"]['requests{method=GET}'] == 3
        assert metrics["counters"]['requests{method=POST}'] == 1

    def test_set_gauge(self):
        """Testa definição de gauge."""
        collector = MetricsCollector()

        collector.set_gauge("temperature", 25.5)
        collector.set_gauge("temperature", 26.0)

        metrics = collector.get_all_metrics()
        assert metrics["gauges"]["temperature"] == 26.0

    def test_observe_histogram(self):
        """Testa observação em histograma."""
        collector = MetricsCollector()

        collector.observe_histogram("latency", 0.5)
        collector.observe_histogram("latency", 1.0)

        metrics = collector.get_all_metrics()

        assert "latency" in metrics["histograms"]
        assert metrics["histograms"]["latency"]["count"] == 2

    def test_measure_context_manager(self):
        """Testa context manager para medição de latência."""
        collector = MetricsCollector()

        with collector.measure("operation"):
            time.sleep(0.1)

        metrics = collector.get_all_metrics()

        # Deve ter criado contador e histograma
        assert "operation_total" in metrics["counters"]
        assert "operation_duration_seconds" in metrics["histograms"]

    def test_reset(self):
        """Testa reset das métricas."""
        collector = MetricsCollector()

        collector.increment("counter", 10)
        collector.set_gauge("gauge", 5)

        collector.reset()

        metrics = collector.get_all_metrics()
        assert len(metrics["counters"]) == 0
        assert len(metrics["gauges"]) == 0

    def test_export_json(self):
        """Testa exportação para JSON."""
        collector = MetricsCollector()
        collector.increment("test", 42)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            collector.export_json(path)

            assert path.exists()

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            assert "counters" in data
            assert data["counters"]["test"] == 42

    def test_export_prometheus(self):
        """Testa exportação no formato Prometheus."""
        collector = MetricsCollector()
        collector.increment("http_requests_total", 100, description="Total HTTP requests")
        collector.set_gauge("cpu_usage", 0.75, description="CPU usage")

        output = collector.export_prometheus()

        assert "# HELP http_requests_total" in output
        assert "# TYPE http_requests_total counter" in output
        assert "http_requests_total 100" in output
        assert "cpu_usage 0.75" in output

    def test_get_all_metrics_structure(self):
        """Testa estrutura do retorno de get_all_metrics."""
        collector = MetricsCollector()

        metrics = collector.get_all_metrics()

        assert "uptime_seconds" in metrics
        assert "collected_at" in metrics
        assert "counters" in metrics
        assert "gauges" in metrics
        assert "histograms" in metrics
        assert "labels" in metrics
        assert "descriptions" in metrics

    def test_uptime_tracking(self):
        """Testa tracking de uptime."""
        collector = MetricsCollector()

        time.sleep(0.1)

        metrics = collector.get_all_metrics()
        assert metrics["uptime_seconds"] >= 0.1

    def test_thread_safe_operations(self):
        """Testa operações thread-safe."""
        collector = MetricsCollector()

        def increment_counter():
            for _ in range(100):
                collector.increment("concurrent_counter")

        threads = [threading.Thread(target=increment_counter) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        metrics = collector.get_all_metrics()
        assert metrics["counters"]["concurrent_counter"] == 1000


class TestIngestionMetrics:
    """Testes para a classe IngestionMetrics."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reseta o singleton antes de cada teste."""
        MetricsCollector._instance = None
        yield
        MetricsCollector._instance = None

    def test_init(self):
        """Testa inicialização."""
        metrics = IngestionMetrics()

        assert metrics.collector is not None
        assert metrics.session_id is not None

    def test_custom_collector(self):
        """Testa uso de collector customizado."""
        collector = MetricsCollector()
        metrics = IngestionMetrics(collector=collector)

        assert metrics.collector is collector

    def test_record_email_scanned(self):
        """Testa registro de e-mail analisado."""
        metrics = IngestionMetrics()

        metrics.record_email_scanned()
        metrics.record_email_scanned()

        all_metrics = metrics.collector.get_all_metrics()
        assert all_metrics["counters"][IngestionMetrics.EMAILS_SCANNED] == 2

    def test_record_email_processed(self):
        """Testa registro de e-mail processado."""
        metrics = IngestionMetrics()

        metrics.record_email_processed(has_attachment=True)
        metrics.record_email_processed(has_attachment=False, filter_result="whitelist")

        all_metrics = metrics.collector.get_all_metrics()

        # Verifica que os contadores existem com labels corretos
        counters = all_metrics["counters"]
        assert any(IngestionMetrics.EMAILS_PROCESSED in k for k in counters)

    def test_record_email_skipped(self):
        """Testa registro de e-mail ignorado."""
        metrics = IngestionMetrics()

        metrics.record_email_skipped("blacklist")
        metrics.record_email_skipped("no_content")
        metrics.record_email_skipped("blacklist")

        all_metrics = metrics.collector.get_all_metrics()
        counters = all_metrics["counters"]

        # Verifica contadores por razão
        blacklist_key = f'{IngestionMetrics.EMAILS_SKIPPED}{{reason=blacklist}}'
        no_content_key = f'{IngestionMetrics.EMAILS_SKIPPED}{{reason=no_content}}'

        assert counters[blacklist_key] == 2
        assert counters[no_content_key] == 1

    def test_record_email_error(self):
        """Testa registro de erro."""
        metrics = IngestionMetrics()

        metrics.record_email_error("timeout")
        metrics.record_email_error("connection")

        all_metrics = metrics.collector.get_all_metrics()
        counters = all_metrics["counters"]

        assert any("timeout" in k for k in counters)
        assert any("connection" in k for k in counters)

    def test_record_batch_created(self):
        """Testa registro de lote criado."""
        metrics = IngestionMetrics()

        metrics.record_batch_created(num_attachments=3)

        all_metrics = metrics.collector.get_all_metrics()

        assert all_metrics["counters"][IngestionMetrics.BATCHES_CREATED] == 1
        assert all_metrics["counters"][IngestionMetrics.ATTACHMENTS_DOWNLOADED] == 3

    def test_record_batch_processed(self):
        """Testa registro de lote processado."""
        metrics = IngestionMetrics()

        metrics.record_batch_processed(num_documents=5, duration_seconds=2.5, status="ok")

        all_metrics = metrics.collector.get_all_metrics()

        assert any(IngestionMetrics.BATCHES_PROCESSED in k for k in all_metrics["counters"])
        assert all_metrics["counters"][IngestionMetrics.DOCUMENTS_EXTRACTED] == 5
        assert IngestionMetrics.BATCH_DURATION in all_metrics["histograms"]

    def test_record_aviso_created(self):
        """Testa registro de aviso criado."""
        metrics = IngestionMetrics()

        metrics.record_aviso_created(has_link=True)
        metrics.record_aviso_created(has_link=False)

        all_metrics = metrics.collector.get_all_metrics()
        counters = all_metrics["counters"]

        assert any("link" in k for k in counters)
        assert any("code" in k for k in counters)

    def test_measure_fetch(self):
        """Testa medição de fetch."""
        metrics = IngestionMetrics()

        with metrics.measure_fetch("attachments"):
            time.sleep(0.05)

        all_metrics = metrics.collector.get_all_metrics()

        assert any("fetch" in k.lower() and "attachments" in k.lower()
                   for k in all_metrics["histograms"])

    def test_measure_process(self):
        """Testa medição de processamento."""
        metrics = IngestionMetrics()

        with metrics.measure_process("batch"):
            time.sleep(0.05)

        all_metrics = metrics.collector.get_all_metrics()

        assert any("process" in k.lower() for k in all_metrics["histograms"])

    def test_set_current_progress(self):
        """Testa definição de progresso."""
        metrics = IngestionMetrics()

        metrics.set_current_progress("attachments", 50, 100)

        all_metrics = metrics.collector.get_all_metrics()
        gauges = all_metrics["gauges"]

        assert gauges["ingestion_progress_attachments"] == 50
        assert gauges["ingestion_total_attachments"] == 100
        assert gauges["ingestion_percent_attachments"] == 50.0

    def test_get_session_summary(self):
        """Testa resumo da sessão."""
        metrics = IngestionMetrics()

        metrics.record_email_scanned()
        metrics.record_email_processed(has_attachment=True)
        metrics.record_batch_created()

        summary = metrics.get_session_summary()

        assert "session_id" in summary
        assert "session_duration_seconds" in summary
        assert "emails_scanned" in summary
        assert "emails_processed" in summary
        assert "batches_created" in summary

    def test_export_session(self):
        """Testa exportação de sessão."""
        metrics = IngestionMetrics()

        metrics.record_email_scanned()
        metrics.record_batch_created()

        with tempfile.TemporaryDirectory() as tmpdir:
            path = metrics.export_session(tmpdir)

            assert path.exists()
            assert "metrics_" in path.name
            assert path.suffix == ".json"

            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            assert "session" in data
            assert "metrics" in data

    def test_session_id_format(self):
        """Testa formato do session_id."""
        metrics = IngestionMetrics()

        # Formato esperado: YYYYMMDD_HHMMSS
        assert len(metrics.session_id) == 15  # 8 + 1 + 6
        assert "_" in metrics.session_id


class TestGlobalMetricsFunctions:
    """Testes para funções globais de métricas."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reseta o singleton antes de cada teste."""
        MetricsCollector._instance = None
        yield
        MetricsCollector._instance = None

    def test_get_global_metrics(self):
        """Testa obtenção de métricas globais."""
        metrics = get_global_metrics()

        assert isinstance(metrics, IngestionMetrics)

    def test_reset_global_metrics(self):
        """Testa reset de métricas globais."""
        metrics = get_global_metrics()
        metrics.record_email_scanned()

        reset_global_metrics()

        all_metrics = metrics.collector.get_all_metrics()
        assert len(all_metrics["counters"]) == 0


class TestMetricsIntegration:
    """Testes de integração para métricas."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reseta o singleton antes de cada teste."""
        MetricsCollector._instance = None
        yield
        MetricsCollector._instance = None

    def test_full_ingestion_workflow(self):
        """Testa fluxo completo de ingestão com métricas."""
        metrics = IngestionMetrics()

        # Simula ingestão
        for i in range(10):
            metrics.record_email_scanned()

            if i < 7:
                metrics.record_email_processed(has_attachment=(i < 3))
            else:
                metrics.record_email_skipped("blacklist")

        # Simula processamento de lotes
        metrics.record_batch_created(num_attachments=5)
        metrics.record_batch_processed(num_documents=3, duration_seconds=1.5)

        metrics.record_aviso_created(has_link=True)

        # Verifica resumo
        summary = metrics.get_session_summary()

        assert summary["emails_scanned"] == 10
        assert summary["emails_skipped"] == 3
        assert summary["batches_created"] == 1
        assert summary["documents_extracted"] == 3
        assert summary["avisos_created"] == 1

    def test_concurrent_metrics_collection(self):
        """Testa coleta concorrente de métricas."""
        metrics = IngestionMetrics()

        def worker(worker_id):
            for _ in range(50):
                metrics.record_email_scanned()
                metrics.record_email_processed(has_attachment=True)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        summary = metrics.get_session_summary()
        assert summary["emails_scanned"] == 250
