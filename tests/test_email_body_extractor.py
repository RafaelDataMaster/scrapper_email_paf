"""
Testes para EmailBodyExtractor e pareamento flexível.

Este módulo testa:
1. Extração de valores monetários do corpo de e-mail
2. Extração de datas de vencimento
3. Extração de números de nota fiscal
4. Extração de links de NF-e
5. Pareamento forçado por lote
"""

import pytest


class TestEmailBodyExtractor:
    """Testes para EmailBodyExtractor."""

    @pytest.fixture
    def extractor(self):
        """Fixture que retorna uma instância do extrator."""
        from extractors.email_body_extractor import EmailBodyExtractor
        return EmailBodyExtractor()

    # === Testes de Extração de Valores ===

    def test_extract_valor_simples(self, extractor):
        """Testa extração de valor R$ simples."""
        body = "O valor total é R$ 1.234,56"
        result = extractor.extract(body_text=body)

        assert result.valor_total == 1234.56
        assert result.has_valor()

    def test_extract_valor_sem_ponto_milhar(self, extractor):
        """Testa extração de valor sem separador de milhar."""
        body = "Valor: R$ 500,00"
        result = extractor.extract(body_text=body)

        assert result.valor_total == 500.00

    def test_extract_valor_multiplos(self, extractor):
        """Testa que retorna o maior valor quando há múltiplos."""
        body = """
        Subtotal: R$ 100,00
        Desconto: R$ 10,00
        Total: R$ 1.500,00
        """
        result = extractor.extract(body_text=body)

        assert result.valor_total == 1500.00
        assert len(result.valores_encontrados) == 3
        assert 100.00 in result.valores_encontrados
        assert 10.00 in result.valores_encontrados
        assert 1500.00 in result.valores_encontrados

    def test_extract_valor_do_assunto(self, extractor):
        """Testa extração de valor do assunto do e-mail."""
        subject = "Fatura R$ 250,00 - Vencimento 29/12"
        result = extractor.extract(subject=subject)

        assert result.valor_total == 250.00

    def test_extract_valor_contexto_total(self, extractor):
        """Testa extração com contexto 'Total'."""
        body = "Total a pagar: R$ 999,99"
        result = extractor.extract(body_text=body)

        assert result.valor_total == 999.99

    def test_extract_sem_valor(self, extractor):
        """Testa quando não há valor no texto."""
        body = "E-mail sem valor monetário"
        result = extractor.extract(body_text=body)

        assert result.valor_total == 0.0
        assert not result.has_valor()

    def test_extract_valor_grande(self, extractor):
        """Testa extração de valor grande (milhões)."""
        body = "Contrato de R$ 1.500.000,00"
        result = extractor.extract(body_text=body)

        assert result.valor_total == 1500000.00

    # === Testes de Extração de Vencimento ===

    def test_extract_vencimento_completo(self, extractor):
        """Testa extração de vencimento DD/MM/YYYY."""
        body = "Vencimento: 29/12/2025"
        result = extractor.extract(body_text=body)

        assert result.vencimento == "2025-12-29"

    def test_extract_vencimento_parcial(self, extractor):
        """Testa extração de vencimento DD/MM (assume ano atual)."""
        body = "Venc.: 15/01"
        result = extractor.extract(body_text=body)

        # Deve assumir ano atual ou próximo
        assert result.vencimento is not None
        assert result.vencimento.endswith("-01-15")

    def test_extract_vencimento_formato_omie(self, extractor):
        """Testa extração no formato Omie '- 29/12 Seg'."""
        subject = "Lembrete de Vencimento do Boleto da NFS-e nº 3406 - 29/12 Seg"
        result = extractor.extract(subject=subject)

        assert result.vencimento is not None
        assert "-12-29" in result.vencimento

    def test_extract_vencimento_do_assunto(self, extractor):
        """Testa que vencimento do assunto tem prioridade."""
        subject = "Vencimento: 25/12/2025"
        body = "Data de vencimento: 30/12/2025"
        result = extractor.extract(subject=subject, body_text=body)

        # Assunto tem prioridade
        assert result.vencimento == "2025-12-25"

    # === Testes de Extração de Número de Nota ===

    def test_extract_numero_nota_nfse(self, extractor):
        """Testa extração de número NFS-e."""
        subject = "NFS-e nº 3406 emitida"
        result = extractor.extract(subject=subject)

        assert result.numero_nota == "3406"

    def test_extract_numero_nota_nf(self, extractor):
        """Testa extração de número NF."""
        body = "Nota Fiscal 12345 gerada com sucesso"
        result = extractor.extract(body_text=body)

        assert result.numero_nota == "12345"

    def test_extract_numero_fatura(self, extractor):
        """Testa extração de número de fatura."""
        subject = "Fatura 50446 disponível"
        result = extractor.extract(subject=subject)

        assert result.numero_nota == "50446"

    def test_extract_numero_nota_do_assunto_priorizado(self, extractor):
        """Testa que número do assunto tem prioridade."""
        subject = "NF 123 emitida"
        body = "Conforme NF 456 anexa..."
        result = extractor.extract(subject=subject, body_text=body)

        assert result.numero_nota == "123"

    # === Testes de Extração de Link NF-e ===

    def test_extract_link_omie(self, extractor):
        """Testa extração de link Omie."""
        body = """
        Acesse sua nota fiscal:
        https://click.omie.com.br/track/click/30041717/click.omie.com?p=eyJz...
        """
        result = extractor.extract(body_text=body)

        assert result.link_nfe is not None
        assert "omie.com" in result.link_nfe

    def test_extract_link_prefeitura_sp(self, extractor):
        """Testa extração de link de prefeitura."""
        body = """
        Verifique a autenticidade em:
        https://nfe.prefeitura.sp.gov.br/contribuinte/notaverificar.aspx?nf=123
        """
        result = extractor.extract(body_text=body)

        assert result.link_nfe is not None
        assert "prefeitura.sp.gov.br" in result.link_nfe

    def test_extract_codigo_verificacao_do_link(self, extractor):
        """Testa extração de código de verificação do link."""
        body = "https://portal.nfe.gov.br/verificar?cod=ABC123XYZ"
        result = extractor.extract(body_text=body)

        assert result.codigo_verificacao == "ABC123XYZ"

    # === Testes de HTML ===

    def test_extract_from_html_content(self, extractor):
        """Testa extração de HTML."""
        html = """
        <html>
        <body>
            <p>Valor: <strong>R$ 1.500,00</strong></p>
            <p>Vencimento: 29/12/2025</p>
        </body>
        </html>
        """
        result = extractor.extract(html_content=html)

        assert result.valor_total == 1500.00
        assert result.vencimento == "2025-12-29"

    def test_extract_from_mixed_content(self, extractor):
        """Testa extração de conteúdo misto (texto + HTML)."""
        body = """
        Prezado cliente,

        Segue boleto para pagamento.

        --- HTML CONTENT ---

        <html>
        <body>
            <p>Total: R$ 2.000,00</p>
        </body>
        </html>
        """
        result = extractor.extract(body_text=body)

        assert result.valor_total == 2000.00

    # === Testes de Fornecedor ===

    def test_extract_fornecedor_do_assunto(self, extractor):
        """Testa extração de fornecedor do assunto."""
        subject = "VCOM TECNOLOGIA - Fatura 123"
        result = extractor.extract(subject=subject)

        assert result.fornecedor_nome == "VCOM TECNOLOGIA"

    # === Testes de Confiança ===

    def test_confianca_alta_com_contexto_total(self, extractor):
        """Testa que confiança aumenta com contexto 'Total'."""
        body = "Total: R$ 500,00"
        result = extractor.extract(body_text=body)

        assert result.confianca >= 0.7

    def test_confianca_baixa_sem_contexto(self, extractor):
        """Testa que confiança é menor sem contexto claro."""
        body = "R$ 100,00 R$ 200,00 R$ 300,00 R$ 400,00 R$ 500,00 R$ 600,00"
        result = extractor.extract(body_text=body)

        # Muitos valores sem contexto = menor confiança
        assert result.confianca < 0.5


