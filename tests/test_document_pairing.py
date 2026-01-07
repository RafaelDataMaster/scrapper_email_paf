"""
Testes para o serviço de pareamento de documentos NF↔Boleto.

Testa os casos:
1. Par simples (1 NF + 1 Boleto)
2. Múltiplas NFs com boletos pareados
3. NF sem boleto correspondente
4. Boleto sem NF correspondente
5. Pareamento por valor (caso Locaweb)
6. Normalização de números de nota
"""
import pytest

from core.batch_result import BatchResult
from core.document_pairing import (
    DocumentPair,
    DocumentPairingService,
    pair_batch_documents,
)
from core.models import BoletoData, DanfeData, InvoiceData, OtherDocumentData


class TestDocumentPair:
    """Testes para a classe DocumentPair."""

    def test_create_pair(self):
        """Testa criação básica de um par."""
        pair = DocumentPair(
            pair_id="batch_123",
            batch_id="batch_123",
            numero_nota="2025/119",
            valor_nf=9290.71,
            valor_boleto=9290.71,
            vencimento="2025-08-18",
            fornecedor="MAIS CONSULTORIA",
            status="OK",
        )

        assert pair.pair_id == "batch_123"
        assert pair.numero_nota == "2025/119"
        assert pair.valor_nf == 9290.71
        assert pair.valor_boleto == 9290.71
        assert pair.status == "OK"

    def test_to_summary(self):
        """Testa conversão para dicionário de resumo."""
        pair = DocumentPair(
            pair_id="batch_123_v1",
            batch_id="batch_123",
            numero_nota="2025/119",
            valor_nf=9290.71,
            valor_boleto=9290.71,
            vencimento="2025-08-18",
            fornecedor="MAIS CONSULTORIA",
            status="OK",
            diferenca=0.0,
            email_subject="ENC: Fatura",
        )

        summary = pair.to_summary()

        assert summary['batch_id'] == "batch_123_v1"
        assert summary['numero_nota'] == "2025/119"
        assert summary['valor_compra'] == 9290.71
        assert summary['valor_boleto'] == 9290.71
        assert summary['status_conciliacao'] == "OK"
        assert summary['diferenca_valor'] == 0.0


class TestDocumentPairingServiceNormalization:
    """Testes para normalização de números de nota."""

    @pytest.fixture
    def service(self):
        return DocumentPairingService()

    def test_normalizar_numero_nota_extrai_sufixo(self, service):
        """Testa normalização que extrai sufixo significativo."""
        # Números longos: extrai sufixo
        assert service._normalizar_numero_nota("202500000000119") == "119"
        assert service._normalizar_numero_nota("202500000000122") == "122"

    def test_normalizar_numero_nota_formato_ano(self, service):
        """Testa normalização de formato ano/numero."""
        assert service._normalizar_numero_nota("2025/119") == "119"
        assert service._normalizar_numero_nota("2025-119") == "119"
        assert service._normalizar_numero_nota("2025.119") == "119"

    def test_normalizar_numero_nota_simples(self, service):
        """Testa números simples."""
        assert service._normalizar_numero_nota("119") == "119"
        assert service._normalizar_numero_nota("00119") == "119"

    def test_numeros_equivalentes(self, service):
        """Testa detecção de números equivalentes."""
        # Mesmo número em formatos diferentes
        assert service._numeros_equivalentes("119", "119") is True
        assert service._numeros_equivalentes("119", "0119") is True
        assert service._numeros_equivalentes("119", "00119") is True
        # Um é sufixo do outro - a função detecta isso corretamente
        assert service._numeros_equivalentes("119", "202500000000119") is True
        # Após normalização também funciona
        n1 = service._normalizar_numero_nota("202500000000119")
        n2 = service._normalizar_numero_nota("2025/119")
        assert service._numeros_equivalentes(n1, n2) is True

    def test_extract_numero_from_filename_nf(self, service):
        """Testa extração de número do nome do arquivo com NF."""
        assert service._extract_numero_from_filename("02_NF 2025.119.pdf") == "2025.119"
        assert service._extract_numero_from_filename("NF-2025-119.pdf") == "2025-119"
        assert service._extract_numero_from_filename("NF_2025/119.pdf") == "2025/119"

    def test_extract_numero_from_filename_boleto(self, service):
        """Testa extração de número do nome do arquivo de boleto."""
        assert service._extract_numero_from_filename("03_BOLETO NF 2025.119.pdf") == "2025.119"

    def test_extract_numero_from_filename_nfse(self, service):
        """Testa extração de número de arquivo XML NFSE."""
        assert service._extract_numero_from_filename("nfse_202500000000119.xml") == "202500000000119"

    def test_extract_numero_from_filename_sem_numero(self, service):
        """Testa arquivo sem número identificável."""
        assert service._extract_numero_from_filename("documento.pdf") is None
        assert service._extract_numero_from_filename("boleto.pdf") is None


