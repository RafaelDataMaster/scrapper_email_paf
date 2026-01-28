"""
Script de Orquestração de Ingestão de E-mails.

Este módulo é responsável por conectar ao servidor de e-mail, baixar anexos PDF
de notas fiscais e encaminhá-los para o pipeline de processamento em lote.

REFATORADO para usar a nova estrutura de lotes (Batch Processing):
- Ingestão organiza anexos em pastas por e-mail (com metadata.json)
- Processamento por lote (pasta) ao invés de arquivo individual
- Correlação entre documentos do mesmo lote (DANFE + Boleto)
- Enriquecimento de dados via contexto do e-mail
- Limpeza automática de lotes antigos (opcional)
- Ingestão unificada de e-mails COM e SEM anexos
- Checkpointing para resume após interrupções

Princípios SOLID aplicados:
- SRP: Responsabilidades separadas em serviços específicos
- OCP: Extensível via registro de novos tipos de documento
- DIP: Injeção de dependências via factory

Usage:
    # Modo padrão (ingestão unificada COM e SEM anexos)
    python run_ingestion.py

    # Ingestão apenas de e-mails COM anexos (modo legado)
    python run_ingestion.py --only-attachments

    # Ingestão apenas de e-mails SEM anexos (links/códigos)
    python run_ingestion.py --only-links

    # Forçar nova ingestão (ignorar checkpoint)
    python run_ingestion.py --fresh

    # Reprocessar lotes existentes
    python run_ingestion.py --reprocess

    # Processar pasta específica
    python run_ingestion.py --batch-folder temp_email/email_123

    # Com limpeza automática de lotes antigos (>48h)
    python run_ingestion.py --cleanup

    # Filtro customizado + correlação desabilitada
    python run_ingestion.py --subject "Nota Fiscal" --no-correlation

    # Ver status do checkpoint atual
    python run_ingestion.py --status
"""

import argparse
import logging
from collections import defaultdict
from pathlib import Path
from typing import List, Optional, Tuple

from config import settings
from core.batch_processor import BatchProcessor, process_email_batch
from core.batch_result import BatchResult

from core.exporters import FileSystemManager
from core.interfaces import EmailIngestorStrategy

from core.models import EmailAvisoData
from ingestors.imap import ImapIngestor
from services.email_ingestion_orchestrator import (
    EmailIngestionOrchestrator,
    IngestionResult,
    IngestionStatus,
    create_orchestrator_from_config,
)
from services.ingestion_service import IngestionService

# Flag global para sinalizar interrupção
_interrupted = False
_current_orchestrator: Optional[EmailIngestionOrchestrator] = None

# Usa a configuração de logging do settings.py (já importado acima)
# que configura RotatingFileHandler + console automaticamente
logger = logging.getLogger(__name__)
logging.getLogger("extractors.carrier_telecom").setLevel(logging.DEBUG)


def create_ingestor_from_config() -> EmailIngestorStrategy:
    """
    Factory para criar ingestor a partir das configurações.

    Facilita injeção de dependências e testes mockados (DIP).

    Returns:
        EmailIngestorStrategy: Ingestor configurado

    Raises:
        ValueError: Se credenciais estiverem faltando
    """
    if not settings.EMAIL_PASS:
        raise ValueError("Por favor, configure o arquivo .env com suas credenciais.")

    return ImapIngestor(
        host=settings.EMAIL_HOST,
        user=settings.EMAIL_USER,
        password=settings.EMAIL_PASS,
        folder=settings.EMAIL_FOLDER,
    )


