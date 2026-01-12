#!/usr/bin/env python3
"""
Script de Exportação para Google Sheets.

Este módulo exporta os documentos processados para uma planilha do Google Sheets,
separando em duas abas:
- 'anexos': Documentos com anexos (lotes do relatorio_lotes.csv)
- 'sem_anexos': E-mails sem anexo com links (EmailAvisoData)

Fontes de Dados:
- PADRÃO: relatorio_lotes.csv (resumo por e-mail - mais simples)
- OPCIONAL: relatorio_consolidado.csv (detalhado por documento)

Uso:
    # Exportar usando relatorio_lotes.csv (PADRÃO - recomendado)
    python scripts/export_to_sheets.py

    # Modo dry-run (não envia para Sheets, apenas mostra o que seria enviado)
    python scripts/export_to_sheets.py --dry-run

    # Usar relatorio_consolidado.csv (modo detalhado)
    python scripts/export_to_sheets.py --use-consolidado

    # Especificar CSVs customizados
    python scripts/export_to_sheets.py --csv-lotes path/to/lotes.csv
    python scripts/export_to_sheets.py --csv-avisos path/to/avisos.csv

    # Especificar spreadsheet ID
    python scripts/export_to_sheets.py --spreadsheet-id "1ABC..."

Variáveis de Ambiente:
    GOOGLE_SPREADSHEET_ID: ID da planilha do Google Sheets
    GOOGLE_CREDENTIALS_PATH: Caminho para credentials.json (default: credentials.json)

Conformidade:
    - Política Interna 5.9
    - POP 4.10 (Master Internet)
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Tuple

import pandas as pd

# Adiciona diretório raiz ao path para imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

# Carrega variáveis de ambiente antes de importar settings
load_dotenv()

from core.models import (
    BoletoData,
    DanfeData,
    DocumentData,
    EmailAvisoData,
    InvoiceData,
    OtherDocumentData,
)

# Importa configurações centralizadas
try:
    from config.settings import (
        GOOGLE_CREDENTIALS_PATH as DEFAULT_CREDENTIALS_PATH,
    )
    from config.settings import (
        GOOGLE_SPREADSHEET_ID as DEFAULT_SPREADSHEET_ID,
    )
except ImportError:
    DEFAULT_SPREADSHEET_ID = os.getenv('GOOGLE_SPREADSHEET_ID', '')
    DEFAULT_CREDENTIALS_PATH = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Constantes
ANEXOS_SHEET_NAME = "anexos"
SEM_ANEXOS_SHEET_NAME = "sem_anexos"

# Headers das abas
ANEXOS_HEADERS = [
    "DATA",
    "ASSUNTO",
    "N_PEDIDO",
    "EMPRESA",
    "VENCIMENTO",
    "FORNECEDOR",
    "NF",
    "VALOR",
    "SITUACAO",
    "AVISOS",
]

SEM_ANEXOS_HEADERS = [
    "DATA",
    "ASSUNTO",
    "N_PEDIDO",
    "EMPRESA",
    "FORNECEDOR",
    "NF",
    "LINK",
    "CÓDIGO",
]


class GoogleSheetsExporterDualTab:
    """
    Exportador para Google Sheets com suporte a duas abas.

    Separa documentos em:
    - Grupo A (anexos): InvoiceData, DanfeData, BoletoData, OtherDocumentData
    - Grupo B (sem_anexos): EmailAvisoData
    """

    def __init__(
        self,
        credentials_path: str = None,
        spreadsheet_id: str = None,
        dry_run: bool = False
    ):
        """
        Inicializa o exportador.

        Args:
            credentials_path: Caminho para o arquivo de credenciais JSON
            spreadsheet_id: ID da planilha do Google Sheets
            dry_run: Se True, apenas simula a exportação sem enviar dados
        """
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self.spreadsheet_id = spreadsheet_id or DEFAULT_SPREADSHEET_ID
        self.dry_run = dry_run
        self._client = None
        self._spreadsheet = None

        if not self.spreadsheet_id and not dry_run:
            raise ValueError(
                "GOOGLE_SPREADSHEET_ID não configurado. "
                "Configure via variável de ambiente ou parâmetro --spreadsheet-id"
            )

    def _authenticate(self):
        """Autentica com Google Sheets API usando Service Account."""
        if self._client is not None:
            return

        try:
            import gspread
            from gspread.exceptions import APIError
        except ImportError:
            raise ImportError(
                "gspread não está instalado. "
                "Execute: pip install gspread"
            )

        if not Path(self.credentials_path).exists():
            raise FileNotFoundError(
                f"Arquivo de credenciais não encontrado: {self.credentials_path}"
            )

        try:
            self._client = gspread.service_account(filename=self.credentials_path)
            self._spreadsheet = self._client.open_by_key(self.spreadsheet_id)
            logger.info(f"✅ Autenticado com sucesso no Google Sheets")
        except Exception as e:
            logger.error(f"❌ Erro na autenticação Google Sheets: {e}")
            raise

    def _get_or_create_worksheet(self, sheet_name: str, headers: List[str]):
        """
        Obtém ou cria uma worksheet com os headers especificados.

        Args:
            sheet_name: Nome da aba
            headers: Lista de nomes das colunas

        Returns:
            gspread.Worksheet
        """
        if self.dry_run:
            return None

        self._authenticate()

        try:
            worksheet = self._spreadsheet.worksheet(sheet_name)
            logger.info(f"📄 Aba '{sheet_name}' encontrada")
        except Exception:
            # Aba não existe, criar
            worksheet = self._spreadsheet.add_worksheet(
                title=sheet_name,
                rows=1000,
                cols=len(headers)
            )
            # Adiciona headers
            worksheet.append_row(headers, value_input_option='USER_ENTERED')
            logger.info(f"📄 Aba '{sheet_name}' criada com headers")

        return worksheet

    def _append_rows_with_retry(self, worksheet, rows: List[List], max_retries: int = 5):
        """
        Adiciona linhas à planilha com retry automático.

        Args:
            worksheet: Worksheet do gspread
            rows: Lista de listas (cada sublista é uma linha)
            max_retries: Número máximo de tentativas
        """
        if self.dry_run or not rows:
            return

        import time

        for attempt in range(max_retries):
            try:
                worksheet.append_rows(rows, value_input_option='USER_ENTERED')
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"⚠️ Tentativa {attempt + 1}/{max_retries} falhou. "
                        f"Aguardando {wait_time}s... Erro: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ Todas as tentativas falharam: {e}")
                    raise

    def separate_documents(
        self,
        documents: List[DocumentData]
    ) -> Tuple[List[DocumentData], List[DocumentData]]:
        """
        Separa documentos em dois grupos.

        Grupo A (anexos): InvoiceData, DanfeData, BoletoData, OtherDocumentData
        Grupo B (sem_anexos): EmailAvisoData

        Args:
            documents: Lista de documentos a separar

        Returns:
            Tupla com (documentos_anexos, documentos_sem_anexos)
        """
        anexos = []
        sem_anexos = []

        for doc in documents:
            if isinstance(doc, EmailAvisoData):
                sem_anexos.append(doc)
            elif isinstance(doc, (InvoiceData, DanfeData, BoletoData, OtherDocumentData)):
                anexos.append(doc)
            else:
                logger.warning(f"⚠️ Tipo de documento desconhecido: {type(doc).__name__}")

        return anexos, sem_anexos

    def export(
        self,
        documents: List[DocumentData],
        batch_size: int = 100,
        source_email_subject_map: dict = None
    ) -> Tuple[int, int]:
        """
        Exporta documentos para Google Sheets em duas abas.

        Args:
            documents: Lista de documentos a exportar
            batch_size: Quantidade de linhas por batch (default: 100)
            source_email_subject_map: Mapa de batch_id -> email_subject para injetar

        Returns:
            Tupla com (qtd_anexos, qtd_sem_anexos) exportados
        """
        if not documents:
            logger.warning("⚠️ Nenhum documento para exportar")
            return 0, 0

        # Injeta source_email_subject se mapa fornecido
        if source_email_subject_map:
            for doc in documents:
                if doc.batch_id and doc.batch_id in source_email_subject_map:
                    doc.source_email_subject = source_email_subject_map[doc.batch_id]

        # Separa documentos
        anexos, sem_anexos = self.separate_documents(documents)

        logger.info(f"📊 Documentos separados: {len(anexos)} anexos, {len(sem_anexos)} sem_anexos")

        # Exporta para aba 'anexos'
        if anexos:
            self._export_anexos(anexos, batch_size)

        # Exporta para aba 'sem_anexos'
        if sem_anexos:
            self._export_sem_anexos(sem_anexos, batch_size)

        return len(anexos), len(sem_anexos)

    def _export_anexos(self, documents: List[DocumentData], batch_size: int = 100):
        """
        Exporta documentos com anexo para aba 'anexos'.

        Args:
            documents: Lista de documentos (InvoiceData, DanfeData, BoletoData, OtherDocumentData)
            batch_size: Quantidade de linhas por batch
        """
        if self.dry_run:
            logger.info(f"🔍 [DRY-RUN] Exportaria {len(documents)} documentos para '{ANEXOS_SHEET_NAME}'")
            for i, doc in enumerate(documents[:5]):  # Mostra primeiros 5
                row = doc.to_anexos_row()
                logger.info(f"  [{i+1}] {row}")
            if len(documents) > 5:
                logger.info(f"  ... e mais {len(documents) - 5} documentos")
            return

        worksheet = self._get_or_create_worksheet(ANEXOS_SHEET_NAME, ANEXOS_HEADERS)

        # Prepara linhas
        rows = []
        for doc in documents:
            try:
                row = doc.to_anexos_row()
                if row:  # Ignora linhas vazias
                    rows.append(row)
            except Exception as e:
                logger.error(f"❌ Erro ao converter documento {doc.arquivo_origem}: {e}")

        # Envia em batches
        total_exported = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            self._append_rows_with_retry(worksheet, batch)
            total_exported += len(batch)
            logger.info(f"📤 Batch exportado: {len(batch)} docs - Total: {total_exported}/{len(rows)}")

        logger.info(f"✅ {total_exported} documentos exportados para '{ANEXOS_SHEET_NAME}'")

    def _export_sem_anexos(self, documents: List[EmailAvisoData], batch_size: int = 100):
        """
        Exporta e-mails sem anexo para aba 'sem_anexos'.

        Args:
            documents: Lista de EmailAvisoData
            batch_size: Quantidade de linhas por batch
        """
        if self.dry_run:
            logger.info(f"🔍 [DRY-RUN] Exportaria {len(documents)} avisos para '{SEM_ANEXOS_SHEET_NAME}'")
            for i, doc in enumerate(documents[:5]):  # Mostra primeiros 5
                row = doc.to_sem_anexos_row()
                logger.info(f"  [{i+1}] {row}")
            if len(documents) > 5:
                logger.info(f"  ... e mais {len(documents) - 5} avisos")
            return

        worksheet = self._get_or_create_worksheet(SEM_ANEXOS_SHEET_NAME, SEM_ANEXOS_HEADERS)

        # Prepara linhas
        rows = []
        for doc in documents:
            try:
                row = doc.to_sem_anexos_row()
                if row:  # Ignora linhas vazias
                    rows.append(row)
            except Exception as e:
                logger.error(f"❌ Erro ao converter aviso {doc.arquivo_origem}: {e}")

        # Envia em batches
        total_exported = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            self._append_rows_with_retry(worksheet, batch)
            total_exported += len(batch)
            logger.info(f"📤 Batch exportado: {len(batch)} avisos - Total: {total_exported}/{len(rows)}")

        logger.info(f"✅ {total_exported} avisos exportados para '{SEM_ANEXOS_SHEET_NAME}'")


def _parse_float_br(value) -> float:
    """
    Converte valor para float, tratando formato brasileiro (vírgula decimal).

    Args:
        value: Valor a converter (pode ser string, float, int ou None)

    Returns:
        float: Valor convertido ou 0.0 se inválido
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove espaços e substitui vírgula por ponto
        value = value.strip().replace('.', '').replace(',', '.')
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def load_documents_from_csv(csv_path: Path) -> List[DocumentData]:
    """
    Carrega documentos de um arquivo CSV.

    Args:
        csv_path: Caminho para o arquivo CSV

    Returns:
        Lista de DocumentData reconstruídos
    """
    import pandas as pd

    if not csv_path.exists():
        logger.warning(f"⚠️ Arquivo não encontrado: {csv_path}")
        return []

    df = pd.read_csv(csv_path, sep=';', encoding='utf-8-sig')
    documents = []

    for _, row in df.iterrows():
        try:
            tipo = row.get('tipo_documento', '').upper()

            # Converte row para dict, tratando NaN como None
            row_dict = {k: (None if pd.isna(v) else v) for k, v in row.items()}

            if tipo == 'NFSE':
                doc = InvoiceData(
                    arquivo_origem=row_dict.get('arquivo_origem', ''),
                    data_processamento=row_dict.get('data_processamento'),
                    empresa=row_dict.get('empresa'),
                    fornecedor_nome=row_dict.get('fornecedor_nome'),
                    numero_nota=str(row_dict.get('numero_nota', '')) if row_dict.get('numero_nota') else None,
                    valor_total=_parse_float_br(row_dict.get('valor_total')),
                    vencimento=row_dict.get('vencimento'),
                    status_conciliacao=row_dict.get('status_conciliacao'),
                    observacoes=row_dict.get('observacoes'),
                    source_email_subject=row_dict.get('email_subject'),
                    batch_id=row_dict.get('batch_id'),
                )
                documents.append(doc)

            elif tipo == 'DANFE':
                doc = DanfeData(
                    arquivo_origem=row_dict.get('arquivo_origem', ''),
                    data_processamento=row_dict.get('data_processamento'),
                    empresa=row_dict.get('empresa'),
                    fornecedor_nome=row_dict.get('fornecedor_nome'),
                    numero_nota=str(row_dict.get('numero_nota', '')) if row_dict.get('numero_nota') else None,
                    valor_total=_parse_float_br(row_dict.get('valor_total')),
                    vencimento=row_dict.get('vencimento'),
                    status_conciliacao=row_dict.get('status_conciliacao'),
                    observacoes=row_dict.get('observacoes'),
                    source_email_subject=row_dict.get('email_subject'),
                    batch_id=row_dict.get('batch_id'),
                )
                documents.append(doc)

            elif tipo == 'BOLETO':
                doc = BoletoData(
                    arquivo_origem=row_dict.get('arquivo_origem', ''),
                    data_processamento=row_dict.get('data_processamento'),
                    empresa=row_dict.get('empresa'),
                    fornecedor_nome=row_dict.get('fornecedor_nome'),
                    numero_documento=str(row_dict.get('numero_documento', '')) if row_dict.get('numero_documento') else None,
                    valor_documento=_parse_float_br(row_dict.get('valor_documento')),
                    vencimento=row_dict.get('vencimento'),
                    status_conciliacao=row_dict.get('status_conciliacao'),
                    observacoes=row_dict.get('observacoes'),
                    source_email_subject=row_dict.get('email_subject'),
                    batch_id=row_dict.get('batch_id'),
                )
                documents.append(doc)

            elif tipo == 'OUTRO':
                doc = OtherDocumentData(
                    arquivo_origem=row_dict.get('arquivo_origem', ''),
                    data_processamento=row_dict.get('data_processamento'),
                    empresa=row_dict.get('empresa'),
                    fornecedor_nome=row_dict.get('fornecedor_nome'),
                    numero_documento=str(row_dict.get('numero_documento', '')) if row_dict.get('numero_documento') else None,
                    valor_total=_parse_float_br(row_dict.get('valor_total')),
                    vencimento=row_dict.get('vencimento'),
                    status_conciliacao=row_dict.get('status_conciliacao'),
                    observacoes=row_dict.get('observacoes'),
                    source_email_subject=row_dict.get('email_subject'),
                    batch_id=row_dict.get('batch_id'),
                )
                documents.append(doc)

            elif tipo == 'AVISO':
                doc = EmailAvisoData(
                    arquivo_origem=row_dict.get('arquivo_origem', ''),
                    data_processamento=row_dict.get('data_processamento'),
                    empresa=row_dict.get('empresa'),
                    fornecedor_nome=row_dict.get('fornecedor_nome'),
                    numero_nota=row_dict.get('numero_nota'),
                    link_nfe=row_dict.get('link_nfe'),
                    codigo_verificacao=row_dict.get('codigo_verificacao'),
                    email_subject_full=row_dict.get('email_subject'),
                    source_email_subject=row_dict.get('email_subject'),
                    batch_id=row_dict.get('batch_id'),
                )
                documents.append(doc)

        except Exception as e:
            logger.error(f"❌ Erro ao processar linha: {e}")

    return documents