class TestDocumentPairingServiceSimple:
    """Testes para pareamento simples (1 NF + 1 Boleto)."""

    @pytest.fixture
    def service(self):
        return DocumentPairingService()

    def test_pair_simples_ok(self, service):
        """Testa par simples com valores iguais."""
        batch = BatchResult(batch_id="test_001")
        batch.email_subject = "ENC: Fatura 123"

        nfse = InvoiceData(
            arquivo_origem="01_NF_123.pdf",
            numero_nota="123",
            valor_total=1000.0,
            fornecedor_nome="Fornecedor A",
            vencimento="2025-01-15",
        )
        boleto = BoletoData(
            arquivo_origem="02_Boleto_123.pdf",
            numero_documento="123",
            valor_documento=1000.0,
            fornecedor_nome="Fornecedor A",
            vencimento="2025-01-15",
        )

        batch.add_document(nfse)
        batch.add_document(boleto)

        pairs = service.pair_documents(batch)

        assert len(pairs) == 1
        assert pairs[0].status == "OK"
        assert pairs[0].valor_nf == 1000.0
        assert pairs[0].valor_boleto == 1000.0
        assert pairs[0].diferenca == 0.0
        assert pairs[0].numero_nota == "123"

    def test_pair_simples_divergente(self, service):
        """Testa par simples com valores diferentes."""
        batch = BatchResult(batch_id="test_002")

        nfse = InvoiceData(
            arquivo_origem="01_NF.pdf",
            numero_nota="456",
            valor_total=1000.0,
            fornecedor_nome="Fornecedor B",
            vencimento="2025-01-15",
        )
        boleto = BoletoData(
            arquivo_origem="02_Boleto.pdf",
            numero_documento="456",
            valor_documento=900.0,
            fornecedor_nome="Fornecedor B",
            vencimento="2025-01-15",
        )

        batch.add_document(nfse)
        batch.add_document(boleto)

        pairs = service.pair_documents(batch)

        assert len(pairs) == 1
        assert pairs[0].status == "DIVERGENTE"
        assert pairs[0].diferenca == 100.0
        assert "Diferença: R$ 100.00" in pairs[0].divergencia

    def test_nf_sem_boleto(self, service):
        """Testa NF sem boleto correspondente (CONFERIR)."""
        batch = BatchResult(batch_id="test_003")

        nfse = InvoiceData(
            arquivo_origem="01_NF.pdf",
            numero_nota="789",
            valor_total=500.0,
            fornecedor_nome="Fornecedor C",
            vencimento="2025-01-20",
        )

        batch.add_document(nfse)

        pairs = service.pair_documents(batch)

        assert len(pairs) == 1
        assert pairs[0].status == "CONFERIR"
        assert "sem boleto para comparação" in pairs[0].divergencia
        assert pairs[0].valor_nf == 500.0
        assert pairs[0].valor_boleto == 0.0