def export_batch_results(batches: List[BatchResult], output_dir: Path) -> None:
    """
    Exporta resultados dos lotes para CSVs.

    Gera os seguintes arquivos:
    - relatorio_boleto.csv: Apenas boletos
    - relatorio_nfse.csv: Apenas NFSe
    - relatorio_danfe.csv: Apenas DANFE
    - relatorio_outro.csv: Outros documentos
    - relatorio_consolidado.csv: TODOS os documentos juntos (tabela final)
    - relatorio_lotes.csv: Resumo por lote com status de conciliação
      (uma linha para cada par NF↔Boleto identificado)

    Todos os CSVs usam separador ';', encoding 'utf-8-sig' e decimal ','.

    Args:
        batches: Lista de resultados de lotes processados
        output_dir: Diretório de saída para os arquivos CSV
    """
    import pandas as pd

    # Agrupa documentos por tipo
    documentos_por_tipo = defaultdict(list)

    # Lista consolidada de TODOS os documentos
    todos_documentos = []

    # Lista de resumos por lote (agora pode ter múltiplos por batch)
    resumos_lotes = []

    for batch in batches:
        for doc in batch.documents:
            doc_type = doc.doc_type
            doc_dict = doc.to_dict()

            # Adiciona contexto do lote
            doc_dict["batch_id"] = batch.batch_id
            doc_dict["email_subject"] = batch.email_subject
            doc_dict["email_sender"] = batch.email_sender

            documentos_por_tipo[doc_type].append(doc_dict)
            todos_documentos.append(doc_dict)

        # Usa to_summaries() para gerar um resumo por par NF↔Boleto
        # Isso separa múltiplas notas do mesmo email em linhas distintas
        batch_summaries = batch.to_summaries()
        resumos_lotes.extend(batch_summaries)

        if len(batch_summaries) > 1:
            logger.debug(
                f"📊 Lote {batch.batch_id}: {len(batch_summaries)} pares NF↔Boleto identificados"
            )

    # Exporta cada tipo separadamente
    for doc_type, documentos in documentos_por_tipo.items():
        if not documentos:
            continue

        nome_arquivo = f"relatorio_{doc_type.lower()}.csv"
        output_path = output_dir / nome_arquivo

        df = pd.DataFrame(documentos)
        df.to_csv(output_path, index=False, sep=";", encoding="utf-8-sig", decimal=",")

        logger.info(f"✅ {len(documentos)} {doc_type} exportados -> {output_path}")

    # Exporta tabela consolidada (TODOS os documentos juntos)
    if todos_documentos:
        output_consolidado = output_dir / "relatorio_consolidado.csv"
        df_consolidado = pd.DataFrame(todos_documentos)

        # Reordena colunas para melhor visualização
        colunas_prioritarias = [
            "batch_id",
            "tipo_documento",
            "status_conciliacao",
            "valor_compra",
            "fornecedor_nome",
            "valor_documento",
            "valor_total",
            "vencimento",
            "data_emissao",
            "numero_nota",
            "numero_documento",
            "email_subject",
        ]
        colunas_existentes = [
            c for c in colunas_prioritarias if c in df_consolidado.columns
        ]
        outras_colunas = [
            c for c in df_consolidado.columns if c not in colunas_prioritarias
        ]
        df_consolidado = df_consolidado[colunas_existentes + outras_colunas]

        df_consolidado.to_csv(
            output_consolidado, index=False, sep=";", encoding="utf-8-sig", decimal=","
        )
        logger.info(
            f"✅ {len(todos_documentos)} documentos -> {output_consolidado.name} (CONSOLIDADO)"
        )

    # Exporta relatório de lotes (resumo por batch)
    if resumos_lotes:
        output_lotes = output_dir / "relatorio_lotes.csv"
        df_lotes = pd.DataFrame(resumos_lotes)

        # Reordena colunas do resumo
        colunas_lote = [
            "batch_id",
            "data",
            "status_conciliacao",
            "divergencia",
            "diferenca_valor",
            "fornecedor",
            "vencimento",
            "numero_nota",
            "valor_compra",
            "valor_boleto",
            "total_documents",
            "total_errors",
            "danfes",
            "boletos",
            "nfses",
            "outros",
            "email_subject",
            "email_sender",
            "empresa",
        ]
        colunas_existentes = [c for c in colunas_lote if c in df_lotes.columns]
        outras_colunas = [c for c in df_lotes.columns if c not in colunas_lote]
        df_lotes = df_lotes[colunas_existentes + outras_colunas]

        df_lotes.to_csv(
            output_lotes, index=False, sep=";", encoding="utf-8-sig", decimal=","
        )

        # Conta quantos batches originais e quantos pares gerados
        batches_originais = len(batches)
        pares_gerados = len(resumos_lotes)
        if pares_gerados > batches_originais:
            logger.info(
                f"✅ {pares_gerados} pares NF↔Boleto (de {batches_originais} emails) -> {output_lotes.name}"
            )
        else:
            logger.info(f"✅ {pares_gerados} lotes -> {output_lotes.name} (AUDITORIA)")