def load_lotes_from_csv(csv_path: Path) -> List[DocumentData]:
    """
    Carrega lotes do relatorio_lotes.csv como documentos para exportação.

    Este é o formato padrão e mais simples - uma linha por e-mail/lote processado.

    Args:
        csv_path: Caminho para o arquivo CSV de lotes

    Returns:
        Lista de DocumentData (OtherDocumentData) representando cada lote
    """
    from datetime import datetime

    import pandas as pd

    if not csv_path.exists():
        logger.warning(f"⚠️ Arquivo não encontrado: {csv_path}")
        return []

    df = pd.read_csv(csv_path, sep=';', encoding='utf-8-sig')
    documents = []

    for _, row in df.iterrows():
        try:
            # Converte row para dict, tratando NaN como None
            row_dict = {k: (None if pd.isna(v) else v) for k, v in row.items()}

            # Determina o valor principal (valor_boleto ou valor_compra)
            valor_boleto = _parse_float_br(row_dict.get('valor_boleto'))
            valor_compra = _parse_float_br(row_dict.get('valor_compra'))
            valor_final = valor_boleto if valor_boleto and valor_boleto > 0 else valor_compra

            # Extrai data do batch_id ou usa data atual
            batch_id = row_dict.get('batch_id', '')
            data_proc = None
            if batch_id and '_' in batch_id:
                # Formato: email_YYYYMMDD_HHMMSS_xxx
                parts = batch_id.split('_')
                if len(parts) >= 2 and len(parts[1]) == 8:
                    try:
                        data_proc = f"{parts[1][:4]}-{parts[1][4:6]}-{parts[1][6:8]}"
                    except:
                        pass
            if not data_proc:
                data_proc = datetime.now().strftime('%Y-%m-%d')

            # Monta avisos/observações
            avisos_parts = []
            status = row_dict.get('status_conciliacao', '')
            if status:
                avisos_parts.append(f"[{status}]")
            divergencia = row_dict.get('divergencia', '')
            if divergencia:
                avisos_parts.append(str(divergencia))

            # Cria OtherDocumentData para representar o lote
            doc = OtherDocumentData(
                arquivo_origem=batch_id,
                data_processamento=data_proc,
                empresa=row_dict.get('empresa'),
                fornecedor_nome=row_dict.get('fornecedor'),
                numero_documento=str(row_dict.get('numero_nota', '')) if row_dict.get('numero_nota') else None,
                valor_total=valor_final,
                vencimento=row_dict.get('vencimento'),
                status_conciliacao=status,
                observacoes=' | '.join(avisos_parts) if avisos_parts else None,
                source_email_subject=row_dict.get('email_subject'),
                source_email_sender=row_dict.get('email_sender'),
                batch_id=batch_id,
            )
            documents.append(doc)

        except Exception as e:
            logger.error(f"❌ Erro ao processar linha de lote: {e}")

    return documents


