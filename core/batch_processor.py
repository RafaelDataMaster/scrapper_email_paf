"""
Processador de Lotes (Batch Processor).

Este módulo implementa a "Camada de Processamento" do plano de refatoração,
responsável por processar uma pasta inteira (lote de e-mail) ao invés de
arquivos individuais.

Mudança de paradigma:
- De: process_file(file_path)
- Para: process_batch(folder_path)

Lógica de priorização XML:
- XML é usado APENAS se tiver TODOS os campos obrigatórios:
  (fornecedor, vencimento, numero_nota, valor)
- Se XML incompleto, processa PDFs para completar os dados
- Cada lote representa UMA compra/locação única

NOVO: Extração de dados do corpo do e-mail:
- Quando NF não é anexo (apenas link), extrai valor do corpo HTML/texto
- Usa EmailBodyExtractor para extrair valores monetários, vencimentos, etc.
- Cria documento sintético (InvoiceData) com dados extraídos do corpo

Princípios SOLID aplicados:
- SRP: Classe focada apenas em orquestrar processamento de lotes
- OCP: Extensível via composição (injeção de processor/correlation_service)
- DIP: Depende de abstrações, não de implementações concretas
- LSP: BatchResult pode ser substituído por subclasses sem quebrar código
"""
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from core.batch_result import BatchResult
from core.correlation_service import CorrelationResult, CorrelationService
from core.empresa_matcher import find_empresa_no_texto
from core.metadata import EmailMetadata
from core.models import DanfeData, DocumentData, InvoiceData
from core.processor import BaseInvoiceProcessor
from extractors.xml_extractor import XmlExtractor

logger = logging.getLogger(__name__)