def export_avisos_to_csv(avisos: List[EmailAvisoData], output_dir: Path) -> None:
    """
    Exporta avisos de e-mails sem anexo para CSV.

    Gera dois arquivos:
    - avisos_emails_sem_anexo_latest.csv: Formato completo para integração Google Sheets
    - relatorio_avisos_links.csv: Formato resumido para leitura rápida

    Args:
        avisos: Lista de EmailAvisoData
        output_dir: Diretório de saída
    """
    import pandas as pd

    if not avisos:
        return

    # Formato completo usando to_dict() - compatível com export_to_sheets.py
    avisos_dicts_full = [aviso.to_dict() for aviso in avisos]

    # CSV principal para integração com Google Sheets
    output_path_sheets = output_dir / "avisos_emails_sem_anexo_latest.csv"
    df_full = pd.DataFrame(avisos_dicts_full)
    df_full.to_csv(output_path_sheets, index=False, sep=";", encoding="utf-8-sig")
    logger.info(
        f"✅ {len(avisos)} aviso(s) -> {output_path_sheets.name} (Google Sheets)"
    )

    # Formato resumido para leitura humana rápida
    avisos_dicts_simple = []
    for aviso in avisos:
        avisos_dicts_simple.append(
            {
                "email_id": aviso.email_id,
                "subject": aviso.subject,
                "sender_name": aviso.sender_name,
                "sender_address": aviso.sender_address,
                "received_date": aviso.received_date,
                "link_nfe": aviso.link_nfe,
                "codigo_verificacao": aviso.codigo_verificacao,
                "empresa": aviso.empresa,
                "status": "PENDENTE_DOWNLOAD",
            }
        )

    output_path_simple = output_dir / "relatorio_avisos_links.csv"
    df_simple = pd.DataFrame(avisos_dicts_simple)
    df_simple.to_csv(output_path_simple, index=False, sep=";", encoding="utf-8-sig")
    logger.info(f"✅ {len(avisos)} aviso(s) -> {output_path_simple.name} (relatório)")


def ingest_unified(
    subject_filter: str = "*",
    apply_correlation: bool = True,
    process_with_attachments: bool = True,
    process_without_attachments: bool = True,
    resume: bool = True,
    timeout_seconds: int = 300,
    max_emails: Optional[int] = None,
    links_first: bool = False,
) -> Tuple[IngestionResult, Optional[EmailIngestionOrchestrator]]:
    """
    Executa ingestão UNIFICADA de e-mails COM e SEM anexos.

    Esta é a nova função principal que usa o EmailIngestionOrchestrator
    para processar ambos os tipos de e-mail em uma única execução.

    Features:
    - Checkpointing automático para resume após interrupções
    - Tratamento graceful de Ctrl+C
    - Filtro inteligente para evitar falsos positivos
    - Processamento com timeout por lote

    Args:
        subject_filter: Filtro de assunto para busca
        apply_correlation: Se True, aplica correlação entre documentos
        process_with_attachments: Processar e-mails COM anexos
        process_without_attachments: Processar e-mails SEM anexos
        resume: Se True, resume de checkpoint existente
        timeout_seconds: Timeout por lote em segundos
        max_emails: Limite máximo de e-mails a processar (None = sem limite)
        links_first: Se True, processa e-mails SEM anexo ANTES dos COM anexo

    Returns:
        Tupla (IngestionResult, orchestrator) - orchestrator para acesso a dados parciais
    """
    global _current_orchestrator

    try:
        orchestrator = create_orchestrator_from_config(
            temp_dir=settings.DIR_TEMP,
            batch_timeout_seconds=timeout_seconds,
        )

        _current_orchestrator = orchestrator

        # Define callback de progresso
        def progress_callback(phase: str, current: int, total: int):
            percent = (current / total * 100) if total > 0 else 0
            logger.info(f"   {phase}: {current}/{total} ({percent:.0f}%)")

        orchestrator.set_progress_callback(progress_callback)

        # Executa ingestão
        result = orchestrator.run(
            subject_filter=subject_filter,
            process_with_attachments=process_with_attachments,
            process_without_attachments=process_without_attachments,
            apply_filter=True,
            apply_correlation=apply_correlation,
            resume=resume,
            limit_emails=max_emails,
            links_first=links_first,
        )

        return result, orchestrator

    except ValueError as e:
        logger.error(f"❌ Erro de configuração: {e}")
        return IngestionResult(status=IngestionStatus.FAILED), None

    except KeyboardInterrupt:
        logger.warning("\n⚠️ Ingestão interrompida pelo usuário")
        # Retorna orchestrator para permitir exportação de dados parciais
        return IngestionResult(
            status=IngestionStatus.INTERRUPTED
        ), _current_orchestrator