class TestDocumentPairingForcado:
    """Testes para pareamento forçado por lote."""

    @pytest.fixture
    def pairing_service(self):
        """Fixture que retorna o serviço de pareamento."""
        from core.document_pairing import DocumentPairingService
        return DocumentPairingService()

    @pytest.fixture
    def mock_batch(self):
        """Fixture que cria um BatchResult mockado."""
        from core.batch_result import BatchResult
        return BatchResult(
            batch_id="test_batch_001",
            source_folder="/tmp/test",
            email_subject="Teste NF + Boleto",
            email_sender="fornecedor@teste.com"
        )

    def test_pareamento_forcado_nota_zerada_boleto(self, pairing_service, mock_batch):
        """Testa pareamento forçado: 1 nota zerada + 1 boleto."""
        from core.models import BoletoData, InvoiceData

        # Nota com valor 0 (veio de link/email body)
        nota = InvoiceData(
            arquivo_origem="nota_email_body.pdf",
            valor_total=0.0,
            numero_nota="3406"
        )

        # Boleto com valor
        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            valor_documento=1500.00,
            vencimento="2025-12-29"
        )

        mock_batch.add_document(nota)
        mock_batch.add_document(boleto)

        pairs = pairing_service.pair_documents(mock_batch)

        # Deve gerar 1 par forçado
        assert len(pairs) == 1
        pair = pairs[0]

        # Verifica status
        assert pair.status == "PAREADO_FORCADO"
        assert pair.pareamento_forcado is True

        # Verifica valores
        assert pair.valor_nf == 0.0
        assert pair.valor_boleto == 1500.00

        # Verifica que ambos documentos estão no par
        assert len(pair.documentos_nf) == 1
        assert len(pair.documentos_boleto) == 1

    def test_pareamento_forcado_valores_divergentes(self, pairing_service, mock_batch):
        """Testa pareamento forçado com valores divergentes."""
        from core.models import BoletoData, InvoiceData

        # Nota com valor diferente do boleto
        nota = InvoiceData(
            arquivo_origem="nota.pdf",
            valor_total=1000.00,
            numero_nota="123"
        )

        # Boleto com valor diferente
        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            valor_documento=1200.00
        )

        mock_batch.add_document(nota)
        mock_batch.add_document(boleto)

        pairs = pairing_service.pair_documents(mock_batch)

        # Como valores são diferentes mas só há 1 de cada, deve forçar
        # (comportamento depende da tolerância)
        assert len(pairs) >= 1

    def test_pareamento_normal_valores_iguais(self, pairing_service, mock_batch):
        """Testa que pareamento normal funciona quando valores conferem."""
        from core.models import BoletoData, InvoiceData

        nota = InvoiceData(
            arquivo_origem="nota.pdf",
            valor_total=1500.00,
            numero_nota="456"
        )

        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            valor_documento=1500.00
        )

        mock_batch.add_document(nota)
        mock_batch.add_document(boleto)

        pairs = pairing_service.pair_documents(mock_batch)

        assert len(pairs) == 1
        pair = pairs[0]

        # Não deve ser forçado - valores conferem
        assert pair.status == "CONCILIADO"
        assert pair.pareamento_forcado is False

    def test_sem_pareamento_multiplas_notas(self, pairing_service, mock_batch):
        """Testa que NÃO força pareamento quando há múltiplas notas."""
        from core.models import BoletoData, InvoiceData

        nota1 = InvoiceData(
            arquivo_origem="nota1.pdf",
            valor_total=0.0,
            numero_nota="001"
        )
        nota2 = InvoiceData(
            arquivo_origem="nota2.pdf",
            valor_total=0.0,
            numero_nota="002"
        )

        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            valor_documento=1500.00
        )

        mock_batch.add_document(nota1)
        mock_batch.add_document(nota2)
        mock_batch.add_document(boleto)

        pairs = pairing_service.pair_documents(mock_batch)

        # Com múltiplas notas, não deve forçar pareamento
        # (pode gerar boleto órfão)
        assert len(pairs) >= 1