class TestDocumentPairingServiceMultiple:
    """Testes para pareamento de múltiplas NFs (caso MAIS CONSULTORIA)."""

    @pytest.fixture
    def service(self):
        return DocumentPairingService()

    def test_multiplas_nfs_pareadas_por_numero(self, service):
        """Testa múltiplas NFs com boletos pareados pelo número da nota."""
        batch = BatchResult(batch_id="email_cc334d1b")
        batch.email_subject = "ENC: Mais Consultoria - NF 2025.119 e NF 2025.122"

        # NF 2025.119 + Boleto
        nf1 = InvoiceData(
            arquivo_origem="02_NF 2025.119.pdf",
            numero_nota="2025/119",
            valor_total=9290.71,
            fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA",
            vencimento="2025-08-18",
        )
        boleto1 = BoletoData(
            arquivo_origem="03_BOLETO NF 2025.119.pdf",
            numero_documento="2025.119",
            valor_documento=9290.71,
            fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA",
            vencimento="2025-08-18",
        )

        # NF 2025.122 + Boleto
        nf2 = InvoiceData(
            arquivo_origem="05_NF 2025.122.pdf",
            numero_nota="2025/122",
            valor_total=6250.0,
            fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA",
            vencimento="2025-08-10",
        )
        boleto2 = BoletoData(
            arquivo_origem="06_BOLETO NF 2025.122.pdf",
            numero_documento="2025.122",
            valor_documento=6250.0,
            fornecedor_nome="MAIS CONSULTORIA E SERVICOS LTDA",
            vencimento="2025-08-10",
        )

        batch.add_document(nf1)
        batch.add_document(boleto1)
        batch.add_document(nf2)
        batch.add_document(boleto2)

        pairs = service.pair_documents(batch)

        # Deve gerar 2 pares separados
        assert len(pairs) == 2

        # Verifica que ambos estão OK
        statuses = [p.status for p in pairs]
        assert all(s == "OK" for s in statuses)

        # Verifica os valores de cada par
        valores_nf = sorted([p.valor_nf for p in pairs])
        assert valores_nf == [6250.0, 9290.71]

        # Verifica que cada par tem diferença 0
        for pair in pairs:
            assert pair.diferenca == 0.0

    def test_multiplas_nfs_uma_sem_boleto(self, service):
        """Testa múltiplas NFs onde uma não tem boleto."""
        batch = BatchResult(batch_id="test_multi_01")

        # NF com boleto
        nf1 = InvoiceData(
            arquivo_origem="01_NF_100.pdf",
            numero_nota="100",
            valor_total=1000.0,
            fornecedor_nome="Fornecedor X",
            vencimento="2025-02-01",
        )
        boleto1 = BoletoData(
            arquivo_origem="02_Boleto_100.pdf",
            numero_documento="100",
            valor_documento=1000.0,
            vencimento="2025-02-01",
        )

        # NF sem boleto
        nf2 = InvoiceData(
            arquivo_origem="03_NF_200.pdf",
            numero_nota="200",
            valor_total=500.0,
            fornecedor_nome="Fornecedor X",
            vencimento="2025-02-05",
        )

        batch.add_document(nf1)
        batch.add_document(boleto1)
        batch.add_document(nf2)

        pairs = service.pair_documents(batch)

        assert len(pairs) == 2

        # Par 100 deve estar OK
        par_100 = next((p for p in pairs if p.numero_nota == "100"), None)
        assert par_100 is not None
        assert par_100.status == "OK"

        # Par 200 deve estar CONFERIR
        par_200 = next((p for p in pairs if p.numero_nota == "200"), None)
        assert par_200 is not None
        assert par_200.status == "CONFERIR"