def show_ingestion_status() -> None:
    """Exibe status atual do checkpoint de ingestão."""
    try:
        orchestrator = create_orchestrator_from_config()
        status = orchestrator.get_status()

        logger.info("\n" + "=" * 60)
        logger.info("📊 STATUS DA INGESTÃO")
        logger.info("=" * 60)
        logger.info(f"   Status: {status['status']}")
        logger.info(f"   Iniciado em: {status['started_at'] or 'N/A'}")
        logger.info(f"   Última atualização: {status['last_updated'] or 'N/A'}")
        logger.info(f"   E-mails processados: {status['total_processed']}")
        logger.info(f"   Lotes criados: {status['batches_created']}")
        logger.info(f"   Avisos criados: {status['avisos_created']}")
        logger.info(f"   Erros: {status['total_errors']}")
        logger.info("=" * 60)
        logger.info("📦 DADOS PARCIAIS SALVOS:")
        logger.info(f"   Lotes salvos: {status.get('partial_batches_saved', 0)}")
        logger.info(f"   Avisos salvos: {status.get('partial_avisos_saved', 0)}")
        logger.info(
            f"   Trabalho pendente: {'Sim' if status['has_pending_work'] else 'Não'}"
        )
        logger.info("=" * 60)

        if status["has_pending_work"]:
            logger.info(
                "\n💡 Execute 'python run_ingestion.py' para continuar de onde parou"
            )
            logger.info("   ou 'python run_ingestion.py --fresh' para iniciar do zero")

        if (
            status.get("partial_batches_saved", 0) > 0
            or status.get("partial_avisos_saved", 0) > 0
        ):
            logger.info("\n📁 Para exportar dados parciais:")
            logger.info("   python run_ingestion.py --export-partial")

    except Exception as e:
        logger.error(f"❌ Erro ao obter status: {e}")


def export_partial_data() -> None:
    """Exporta dados parciais salvos de execuções anteriores."""
    try:
        orchestrator = create_orchestrator_from_config()
        batches, avisos = orchestrator.get_partial_results_count()

        if batches == 0 and avisos == 0:
            logger.info("ℹ️ Não há dados parciais para exportar.")
            return

        logger.info(f"📦 Exportando {batches} lotes e {avisos} avisos parciais...")
        exported_batches, exported_avisos = orchestrator.export_partial_results_to_csv(
            settings.DIR_SAIDA
        )

        logger.info("\n" + "=" * 60)
        logger.info("✅ EXPORTAÇÃO DE DADOS PARCIAIS CONCLUÍDA")
        logger.info("=" * 60)
        logger.info(f"   Lotes exportados: {exported_batches}")
        logger.info(f"   Avisos exportados: {exported_avisos}")
        logger.info(f"   Diretório: {settings.DIR_SAIDA}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Erro ao exportar dados parciais: {e}")


def ingest_and_process(
    ingestor: Optional[EmailIngestorStrategy] = None,
    subject_filter: str = "ENC",
    apply_correlation: bool = True,
) -> List[BatchResult]:
    """
    Executa ingestão de e-mails e processamento em lote.

    Fluxo completo:
    1. Conecta ao servidor de e-mail
    2. Baixa anexos e organiza em pastas de lote (temp_email/)
    3. Processa cada lote (extração de dados)
    4. Aplica correlação entre documentos (se habilitado)

    Args:
        ingestor: Ingestor de e-mail (opcional, usa factory se None)
        subject_filter: Filtro de assunto para busca (padrão: "ENC")
        apply_correlation: Se True, aplica correlação entre documentos

    Returns:
        Lista de BatchResult com documentos processados e correlacionados
    """
    # 1. Cria ingestor se não fornecido
    if ingestor is None:
        ingestor = create_ingestor_from_config()

    # 2. Prepara serviços
    ingestion_service = IngestionService(ingestor=ingestor, temp_dir=settings.DIR_TEMP)
    batch_processor = BatchProcessor()

    # 3. Prepara diretórios
    file_manager = FileSystemManager(
        temp_dir=settings.DIR_TEMP, output_dir=settings.DIR_SAIDA
    )
    file_manager.setup_directories()

    # 4. Ingestão: baixa e-mails e organiza em pastas
    logger.info(f"📧 Conectando a {settings.EMAIL_HOST}...")

    try:
        batch_folders = ingestion_service.ingest_emails(
            subject_filter=subject_filter, create_ignored_folder=True
        )
    except Exception as e:
        logger.error(f"❌ Erro na ingestão: {e}")
        return []

    if not batch_folders:
        logger.warning("⚠️ Nenhum anexo encontrado.")
        return []

    logger.info(f"📦 {len(batch_folders)} lote(s) criado(s)")

    # 5. Processamento: processa cada lote
    results: List[BatchResult] = []

    for folder in batch_folders:
        try:
            logger.info(f"🔄 Processando lote: {folder.name}")

            batch_result = batch_processor.process_batch(
                folder, apply_correlation=apply_correlation
            )

            if batch_result.total_documents > 0:
                results.append(batch_result)
                logger.info(
                    f"   ✓ {batch_result.total_documents} documento(s) | "
                    f"Valor: R$ {batch_result.get_valor_compra():,.2f}"
                )
            else:
                logger.warning("   ⚠️ Nenhum documento extraído")

        except Exception as e:
            logger.error(f"   ❌ Erro: {e}")

    return results


