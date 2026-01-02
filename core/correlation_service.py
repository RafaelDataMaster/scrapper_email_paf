"""
Serviço de Correlação entre Documentos.

Este módulo implementa a "Camada Prata" do plano de refatoração,
responsável por cruzar dados entre DANFE e Boleto do mesmo lote.

Regras de Negócio Implementadas:
1. Herança de Dados: Boleto herda numero_nota da DANFE, DANFE herda vencimento do Boleto
2. Fallback de Identificação: Usa metadados do e-mail quando OCR falha
3. Validação Cruzada: Compara valores entre DANFE e Boletos

Princípios SOLID aplicados:
- SRP: Classe focada apenas em correlação/enriquecimento
- OCP: Novas regras podem ser adicionadas via métodos sem alterar existentes
- DIP: Depende de abstrações (DocumentData), não de implementações concretas
"""
from typing import Optional

from core.batch_result import BatchResult, CorrelationResult
from core.metadata import EmailMetadata
from core.models import (
    BoletoData,
    DanfeData,
    DocumentData,
    InvoiceData,
    OtherDocumentData,
)


class CorrelationService:
    """
    Serviço de correlação e enriquecimento de documentos.

    Aplica regras de negócio para cruzar informações entre
    diferentes documentos do mesmo lote (e-mail).

    Usage:
        service = CorrelationService()
        result = service.correlate(batch_result, metadata)
    """

    # Tolerância para comparação de valores (em reais)
    TOLERANCIA_VALOR = 0.01

    def correlate(
        self,
        batch: BatchResult,
        metadata: Optional[EmailMetadata] = None
    ) -> CorrelationResult:
        """
        Executa correlação completa entre documentos do lote.

        Args:
            batch: Resultado do processamento em lote
            metadata: Metadados do e-mail (opcional)

        Returns:
            CorrelationResult com status e dados herdados
        """
        result = CorrelationResult(batch_id=batch.batch_id)

        # 1. Enriquecimento com metadados do e-mail
        if metadata:
            self._enrich_from_metadata(batch, metadata)

        # 2. Herança de dados entre documentos
        self._apply_data_inheritance(batch, result)

        # 3. Validação cruzada de valores
        self._validate_cross_values(batch, result)

        # 4. Propaga status e valor_total_lote para cada documento
        self._propagate_batch_context(batch, result)

        return result

    def _propagate_batch_context(
        self,
        batch: BatchResult,
        result: CorrelationResult
    ) -> None:
        """
        Propaga informações de contexto do lote para cada documento.

        Preenche os campos status_conciliacao e valor_total_lote em cada
        documento, permitindo que a exportação inclua essas informações.

        Args:
            batch: Resultado do processamento em lote
            result: Resultado da correlação com status calculado
        """
        valor_total_lote = batch.get_valor_total_lote()

        for doc in batch.documents:
            doc.status_conciliacao = result.status
            doc.valor_total_lote = valor_total_lote

    def _enrich_from_metadata(
        self,
        batch: BatchResult,
        metadata: EmailMetadata
    ) -> None:
        """
        Enriquece documentos com dados do metadata do e-mail.

        Regra 2 do plano: Fallback de Identificação
        - Se OCR do fornecedor falhou, usa email_sender_name
        - Se CNPJ não foi achado, procura no email_body_text
        - Se numero_pedido não foi achado, procura no assunto/corpo
        """
        # Extrai dados do contexto do e-mail
        fallback_fornecedor = metadata.get_fallback_fornecedor()
        cnpj_from_email = metadata.extract_cnpj_from_body()
        pedido_from_email = metadata.extract_numero_pedido_from_context()

        for doc in batch.documents:
            # Fallback para fornecedor
            if not self._has_fornecedor(doc) and fallback_fornecedor:
                self._set_fornecedor(doc, fallback_fornecedor)

            # Fallback para CNPJ
            if not self._has_cnpj(doc) and cnpj_from_email:
                self._set_cnpj(doc, cnpj_from_email)

            # Fallback para número de pedido
            if not self._has_numero_pedido(doc) and pedido_from_email:
                self._set_numero_pedido(doc, pedido_from_email)

        # Atualiza contexto no batch
        batch.email_subject = metadata.email_subject
        batch.email_sender = metadata.email_sender_name

    def _apply_data_inheritance(
        self,
        batch: BatchResult,
        result: CorrelationResult
    ) -> None:
        """
        Aplica herança de dados entre documentos do mesmo lote.

        Regra 1 do plano: Herança de Dados (Complementação)
        - Boleto herda numero_nota da DANFE (se não conseguiu ler)
        - DANFE herda vencimento do Boleto (ou da primeira parcela)
        """
        danfes = batch.danfes
        boletos = batch.boletos
        nfses = batch.nfses

        # Se tem DANFE e Boleto, faz cruzamento
        if danfes and boletos:
            # Pega o numero_nota da primeira DANFE (geralmente só tem uma)
            numero_nota = None
            for danfe in danfes:
                if danfe.numero_nota:
                    numero_nota = danfe.numero_nota
                    break

            # Pega o vencimento do primeiro boleto
            vencimento = None
            for boleto in boletos:
                if boleto.vencimento:
                    vencimento = boleto.vencimento
                    break

            # Boleto herda numero_nota da DANFE
            if numero_nota:
                for boleto in boletos:
                    if not boleto.referencia_nfse:
                        boleto.referencia_nfse = numero_nota
                result.numero_nota_herdado = numero_nota

            # DANFE herda vencimento do Boleto
            if vencimento:
                for danfe in danfes:
                    if not danfe.vencimento:
                        danfe.vencimento = vencimento
                result.vencimento_herdado = vencimento

        # Se tem NFSe e Boleto, também faz cruzamento
        if nfses and boletos:
            # Pega o numero_nota da primeira NFSe
            numero_nota = None
            for nfse in nfses:
                if nfse.numero_nota:
                    numero_nota = nfse.numero_nota
                    break

            # Pega o vencimento do primeiro boleto
            vencimento = None
            for boleto in boletos:
                if boleto.vencimento:
                    vencimento = boleto.vencimento
                    break

            # Boleto herda numero_nota da NFSe
            if numero_nota:
                for boleto in boletos:
                    if not boleto.referencia_nfse:
                        boleto.referencia_nfse = numero_nota
                if not result.numero_nota_herdado:
                    result.numero_nota_herdado = numero_nota

            # NFSe herda vencimento do Boleto
            if vencimento:
                for nfse in nfses:
                    if not nfse.vencimento:
                        nfse.vencimento = vencimento
                if not result.vencimento_herdado:
                    result.vencimento_herdado = vencimento

        # Herança de numero_pedido entre todos os documentos
        numero_pedido = self._find_numero_pedido_in_batch(batch)
        if numero_pedido:
            self._propagate_numero_pedido(batch, numero_pedido)
            result.numero_pedido_herdado = numero_pedido

    def _validate_cross_values(
        self,
        batch: BatchResult,
        result: CorrelationResult
    ) -> None:
        """
        Valida valores cruzados entre documentos.

        Regra 3 do plano: Validação Cruzada (Auditoria)
        - Soma valor dos Boletos
        - Compara com valor_total da DANFE/NFSe
        - Define status_conciliacao
        """
        valor_notas = batch.get_valor_total_danfes() + batch.get_valor_total_nfses()
        valor_boletos = batch.get_valor_total_boletos()

        result.danfe_valor = valor_notas
        result.boleto_valor = valor_boletos
        result.diferenca = abs(valor_notas - valor_boletos)

        # Determina status de conciliação
        if batch.has_boleto and not batch.has_danfe and not batch.nfses:
            # Só boleto, sem nota = órfão
            result.status = "ORFAO"
            result.divergencia = "Boleto sem nota fiscal correspondente"
        elif valor_notas > 0 and valor_boletos > 0:
            # Tem ambos, compara valores
            if result.diferenca <= self.TOLERANCIA_VALOR:
                result.status = "OK"
            else:
                result.status = "DIVERGENTE"
                result.divergencia = (
                    f"Valor nota: R$ {valor_notas:.2f} | "
                    f"Valor boletos: R$ {valor_boletos:.2f} | "
                    f"Diferença: R$ {result.diferenca:.2f}"
                )
        elif valor_notas > 0 and valor_boletos == 0:
            # Nota sem boleto
            result.status = "OK"
            result.divergencia = "Nota fiscal sem boleto (pagamento pode ser diferente)"
        else:
            # Nenhum valor encontrado
            result.status = "OK"

    def _find_numero_pedido_in_batch(self, batch: BatchResult) -> Optional[str]:
        """Procura numero_pedido em qualquer documento do lote."""
        for doc in batch.documents:
            pedido = self._get_numero_pedido(doc)
            if pedido:
                return pedido
        return None

    def _propagate_numero_pedido(self, batch: BatchResult, numero_pedido: str) -> None:
        """Propaga numero_pedido para todos os documentos que não têm."""
        for doc in batch.documents:
            if not self._get_numero_pedido(doc):
                self._set_numero_pedido(doc, numero_pedido)

    # === Métodos auxiliares de acesso a campos ===
    # Encapsulam diferenças entre tipos de documento (polimorfismo)

    def _has_fornecedor(self, doc: DocumentData) -> bool:
        """Verifica se documento tem fornecedor preenchido."""
        if isinstance(doc, (DanfeData, InvoiceData, OtherDocumentData)):
            return bool(doc.fornecedor_nome and doc.fornecedor_nome.strip())
        if isinstance(doc, BoletoData):
            return bool(doc.fornecedor_nome and doc.fornecedor_nome.strip())
        return False

    def _set_fornecedor(self, doc: DocumentData, value: str) -> None:
        """Define fornecedor no documento."""
        if isinstance(doc, (DanfeData, InvoiceData, OtherDocumentData, BoletoData)):
            doc.fornecedor_nome = value

    def _has_cnpj(self, doc: DocumentData) -> bool:
        """Verifica se documento tem CNPJ preenchido."""
        if isinstance(doc, DanfeData):
            return bool(doc.cnpj_emitente)
        if isinstance(doc, InvoiceData):
            return bool(doc.cnpj_prestador)
        if isinstance(doc, OtherDocumentData):
            return bool(doc.cnpj_fornecedor)
        if isinstance(doc, BoletoData):
            return bool(doc.cnpj_beneficiario)
        return False

    def _set_cnpj(self, doc: DocumentData, value: str) -> None:
        """Define CNPJ no documento."""
        if isinstance(doc, DanfeData):
            doc.cnpj_emitente = value
        elif isinstance(doc, InvoiceData):
            doc.cnpj_prestador = value
        elif isinstance(doc, OtherDocumentData):
            doc.cnpj_fornecedor = value
        elif isinstance(doc, BoletoData):
            doc.cnpj_beneficiario = value

    def _has_numero_pedido(self, doc: DocumentData) -> bool:
        """Verifica se documento tem numero_pedido preenchido."""
        if isinstance(doc, (DanfeData, InvoiceData, BoletoData)):
            return bool(doc.numero_pedido)
        return False

    def _get_numero_pedido(self, doc: DocumentData) -> Optional[str]:
        """Obtém numero_pedido do documento."""
        if isinstance(doc, (DanfeData, InvoiceData, BoletoData)):
            return doc.numero_pedido
        return None

    def _set_numero_pedido(self, doc: DocumentData, value: str) -> None:
        """Define numero_pedido no documento."""
        if isinstance(doc, (DanfeData, InvoiceData, BoletoData)):
            doc.numero_pedido = value


def correlate_batch(
    batch: BatchResult,
    metadata: Optional[EmailMetadata] = None
) -> CorrelationResult:
    """
    Função utilitária para correlacionar um lote.

    Wrapper simples para uso direto sem instanciar a classe.

    Args:
        batch: Resultado do processamento em lote
        metadata: Metadados do e-mail (opcional)

    Returns:
        CorrelationResult com status e dados herdados
    """
    service = CorrelationService()
    return service.correlate(batch, metadata)
