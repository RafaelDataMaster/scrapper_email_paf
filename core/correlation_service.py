"""
Serviço de Correlação entre Documentos.

Este módulo implementa a "Camada Prata" do plano de refatoração,
responsável por cruzar dados entre Nota e Boleto do mesmo lote.

Regras de Negócio Implementadas:
1. Herança de Dados: Boleto herda numero_nota da Nota, Nota herda vencimento do Boleto
2. Fallback de Identificação: Usa metadados do e-mail quando OCR falha
3. Validação Cruzada: valor_compra - valor_boleto = 0 → OK
4. Sem Boleto: status = "CONFERIR" (conferir valor - sem boleto para comparação)
5. Sem Vencimento: Alerta + data de processamento como vencimento de alerta
5. Detecção de Duplicatas: Identifica encaminhamentos duplicados de e-mail

Princípios SOLID aplicados:
- SRP: Classe focada apenas em correlação/enriquecimento
- OCP: Novas regras podem ser adicionadas via métodos sem alterar existentes
- DIP: Depende de abstrações (DocumentData), não de implementações concretas
"""
from typing import Dict, List, Optional, Set, Tuple

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

    Cada lote representa UMA compra/locação única.

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

        # 2. Herança de dados entre documentos (passa metadata para fallback de vencimento)
        self._apply_data_inheritance(batch, result, metadata)

        # 3. Detecta documentos duplicados (encaminhamentos duplicados)
        duplicatas = self._detect_duplicate_documents(batch)

        # 4. Validação cruzada de valores (compara com boleto)
        self._validate_cross_values(batch, result, duplicatas)

        # 5. Verifica se lote ficou sem vencimento após toda herança
        vencimento_final = batch._get_primeiro_vencimento()
        if not vencimento_final:
            result.sem_vencimento = True

        # 6. Adiciona alerta de vencimento não encontrado se necessário
        self._apply_vencimento_alerta(batch, result)

        # 7. Propaga status e valor_compra para cada documento
        self._propagate_batch_context(batch, result)

        return result

    def _propagate_batch_context(
        self,
        batch: BatchResult,
        result: CorrelationResult
    ) -> None:
        """
        Propaga informações de contexto do lote para cada documento.

        Preenche os campos status_conciliacao e valor_compra em cada
        documento, permitindo que a exportação inclua essas informações.

        Args:
            batch: Resultado do processamento em lote
            result: Resultado da correlação com status calculado
        """
        valor_compra = batch.get_valor_compra()

        for doc in batch.documents:
            doc.status_conciliacao = result.status
            doc.valor_compra = valor_compra

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

        NOTA: Vencimento do email é aplicado DEPOIS da herança de documentos
        (em _apply_data_inheritance) para garantir que boleto tem prioridade.
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

            # NOTA: Vencimento do email é aplicado em _apply_data_inheritance
            # como fallback FINAL, após herança de dados do boleto

        # Atualiza contexto no batch
        batch.email_subject = metadata.email_subject
        # Usa email_sender_name, com fallback para email_sender_address se vazio
        batch.email_sender = metadata.email_sender_name or metadata.email_sender_address

    def _apply_data_inheritance(
        self,
        batch: BatchResult,
        result: CorrelationResult,
        metadata: Optional[EmailMetadata] = None
    ) -> None:
        """
        Aplica herança de dados entre documentos do mesmo lote.

        Regra 1 do plano: Herança de Dados (Complementação)
        - Boleto herda numero_nota da Nota (se não conseguiu ler)
        - Nota herda vencimento do Boleto (ou da primeira parcela)
        - Se nenhum documento tem vencimento, usa vencimento do e-mail (fallback final)
        """
        danfes = batch.danfes
        boletos = batch.boletos
        nfses = batch.nfses
        outros = batch.outros

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

        #Fallback pra pegar o numero da nota do numero do documento do outros
        if outros and boletos:
            numero_nota = None
            for outro in outros:
                if outro.numero_documento:
                    numero_nota = outro.numero_documento
                    break

            if numero_nota:
                for boleto in boletos:
                    if not boleto.referencia_nfse:
                        boleto.referencia_nfse = numero_nota
                if not result.numero_nota_herdado:
                    result.numero_nota_herdado = numero_nota

        # Fallback final: Se nenhum documento tem vencimento, tenta extrair do e-mail
        if not result.vencimento_herdado and metadata:
            vencimento_from_email = metadata.extra.get('vencimento_from_email')
            if not vencimento_from_email:
                vencimento_from_email = metadata.extract_vencimento_from_context()

            if vencimento_from_email:
                # Normaliza para formato ISO
                vencimento_iso = self._normalize_vencimento_to_iso(vencimento_from_email)
                # Propaga vencimento do e-mail para todos os documentos sem vencimento
                for doc in batch.documents:
                    if not self._has_vencimento(doc):
                        self._set_vencimento(doc, vencimento_from_email)
                result.vencimento_herdado = vencimento_iso

        # Herança de numero_pedido entre todos os documentos
        numero_pedido = self._find_numero_pedido_in_batch(batch)
        if numero_pedido:
            self._propagate_numero_pedido(batch, numero_pedido)
            result.numero_pedido_herdado = numero_pedido

        # Fallback: Se nenhum documento tem numero_nota, tenta extrair do e-mail
        numero_nota_batch = batch._get_primeiro_numero_nota()
        if not numero_nota_batch and metadata:
            numero_nota_from_email = metadata.extract_numero_nota_from_context()
            if numero_nota_from_email:
                # Propaga numero_nota do e-mail para documentos sem numero_nota
                self._propagate_numero_nota_from_email(batch, numero_nota_from_email)
                result.numero_nota_herdado = numero_nota_from_email
                result.numero_nota_fonte = 'email'

    def _detect_duplicate_documents(
        self,
        batch: BatchResult
    ) -> Dict[str, List[str]]:
        """
        Detecta documentos duplicados no lote (encaminhamentos duplicados de e-mail).

        Identifica documentos com mesmo número de nota ou mesma combinação
        de fornecedor+valor, que indicam encaminhamento duplicado do mesmo e-mail.

        Args:
            batch: Resultado do processamento em lote

        Returns:
            Dicionário com tipo de duplicata e lista de identificadores duplicados
            Ex: {'numero_nota': ['12345'], 'fornecedor_valor': ['EMPRESA X/1500.00']}
        """
        duplicatas: Dict[str, List[str]] = {
            'numero_nota': [],
            'fornecedor_valor': []
        }

        # Detecta duplicatas por número de nota
        notas_vistas: Dict[str, int] = {}
        for doc in batch.documents:
            numero = getattr(doc, 'numero_nota', None)
            if numero:
                numero_str = str(numero).strip()
                notas_vistas[numero_str] = notas_vistas.get(numero_str, 0) + 1

        for nota, count in notas_vistas.items():
            if count > 1:
                duplicatas['numero_nota'].append(nota)

        # Detecta duplicatas por fornecedor + valor
        forn_valor_vistas: Dict[str, int] = {}
        for doc in batch.documents:
            fornecedor = getattr(doc, 'fornecedor_nome', None)
            valor = getattr(doc, 'valor_total', None) or getattr(doc, 'valor_documento', None)
            if fornecedor and valor:
                # Normaliza para comparação
                forn_norm = " ".join(fornecedor.split()).upper()[:30]  # Primeiros 30 chars
                key = f"{forn_norm}/{round(float(valor), 2)}"
                forn_valor_vistas[key] = forn_valor_vistas.get(key, 0) + 1

        for key, count in forn_valor_vistas.items():
            if count > 1 and key not in [f"{n}" for n in duplicatas['numero_nota']]:
                duplicatas['fornecedor_valor'].append(key)

        return duplicatas

    def _validate_cross_values(
        self,
        batch: BatchResult,
        result: CorrelationResult,
        duplicatas: Optional[Dict[str, List[str]]] = None
    ) -> None:
        """
        Valida valores cruzados entre documentos.

        Regra de conciliação:
        - Se tem boleto: valor_compra - valor_boleto = 0 → OK, senão DIVERGENTE
        - Se não tem boleto: CONFERIR (conferir valor - sem boleto para comparação)
        - Adiciona aviso de encaminhamento duplicado se detectado
        """
        duplicatas = duplicatas or {}
        valor_compra = batch.get_valor_compra()
        valor_boleto = batch.get_valor_total_boletos()

        result.valor_compra = valor_compra
        result.valor_boleto = valor_boleto
        result.diferenca = round(valor_compra - valor_boleto, 2)

        # Monta aviso de duplicatas se houver
        aviso_duplicata = ""
        if duplicatas.get('numero_nota'):
            aviso_duplicata = f" [ENCAMINHAMENTO DUPLICADO - notas: {', '.join(duplicatas['numero_nota'])}]"
        elif duplicatas.get('fornecedor_valor'):
            aviso_duplicata = f" [ENCAMINHAMENTO DUPLICADO - mesmos valores detectados]"

        # Determina status de conciliação
        if batch.has_boleto:
            # Tem boleto - compara valores
            if abs(result.diferenca) <= self.TOLERANCIA_VALOR:
                result.status = "CONCILIADO"
                if aviso_duplicata:
                    result.divergencia = aviso_duplicata.strip(" []")
            else:
                result.status = "DIVERGENTE"
                result.divergencia = (
                    f"Valor compra: R$ {valor_compra:.2f} | "
                    f"Valor boleto: R$ {valor_boleto:.2f} | "
                    f"Diferença: R$ {result.diferenca:.2f}"
                ) + aviso_duplicata
        else:
            # Sem boleto - precisa conferir manualmente
            result.status = "CONFERIR"
            result.divergencia = f"Conferir valor (R$ {valor_compra:.2f}) - sem boleto para comparação" + aviso_duplicata

    def _apply_vencimento_alerta(
        self,
        batch: BatchResult,
        result: CorrelationResult
    ) -> None:
        """
        Aplica alerta de vencimento não encontrado.

        Se nenhum documento tem vencimento após toda herança,
        adiciona aviso na divergência mas deixa vencimento vazio/nulo.
        """
        if not result.sem_vencimento:
            return

        aviso_vencimento = " [VENCIMENTO NÃO ENCONTRADO - verificar urgente]"

        if result.divergencia:
            result.divergencia += aviso_vencimento
        else:
            result.divergencia = aviso_vencimento.strip()

        # Não propaga data de alerta - deixa vencimento vazio/nulo
        # result.vencimento_alerta permanece None
        # result.vencimento_herdado permanece None

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

    def _propagate_numero_nota_from_email(self, batch: BatchResult, numero_nota: str) -> None:
        """
        Propaga numero_nota extraído do e-mail para documentos que não têm.

        Este é um fallback final quando nenhum documento do lote possui
        numero_nota extraído do próprio documento (PDF/XML).

        Args:
            batch: Lote de documentos
            numero_nota: Número da nota/fatura extraído do e-mail
        """
        for doc in batch.documents:
            if not self._has_numero_nota(doc):
                self._set_numero_nota(doc, numero_nota)

    def _has_numero_nota(self, doc: DocumentData) -> bool:
        """Verifica se documento tem numero_nota preenchido."""
        if isinstance(doc, (DanfeData, InvoiceData)):
            return bool(doc.numero_nota and str(doc.numero_nota).strip())
        if isinstance(doc, OtherDocumentData):
            return bool(doc.numero_documento and str(doc.numero_documento).strip())
        if isinstance(doc, BoletoData):
            return bool(doc.numero_documento and str(doc.numero_documento).strip())
        return False

    def _set_numero_nota(self, doc: DocumentData, numero_nota: str) -> None:
        """Define numero_nota no documento."""
        if isinstance(doc, (DanfeData, InvoiceData)):
            doc.numero_nota = numero_nota
        elif isinstance(doc, (OtherDocumentData, BoletoData)):
            doc.numero_documento = numero_nota

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
        elif isinstance(doc,(OtherDocumentData)):
            return bool(doc.numero_documento)
        return False

    def _get_numero_pedido(self, doc: DocumentData) -> Optional[str]:
        """Obtém numero_pedido do documento."""
        if isinstance(doc, (DanfeData, InvoiceData, BoletoData)):
            return doc.numero_pedido
        elif isinstance(doc,(OtherDocumentData)):
            return doc.numero_documento
        return None

    def _set_numero_pedido(self, doc: DocumentData, value: str) -> None:
        """Define numero_pedido no documento."""
        if isinstance(doc, (DanfeData, InvoiceData, BoletoData)):
            doc.numero_pedido = value
        elif isinstance(doc,(OtherDocumentData)):
            doc.numero_documento = value

    def _has_vencimento(self, doc: DocumentData) -> bool:
        """Verifica se documento tem vencimento preenchido."""
        vencimento = getattr(doc, 'vencimento', None)
        return bool(vencimento and str(vencimento).strip())

    def _set_vencimento(self, doc: DocumentData, value: str) -> None:
        """Define vencimento no documento, convertendo para formato ISO."""
        if hasattr(doc, 'vencimento'):
            # Converte DD/MM/YYYY para YYYY-MM-DD se necessário
            normalized = self._normalize_vencimento_to_iso(value)
            doc.vencimento = normalized

    def _normalize_vencimento_to_iso(self, value: str) -> str:
        """Converte vencimento para formato ISO (YYYY-MM-DD)."""
        import re
        if not value:
            return value

        # Se já está no formato ISO (YYYY-MM-DD), retorna como está
        if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return value

        # Tenta converter DD/MM/YYYY ou DD-MM-YYYY ou DD.MM.YYYY
        match = re.match(r'^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})$', value)
        if match:
            dia, mes, ano = match.groups()
            return f"{ano}-{int(mes):02d}-{int(dia):02d}"

        # Retorna valor original se não conseguir converter
        return value


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