def reprocess_existing_batches(
    root_folder: Optional[Path] = None,
    apply_correlation: bool = True,
    timeout_seconds: int = 300,
) -> List[BatchResult]:
    """
    Reprocessa lotes existentes (pastas já criadas).

    Útil para re-executar extração após correções de bugs ou
    ajustes nos extractors sem precisar baixar e-mails novamente.

    Args:
        root_folder: Pasta raiz com lotes (default: settings.DIR_TEMP)
        apply_correlation: Se True, aplica correlação entre documentos
        timeout_seconds: Timeout por lote em segundos

    Returns:
        Lista de BatchResult com documentos reprocessados
    """
    root_folder = root_folder or settings.DIR_TEMP

    if not root_folder.exists():
        logger.warning(f"⚠️ Pasta não encontrada: {root_folder}")
        return []

    batch_processor = BatchProcessor()
    results = batch_processor.process_multiple_batches(
        root_folder,
        apply_correlation=apply_correlation,
        timeout_seconds=timeout_seconds,
    )

    # Contabiliza resultados
    ok_count = sum(1 for r in results if r.status == "OK")
    timeout_count = sum(1 for r in results if r.status == "TIMEOUT")
    error_count = sum(1 for r in results if r.status == "ERROR")

    logger.info(
        f"📦 {len(results)} lote(s) reprocessado(s): {ok_count} OK, {timeout_count} TIMEOUT, {error_count} ERRO"
    )

    return results