def load_avisos_from_csv(csv_path: Path) -> List[EmailAvisoData]:
    """
    Carrega avisos (e-mails sem anexo) de um arquivo CSV específico.

    Args:
        csv_path: Caminho para o arquivo CSV de avisos

    Returns:
        Lista de EmailAvisoData
    """
    import pandas as pd

    if not csv_path.exists():
        logger.warning(f"⚠️ Arquivo não encontrado: {csv_path}")
        return []

    df = pd.read_csv(csv_path, sep=';', encoding='utf-8-sig')
    avisos = []

    for _, row in df.iterrows():
        try:
            # Converte row para dict, tratando NaN como None
            row_dict = {k: (None if pd.isna(v) else v) for k, v in row.items()}

            doc = EmailAvisoData(
                arquivo_origem=row_dict.get('arquivo_origem', ''),
                data_processamento=row_dict.get('data_processamento'),
                empresa=row_dict.get('empresa'),
                fornecedor_nome=row_dict.get('fornecedor_nome'),
                numero_nota=row_dict.get('numero_nota'),
                link_nfe=row_dict.get('link_nfe'),
                codigo_verificacao=row_dict.get('codigo_verificacao'),
                dominio_portal=row_dict.get('dominio_portal'),
                email_subject_full=row_dict.get('email_subject'),
                source_email_subject=row_dict.get('email_subject'),
                vencimento=row_dict.get('vencimento'),
                observacoes=row_dict.get('observacoes'),
                status_conciliacao=row_dict.get('status_conciliacao'),
            )
            avisos.append(doc)

        except Exception as e:
            logger.error(f"❌ Erro ao processar linha de aviso: {e}")

    return avisos