class BatchProcessor:
    """
    Processador de lotes de documentos.

    Processa uma pasta inteira (lote de e-mail) contendo múltiplos
    documentos, aplicando correlação e enriquecimento cruzado.

    Cada lote representa UMA compra/locação única.

    Lógica de XML:
    - XML é prioritário APENAS se estiver completo (todos os campos)
    - Campos obrigatórios: fornecedor, vencimento, numero_nota, valor
    - Se incompleto, usa PDFs para complementar

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

    # Campos obrigatórios para considerar XML completo
    CAMPOS_OBRIGATORIOS_XML = {'fornecedor_nome', 'vencimento', 'numero_nota', 'valor_total'}

    def _parse_email_date(self, date_str: Optional[str]) -> Optional[str]:
        """
        Converte a data do email para formato ISO (YYYY-MM-DD).

        O campo received_date do metadata pode vir em diversos formatos:
        - RFC 2822: "Tue, 14 Jan 2025 10:30:00 -0300"
        - ISO: "2025-01-14T10:30:00"
        - Simples: "14/01/2025"

        Args:
            date_str: String com a data do email

        Returns:
            Data em formato ISO (YYYY-MM-DD) ou None se não puder parsear
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        # Tenta formato RFC 2822 (padrão de e-mail)
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            return dt.strftime('%Y-%m-%d')
        except Exception:
            pass

        # Tenta formato ISO com timezone
        try:
            from datetime import datetime
            # Remove timezone info se presente
            if '+' in date_str:
                date_str = date_str.split('+')[0].strip()
            if 'T' in date_str:
                dt = datetime.fromisoformat(date_str.replace('Z', ''))
                return dt.strftime('%Y-%m-%d')
        except Exception:
            pass

        # Tenta formato brasileiro (DD/MM/YYYY)
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str[:10], '%d/%m/%Y')
            return dt.strftime('%Y-%m-%d')
        except Exception:
            pass

        # Tenta formato ISO simples (YYYY-MM-DD)
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str[:10], '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        except Exception:
            pass

        logger.warning(f"Não foi possível parsear data do email: {date_str}")
        return None

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

        Lógica:
        1. Processa XMLs primeiro
        2. Verifica se XML está completo (todos os campos obrigatórios)
        3. Se XML completo para uma nota, ignora PDF correspondente
        4. Se XML incompleto, processa PDF para complementar dados

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
            # Usa email_sender_name, com fallback para email_sender_address se vazio
            result.email_sender = metadata.email_sender_name or metadata.email_sender_address
            # Extrai data do email do metadata (received_date)
            result.email_date = self._parse_email_date(metadata.received_date)

        # 2. Lista arquivos processáveis (separados por tipo)
        xml_files, pdf_files = self._list_files_by_type(folder_path)

        if not xml_files and not pdf_files:
            return result

        # 3. Processa XMLs primeiro
        xml_docs: List[DocumentData] = []
        xml_notas_completas: Set[str] = set()  # Números de nota de XMLs completos

        for file_path in xml_files:
            try:
                doc = self._process_xml(file_path)
                if doc:
                    xml_docs.append(doc)
                    # Verifica se XML está completo
                    if self._is_xml_complete(doc):
                        numero_nota = getattr(doc, 'numero_nota', None)
                        if numero_nota:
                            xml_notas_completas.add(str(numero_nota).strip())
            except Exception as e:
                result.add_error(str(file_path), str(e))

        # 4. Processa PDFs
        pdf_docs: List[DocumentData] = []

        for file_path in pdf_files:
            try:
                doc = self._process_single_file(file_path)
                if doc:
                    pdf_docs.append(doc)
            except Exception as e:
                result.add_error(str(file_path), str(e))

        # 5. Mescla documentos: XML completo prevalece, senão usa PDF
        final_docs = self._merge_documents(xml_docs, pdf_docs, xml_notas_completas)

        for doc in final_docs:
            result.add_document(doc)

        # 6. NOVO: Extrai dados do corpo do e-mail se não há NF anexada
        # Útil para e-mails onde a NF é um link (Omie, prefeituras)
        if metadata and not self._has_nota_with_valor(final_docs):
            email_body_doc = self._extract_from_email_body(metadata, batch_id)
            if email_body_doc:
                result.add_document(email_body_doc)
                logger.info(f"📧 Dados extraídos do corpo do e-mail: valor={getattr(email_body_doc, 'valor_total', 0)}")

        # 7. Aplica correlação entre documentos (se habilitado)
        if apply_correlation and result.total_documents > 0:
            correlation_result = self.correlation_service.correlate(result, metadata)
            result.correlation_result = correlation_result

        return result

    def _has_nota_with_valor(self, docs: List[DocumentData]) -> bool:
        """
        Verifica se há alguma nota fiscal com valor > 0 na lista.

        Args:
            docs: Lista de documentos processados

        Returns:
            True se existe NF/DANFE com valor_total > 0
        """
        from core.models import BoletoData

        for doc in docs:
            # Ignora boletos
            if isinstance(doc, BoletoData):
                continue

            # Verifica se tem valor
            valor = getattr(doc, 'valor_total', 0) or 0
            if valor > 0:
                return True

        return False

    def _extract_from_email_body(
        self,
        metadata: 'EmailMetadata',
        batch_id: str
    ) -> Optional[DocumentData]:
        """
        Extrai dados do corpo do e-mail quando não há NF anexada.

        Cria um InvoiceData sintético com os dados extraídos do corpo.
        Útil para e-mails da Omie, prefeituras, etc.

        Args:
            metadata: Metadados do e-mail
            batch_id: ID do lote

        Returns:
            InvoiceData com dados extraídos ou None
        """
        try:
            from extractors.email_body_extractor import EmailBodyExtractor

            # Verifica se tem corpo de e-mail
            if not metadata.email_body_text:
                return None

            # Extrai dados do corpo
            extractor = EmailBodyExtractor()
            result = extractor.extract(
                body_text=metadata.email_body_text,
                subject=metadata.email_subject
            )

            # Só cria documento se encontrou algo útil
            if not result.has_valor() and not result.numero_nota and not result.link_nfe:
                return None

            # Cria InvoiceData sintético
            from datetime import datetime

            doc = InvoiceData(
                arquivo_origem=f"{batch_id}_email_body",
                texto_bruto=f"[Extraído do corpo do e-mail] {(metadata.email_body_text or '')[:300]}",
                data_processamento=datetime.now().strftime('%Y-%m-%d'),
                # Campos extraídos
                valor_total=result.valor_total,
                numero_nota=result.numero_nota,
                vencimento=result.vencimento,
                fornecedor_nome=result.fornecedor_nome or metadata.email_sender_name,
                # Metadados
                source_email_subject=metadata.email_subject,
                source_email_sender=metadata.email_sender_name or metadata.email_sender_address,
                # Campos extras
                observacoes=f"[EXTRAÍDO DO E-MAIL] Link: {result.link_nfe or 'N/A'}" if result.link_nfe else None,
            )

            logger.debug(
                f"EmailBody extraction: valor={result.valor_total}, "
                f"numero={result.numero_nota}, venc={result.vencimento}"
            )

            return doc

        except ImportError as e:
            logger.warning(f"EmailBodyExtractor não disponível: {e}")
            return None
        except Exception as e:
            logger.warning(f"Erro ao extrair do corpo do e-mail: {e}")
            return None

    def _is_xml_complete(self, doc: DocumentData) -> bool:
        """
        Verifica se um documento XML tem todos os campos obrigatórios.

        Campos obrigatórios: fornecedor_nome, vencimento, numero_nota, valor_total

        Args:
            doc: Documento extraído do XML

        Returns:
            True se todos os campos obrigatórios estão preenchidos
        """
        # Só verifica notas (DANFE e NFS-e)
        if not isinstance(doc, (DanfeData, InvoiceData)):
            return False

        fornecedor = getattr(doc, 'fornecedor_nome', None)
        vencimento = getattr(doc, 'vencimento', None)
        numero_nota = getattr(doc, 'numero_nota', None)
        valor_total = getattr(doc, 'valor_total', None)

        return all([
            fornecedor and str(fornecedor).strip(),
            vencimento and str(vencimento).strip(),
            numero_nota and str(numero_nota).strip(),
            valor_total and float(valor_total) > 0
        ])

    def _get_campos_faltantes(self, doc: DocumentData) -> List[str]:
        """
        Retorna lista de campos obrigatórios que estão faltando.

        Args:
            doc: Documento a verificar

        Returns:
            Lista de nomes de campos faltantes
        """
        faltantes = []

        fornecedor = getattr(doc, 'fornecedor_nome', None)
        if not (fornecedor and str(fornecedor).strip()):
            faltantes.append('fornecedor_nome')

        vencimento = getattr(doc, 'vencimento', None)
        if not (vencimento and str(vencimento).strip()):
            faltantes.append('vencimento')

        numero_nota = getattr(doc, 'numero_nota', None)
        if not (numero_nota and str(numero_nota).strip()):
            faltantes.append('numero_nota')

        valor_total = getattr(doc, 'valor_total', None)
        if not (valor_total and float(valor_total) > 0):
            faltantes.append('valor_total')

        return faltantes

    def _merge_documents(
        self,
        xml_docs: List[DocumentData],
        pdf_docs: List[DocumentData],
        xml_notas_completas: Set[str]
    ) -> List[DocumentData]:
        """
        Mescla documentos XML e PDF priorizando XMLs completos.

        Lógica:
        - Se XML está completo para uma nota, ignora PDF dessa nota
        - Se XML incompleto, tenta complementar com dados do PDF
        - Boletos de PDF são sempre incluídos (não têm XML correspondente)

        Args:
            xml_docs: Documentos extraídos de XMLs
            pdf_docs: Documentos extraídos de PDFs
            xml_notas_completas: Números de nota de XMLs completos

        Returns:
            Lista final de documentos mesclados
        """
        final_docs: List[DocumentData] = []
        pdf_notas_usadas: Set[str] = set()

        # Adiciona todos os XMLs
        for xml_doc in xml_docs:
            numero_nota = getattr(xml_doc, 'numero_nota', None)
            numero_str = str(numero_nota).strip() if numero_nota else ""

            if numero_str in xml_notas_completas:
                # XML completo - usa direto
                final_docs.append(xml_doc)
                pdf_notas_usadas.add(numero_str)
            else:
                # XML incompleto - tenta complementar com PDF
                pdf_complementar = self._find_pdf_for_xml(xml_doc, pdf_docs)
                if pdf_complementar:
                    # Complementa campos faltantes do XML com dados do PDF
                    doc_mesclado = self._complementar_xml_com_pdf(xml_doc, pdf_complementar)
                    final_docs.append(doc_mesclado)
                    # Marca número da nota do PDF como usado
                    pdf_nota = getattr(pdf_complementar, 'numero_nota', None)
                    if pdf_nota:
                        pdf_notas_usadas.add(str(pdf_nota).strip())
                else:
                    # Sem PDF correspondente, usa XML mesmo incompleto
                    final_docs.append(xml_doc)

        # Adiciona PDFs que não foram usados para complementar XMLs
        for pdf_doc in pdf_docs:
            numero_nota = getattr(pdf_doc, 'numero_nota', None)
            numero_str = str(numero_nota).strip() if numero_nota else ""

            # Boletos não têm numero_nota no mesmo sentido, inclui sempre
            from core.models import BoletoData
            if isinstance(pdf_doc, BoletoData):
                final_docs.append(pdf_doc)
                continue

            # Verifica se já foi usado ou se XML completo já cobre essa nota
            if numero_str and numero_str in xml_notas_completas:
                continue

            if numero_str and numero_str in pdf_notas_usadas:
                # Já usado para complementar XML
                continue

            # PDF órfão (sem XML correspondente) - inclui
            final_docs.append(pdf_doc)

        return final_docs

    def _find_pdf_for_xml(
        self,
        xml_doc: DocumentData,
        pdf_docs: List[DocumentData]
    ) -> Optional[DocumentData]:
        """
        Encontra PDF correspondente a um XML para complementação.

        Critérios de match:
        1. Mesmo numero_nota
        2. Mesmo fornecedor + valor (aproximado)

        Args:
            xml_doc: Documento XML incompleto
            pdf_docs: Lista de documentos PDF disponíveis

        Returns:
            Documento PDF correspondente ou None
        """
        xml_nota = getattr(xml_doc, 'numero_nota', None)
        xml_fornecedor = getattr(xml_doc, 'fornecedor_nome', None)
        xml_valor = getattr(xml_doc, 'valor_total', None)

        for pdf_doc in pdf_docs:
            # Só compara notas (não boletos)
            if not isinstance(pdf_doc, (DanfeData, InvoiceData)):
                continue

            # Match por numero_nota
            pdf_nota = getattr(pdf_doc, 'numero_nota', None)
            if xml_nota and pdf_nota:
                if str(xml_nota).strip() == str(pdf_nota).strip():
                    return pdf_doc

            # Match por fornecedor + valor
            pdf_fornecedor = getattr(pdf_doc, 'fornecedor_nome', None)
            pdf_valor = getattr(pdf_doc, 'valor_total', None)

            if xml_fornecedor and pdf_fornecedor and xml_valor and pdf_valor:
                fornecedor_match = self._normalize_fornecedor(xml_fornecedor) == self._normalize_fornecedor(pdf_fornecedor)
                valor_match = abs(float(xml_valor) - float(pdf_valor)) < 0.01

                if fornecedor_match and valor_match:
                    return pdf_doc

        return None

    def _complementar_xml_com_pdf(
        self,
        xml_doc: DocumentData,
        pdf_doc: DocumentData
    ) -> DocumentData:
        """
        Complementa campos faltantes do XML com dados do PDF.

        O XML é a base, PDF só preenche campos vazios.

        Args:
            xml_doc: Documento XML (base)
            pdf_doc: Documento PDF (complemento)

        Returns:
            Documento mesclado
        """
        # Campos a complementar se vazios no XML
        campos_complementar = [
            'fornecedor_nome',
            'vencimento',
            'numero_nota',
            'valor_total',
            'numero_pedido',
            'numero_fatura',
            'data_emissao',
        ]

        for campo in campos_complementar:
            xml_valor = getattr(xml_doc, campo, None)
            pdf_valor = getattr(pdf_doc, campo, None)

            # Se XML não tem o campo mas PDF tem, copia
            if not xml_valor and pdf_valor:
                try:
                    setattr(xml_doc, campo, pdf_valor)
                except AttributeError:
                    pass  # Campo pode ser read-only

        return xml_doc

    def _normalize_fornecedor(self, fornecedor: str) -> str:
        """
        Normaliza nome do fornecedor para comparação.

        Remove quebras de linha, espaços extras, prefixos como "CNPJ".

        Args:
            fornecedor: Nome original do fornecedor

        Returns:
            Nome normalizado
        """
        if not fornecedor:
            return ""

        # Remove quebras de linha e espaços extras
        normalized = " ".join(fornecedor.split())

        # Remove prefixos comuns indesejados
        prefixos_remover = ["CNPJ", "CPF", "RAZÃO SOCIAL", "RAZAO SOCIAL"]
        for prefixo in prefixos_remover:
            if normalized.upper().startswith(prefixo):
                normalized = normalized[len(prefixo):].strip()
                # Remove possível separador após prefixo
                if normalized.startswith(":") or normalized.startswith("-"):
                    normalized = normalized[1:].strip()

        return normalized.strip().upper()

    def _list_files_by_type(self, folder_path: Path) -> Tuple[List[Path], List[Path]]:
        """
        Lista arquivos processáveis separados por tipo (XML e PDF).

        Args:
            folder_path: Pasta a ser listada

        Returns:
            Tupla (xml_files, pdf_files)
        """
        if not folder_path.exists():
            return [], []

        xml_files = []
        pdf_files = []

        for item in sorted(folder_path.iterdir()):
            if item.is_file() and self._is_processable(item):
                if item.suffix.lower() == '.xml':
                    xml_files.append(item)
                elif item.suffix.lower() == '.pdf':
                    pdf_files.append(item)

        return xml_files, pdf_files

    # Timeout padrão para processamento de batch (5 minutos)
    BATCH_TIMEOUT_SECONDS: int = 300

    def process_multiple_batches(
        self,
        root_folder: Union[str, Path],
        apply_correlation: bool = True,
        timeout_seconds: Optional[int] = None
    ) -> List[BatchResult]:
        """
        Processa múltiplas pastas (lotes) de uma vez com timeout por lote.

        Args:
            root_folder: Pasta raiz contendo subpastas de lotes
            apply_correlation: Se True, aplica correlação entre documentos
            timeout_seconds: Timeout por batch em segundos (default: 300 = 5 min)

        Returns:
            Lista de BatchResult, um para cada lote
        """
        import json
        import logging
        import time
        from concurrent.futures import ThreadPoolExecutor
        from concurrent.futures import TimeoutError as FuturesTimeoutError
        from datetime import datetime

        logger = logging.getLogger(__name__)
        timeout = timeout_seconds or self.BATCH_TIMEOUT_SECONDS

        root_folder = Path(root_folder)
        results = []
        timeouts = []  # Lista de batches que deram timeout

        if not root_folder.exists():
            return results

        # Lista lotes para processar
        batch_folders = [item for item in sorted(root_folder.iterdir())
                         if item.is_dir() and not item.name.startswith('.')]
        total_batches = len(batch_folders)

        logger.info(f"⏳ Iniciando processamento de {total_batches} lotes (timeout: {timeout}s)...")
        overall_start = time.time()

        # Processa cada subpasta como um lote com timeout
        for idx, item in enumerate(batch_folders, 1):
            batch_start = time.time()
            batch_result = None

            try:
                # Executa com timeout usando ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.process_batch, item, apply_correlation)
                    batch_result = future.result(timeout=timeout)
                    batch_result.processing_time = time.time() - batch_start
                    batch_result.status = "OK"

            except FuturesTimeoutError:
                # Timeout! Cria resultado vazio com status TIMEOUT
                batch_elapsed = time.time() - batch_start
                logger.error(f"⏱️ [{idx}/{total_batches}] TIMEOUT: {item.name} excedeu {timeout}s!")

                batch_result = BatchResult(
                    batch_id=item.name,
                    source_folder=str(item),
                    status="TIMEOUT",
                    processing_time=batch_elapsed,
                    timeout_error=f"Processamento excedeu {timeout}s"
                )
                batch_result.add_error(str(item), f"TIMEOUT após {batch_elapsed:.1f}s")

                # Registra para log de timeouts
                timeouts.append({
                    "batch_id": item.name,
                    "folder": str(item),
                    "timeout_seconds": timeout,
                    "timestamp": datetime.now().isoformat()
                })

            except Exception as e:
                # Erro genérico
                batch_elapsed = time.time() - batch_start
                logger.error(f"❌ [{idx}/{total_batches}] ERRO: {item.name}: {e}")

                batch_result = BatchResult(
                    batch_id=item.name,
                    source_folder=str(item),
                    status="ERROR",
                    processing_time=batch_elapsed,
                    timeout_error=str(e)
                )
                batch_result.add_error(str(item), str(e))

            results.append(batch_result)
            batch_elapsed = batch_result.processing_time

            # Log de progresso
            if batch_result.status == "TIMEOUT":
                pass  # Já logou acima
            elif batch_result.status == "ERROR":
                pass  # Já logou acima
            elif batch_elapsed > 5:
                logger.warning(f"🐢 [{idx}/{total_batches}] {item.name}: {batch_elapsed:.1f}s (LENTO!)")
            else:
                logger.debug(f"✅ [{idx}/{total_batches}] {item.name}: {batch_elapsed:.1f}s")

        overall_elapsed = time.time() - overall_start
        logger.info(f"⏱️ Tempo total de processamento: {overall_elapsed:.1f}s ({overall_elapsed/60:.1f} min)")

        # Salva log de timeouts para reprocessamento posterior
        if timeouts:
            timeout_log_path = root_folder / "_timeouts.json"
            try:
                # Carrega timeouts anteriores (se existir)
                existing_timeouts = []
                if timeout_log_path.exists():
                    existing_timeouts = json.loads(timeout_log_path.read_text(encoding='utf-8'))

                # Adiciona novos timeouts
                all_timeouts = existing_timeouts + timeouts
                timeout_log_path.write_text(
                    json.dumps(all_timeouts, indent=2, ensure_ascii=False),
                    encoding='utf-8'
                )
                logger.warning(f"⚠️ {len(timeouts)} timeout(s) registrado(s) em {timeout_log_path}")
            except Exception as e:
                logger.error(f"Erro ao salvar log de timeouts: {e}")

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
                doc = result.document

                # Detecta empresa no conteúdo do XML
                # Tenta múltiplos encodings pois alguns XMLs usam Latin-1
                xml_content = None
                for encoding in ('utf-8', 'latin-1', 'cp1252'):
                    try:
                        xml_content = file_path.read_text(encoding=encoding)
                        break
                    except UnicodeDecodeError:
                        continue

                if xml_content:
                    try:
                        empresa_match = find_empresa_no_texto(xml_content)
                        if empresa_match and not getattr(doc, 'empresa', None):
                            doc.empresa = empresa_match.codigo
                    except Exception:
                        pass  # Ignora erros de detecção

                return doc
            else:
                logger.debug(f"Erro ao processar XML {file_path.name}: {result.error}")
                return None

        except Exception as e:
            logger.debug(f"Erro ao processar XML {file_path.name}: {e}")
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