class TestDocumentPairingServiceByValue:
    """Testes para pareamento por valor (caso Locaweb)."""

    @pytest.fixture
    def service(self):
        return DocumentPairingService()

    def test_pareamento_por_valor_sem_numero_nota(self, service):
        """Testa pareamento por valor quando não há número de nota."""
        batch = BatchResult(batch_id="test_locaweb")
        batch.email_subject = "ENC: A sua fatura Locaweb já está disponível!"

        # Fatura Locaweb (sem número de nota específico)
        outro = OtherDocumentData(
            arquivo_origem="02_Fatura Locaweb.pdf",
            valor_total=352.08,
            fornecedor_nome="LOCAWEB",
            vencimento="2025-09-01",
        )
        boleto = BoletoData(
            arquivo_origem="01_Boleto Locaweb.pdf",
            valor_documento=352.08,
            fornecedor_nome="Yapay a serviço de Locaweb S/A",
            vencimento="2025-09-01",
        )

        batch.add_document(outro)
        batch.add_document(boleto)

        pairs = service.pair_documents(batch)

        assert len(pairs) == 1
        assert pairs[0].status == "OK"
        assert pairs[0].valor_nf == 352.08
        assert pairs[0].valor_boleto == 352.08

    def test_pareamento_por_valor_multiplos(self, service):
        """Testa pareamento por valor com múltiplos documentos."""
        batch = BatchResult(batch_id="test_valor_multi")

        # Doc 1: valor 100
        doc1 = OtherDocumentData(
            arquivo_origem="doc1.pdf",
            valor_total=100.0,
            fornecedor_nome="Fornecedor",
            vencimento="2025-01-01",
        )
        boleto1 = BoletoData(
            arquivo_origem="boleto1.pdf",
            valor_documento=100.0,
            vencimento="2025-01-01",
        )

        # Doc 2: valor 200
        doc2 = OtherDocumentData(
            arquivo_origem="doc2.pdf",
            valor_total=200.0,
            fornecedor_nome="Fornecedor",
            vencimento="2025-01-02",
        )
        boleto2 = BoletoData(
            arquivo_origem="boleto2.pdf",
            valor_documento=200.0,
            vencimento="2025-01-02",
        )

        batch.add_document(doc1)
        batch.add_document(boleto1)
        batch.add_document(doc2)
        batch.add_document(boleto2)

        pairs = service.pair_documents(batch)

        assert len(pairs) == 2
        assert all(p.status == "OK" for p in pairs)


class TestDocumentPairingServiceEdgeCases:
    """Testes para casos especiais e edge cases."""

    @pytest.fixture
    def service(self):
        return DocumentPairingService()

    def test_batch_vazio(self, service):
        """Testa batch sem documentos."""
        batch = BatchResult(batch_id="test_vazio")

        pairs = service.pair_documents(batch)

        assert len(pairs) == 1
        assert pairs[0].status == "CONFERIR"
        assert "Nenhum documento com valor encontrado" in pairs[0].divergencia

    def test_apenas_boleto_sem_nf(self, service):
        """Testa batch com apenas boleto (sem NF)."""
        batch = BatchResult(batch_id="test_so_boleto")

        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            numero_documento="999",
            valor_documento=750.0,
            fornecedor_nome="Fornecedor Z",
            vencimento="2025-03-01",
        )

        batch.add_document(boleto)

        pairs = service.pair_documents(batch)

        assert len(pairs) == 1
        # Boleto sem NF também precisa de conferência
        assert pairs[0].valor_boleto == 750.0
        assert pairs[0].valor_nf == 0.0

    def test_danfe_com_boleto(self, service):
        """Testa DANFE (NF-e) com boleto."""
        batch = BatchResult(batch_id="test_danfe")

        danfe = DanfeData(
            arquivo_origem="danfe.xml",
            numero_nota="74970",
            valor_total=22.16,
            fornecedor_nome="REPROMAQ",
            vencimento="2025-08-08",
        )
        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            numero_documento="74970",
            valor_documento=22.16,
            vencimento="2025-08-08",
        )

        batch.add_document(danfe)
        batch.add_document(boleto)

        pairs = service.pair_documents(batch)

        assert len(pairs) == 1
        assert pairs[0].status == "OK"
        assert pairs[0].numero_nota == "74970"

    def test_vencimento_nao_encontrado_adiciona_alerta(self, service):
        """Testa que documentos sem vencimento recebem alerta."""
        batch = BatchResult(batch_id="test_sem_vencimento")

        nfse = InvoiceData(
            arquivo_origem="nf.pdf",
            numero_nota="123",
            valor_total=100.0,
            fornecedor_nome="Fornecedor",
            # Sem vencimento!
        )

        batch.add_document(nfse)

        pairs = service.pair_documents(batch)

        assert len(pairs) == 1
        assert "VENCIMENTO NÃO ENCONTRADO" in pairs[0].divergencia
        # Deve ter preenchido com data atual
        assert pairs[0].vencimento is not None


