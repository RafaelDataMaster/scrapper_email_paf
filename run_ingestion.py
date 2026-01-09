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

Princípios SOLID aplicados:
- SRP: Responsabilidades separadas em serviços específicos
- OCP: Extensível via registro de novos tipos de documento
- DIP: Injeção de dependências via factory

Usage:
    # Modo padrão (ingestão de e-mails)
    python run_ingestion.py

    # Reprocessar lotes existentes
    python run_ingestion.py --reprocess

    # Processar pasta específica
    python run_ingestion.py --batch-folder temp_email/email_123

    # Com limpeza automática de lotes antigos (>48h)
    python run_ingestion.py --cleanup

    # Filtro customizado + correlação desabilitada
    python run_ingestion.py --subject "Nota Fiscal" --no-correlation
"""

import argparse
import logging
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

from config import settings
from core.batch_processor import BatchProcessor, process_email_batch
from core.batch_result import BatchResult
from core.correlation_service import CorrelationService
from core.exporters import CsvExporter, FileSystemManager
from core.interfaces import EmailIngestorStrategy
from core.metadata import EmailMetadata
from ingestors.imap import ImapIngestor
from services.ingestion_service import IngestionService

# Configurar logging estruturado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


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
        folder=settings.EMAIL_FOLDER
    )


def export_batch_results(
    batches: List[BatchResult],
    output_dir: Path
) -> None:
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
            doc_dict['batch_id'] = batch.batch_id
            doc_dict['email_subject'] = batch.email_subject
            doc_dict['email_sender'] = batch.email_sender

            documentos_por_tipo[doc_type].append(doc_dict)
            todos_documentos.append(doc_dict)

        # Usa to_summaries() para gerar um resumo por par NF↔Boleto
        # Isso separa múltiplas notas do mesmo email em linhas distintas
        batch_summaries = batch.to_summaries()
        resumos_lotes.extend(batch_summaries)

        if len(batch_summaries) > 1:
            logger.debug(f"📊 Lote {batch.batch_id}: {len(batch_summaries)} pares NF↔Boleto identificados")

    # Exporta cada tipo separadamente
    for doc_type, documentos in documentos_por_tipo.items():
        if not documentos:
            continue

        nome_arquivo = f"relatorio_{doc_type.lower()}.csv"
        output_path = output_dir / nome_arquivo

        df = pd.DataFrame(documentos)
        df.to_csv(output_path, index=False, sep=';', encoding='utf-8-sig', decimal=',')

        logger.info(f"✅ {len(documentos)} {doc_type} exportados -> {output_path}")

    # Exporta tabela consolidada (TODOS os documentos juntos)
    if todos_documentos:
        output_consolidado = output_dir / "relatorio_consolidado.csv"
        df_consolidado = pd.DataFrame(todos_documentos)

        # Reordena colunas para melhor visualização
        colunas_prioritarias = [
            'batch_id', 'tipo_documento', 'status_conciliacao', 'valor_compra',
            'fornecedor_nome', 'valor_documento', 'valor_total', 'vencimento',
            'data_emissao', 'numero_nota', 'numero_documento', 'email_subject'
        ]
        colunas_existentes = [c for c in colunas_prioritarias if c in df_consolidado.columns]
        outras_colunas = [c for c in df_consolidado.columns if c not in colunas_prioritarias]
        df_consolidado = df_consolidado[colunas_existentes + outras_colunas]

        df_consolidado.to_csv(
            output_consolidado, index=False, sep=';', encoding='utf-8-sig', decimal=','
        )
        logger.info(f"✅ {len(todos_documentos)} documentos -> {output_consolidado.name} (CONSOLIDADO)")

    # Exporta relatório de lotes (resumo por batch)
    if resumos_lotes:
        output_lotes = output_dir / "relatorio_lotes.csv"
        df_lotes = pd.DataFrame(resumos_lotes)

        # Reordena colunas do resumo
        colunas_lote = [
            'batch_id', 'status_conciliacao', 'divergencia', 'diferenca_valor',
            'fornecedor', 'vencimento', 'numero_nota', 'valor_compra', 'valor_boleto',
            'total_documents', 'total_errors',
            'danfes', 'boletos', 'nfses', 'outros',
            'email_subject', 'email_sender', 'empresa'
        ]
        colunas_existentes = [c for c in colunas_lote if c in df_lotes.columns]
        outras_colunas = [c for c in df_lotes.columns if c not in colunas_lote]
        df_lotes = df_lotes[colunas_existentes + outras_colunas]

        df_lotes.to_csv(
            output_lotes, index=False, sep=';', encoding='utf-8-sig', decimal=','
        )

        # Conta quantos batches originais e quantos pares gerados
        batches_originais = len(batches)
        pares_gerados = len(resumos_lotes)
        if pares_gerados > batches_originais:
            logger.info(f"✅ {pares_gerados} pares NF↔Boleto (de {batches_originais} emails) -> {output_lotes.name}")
        else:
            logger.info(f"✅ {pares_gerados} lotes -> {output_lotes.name} (AUDITORIA)")


def ingest_and_process(
    ingestor: Optional[EmailIngestorStrategy] = None,
    subject_filter: str = "ENC",
    apply_correlation: bool = True
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
    ingestion_service = IngestionService(
        ingestor=ingestor,
        temp_dir=settings.DIR_TEMP
    )
    batch_processor = BatchProcessor()

    # 3. Prepara diretórios
    file_manager = FileSystemManager(
        temp_dir=settings.DIR_TEMP,
        output_dir=settings.DIR_SAIDA
    )
    file_manager.setup_directories()

    # 4. Ingestão: baixa e-mails e organiza em pastas
    logger.info(f"📧 Conectando a {settings.EMAIL_HOST}...")

    try:
        batch_folders = ingestion_service.ingest_emails(
            subject_filter=subject_filter,
            create_ignored_folder=True
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
                folder,
                apply_correlation=apply_correlation
            )

            if batch_result.total_documents > 0:
                results.append(batch_result)
                logger.info(
                    f"   ✓ {batch_result.total_documents} documento(s) | "
                    f"Valor: R$ {batch_result.get_valor_compra():,.2f}"
                )
            else:
                logger.warning(f"   ⚠️ Nenhum documento extraído")

        except Exception as e:
            logger.error(f"   ❌ Erro: {e}")

    return results


def reprocess_existing_batches(
    root_folder: Optional[Path] = None,
    apply_correlation: bool = True,
    timeout_seconds: int = 300
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
        timeout_seconds=timeout_seconds
    )

    # Contabiliza resultados
    ok_count = sum(1 for r in results if r.status == "OK")
    timeout_count = sum(1 for r in results if r.status == "TIMEOUT")
    error_count = sum(1 for r in results if r.status == "ERROR")
    
    logger.info(f"📦 {len(results)} lote(s) reprocessado(s): {ok_count} OK, {timeout_count} TIMEOUT, {error_count} ERRO")

    return results


def reprocess_timeout_batches(
    root_folder: Optional[Path] = None,
    apply_correlation: bool = True,
    timeout_seconds: int = 600  # Timeout maior para segunda tentativa
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
        timeouts = json.loads(timeout_log_path.read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"❌ Erro ao ler {timeout_log_path}: {e}")
        return []

    if not timeouts:
        logger.info("✅ Lista de timeouts vazia.")
        return []

    # Extrai batch_ids únicos
    batch_ids = list(set(t['batch_id'] for t in timeouts))
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
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
            import time
            
            batch_start = time.time()
            
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(batch_processor.process_batch, batch_folder, apply_correlation)
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
                timeout_error=f"TIMEOUT na segunda tentativa ({timeout_seconds}s)"
            )
            results.append(result)
            
        except Exception as e:
            logger.error(f"   ❌ {batch_id}: ERRO - {e}")
            result = BatchResult(
                batch_id=batch_id,
                source_folder=str(batch_folder),
                status="ERROR",
                timeout_error=str(e)
            )
            results.append(result)

    # Remove timeouts que foram resolvidos
    resolved = [r.batch_id for r in results if r.status == "OK"]
    if resolved:
        remaining_timeouts = [t for t in timeouts if t['batch_id'] not in resolved]
        try:
            if remaining_timeouts:
                timeout_log_path.write_text(
                    json.dumps(remaining_timeouts, indent=2, ensure_ascii=False),
                    encoding='utf-8'
                )
            else:
                timeout_log_path.unlink()  # Remove arquivo se não há mais timeouts
            logger.info(f"📝 {len(resolved)} timeout(s) resolvido(s)")
        except Exception as e:
            logger.warning(f"Erro ao atualizar log de timeouts: {e}")

    return results


def process_single_batch(
    folder_path: Path,
    apply_correlation: bool = True
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
        description='Ingestão e processamento de e-mails com notas fiscais',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Ingestão padrão
  python run_ingestion.py

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
        """
    )

    parser.add_argument(
        '--reprocess',
        action='store_true',
        help='Reprocessar lotes existentes em temp_email'
    )
    parser.add_argument(
        '--batch-folder',
        type=str,
        help='Processar pasta de lote específica'
    )
    parser.add_argument(
        '--subject',
        type=str,
        default='ENC',
        help='Filtro de assunto para busca (default: ENC)'
    )
    parser.add_argument(
        '--no-correlation',
        action='store_true',
        help='Desabilitar correlação entre documentos'
    )
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='Limpar lotes antigos (> 48h) após processamento'
    )
    parser.add_argument(
        '--reprocess-timeouts',
        action='store_true',
        help='Reprocessar apenas lotes que deram timeout anteriormente'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Timeout por lote em segundos (default: 300 = 5 min)'
    )

    args = parser.parse_args()

    apply_correlation = not args.no_correlation

    # 1. Verificação de configuração
    try:
        if ingestor is None and not args.reprocess and not args.batch_folder and not args.reprocess_timeouts:
            ingestor = create_ingestor_from_config()
    except ValueError as e:
        logger.error(f"❌ Erro de configuração: {e}")
        return

    # 2. Executa modo apropriado
    results: List[BatchResult] = []

    if args.reprocess_timeouts:
        # Modo: Reprocessar apenas timeouts
        logger.info("🔄 Reprocessando lotes que deram timeout...")
        results = reprocess_timeout_batches(
            settings.DIR_TEMP,
            apply_correlation,
            timeout_seconds=args.timeout * 2  # Dobra o timeout para segunda tentativa
        )

    elif args.batch_folder:
        # Modo: Processar pasta específica
        logger.info(f"🔄 Processando lote: {args.batch_folder}")
        result = process_single_batch(
            Path(args.batch_folder),
            apply_correlation
        )
        if result:
            results.append(result)

    elif args.reprocess:
        # Modo: Reprocessar lotes existentes
        logger.info("🔄 Reprocessando lotes existentes...")
        results = reprocess_existing_batches(
            settings.DIR_TEMP,
            apply_correlation,
            timeout_seconds=args.timeout
        )

    else:
        # Modo: Ingestão padrão
        logger.info(f"📧 Iniciando ingestão (filtro: '{args.subject}')...")
        results = ingest_and_process(
            ingestor=ingestor,
            subject_filter=args.subject,
            apply_correlation=apply_correlation
        )

    # 3. Exportação de resultados
    if results:
        logger.info("\n📊 Exportando resultados...")
        export_batch_results(results, settings.DIR_SAIDA)

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
        
        # Aviso se teve timeouts
        if timeout_count > 0:
            logger.warning(f"\n⚠️  {timeout_count} lote(s) deram timeout!")
            logger.warning("   Execute 'python run_ingestion.py --reprocess-timeouts' para tentar novamente")
    else:
        logger.warning("⚠️ Nenhum resultado para exportar.")

    # 4. Limpeza opcional
    if args.cleanup:
        logger.info("\n🧹 Limpando lotes antigos...")
        ingestion_service = IngestionService(
            ingestor=ingestor or create_ingestor_from_config(),
            temp_dir=settings.DIR_TEMP
        )
        removed = ingestion_service.cleanup_old_batches(max_age_hours=48)
        logger.info(f"   {removed} pasta(s) removida(s)")


if __name__ == "__main__":
    main()
