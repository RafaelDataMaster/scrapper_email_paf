"""
Processador de Lotes (Batch Processor).

Este módulo implementa a "Camada de Processamento" do plano de refatoração,
responsável por processar uma pasta inteira (lote de e-mail) ao invés de
arquivos individuais.

Mudança de paradigma:
- De: process_file(file_path)
- Para: process_batch(folder_path)

Princípios SOLID aplicados:
- SRP: Classe focada apenas em orquestrar processamento de lotes
- OCP: Extensível via composição (injeção de processor/correlation_service)
- DIP: Depende de abstrações, não de implementações concretas
- LSP: BatchResult pode ser substituído por subclasses sem quebrar código
"""
import os
from pathlib import Path
from typing import List, Optional, Union

from core.batch_result import BatchResult
from core.correlation_service import CorrelationResult, CorrelationService
from core.metadata import EmailMetadata
from core.models import DocumentData
from core.processor import BaseInvoiceProcessor
from core.xml_extractor import XmlExtractor


class BatchProcessor:
    """
    Processador de lotes de documentos.

    Processa uma pasta inteira (lote de e-mail) contendo múltiplos
    documentos, aplicando correlação e enriquecimento cruzado.

    Attributes:
        processor: Processador individual de documentos
        correlation_service: Serviço de correlação entre documentos

    Usage:
        batch_processor = BatchProcessor()
        result = batch_processor.process_batch("temp/email_20251231_abc123")
    """

    # Extensões de arquivo suportadas
    SUPPORTED_EXTENSIONS = {'.pdf', '.xml'}

    # Arquivos a ignorar no processamento
    IGNORED_FILES = {'metadata.json', '.gitkeep', 'thumbs.db', 'desktop.ini'}

    def __init__(
        self,
        processor: Optional[BaseInvoiceProcessor] = None,
        correlation_service: Optional[CorrelationService] = None,
    ):
        """
        Inicializa o processador de lotes.

        Args:
            processor: Processador de documentos individuais (DIP)
            correlation_service: Serviço de correlação (DIP)
        """
        self.processor = processor or BaseInvoiceProcessor()
        self.correlation_service = correlation_service or CorrelationService()

    def process_batch(
        self,
        folder_path: Union[str, Path],
        apply_correlation: bool = True
    ) -> BatchResult:
        """
        Processa uma pasta (lote) de documentos.

        Args:
            folder_path: Caminho da pasta do lote
            apply_correlation: Se True, aplica correlação entre documentos

        Returns:
            BatchResult com todos os documentos processados
        """
        folder_path = Path(folder_path)

        # Gera batch_id a partir do nome da pasta
        batch_id = folder_path.name

        result = BatchResult(
            batch_id=batch_id,
            source_folder=str(folder_path)
        )

        # 1. Carrega metadados (se existir)
        metadata = EmailMetadata.load(folder_path)
        if metadata:
            result.metadata_path = str(folder_path / "metadata.json")
            result.email_subject = metadata.email_subject
            result.email_sender = metadata.email_sender_name

        # 2. Lista arquivos processáveis
        files = self._list_processable_files(folder_path)

        if not files:
            return result

        # 3. Processa cada arquivo
        for file_path in files:
            try:
                doc = self._process_single_file(file_path)
                if doc:
                    result.add_document(doc)
            except Exception as e:
                result.add_error(str(file_path), str(e))

        # 4. Aplica correlação entre documentos (se habilitado)
        if apply_correlation and result.total_documents > 0:
            correlation_result = self.correlation_service.correlate(result, metadata)
            result.correlation_result = correlation_result

        return result

    def process_multiple_batches(
        self,
        root_folder: Union[str, Path],
        apply_correlation: bool = True
    ) -> List[BatchResult]:
        """
        Processa múltiplas pastas (lotes) de uma vez.

        Args:
            root_folder: Pasta raiz contendo subpastas de lotes
            apply_correlation: Se True, aplica correlação entre documentos

        Returns:
            Lista de BatchResult, um para cada lote
        """
        root_folder = Path(root_folder)
        results = []

        if not root_folder.exists():
            return results

        # Processa cada subpasta como um lote
        for item in sorted(root_folder.iterdir()):
            if item.is_dir() and not item.name.startswith('.'):
                batch_result = self.process_batch(item, apply_correlation)
                results.append(batch_result)

        return results

    def process_legacy_files(
        self,
        folder_path: Union[str, Path],
        recursive: bool = True
    ) -> BatchResult:
        """
        Processa arquivos legados (sem estrutura de lote/metadata).

        Modo de compatibilidade para failed_cases_pdf e outros diretórios
        que contêm PDFs soltos sem contexto de e-mail.

        Args:
            folder_path: Pasta contendo arquivos legados
            recursive: Se True, busca arquivos em subpastas

        Returns:
            BatchResult com todos os documentos (sem correlação de lote)
        """
        folder_path = Path(folder_path)
        batch_id = f"legacy_{folder_path.name}"

        result = BatchResult(
            batch_id=batch_id,
            source_folder=str(folder_path)
        )

        # Busca arquivos (recursiva ou não)
        if recursive:
            files = self._list_processable_files_recursive(folder_path)
        else:
            files = self._list_processable_files(folder_path)

        if not files:
            return result

        # Cria metadata legado para rastreabilidade
        legacy_metadata = EmailMetadata.create_legacy(
            batch_id=batch_id,
            file_paths=[str(f) for f in files]
        )

        # Processa cada arquivo
        for file_path in files:
            try:
                doc = self._process_single_file(file_path)
                if doc:
                    result.add_document(doc)
            except Exception as e:
                result.add_error(str(file_path), str(e))

        # Não aplica correlação em modo legado (não há contexto de lote)

        return result

    def _process_single_file(self, file_path: Path) -> Optional[DocumentData]:
        """
        Processa um único arquivo.

        Args:
            file_path: Caminho do arquivo

        Returns:
            DocumentData ou None se falhar
        """
        # Processa PDF
        if file_path.suffix.lower() == '.pdf':
            return self.processor.process(str(file_path))

        # Processa XML (NF-e / NFS-e)
        if file_path.suffix.lower() == '.xml':
            return self._process_xml(file_path)

        return None

    def _process_xml(self, file_path: Path) -> Optional[DocumentData]:
        """
        Processa um arquivo XML de NF-e ou NFS-e.

        Args:
            file_path: Caminho do arquivo XML

        Returns:
            DocumentData (DanfeData ou InvoiceData) ou None se falhar
        """
        try:
            extractor = XmlExtractor()
            result = extractor.extract(str(file_path))

            if result.success and result.document:
                return result.document
            else:
                print(f"Erro ao processar XML {file_path.name}: {result.error}")
                return None

        except Exception as e:
            print(f"Erro ao processar XML {file_path.name}: {e}")
            return None

    def _list_processable_files(self, folder_path: Path) -> List[Path]:
        """
        Lista arquivos processáveis em uma pasta (não recursivo).

        Args:
            folder_path: Pasta a ser listada

        Returns:
            Lista de caminhos de arquivos
        """
        if not folder_path.exists():
            return []

        files = []
        for item in sorted(folder_path.iterdir()):
            if item.is_file() and self._is_processable(item):
                files.append(item)

        return files

    def _list_processable_files_recursive(self, folder_path: Path) -> List[Path]:
        """
        Lista arquivos processáveis recursivamente.

        Args:
            folder_path: Pasta raiz

        Returns:
            Lista de caminhos de arquivos
        """
        if not folder_path.exists():
            return []

        files = []
        for item in sorted(folder_path.rglob("*")):
            if item.is_file() and self._is_processable(item):
                files.append(item)

        return files

    def _is_processable(self, file_path: Path) -> bool:
        """
        Verifica se um arquivo pode ser processado.

        Args:
            file_path: Caminho do arquivo

        Returns:
            True se o arquivo deve ser processado
        """
        # Ignora arquivos conhecidos
        if file_path.name.lower() in self.IGNORED_FILES:
            return False

        # Ignora arquivos ocultos
        if file_path.name.startswith('.'):
            return False

        # Ignora pasta 'ignored' (lixo segregado)
        if 'ignored' in file_path.parts:
            return False

        # Verifica extensão
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS


def process_email_batch(
    folder_path: Union[str, Path],
    apply_correlation: bool = True
) -> BatchResult:
    """
    Função utilitária para processar um lote.

    Wrapper simples para uso direto sem instanciar a classe.

    Args:
        folder_path: Caminho da pasta do lote
        apply_correlation: Se True, aplica correlação

    Returns:
        BatchResult com documentos processados
    """
    processor = BatchProcessor()
    return processor.process_batch(folder_path, apply_correlation)


def process_legacy_folder(
    folder_path: Union[str, Path],
    recursive: bool = True
) -> BatchResult:
    """
    Função utilitária para processar pasta legada.

    Wrapper simples para uso direto sem instanciar a classe.

    Args:
        folder_path: Pasta com arquivos legados
        recursive: Se True, busca em subpastas

    Returns:
        BatchResult com documentos processados
    """
    processor = BatchProcessor()
    return processor.process_legacy_files(folder_path, recursive)
