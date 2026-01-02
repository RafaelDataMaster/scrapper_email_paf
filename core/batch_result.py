"""
Resultado de processamento em lote.

Este módulo define estruturas de dados para armazenar os resultados
do processamento de um lote (pasta de e-mail com múltiplos documentos).

Princípios SOLID aplicados:
- SRP: Classe focada apenas em resultados de lote
- OCP: Extensível via composição sem modificar código existente
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.models import (
    BoletoData,
    DanfeData,
    DocumentData,
    InvoiceData,
    OtherDocumentData,
)

if TYPE_CHECKING:
    from core.batch_result import CorrelationResult


@dataclass
class BatchResult:
    """
    Resultado do processamento de um lote de documentos.

    Agrupa todos os documentos extraídos de uma pasta de e-mail,
    mantendo rastreabilidade e permitindo correlação posterior.

    Attributes:
        batch_id: Identificador único do lote (pasta)
        documents: Lista de documentos extraídos
        errors: Lista de erros ocorridos durante processamento
        metadata_path: Caminho do metadata.json (se existir)
        source_folder: Pasta de origem do lote
    """
    batch_id: str
    documents: List[DocumentData] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metadata_path: Optional[str] = None
    source_folder: Optional[str] = None

    # Campos de contexto enriquecido (vindos do metadata.json)
    email_subject: Optional[str] = None
    email_sender: Optional[str] = None

    # Resultado da correlação (preenchido após correlate())
    correlation_result: Optional[CorrelationResult] = None

    def add_document(self, doc: DocumentData) -> None:
        """Adiciona um documento ao lote."""
        self.documents.append(doc)

    def add_error(self, file_path: str, error_msg: str) -> None:
        """Registra um erro de processamento."""
        self.errors.append({
            'file': file_path,
            'error': error_msg
        })

    @property
    def danfes(self) -> List[DanfeData]:
        """Retorna apenas DANFEs do lote."""
        return [d for d in self.documents if isinstance(d, DanfeData)]

    @property
    def boletos(self) -> List[BoletoData]:
        """Retorna apenas Boletos do lote."""
        return [d for d in self.documents if isinstance(d, BoletoData)]

    @property
    def nfses(self) -> List[InvoiceData]:
        """Retorna apenas NFSes do lote."""
        return [d for d in self.documents if isinstance(d, InvoiceData)]

    @property
    def outros(self) -> List[OtherDocumentData]:
        """Retorna apenas documentos 'Outros' do lote."""
        return [d for d in self.documents if isinstance(d, OtherDocumentData)]

    @property
    def total_documents(self) -> int:
        """Total de documentos processados."""
        return len(self.documents)

    @property
    def total_errors(self) -> int:
        """Total de erros ocorridos."""
        return len(self.errors)

    @property
    def has_danfe(self) -> bool:
        """Verifica se o lote contém DANFE."""
        return len(self.danfes) > 0

    @property
    def has_boleto(self) -> bool:
        """Verifica se o lote contém Boleto."""
        return len(self.boletos) > 0

    @property
    def is_empty(self) -> bool:
        """Verifica se o lote está vazio."""
        return self.total_documents == 0

    def get_valor_total_danfes(self) -> float:
        """Soma o valor total de todas as DANFEs do lote."""
        return sum(d.valor_total or 0.0 for d in self.danfes)

    def get_valor_total_boletos(self) -> float:
        """Soma o valor total de todos os Boletos do lote."""
        return sum(b.valor_documento or 0.0 for b in self.boletos)

    def get_valor_total_nfses(self) -> float:
        """Soma o valor total de todas as NFSes do lote."""
        return sum(n.valor_total or 0.0 for n in self.nfses)

    def get_valor_total_lote(self) -> float:
        """Soma o valor total de todos os documentos do lote."""
        total = 0.0
        for doc in self.documents:
            if isinstance(doc, (DanfeData, InvoiceData, OtherDocumentData)):
                total += doc.valor_total or 0.0
            elif isinstance(doc, BoletoData):
                total += doc.valor_documento or 0.0
        return total

    def to_summary(self) -> Dict[str, Any]:
        """
        Gera um resumo do lote para relatórios.

        Returns:
            Dicionário com estatísticas do lote
        """
        summary = {
            'batch_id': self.batch_id,
            'source_folder': self.source_folder,
            'email_subject': self.email_subject,
            'email_sender': self.email_sender,
            'total_documents': self.total_documents,
            'total_errors': self.total_errors,
            'danfes': len(self.danfes),
            'boletos': len(self.boletos),
            'nfses': len(self.nfses),
            'outros': len(self.outros),
            'valor_total_lote': self.get_valor_total_lote(),
            'valor_danfes': self.get_valor_total_danfes(),
            'valor_boletos': self.get_valor_total_boletos(),
        }

        # Adiciona dados de conciliação se disponível
        if self.correlation_result:
            summary['status_conciliacao'] = self.correlation_result.status
            summary['divergencia'] = self.correlation_result.divergencia
            summary['diferenca_valor'] = self.correlation_result.diferenca

        return summary


@dataclass
class CorrelationResult:
    """
    Resultado da correlação entre documentos de um lote.

    Armazena o resultado da análise cruzada entre DANFE e Boleto,
    incluindo divergências detectadas.

    Attributes:
        batch_id: Identificador do lote
        status: Status da conciliação ('OK', 'DIVERGENTE', 'ORFAO')
        divergencia: Descrição da divergência (se houver)
        danfe_valor: Valor total das DANFEs
        boleto_valor: Valor total dos Boletos
        diferenca: Diferença absoluta entre valores
    """
    batch_id: str
    status: str = "OK"
    divergencia: Optional[str] = None
    danfe_valor: float = 0.0
    boleto_valor: float = 0.0
    diferenca: float = 0.0

    # Dados herdados entre documentos
    vencimento_herdado: Optional[str] = None
    numero_nota_herdado: Optional[str] = None
    numero_pedido_herdado: Optional[str] = None

    def is_ok(self) -> bool:
        """Verifica se a conciliação está OK."""
        return self.status == "OK"

    def is_divergente(self) -> bool:
        """Verifica se há divergência de valores."""
        return self.status == "DIVERGENTE"

    def is_orfao(self) -> bool:
        """Verifica se é documento órfão (boleto sem nota)."""
        return self.status == "ORFAO"
