"""
Módulo de exportação de dados extraídos.

Implementa o padrão Strategy para exportação, permitindo adicionar novos
formatos (Google Sheets, SQL, etc.) sem modificar código existente (OCP).
"""

from abc import ABC, abstractmethod
from typing import List
from pathlib import Path
import pandas as pd
from core.models import DocumentData


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
    Exportador para Google Sheets (implementação futura).
    
    Placeholder para integração futura com Google Sheets API.
    Quando implementado, permitirá enviar dados diretamente para planilhas
    sem modificar o código de orquestração.
    """
    
    def __init__(self, credentials_path: str, spreadsheet_id: str):
        """
        Inicializa o exportador do Google Sheets.
        
        Args:
            credentials_path: Caminho para o arquivo de credenciais JSON
            spreadsheet_id: ID da planilha do Google Sheets
        """
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id
        # TODO: Inicializar cliente da API do Google Sheets
    
    def export(self, data: List[DocumentData], destination: str) -> None:
        """
        Exporta documentos para Google Sheets.
        
        Args:
            data: Lista de objetos DocumentData
            destination: Nome da aba/sheet onde os dados serão inseridos
        
        Raises:
            NotImplementedError: Ainda não implementado
        """
        raise NotImplementedError(
            "Exportação para Google Sheets será implementada na próxima fase. "
            "Por enquanto, use CsvExporter."
        )


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


class AttachmentDownloader:
    """
    Responsável por baixar e salvar anexos de email.
    
    Separado da lógica de ingestão e processamento (SRP).
    """
    
    def __init__(self, file_manager: FileSystemManager):
        """
        Inicializa o downloader.
        
        Args:
            file_manager: Gerenciador de sistema de arquivos
        """
        self.file_manager = file_manager
    
    def save_attachment(self, filename: str, content: bytes) -> Path:
        """
        Salva um anexo no diretório temporário.
        
        Args:
            filename: Nome original do arquivo
            content: Conteúdo binário do arquivo
            
        Returns:
            Path do arquivo salvo
            
        Raises:
            OSError: Se houver erro ao salvar o arquivo
        """
        import uuid
        
        # Gera nome único para evitar colisões
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        file_path = self.file_manager.get_temp_file_path(unique_filename)
        
        # Salva o arquivo
        with open(file_path, 'wb') as f:
            f.write(content)
        
        return file_path
