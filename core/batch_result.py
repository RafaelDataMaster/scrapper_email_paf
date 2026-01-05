"""
Resultado de processamento em lote.

Este módulo define estruturas de dados para armazenar os resultados
do processamento de um lote (pasta de e-mail com múltiplos documentos).

Cada lote representa UMA compra/locação única, então temos:
- valor_compra: valor da compra (não soma de documentos)
- Priorização de XML quando completo (tem todos os campos)
- Fallback para PDF quando XML incompleto

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

    Cada lote representa UMA compra/locação única.

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
    def has_nfse(self) -> bool:
        """Verifica se o lote contém NFS-e."""
        return len(self.nfses) > 0

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

    def get_valor_compra(self) -> float:
        """
        Obtém o valor da compra/locação do lote.

        Cada lote representa UMA compra, então pega o valor da primeira
        nota fiscal encontrada (NFS-e ou DANFE).

        Se não houver nota, usa o valor do primeiro boleto.

        Returns:
            Valor da compra ou 0.0 se não encontrar
        """
        # Prioridade 1: NFS-e
        for nfse in self.nfses:
            if nfse.valor_total and nfse.valor_total > 0:
                return nfse.valor_total

        # Prioridade 2: DANFE
        for danfe in self.danfes:
            if danfe.valor_total and danfe.valor_total > 0:
                return danfe.valor_total

        # Prioridade 3: Outros documentos
        for outro in self.outros:
            if outro.valor_total and outro.valor_total > 0:
                return outro.valor_total

        # Fallback: Boleto
        for boleto in self.boletos:
            if boleto.valor_documento and boleto.valor_documento > 0:
                return boleto.valor_documento

        return 0.0

    def _normalize_fornecedor(self, fornecedor: str) -> str:
        """
        Normaliza nome do fornecedor removendo sujeiras comuns.

        - Remove quebras de linha
        - Remove espaços extras
        - Remove prefixos como "CNPJ", "CPF", "RAZÃO SOCIAL"

        Args:
            fornecedor: Nome original do fornecedor

        Returns:
            Nome limpo e normalizado
        """
        if not fornecedor:
            return ""

        # Remove quebras de linha e espaços extras
        normalized = " ".join(fornecedor.split())

        # Remove prefixos comuns indesejados
        prefixos_remover = ["CNPJ", "CPF", "RAZÃO SOCIAL", "RAZAO SOCIAL", "NOME:"]
        for prefixo in prefixos_remover:
            if normalized.upper().startswith(prefixo):
                normalized = normalized[len(prefixo):].strip()
                # Remove possível separador após prefixo
                if normalized.startswith(":") or normalized.startswith("-"):
                    normalized = normalized[1:].strip()

        return normalized.strip()

    def _get_primeiro_fornecedor(self) -> Optional[str]:
        """
        Extrai o nome do fornecedor priorizando notas fiscais.

        Ordem de prioridade:
        1. NFS-e
        2. DANFE
        3. Outros documentos
        4. Boletos
        """
        # Prioridade 1: NFS-e
        for nfse in self.nfses:
            fornecedor = getattr(nfse, 'fornecedor_nome', None)
            if fornecedor:
                return self._normalize_fornecedor(fornecedor)

        # Prioridade 2: DANFE
        for danfe in self.danfes:
            fornecedor = getattr(danfe, 'fornecedor_nome', None)
            if fornecedor:
                return self._normalize_fornecedor(fornecedor)

        # Prioridade 3: Outros documentos
        for outro in self.outros:
            fornecedor = getattr(outro, 'fornecedor_nome', None)
            if fornecedor:
                return self._normalize_fornecedor(fornecedor)

        # Prioridade 4: Boletos
        for boleto in self.boletos:
            fornecedor = getattr(boleto, 'fornecedor_nome', None)
            if fornecedor:
                return self._normalize_fornecedor(fornecedor)

        return None

    def _get_primeiro_vencimento(self) -> Optional[str]:
        """
        Extrai a data de vencimento priorizando notas e boletos.

        Ordem de prioridade:
        1. NFS-e
        2. DANFE
        3. Boletos (geralmente têm vencimento)
        4. Outros documentos
        """
        # Prioridade 1: NFS-e
        for nfse in self.nfses:
            vencimento = getattr(nfse, 'vencimento', None)
            if vencimento:
                return vencimento

        # Prioridade 2: DANFE
        for danfe in self.danfes:
            vencimento = getattr(danfe, 'vencimento', None)
            if vencimento:
                return vencimento

        # Prioridade 3: Boletos (geralmente têm vencimento)
        for boleto in self.boletos:
            vencimento = getattr(boleto, 'vencimento', None)
            if vencimento:
                return vencimento

        # Prioridade 4: Outros documentos
        for outro in self.outros:
            vencimento = getattr(outro, 'vencimento', None)
            if vencimento:
                return vencimento

        return None

    def _get_primeiro_numero_nota(self) -> Optional[str]:
        """
        Extrai o número da nota/fatura priorizando NFSE e DANFE.

        Ordem de prioridade:
        1. NFS-e (InvoiceData) - numero_nota
        2. DANFE (DanfeData) - numero_nota
        3. Outros documentos - numero_documento
        4. Boletos - numero_documento
        """
        # Primeira passada: prioriza NFSE
        for doc in self.nfses:
            numero = getattr(doc, 'numero_nota', None)
            if numero:
                return numero

        # Segunda passada: prioriza DANFE
        for doc in self.danfes:
            numero = getattr(doc, 'numero_nota', None)
            if numero:
                return numero

        # Terceira passada: outros documentos
        for doc in self.outros:
            numero = getattr(doc, 'numero_documento', None)
            if numero:
                return numero

        # Última opção: boletos
        for doc in self.boletos:
            numero = getattr(doc, 'numero_documento', None)
            if numero:
                return numero

        return None

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
            'fornecedor': self._get_primeiro_fornecedor(),
            'vencimento': self._get_primeiro_vencimento(),
            'numero_nota': self._get_primeiro_numero_nota(),
            'total_documents': self.total_documents,
            'total_errors': self.total_errors,
            'danfes': len(self.danfes),
            'boletos': len(self.boletos),
            'nfses': len(self.nfses),
            'outros': len(self.outros),
            'valor_compra': self.get_valor_compra(),
            'valor_boleto': self.get_valor_total_boletos(),
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

    Armazena o resultado da análise cruzada entre Nota e Boleto,
    incluindo divergências detectadas.

    Lógica de conciliação:
    - Se tem boleto: valor_compra - valor_boleto deve ser 0
    - Se não tem boleto: status = "CONFERIR" (sem boleto para comparação)

    Attributes:
        batch_id: Identificador do lote
        status: Status da conciliação ('OK', 'DIVERGENTE', 'CONFERIR')
        divergencia: Descrição da divergência ou observação
        valor_compra: Valor da compra (da nota)
        valor_boleto: Valor do boleto
        diferenca: Diferença entre valores
    """
    batch_id: str
    status: str = "OK"
    divergencia: Optional[str] = None
    valor_compra: float = 0.0
    valor_boleto: float = 0.0
    diferenca: float = 0.0

    # Dados herdados entre documentos
    vencimento_herdado: Optional[str] = None
    numero_nota_herdado: Optional[str] = None
    numero_pedido_herdado: Optional[str] = None

    # Fonte dos dados herdados (para auditoria)
    numero_nota_fonte: Optional[str] = None  # 'documento', 'email', None

    # Flags de alerta
    sem_vencimento: bool = False
    vencimento_alerta: Optional[str] = None  # Data de alerta quando vencimento não encontrado

    def is_ok(self) -> bool:
        """Verifica se a conciliação está OK."""
        return self.status == "OK"

    def is_divergente(self) -> bool:
        """Verifica se há divergência de valores."""
        return self.status == "DIVERGENTE"

    def is_conferir(self) -> bool:
        """Verifica se precisa conferência manual (sem boleto)."""
        return self.status == "CONFERIR"