class TestBatchResultToSummaries:
    """Testes para o método to_summaries() do BatchResult."""

    def test_to_summaries_simples(self):
        """Testa to_summaries com um único par."""
        batch = BatchResult(batch_id="test_simple")
        batch.email_subject = "ENC: Fatura"

        nfse = InvoiceData(
            arquivo_origem="nf.pdf",
            numero_nota="123",
            valor_total=1000.0,
            fornecedor_nome="Fornecedor",
            vencimento="2025-01-15",
        )
        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            numero_documento="123",
            valor_documento=1000.0,
            vencimento="2025-01-15",
        )

        batch.add_document(nfse)
        batch.add_document(boleto)

        summaries = batch.to_summaries()

        assert len(summaries) == 1
        assert summaries[0]['status_conciliacao'] == "OK"
        assert summaries[0]['valor_compra'] == 1000.0

    def test_to_summaries_multiplos(self):
        """Testa to_summaries com múltiplos pares."""
        batch = BatchResult(batch_id="test_multi")

        # Par 1
        nf1 = InvoiceData(
            arquivo_origem="nf1.pdf",
            numero_nota="100",
            valor_total=1000.0,
            fornecedor_nome="Fornecedor",
            vencimento="2025-01-15",
        )
        boleto1 = BoletoData(
            arquivo_origem="boleto1.pdf",
            numero_documento="100",
            valor_documento=1000.0,
            vencimento="2025-01-15",
        )

        # Par 2
        nf2 = InvoiceData(
            arquivo_origem="nf2.pdf",
            numero_nota="200",
            valor_total=500.0,
            fornecedor_nome="Fornecedor",
            vencimento="2025-01-20",
        )
        boleto2 = BoletoData(
            arquivo_origem="boleto2.pdf",
            numero_documento="200",
            valor_documento=500.0,
            vencimento="2025-01-20",
        )

        batch.add_document(nf1)
        batch.add_document(boleto1)
        batch.add_document(nf2)
        batch.add_document(boleto2)

        summaries = batch.to_summaries()

        assert len(summaries) == 2
        assert all(s['status_conciliacao'] == "OK" for s in summaries)

    def test_has_multiple_invoices(self):
        """Testa detecção de múltiplas notas."""
        batch = BatchResult(batch_id="test")

        # Apenas uma nota
        nf1 = InvoiceData(arquivo_origem="nf1.pdf", valor_total=100.0)
        batch.add_document(nf1)

        assert batch.has_multiple_invoices() is False

        # Adiciona segunda nota
        nf2 = InvoiceData(arquivo_origem="nf2.pdf", valor_total=200.0)
        batch.add_document(nf2)

        assert batch.has_multiple_invoices() is True


class TestPairBatchDocumentsFunction:
    """Testes para a função de conveniência pair_batch_documents()."""

    def test_pair_batch_documents(self):
        """Testa função de conveniência."""
        batch = BatchResult(batch_id="test_func")

        nfse = InvoiceData(
            arquivo_origem="nf.pdf",
            numero_nota="456",
            valor_total=500.0,
            fornecedor_nome="Fornecedor",
            vencimento="2025-02-01",
        )

        batch.add_document(nfse)

        pairs = pair_batch_documents(batch)

        assert len(pairs) == 1
        assert pairs[0].numero_nota == "456"
