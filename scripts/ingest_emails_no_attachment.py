"""
Script de Ingestão de E-mails Sem Anexo.

Este script conecta ao servidor de e-mail, busca e-mails que NÃO possuem
anexos PDF/XML válidos e cria registros de "aviso" com:
- Link de NF-e/download
- Código de verificação/autenticação
- Número da nota fiscal (extraído do link ou assunto)

Os avisos são exportados para CSV na coluna de observações.

Usage:
    python scripts/ingest_emails_no_attachment.py
    python scripts/ingest_emails_no_attachment.py --subject "Nota Fiscal"
    python scripts/ingest_emails_no_attachment.py --limit 50
    python scripts/ingest_emails_no_attachment.py --output avisos_nfe.csv
    python scripts/ingest_emails_no_attachment.py --keep-history  # Mantém versões com timestamp
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

# Adiciona o diretório raiz ao path para importar módulos do projeto
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from core.models import EmailAvisoData
from ingestors.imap import ImapIngestor
from services.ingestion_service import IngestionService

# Usa a configuração de logging do settings.py (importado acima)
# que configura RotatingFileHandler + console automaticamente
logger = logging.getLogger(__name__)


def export_avisos_to_csv(
    avisos: List[EmailAvisoData],
    output_path: Path
) -> None:
    """
    Exporta lista de avisos para CSV.

    Args:
        avisos: Lista de EmailAvisoData
        output_path: Caminho do arquivo CSV
    """
    if not avisos:
        logger.warning("Nenhum aviso para exportar.")
        return

    # Converte para dicionários
    records = [aviso.to_dict() for aviso in avisos]

    # Cria DataFrame
    df = pd.DataFrame(records)

    # Reordena colunas para melhor visualização
    colunas_prioritarias = [
        'tipo_documento',
        'arquivo_origem',
        'data_processamento',
        'fornecedor_nome',
        'numero_nota',
        'link_nfe',
        'codigo_verificacao',
        'dominio_portal',
        'email_subject',
        'observacoes',
    ]
    colunas_existentes = [c for c in colunas_prioritarias if c in df.columns]
    outras_colunas = [c for c in df.columns if c not in colunas_prioritarias]
    df = df[colunas_existentes + outras_colunas]

    # Exporta
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(
        output_path,
        index=False,
        sep=';',
        encoding='utf-8-sig',
        decimal=','
    )

    logger.info(f"✅ {len(avisos)} avisos exportados para: {output_path}")


def print_summary(avisos: List[EmailAvisoData]) -> None:
    """Imprime resumo dos avisos processados."""

    print("\n" + "=" * 70)
    print("📧 RESUMO - E-MAILS SEM ANEXO PROCESSADOS")
    print("=" * 70)

    print(f"\n📊 Total de avisos: {len(avisos)}")

    # Agrupa por domínio
    dominios = {}
    for aviso in avisos:
        dominio = aviso.dominio_portal or "desconhecido"
        dominios[dominio] = dominios.get(dominio, 0) + 1

    if dominios:
        print("\n🌐 Por portal/domínio:")
        for dominio, count in sorted(dominios.items(), key=lambda x: x[1], reverse=True):
            print(f"   {dominio}: {count}")

    # Estatísticas
    com_link = sum(1 for a in avisos if a.link_nfe)
    com_codigo = sum(1 for a in avisos if a.codigo_verificacao)
    com_numero_nf = sum(1 for a in avisos if a.numero_nota)

    print(f"\n📈 Estatísticas:")
    print(f"   Com link de NF-e: {com_link}")
    print(f"   Com código de verificação: {com_codigo}")
    print(f"   Com número de NF extraído: {com_numero_nf}")

    # Exemplos
    if avisos:
        print("\n📋 Exemplos de avisos:")
        print("-" * 60)
        for aviso in avisos[:5]:
            print(f"\n   📧 {aviso.email_subject_full[:60] if aviso.email_subject_full else 'Sem assunto'}...")
            print(f"      De: {aviso.fornecedor_nome or 'N/A'}")
            if aviso.link_nfe:
                link_display = aviso.link_nfe[:60] + "..." if len(aviso.link_nfe) > 60 else aviso.link_nfe
                print(f"      🔗 Link: {link_display}")
            if aviso.codigo_verificacao:
                print(f"      🔑 Código: {aviso.codigo_verificacao}")
            if aviso.numero_nota:
                print(f"      📄 NF: {aviso.numero_nota}")

    print("\n" + "=" * 70)


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description='Ingere e-mails sem anexo e extrai links/códigos de NF-e'
    )
    parser.add_argument(
        '--subject',
        type=str,
        default='ENC',
        help='Filtro de assunto (default: ENC)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Máximo de e-mails a processar (default: 100)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Arquivo CSV de saída (default: data/output/avisos_emails_sem_anexo_latest.csv)'
    )
    parser.add_argument(
        '--keep-history',
        action='store_true',
        default=False,
        help='Mantém versões anteriores com timestamp (default: só salva _latest)'
    )

    args = parser.parse_args()

    # Verifica configuração
    if not settings.EMAIL_PASS:
        logger.error("❌ Erro: Configure as credenciais de e-mail no arquivo .env")
        logger.error("   EMAIL_HOST, EMAIL_USER, EMAIL_PASS")
        return

    logger.info("📧 Iniciando ingestão de e-mails sem anexo...")
    logger.info(f"   Servidor: {settings.EMAIL_HOST}")
    logger.info(f"   Usuário: {settings.EMAIL_USER}")
    logger.info(f"   Filtro: '{args.subject}'")
    logger.info(f"   Limite: {args.limit}")

    # Cria ingestor e serviço
    try:
        ingestor = ImapIngestor(
            host=settings.EMAIL_HOST,
            user=settings.EMAIL_USER,
            password=settings.EMAIL_PASS,
            folder=settings.EMAIL_FOLDER
        )

        service = IngestionService(
            ingestor=ingestor,
            temp_dir=settings.DIR_TEMP
        )

        # Busca e processa e-mails sem anexo
        logger.info("\n🔍 Buscando e-mails sem anexo...")

        avisos = service.ingest_emails_without_attachments(
            subject_filter=args.subject,
            limit=args.limit
        )

        if not avisos:
            logger.warning("⚠️ Nenhum e-mail sem anexo com link/código encontrado.")
            return

        # Nota: A detecção de empresa agora é feita no IngestionService
        # usando o texto completo do e-mail (não truncado)

        logger.info(f"✅ {len(avisos)} e-mails processados com sucesso!")

        # Imprime resumo
        print_summary(avisos)

        # Define arquivo de saída
        latest_path = Path("data/output/avisos_emails_sem_anexo_latest.csv")

        if args.output:
            output_path = Path(args.output)
            export_avisos_to_csv(avisos, output_path)
            logger.info(f"\n💾 Arquivo salvo:")
            logger.info(f"   - {output_path}")
        elif args.keep_history:
            # Salva versão com timestamp + latest
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = Path(f"data/output/avisos_emails_sem_anexo_{timestamp}.csv")
            export_avisos_to_csv(avisos, output_path)
            export_avisos_to_csv(avisos, latest_path)
            logger.info(f"\n💾 Arquivos salvos:")
            logger.info(f"   - {output_path}")
            logger.info(f"   - {latest_path}")
        else:
            # Só salva latest (padrão)
            export_avisos_to_csv(avisos, latest_path)
            logger.info(f"\n💾 Arquivo salvo:")
            logger.info(f"   - {latest_path}")

    except Exception as e:
        logger.error(f"\n❌ Erro durante ingestão: {e}")
        raise


if __name__ == "__main__":
    main()