def main():
    """Função principal do script."""
    parser = argparse.ArgumentParser(
        description='Exporta documentos processados para Google Sheets'
    )
    parser.add_argument(
        '--spreadsheet-id',
        type=str,
        help='ID da planilha do Google Sheets (ou use GOOGLE_SPREADSHEET_ID)'
    )
    parser.add_argument(
        '--credentials',
        type=str,
        default='credentials.json',
        help='Caminho para o arquivo de credenciais (default: credentials.json)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simula a exportação sem enviar dados'
    )
    parser.add_argument(
        '--use-consolidado',
        action='store_true',
        help='Usa relatorio_consolidado.csv (detalhado) ao invés de relatorio_lotes.csv (padrão)'
    )
    parser.add_argument(
        '--csv-lotes',
        type=str,
        help='Caminho para o CSV de lotes (default: data/output/relatorio_lotes.csv)'
    )
    parser.add_argument(
        '--csv-consolidado',
        type=str,
        help='Caminho para o CSV consolidado (usado com --use-consolidado)'
    )
    parser.add_argument(
        '--csv-avisos',
        type=str,
        help='Caminho para o CSV de avisos (default: data/output/avisos_emails_sem_anexo_latest.csv)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Quantidade de linhas por batch (default: 100)'
    )

    args = parser.parse_args()

    # Define caminhos padrão
    base_dir = Path(__file__).resolve().parent.parent
    csv_lotes = Path(args.csv_lotes) if args.csv_lotes else base_dir / 'data' / 'output' / 'relatorio_lotes.csv'
    csv_consolidado = Path(args.csv_consolidado) if args.csv_consolidado else base_dir / 'data' / 'output' / 'relatorio_consolidado.csv'
    csv_avisos = Path(args.csv_avisos) if args.csv_avisos else base_dir / 'data' / 'output' / 'avisos_emails_sem_anexo_latest.csv'

    logger.info("=" * 60)
    logger.info("📤 EXPORTAÇÃO PARA GOOGLE SHEETS")
    logger.info("=" * 60)

    # Carrega documentos
    documents = []

    if args.use_consolidado:
        # Modo detalhado: usa relatorio_consolidado.csv
        if csv_consolidado.exists():
            logger.info(f"📂 Carregando documentos de: {csv_consolidado}")
            docs_consolidado = load_documents_from_csv(csv_consolidado)
            # Filtra apenas anexos (não avisos)
            docs_anexos = [d for d in docs_consolidado if not isinstance(d, EmailAvisoData)]
            documents.extend(docs_anexos)
            logger.info(f"  ✅ {len(docs_anexos)} documentos carregados")
        else:
            logger.warning(f"⚠️ CSV consolidado não encontrado: {csv_consolidado}")
    else:
        # Modo padrão: usa relatorio_lotes.csv (mais simples)
        if csv_lotes.exists():
            logger.info(f"📂 Carregando lotes de: {csv_lotes}")
            docs_lotes = load_lotes_from_csv(csv_lotes)
            documents.extend(docs_lotes)
            logger.info(f"  ✅ {len(docs_lotes)} lotes carregados")
        else:
            logger.warning(f"⚠️ CSV de lotes não encontrado: {csv_lotes}")

    if csv_avisos.exists():
        logger.info(f"📂 Carregando avisos de: {csv_avisos}")
        avisos = load_avisos_from_csv(csv_avisos)
        documents.extend(avisos)
        logger.info(f"  ✅ {len(avisos)} avisos carregados")
    else:
        logger.warning(f"⚠️ CSV de avisos não encontrado: {csv_avisos}")

    if not documents:
        logger.error("❌ Nenhum documento encontrado para exportar")
        return 1

    logger.info(f"📊 Total de documentos: {len(documents)}")

    # Inicializa exportador
    try:
        exporter = GoogleSheetsExporterDualTab(
            credentials_path=args.credentials,
            spreadsheet_id=args.spreadsheet_id,
            dry_run=args.dry_run
        )
    except ValueError as e:
        logger.error(f"❌ Erro de configuração: {e}")
        return 1

    # Exporta
    try:
        qtd_anexos, qtd_sem_anexos = exporter.export(
            documents,
            batch_size=args.batch_size
        )

        logger.info("=" * 60)
        logger.info("✅ EXPORTAÇÃO CONCLUÍDA")
        logger.info(f"   📎 Anexos: {qtd_anexos}")
        logger.info(f"   🔗 Sem Anexos: {qtd_sem_anexos}")
        logger.info("=" * 60)

        return 0

    except Exception as e:
        logger.error(f"❌ Erro na exportação: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