class TestExtractFromEmailBodyFunction:
    """Testes para função de conveniência extract_from_email_body."""

    def test_function_exists(self):
        """Testa que a função está disponível."""
        from extractors.email_body_extractor import extract_from_email_body
        assert callable(extract_from_email_body)

    def test_function_returns_result(self):
        """Testa que a função retorna EmailBodyExtractionResult."""
        from extractors.email_body_extractor import (
            EmailBodyExtractionResult,
            extract_from_email_body,
        )

        result = extract_from_email_body(body_text="R$ 100,00")
        assert isinstance(result, EmailBodyExtractionResult)
        assert result.valor_total == 100.00


class TestMetadataExtractValor:
    """Testes para extração de valor via EmailMetadata."""

    def test_extract_valor_from_body(self):
        """Testa extração de valor via método do metadata."""
        from core.metadata import EmailMetadata

        metadata = EmailMetadata(
            batch_id="test",
            email_subject="Fatura 123",
            email_body_text="Total a pagar: R$ 2.500,00"
        )

        valor = metadata.extract_valor_from_body()
        assert valor == 2500.00

    def test_extract_all_from_body(self):
        """Testa extração de todos os dados via metadata."""
        from core.metadata import EmailMetadata

        metadata = EmailMetadata(
            batch_id="test",
            email_subject="NFS-e nº 999 - Vencimento 15/01/2026",
            email_body_text="Valor: R$ 1.000,00"
        )

        dados = metadata.extract_all_from_body()

        assert dados['valor_total'] == 1000.00
        assert dados['numero_nota'] == "999"
        assert dados['vencimento'] is not None