def reprocess_timeout_batches(
    root_folder: Optional[Path] = None,
    apply_correlation: bool = True,
    timeout_seconds: int = 600,  # Timeout maior para segunda tentativa
) -> List[BatchResult]:
    """
    Reprocessa apenas lotes que deram timeout anteriormente.

    Lê o arquivo _timeouts.json e tenta processar novamente apenas esses lotes,
    com timeout aumentado para 10 minutos.

    Args:
        root_folder: Pasta raiz com lotes (default: settings.DIR_TEMP)
        apply_correlation: Se True, aplica correlação entre documentos
        timeout_seconds: Timeout por lote (default: 600 = 10 min)

    Returns:
        Lista de BatchResult com documentos reprocessados
    """
    import json

    root_folder = root_folder or settings.DIR_TEMP
    timeout_log_path = root_folder / "_timeouts.json"

    if not timeout_log_path.exists():
        logger.info("✅ Nenhum timeout registrado para reprocessar.")
        return []

    # Carrega lista de timeouts
    try:
        timeouts = json.loads(timeout_log_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"❌ Erro ao ler {timeout_log_path}: {e}")
        return []

    if not timeouts:
        logger.info("✅ Lista de timeouts vazia.")
        return []

    # Extrai batch_ids únicos
    batch_ids = list(set(t["batch_id"] for t in timeouts))
    logger.info(f"🔄 Reprocessando {len(batch_ids)} lote(s) que deram timeout...")

    batch_processor = BatchProcessor()
    results = []

    for idx, batch_id in enumerate(batch_ids, 1):
        batch_folder = root_folder / batch_id

        if not batch_folder.exists():
            logger.warning(f"⚠️ Pasta não encontrada: {batch_folder}")
            continue

        logger.info(f"   [{idx}/{len(batch_ids)}] {batch_id}...")

        try:
            import time
            from concurrent.futures import ThreadPoolExecutor
            from concurrent.futures import TimeoutError as FuturesTimeoutError

            batch_start = time.time()

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    batch_processor.process_batch, batch_folder, apply_correlation
                )
                result = future.result(timeout=timeout_seconds)
                result.processing_time = time.time() - batch_start
                result.status = "OK"
                results.append(result)
                logger.info(f"   ✅ {batch_id}: OK ({result.processing_time:.1f}s)")

        except FuturesTimeoutError:
            logger.error(f"   ⏱️ {batch_id}: TIMEOUT novamente!")
            result = BatchResult(
                batch_id=batch_id,
                source_folder=str(batch_folder),
                status="TIMEOUT",
                processing_time=timeout_seconds,
                timeout_error=f"TIMEOUT na segunda tentativa ({timeout_seconds}s)",
            )
            results.append(result)

        except Exception as e:
            logger.error(f"   ❌ {batch_id}: ERRO - {e}")
            result = BatchResult(
                batch_id=batch_id,
                source_folder=str(batch_folder),
                status="ERROR",
                timeout_error=str(e),
            )
            results.append(result)

    # Remove timeouts que foram resolvidos
    resolved = [r.batch_id for r in results if r.status == "OK"]
    if resolved:
        remaining_timeouts = [t for t in timeouts if t["batch_id"] not in resolved]
        try:
            if remaining_timeouts:
                timeout_log_path.write_text(
                    json.dumps(remaining_timeouts, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            else:
                timeout_log_path.unlink()  # Remove arquivo se não há mais timeouts
            logger.info(f"📝 {len(resolved)} timeout(s) resolvido(s)")
        except Exception as e:
            logger.warning(f"Erro ao atualizar log de timeouts: {e}")

    return results


def process_single_batch(
    folder_path: Path, apply_correlation: bool = True
) -> Optional[BatchResult]:
    """
    Processa um único lote específico.

    Útil para debugging ou reprocessamento seletivo de um único e-mail.

    Args:
        folder_path: Caminho da pasta do lote (ex: temp_email/email_123)
        apply_correlation: Se True, aplica correlação entre documentos

    Returns:
        BatchResult com documentos processados ou None se pasta não existe
    """
    if not folder_path.exists():
        logger.error(f"❌ Pasta não encontrada: {folder_path}")
        return None

    batch_result = process_email_batch(folder_path, apply_correlation)

    if batch_result.total_documents > 0:
        logger.info(
            f"✅ {batch_result.total_documents} documento(s) | "
            f"Valor: R$ {batch_result.get_valor_compra():,.2f}"
        )
    else:
        logger.warning("⚠️ Nenhum documento extraído")

    return batch_result


def main(ingestor: Optional[EmailIngestorStrategy] = None):
    """
    Função principal de orquestração da ingestão.

    Args:
        ingestor: Ingestor de e-mail customizado. Se None, usa factory padrão.
                  Permite injeção de dependência para testes (DIP).
    """
    # Parse argumentos
    parser = argparse.ArgumentParser(
        description="Ingestão e processamento de e-mails com notas fiscais",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Ingestão unificada de TODOS os e-mails (COM e SEM anexos)
  python run_ingestion.py

  # Filtrar apenas e-mails com "ENC" no assunto
  python run_ingestion.py --subject "ENC"

  # Apenas e-mails COM anexos (modo legado)
  python run_ingestion.py --only-attachments

  # Apenas e-mails SEM anexos (links/códigos)
  python run_ingestion.py --only-links

  # Forçar nova ingestão (ignorar checkpoint)
  python run_ingestion.py --fresh

  # Ver status do checkpoint
  python run_ingestion.py --status

  # Reprocessar lotes existentes (com timeout de 5 min)
  python run_ingestion.py --reprocess

  # Reprocessar com timeout customizado (10 min)
  python run_ingestion.py --reprocess --timeout 600

  # Reprocessar apenas lotes que deram timeout
  python run_ingestion.py --reprocess-timeouts

  # Processar pasta específica
  python run_ingestion.py --batch-folder temp_email/email_123

  # Sem correlação entre documentos
  python run_ingestion.py --no-correlation

  # Filtro de assunto customizado
  python run_ingestion.py --subject "Nota Fiscal"

  # Com limpeza automática de lotes antigos (>48h)
  python run_ingestion.py --cleanup

  # Reprocessar e limpar em seguida
  python run_ingestion.py --reprocess --cleanup
        """,
    )

    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Reprocessar lotes existentes em temp_email",
    )
    parser.add_argument(
        "--batch-folder", type=str, help="Processar pasta de lote específica"
    )
    parser.add_argument(
        "--subject",
        type=str,
        default="*",
        help="Filtro de assunto para busca (default: * = TODOS)",
    )
    parser.add_argument(
        "--no-correlation",
        action="store_true",
        help="Desabilitar correlação entre documentos",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Limpar lotes antigos (> 48h) após processamento",
    )
    parser.add_argument(
        "--reprocess-timeouts",
        action="store_true",
        help="Reprocessar apenas lotes que deram timeout anteriormente",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout por lote em segundos (default: 300 = 5 min)",
    )
    parser.add_argument(
        "--only-attachments",
        action="store_true",
        help="Processar apenas e-mails COM anexos (modo legado)",
    )
    parser.add_argument(
        "--only-links",
        action="store_true",
        help="Processar apenas e-mails SEM anexos (links/códigos)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Forçar nova ingestão (ignorar checkpoint existente)",
    )
    parser.add_argument(
        "--status", action="store_true", help="Exibir status do checkpoint de ingestão"
    )
    parser.add_argument(
        "--export-partial",
        action="store_true",
        help="Exportar dados parciais de execuções anteriores",
    )
    parser.add_argument(
        "--max-emails",
        type=int,
        default=None,
        help="Limite máximo de e-mails a processar por execução (default: sem limite)",
    )
    parser.add_argument(
        "--links-first",
        action="store_true",
        help="Processar e-mails SEM anexo (links/códigos) ANTES dos COM anexo",
    )
    parser.add_argument(
        "--export-metrics",
        action="store_true",
        help="Exportar métricas de telemetria para arquivo JSON",
    )

    args = parser.parse_args()

    apply_correlation = not args.no_correlation

    # 0. Modo status: apenas exibe status e sai
    if args.status:
        show_ingestion_status()
        return

    # 0.1 Modo export-partial: exporta dados parciais e sai
    if args.export_partial:
        export_partial_data()
        return

    # 1. Verificação de configuração
    try:
        if (
            ingestor is None
            and not args.reprocess
            and not args.batch_folder
            and not args.reprocess_timeouts
        ):
            ingestor = create_ingestor_from_config()
    except ValueError as e:
        logger.error(f"❌ Erro de configuração: {e}")
        return

    # 2. Executa modo apropriado
    results: List[BatchResult] = []
    avisos: List[EmailAvisoData] = []
    ingestion_result: Optional[IngestionResult] = None
    orchestrator: Optional[EmailIngestionOrchestrator] = None

    if args.reprocess_timeouts:
        # Modo: Reprocessar apenas timeouts
        logger.info("🔄 Reprocessando lotes que deram timeout...")
        results = reprocess_timeout_batches(
            settings.DIR_TEMP,
            apply_correlation,
            timeout_seconds=args.timeout * 2,  # Dobra o timeout para segunda tentativa
        )

    elif args.batch_folder:
        # Modo: Processar pasta específica
        logger.info(f"🔄 Processando lote: {args.batch_folder}")
        result = process_single_batch(Path(args.batch_folder), apply_correlation)
        if result:
            results.append(result)

    elif args.reprocess:
        # Modo: Reprocessar lotes existentes
        logger.info("🔄 Reprocessando lotes existentes...")
        results = reprocess_existing_batches(
            settings.DIR_TEMP, apply_correlation, timeout_seconds=args.timeout
        )

    elif args.only_attachments:
        # Modo: Apenas e-mails COM anexos (legado)
        filter_msg = "TODOS" if args.subject == "*" else f"'{args.subject}'"
        logger.info(
            f"📧 Iniciando ingestão apenas COM anexos (filtro: {filter_msg})..."
        )
        results = ingest_and_process(
            ingestor=ingestor,
            subject_filter=args.subject,
            apply_correlation=apply_correlation,
        )

    else:
        # Modo: Ingestão UNIFICADA (COM e SEM anexos)
        filter_msg = (
            "TODOS os e-mails" if args.subject == "*" else f"filtro: '{args.subject}'"
        )
        logger.info(f"📧 Iniciando ingestão UNIFICADA ({filter_msg})...")

        # Determina o que processar
        process_attachments = not args.only_links
        process_links = not args.only_attachments

        ingestion_result, orchestrator = ingest_unified(
            subject_filter=args.subject,
            apply_correlation=apply_correlation,
            process_with_attachments=process_attachments,
            process_without_attachments=process_links,
            resume=not args.fresh,
            timeout_seconds=args.timeout,
            max_emails=args.max_emails,
            links_first=args.links_first,
        )

        # Extrai resultados
        results = ingestion_result.batch_results
        avisos = ingestion_result.avisos

        # Log do resumo da ingestão unificada
        logger.info(f"\n📊 {ingestion_result.summary()}")

        # Se foi interrompido, exporta dados parciais automaticamente
        if ingestion_result.status == IngestionStatus.INTERRUPTED and orchestrator:
            logger.info("\n💾 Exportando dados parciais salvos...")
            orchestrator.export_partial_results_to_csv(settings.DIR_SAIDA)

    # 3. Exportação de resultados
    if results or avisos:
        logger.info("\n📊 Exportando resultados...")

        if results:
            export_batch_results(results, settings.DIR_SAIDA)

        if avisos:
            export_avisos_to_csv(avisos, settings.DIR_SAIDA)

        # Resumo final
        total_docs = sum(r.total_documents for r in results)
        total_erros = sum(r.total_errors for r in results)
        valor_total = sum(r.get_valor_compra() for r in results)

        # Contagem de status
        ok_count = sum(1 for r in results if r.status == "OK")
        timeout_count = sum(1 for r in results if r.status == "TIMEOUT")
        error_count = sum(1 for r in results if r.status == "ERROR")

        logger.info("\n" + "=" * 60)
        logger.info("📊 RESUMO FINAL")
        logger.info("=" * 60)
        logger.info(f"   Lotes processados: {len(results)}")
        logger.info(f"      ✅ OK: {ok_count}")
        if timeout_count > 0:
            logger.info(f"      ⏱️ TIMEOUT: {timeout_count}")
        if error_count > 0:
            logger.info(f"      ❌ ERRO: {error_count}")
        logger.info(f"   Total de documentos: {total_docs}")
        logger.info(f"   Total de erros: {total_erros}")
        logger.info(f"   Valor total: R$ {valor_total:,.2f}")
        logger.info("=" * 60)

        # Exibe avisos de links/códigos se houver
        if avisos:
            logger.info("\n📋 AVISOS (e-mails sem anexo com links/códigos):")
            logger.info(f"   Total de avisos: {len(avisos)}")
            for aviso in avisos[:5]:  # Mostra apenas os 5 primeiros
                logger.info(
                    f"      • {aviso.subject[:50]}... -> {aviso.link_nfe or aviso.codigo_verificacao}"
                )
            if len(avisos) > 5:
                logger.info(f"      ... e mais {len(avisos) - 5} aviso(s)")

        # Aviso se teve timeouts
        if timeout_count > 0:
            logger.warning(f"\n⚠️  {timeout_count} lote(s) deram timeout!")
            logger.warning(
                "   Execute 'python run_ingestion.py --reprocess-timeouts' para tentar novamente"
            )

        # Aviso sobre checkpoint se foi interrompido
        if ingestion_result and ingestion_result.status == IngestionStatus.INTERRUPTED:
            logger.warning("\n⚠️ Ingestão foi interrompida!")
            logger.warning("   ✅ Dados parciais foram salvos automaticamente")
            logger.warning(
                "   Execute 'python run_ingestion.py' para continuar de onde parou"
            )
            logger.warning(
                "   ou 'python run_ingestion.py --fresh' para iniciar do zero"
            )
            logger.warning(
                "   Para exportar apenas os parciais: 'python run_ingestion.py --export-partial'"
            )

    else:
        logger.warning("⚠️ Nenhum resultado para exportar.")

    # 4. Exportação de métricas (opcional)
    if args.export_metrics and orchestrator:
        logger.info("\n📊 Exportando métricas de telemetria...")
        metrics_path = orchestrator.export_metrics(settings.DIR_SAIDA)
        if metrics_path:
            logger.info(f"   Métricas salvas em: {metrics_path}")

    # Sempre mostra resumo de métricas se houver orchestrator
    if orchestrator:
        orchestrator.log_metrics_summary()

    # 5. Limpeza opcional
    if args.cleanup:
        logger.info("\n🧹 Limpando lotes antigos...")
        ingestion_service = IngestionService(
            ingestor=ingestor or create_ingestor_from_config(),
            temp_dir=settings.DIR_TEMP,
        )
        removed = ingestion_service.cleanup_old_batches(max_age_hours=48)
        logger.info(f"   {removed} pasta(s) removida(s)")


if __name__ == "__main__":
    main()
