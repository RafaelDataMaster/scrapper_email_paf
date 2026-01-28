"""
Resultado de processamento em lote.

Este módulo define estruturas de dados para armazenar os resultados
do processamento de um lote (pasta de e-mail com múltiplos documentos).

Cada lote pode conter MÚLTIPLAS compras/locações (múltiplas NFs + boletos),
então o método to_summaries() gera um resumo para cada par NF↔Boleto.

Funcionalidades:
- Pareamento inteligente NF↔Boleto por número da nota ou valor
- Separação de múltiplas notas do mesmo email em linhas distintas
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
    EmailAvisoData,
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
    email_date: Optional[str] = None  # Data de recebimento do email (ISO format)

    # Resultado da correlação (preenchido após correlate())
    correlation_result: Optional[CorrelationResult] = None

    # Status de processamento (OK, TIMEOUT, ERROR)
    status: str = "OK"
    processing_time: float = 0.0
    timeout_error: Optional[str] = None

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
    def avisos(self) -> List[EmailAvisoData]:
        """Retorna apenas Avisos (e-mails sem anexo) do lote."""
        return [d for d in self.documents if isinstance(d, EmailAvisoData)]

    @property
    def has_aviso(self) -> bool:
        """Verifica se o lote contém Aviso (e-mail sem anexo)."""
        return len(self.avisos) > 0

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
        valor, _ = self.get_valor_compra_fonte()
        return valor

    def get_valor_compra_fonte(self) -> tuple:
        """
        Obtém o valor da compra/locação do lote e identifica a fonte.

        Cada lote representa UMA compra, então pega o valor da primeira
        nota fiscal encontrada (NFS-e ou DANFE).

        Se não houver nota, usa o valor de OUTROS ou Boleto.

        Returns:
            Tupla (valor: float, fonte: str) onde fonte é:
            - 'NFSE': Valor veio de NFS-e (confiável)
            - 'DANFE': Valor veio de DANFE (confiável)
            - 'OUTROS': Valor veio de documento genérico (menos confiável)
            - 'BOLETO': Valor veio do boleto (fallback)
            - None: Nenhum valor encontrado
        """
        # Prioridade 1: NFS-e
        for nfse in self.nfses:
            if nfse.valor_total and nfse.valor_total > 0:
                return (nfse.valor_total, 'NFSE')

        # Prioridade 2: DANFE
        for danfe in self.danfes:
            if danfe.valor_total and danfe.valor_total > 0:
                return (danfe.valor_total, 'DANFE')

        # Prioridade 3: Outros documentos
        for outro in self.outros:
            if outro.valor_total and outro.valor_total > 0:
                return (outro.valor_total, 'OUTROS')

        # Fallback: Boleto
        for boleto in self.boletos:
            if boleto.valor_documento and boleto.valor_documento > 0:
                return (boleto.valor_documento, 'BOLETO')

        return (0.0, None)

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

    def get_primeiro_vencimento(self) -> Optional[str]:
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

    def get_primeiro_numero_nota(self) -> Optional[str]:
        """
        Extrai o número da nota/fatura priorizando NFSE e DANFE.

        Ordem de prioridade:
        1. NFS-e (InvoiceData) - numero_nota
        2. DANFE (DanfeData) - numero_nota
        3. Fallback para numero_pedido ou numero_fatura em NFSE/DANFE
        4. Outros documentos - numero_documento
        5. Boletos - numero_documento
        """
        # Primeira passada: prioriza NFSE com numero_nota
        for doc in self.nfses:
            numero = getattr(doc, 'numero_nota', None)
            if numero:
                return numero

        # Segunda passada: prioriza DANFE com numero_nota
        for doc in self.danfes:
            numero = getattr(doc, 'numero_nota', None)
            if numero:
                return numero

        # Terceira passada: fallback para numero_pedido ou numero_fatura em NFSE
        for doc in self.nfses:
            numero_pedido = getattr(doc, 'numero_pedido', None)
            if numero_pedido:
                return numero_pedido
            numero_fatura = getattr(doc, 'numero_fatura', None)
            if numero_fatura:
                return numero_fatura

        # Quarta passada: fallback para numero_pedido ou numero_fatura em DANFE
        for doc in self.danfes:
            numero_pedido = getattr(doc, 'numero_pedido', None)
            if numero_pedido:
                return numero_pedido
            numero_fatura = getattr(doc, 'numero_fatura', None)
            if numero_fatura:
                return numero_fatura

        # Quinta passada: outros documentos
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
        Gera um resumo do lote para relatórios (compatibilidade).

        NOTA: Para lotes com múltiplas NFs, use to_summaries() que retorna
        uma lista de resumos, um para cada par NF↔Boleto.

        Returns:
            Dicionário com estatísticas do lote
        """
        vencimento = self.get_primeiro_vencimento()
        # Não aplica fallback - deixa vencimento vazio/nulo se não encontrado

        summary = {
            'batch_id': self.batch_id,
            'source_folder': self.source_folder,
            'email_subject': self.email_subject,
            'email_sender': self.email_sender,
            'fornecedor': self._get_primeiro_fornecedor(),
            'vencimento': vencimento,
            'numero_nota': self.get_primeiro_numero_nota(),
            'total_documents': self.total_documents,
            'total_errors': self.total_errors,
            'danfes': len(self.danfes),
            'boletos': len(self.boletos),
            'nfses': len(self.nfses),
            'outros': len(self.outros),
            'avisos': len(self.avisos),
            'valor_compra': self.get_valor_compra(),
            'valor_boleto': self.get_valor_total_boletos(),
        }

        # Adiciona dados de conciliação se disponível
        if self.correlation_result:
            summary['status_conciliacao'] = self.correlation_result.status
            summary['divergencia'] = self.correlation_result.divergencia
            summary['diferenca_valor'] = self.correlation_result.diferenca

        return summary

    def to_summaries(self) -> List[Dict[str, Any]]:
        """
        Gera lista de resumos do lote, um para cada par NF↔Boleto.

        Esta função usa o serviço de pareamento para identificar pares
        de documentos (NF + Boleto) e gera um resumo separado para cada.

        Casos tratados:
        - 1 NF + 1 Boleto → 1 resumo
        - 2 NFs + 2 Boletos pareados → 2 resumos
        - 1 NF sem boleto → 1 resumo com status CONFERIR
        - Documentos sem par → agrupados por valor

        Returns:
            Lista de dicionários com estatísticas de cada par
        """
        from core.document_pairing import pair_batch_documents

        # Usa o serviço de pareamento
        pairs = pair_batch_documents(self)

        # Converte cada par para o formato de resumo
        summaries = []
        for pair in pairs:
            summary = pair.to_summary()
            summaries.append(summary)

        return summaries

    def has_multiple_invoices(self) -> bool:
        """
        Verifica se o lote contém múltiplas notas fiscais.

        Útil para decidir se deve usar to_summary() ou to_summaries().

        Returns:
            True se há mais de uma nota fiscal no lote
        """
        total_notas = len(self.nfses) + len(self.danfes)
        # Conta também "outros" que tenham valor (podem ser faturas)
        for outro in self.outros:
            if outro.valor_total and outro.valor_total > 0:
                total_notas += 1
        return total_notas > 1

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializa o BatchResult para dicionário.

        Returns:
            Dicionário serializável em JSON
        """
        return {
            "batch_id": self.batch_id,
            "email_subject": self.email_subject,
            "email_sender": self.email_sender,
            "source_folder": self.source_folder,
            "status": self.status,
            "processing_time": self.processing_time,
            "documents": [doc.to_dict() for doc in self.documents],
            "errors": self.errors,
            "metadata_path": self.metadata_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchResult":
        """
        Reconstrói um BatchResult a partir de um dicionário.

        Usado para carregar resultados parciais salvos em JSONL.

        Args:
            data: Dicionário com dados do batch

        Returns:
            Instância de BatchResult
        """
        # Cria instância básica
        batch = cls(
            batch_id=data.get("batch_id", "unknown"),
            email_subject=data.get("email_subject"),
            email_sender=data.get("email_sender"),
            source_folder=data.get("source_folder"),
            status=data.get("status", "OK"),
            processing_time=data.get("processing_time", 0.0),
            metadata_path=data.get("metadata_path"),
            errors=data.get("errors", []),
        )

        # Reconstrói documentos a partir dos dicts
        for doc_dict in data.get("documents", []):
            doc = cls._document_from_dict(doc_dict)
            if doc:
                batch.documents.append(doc)

        return batch

    @staticmethod
    def _document_from_dict(doc_dict: Dict[str, Any]) -> Optional[DocumentData]:
        """
        Reconstrói um DocumentData a partir de um dicionário.

        Args:
            doc_dict: Dicionário com dados do documento

        Returns:
            Instância do tipo correto de DocumentData ou None
        """
        doc_type = doc_dict.get("tipo_documento") or doc_dict.get("doc_type", "")

        try:
            if doc_type == "BOLETO":
                return BoletoData(
                    arquivo_origem=doc_dict.get("arquivo_origem", ""),
                    fornecedor_nome=doc_dict.get("fornecedor_nome"),
                    valor_documento=doc_dict.get("valor_documento") or 0.0,
                    vencimento=doc_dict.get("vencimento"),
                    numero_documento=doc_dict.get("numero_documento"),
                    linha_digitavel=doc_dict.get("linha_digitavel"),
                    nosso_numero=doc_dict.get("nosso_numero"),
                    banco_nome=doc_dict.get("banco_nome"),
                    empresa=doc_dict.get("empresa"),
                )
            elif doc_type == "DANFE":
                return DanfeData(
                    arquivo_origem=doc_dict.get("arquivo_origem", ""),
                    fornecedor_nome=doc_dict.get("fornecedor_nome"),
                    cnpj_emitente=doc_dict.get("cnpj_prestador") or doc_dict.get("fornecedor_cnpj"),
                    valor_total=doc_dict.get("valor_total") or 0.0,
                    numero_nota=doc_dict.get("numero_nota"),
                    chave_acesso=doc_dict.get("chave_acesso"),
                    data_emissao=doc_dict.get("data_emissao"),
                    empresa=doc_dict.get("empresa"),
                )
            elif doc_type == "NFSE":
                return InvoiceData(
                    arquivo_origem=doc_dict.get("arquivo_origem", ""),
                    fornecedor_nome=doc_dict.get("fornecedor_nome"),
                    cnpj_prestador=doc_dict.get("cnpj_emitente") or doc_dict.get("fornecedor_cnpj"),
                    valor_total=doc_dict.get("valor_total") or 0.0,
                    numero_nota=doc_dict.get("numero_nota"),
                    data_emissao=doc_dict.get("data_emissao"),
                    vencimento=doc_dict.get("vencimento"),
                    empresa=doc_dict.get("empresa"),
                )
            elif doc_type == "AVISO":
                return EmailAvisoData(
                    arquivo_origem=doc_dict.get("arquivo_origem", ""),
                    link_nfe=doc_dict.get("link_nfe"),
                    codigo_verificacao=doc_dict.get("codigo_verificacao"),
                    email_subject_full=doc_dict.get("email_subject"),
                    fornecedor_nome=doc_dict.get("fornecedor_nome"),
                    empresa=doc_dict.get("empresa"),
                )
            else:
                # Tipo desconhecido, usa OtherDocumentData
                return OtherDocumentData(
                    arquivo_origem=doc_dict.get("arquivo_origem", ""),
                    fornecedor_nome=doc_dict.get("fornecedor_nome"),
                    valor_total=doc_dict.get("valor_total") or 0.0,
                    empresa=doc_dict.get("empresa"),
                )
        except Exception:
            return None


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
    status: str = "CONCILIADO"
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
        """Verifica se a conciliação está OK (CONCILIADO)."""
        return self.status == "CONCILIADO"

    def is_divergente(self) -> bool:
        """Verifica se há divergência de valores."""
        return self.status == "DIVERGENTE"

    def is_conferir(self) -> bool:
        """Verifica se precisa conferência manual (sem boleto)."""
        return self.status == "CONFERIR"
