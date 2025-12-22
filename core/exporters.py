"""
Módulo de exportação de dados extraídos.

Implementa o padrão Strategy para exportação, permitindo adicionar novos
formatos (Google Sheets, SQL, etc.) sem modificar código existente (OCP).

Conformidade: GoogleSheetsExporter com retry strategy para Política 5.9.
"""

from abc import ABC, abstractmethod
from typing import List
from pathlib import Path
import pandas as pd
import logging
from core.models import DocumentData

# Imports para Google Sheets (instalados via requirements.txt)
try:
    import gspread
    from gspread.exceptions import APIError
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_sleep_log
    )
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    gspread = None
    APIError = Exception

logger = logging.getLogger('scrapper')


class DataExporter(ABC):
    """
    Interface abstrata para exportadores de dados.
    
    Permite trocar a implementação de exportação sem afetar o código cliente,
    seguindo o Dependency Inversion Principle (DIP).
    """
    
    @abstractmethod
    def export(self, data: List[DocumentData], destination: str) -> None:
        """
        Exporta uma lista de documentos para um destino.
        
        Args:
            data: Lista de objetos DocumentData (InvoiceData, BoletoData, etc.)
            destination: Caminho ou identificador do destino
        
        Raises:
            ExportError: Se houver falha na exportação
        """
        pass


class CsvExporter(DataExporter):
    """
    Exportador para formato CSV usando pandas.
    
    Converte documentos em DataFrame e salva como CSV com encoding UTF-8.
    """
    
    def export(self, data: List[DocumentData], destination: str) -> None:
        """
        Exporta documentos para arquivo CSV.
        
        Args:
            data: Lista de objetos DocumentData
            destination: Caminho do arquivo CSV de saída
        
        Raises:
            ValueError: Se a lista de dados estiver vazia
            OSError: Se houver erro ao salvar o arquivo
        """
        if not data:
            raise ValueError("Lista de dados vazia. Nada para exportar.")
        
        # Converte cada documento para dicionário usando to_dict()
        records = [doc.to_dict() for doc in data]
        
        # Cria DataFrame e exporta
        df = pd.DataFrame(records)
        df.to_csv(
            destination,
            index=False,
            encoding='utf-8-sig',  # BOM para Excel no Windows
            sep=';',
            decimal=','
        )


class GoogleSheetsExporter(DataExporter):
    """
    Exportador para Google Sheets com retry strategy.
    
    Conformidade: Implementa lançamento de títulos na planilha PAF conforme
    POP 4.4 e 4.10 (Master Internet).
    
    Features:
    - Autenticação via Service Account
    - Retry automático com exponential backoff (até 5 tentativas)
    - Logging detalhado para auditoria
    - Batch processing (100 linhas por vez) para performance
    - Modo single row para tempo real (ingestão de e-mails)
    """
    
    def __init__(self, credentials_path: str = 'credentials.json', 
                 spreadsheet_id: str = None):
        """
        Inicializa o exportador do Google Sheets.
        
        Args:
            credentials_path: Caminho para o arquivo de credenciais JSON da Service Account
            spreadsheet_id: ID da planilha do Google Sheets (extraído da URL)
            
        Raises:
            ImportError: Se gspread não estiver instalado
            FileNotFoundError: Se credentials.json não existir
        """
        if not GSPREAD_AVAILABLE:
            raise ImportError(
                "gspread não está instalado. "
                "Execute: pip install gspread tenacity"
            )
        
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        self._client = None
        self._worksheet = None
    
    def _authenticate(self):
        """
        Autentica com Google Sheets API usando Service Account.
        
        Raises:
            FileNotFoundError: Se credentials.json não existir
            gspread.exceptions.GSpreadException: Se autenticação falhar
        """
        if self._client is None:
            try:
                self._client = gspread.service_account(filename=self.credentials_path)
                logger.info(f"Autenticado com sucesso no Google Sheets")
            except FileNotFoundError:
                logger.error(f"Arquivo de credenciais não encontrado: {self.credentials_path}")
                raise
            except Exception as e:
                logger.error(f"Erro na autenticação Google Sheets: {e}")
                raise
    
    def _get_worksheet(self, destination: str):
        """
        Obtém referência à planilha de destino.
        
        Args:
            destination: Nome da aba/worksheet (ex: "PAF NOVO - SETORES CSC")
            
        Returns:
            gspread.Worksheet: Referência à aba da planilha
        """
        if self._worksheet is None:
            self._authenticate()
            spreadsheet = self._client.open_by_key(self.spreadsheet_id)
            self._worksheet = spreadsheet.worksheet(destination)
            logger.info(f"Conectado à planilha: {destination}")
        return self._worksheet
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(APIError),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _append_rows_with_retry(self, worksheet, rows: List[List]):
        """
        Adiciona linhas à planilha com retry automático.
        
        Conformidade: Retry strategy garante resiliência contra rate limits
        da API do Google Sheets (300 req/min).
        
        Args:
            worksheet: Worksheet do gspread
            rows: Lista de listas (cada sublista é uma linha)
            
        Raises:
            APIError: Se todas as tentativas falharem
        """
        worksheet.append_rows(rows, value_input_option='USER_ENTERED')
    
    def export(self, data: List[DocumentData], destination: str, 
               batch_size: int = 100) -> None:
        """
        Exporta documentos para Google Sheets em lotes.
        
        Conformidade: Registra títulos na planilha PAF conforme POP 4.4 e 4.10.
        
        Args:
            data: Lista de objetos DocumentData
            destination: Nome da aba/worksheet na planilha
            batch_size: Quantidade de linhas por batch (default: 100)
            
        Raises:
            ValueError: Se lista de dados estiver vazia
            APIError: Se API do Google Sheets falhar após retries
        """
        if not data:
            raise ValueError("Lista de dados vazia. Nada para exportar.")
        
        worksheet = self._get_worksheet(destination)
        
        # Acumula linhas para batch processing
        buffer = []
        total_exported = 0
        
        for doc in data:
            row = doc.to_sheets_row()  # Retorna lista com 18 valores na ordem PAF
            buffer.append(row)
            
            # Envia batch quando atingir o tamanho
            if len(buffer) >= batch_size:
                self._append_rows_with_retry(worksheet, buffer)
                total_exported += len(buffer)
                logger.info(f"Batch exportado: {len(buffer)} documentos - "
                           f"Total: {total_exported}/{len(data)}")
                buffer = []
        
        # Envia linhas restantes
        if buffer:
            self._append_rows_with_retry(worksheet, buffer)
            total_exported += len(buffer)
            logger.info(f"Batch final exportado: {len(buffer)} documentos")
        
        logger.info(f"Exportação concluída: {total_exported} documentos para '{destination}'")
    
    def export_single(self, doc: DocumentData, destination: str) -> None:
        """
        Exporta um único documento em tempo real (modo individual).
        
        Ideal para ingestão de e-mails onde documentos chegam um a um.
        
        Args:
            doc: Documento individual a exportar
            destination: Nome da aba/worksheet na planilha
        """
        worksheet = self._get_worksheet(destination)
        row = doc.to_sheets_row()
        
        self._append_rows_with_retry(worksheet, [row])
        logger.info(f"Documento exportado com sucesso: {doc.arquivo_origem} - "
                   f"Tipo: {doc.doc_type}")


class FileSystemManager:
    """
    Gerenciador de sistema de arquivos e pastas temporárias.
    
    Responsabilidade única: gerenciar criação, limpeza e organização de diretórios.
    Separado da lógica de ingestão (SRP - Single Responsibility Principle).
    """
    
    def __init__(self, temp_dir: Path, output_dir: Path):
        """
        Inicializa o gerenciador de arquivos.
        
        Args:
            temp_dir: Diretório para arquivos temporários
            output_dir: Diretório para saídas finais
        """
        self.temp_dir = Path(temp_dir)
        self.output_dir = Path(output_dir)
    
    def setup_directories(self) -> None:
        """
        Cria diretórios necessários se não existirem.
        """
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def clean_temp_directory(self) -> None:
        """
        Remove e recria o diretório temporário.
        Útil para limpar arquivos de execuções anteriores.
        """
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def get_temp_file_path(self, filename: str) -> Path:
        """
        Retorna caminho completo para arquivo temporário.
        
        Args:
            filename: Nome do arquivo
            
        Returns:
            Path completo no diretório temporário
        """
        return self.temp_dir / filename
    
    def get_output_file_path(self, filename: str) -> Path:
        """
        Retorna caminho completo para arquivo de saída.
        
        Args:
            filename: Nome do arquivo
            
        Returns:
            Path completo no diretório de saída
        """
        return self.output_dir / filename

