"""
Testes de integração para sistema PAF
Valida conformidade com Policy 5.9 e POP 4.10
"""
from datetime import datetime

import pytest

from config.bancos import NOMES_BANCOS
from config.feriados_sp import SPBusinessCalendar
from core.diagnostics import ExtractionDiagnostics
from core.models import BoletoData, InvoiceData
from extractors.boleto import BoletoExtractor
from extractors.nfse_generic import NfseGenericExtractor


class TestSPBusinessCalendar:
    """Testes para calendário de dias úteis de São Paulo"""

    def test_feriados_fixos_2025(self):
        """Verifica feriados fixos de São Paulo em 2025"""
        calendario = SPBusinessCalendar()

        # 25 de janeiro - Aniversário de São Paulo
        assert not calendario.is_working_day(datetime(2025, 1, 25))

        # 20 de novembro - Consciência Negra
        assert not calendario.is_working_day(datetime(2025, 11, 20))

        # Dia normal de trabalho
        assert calendario.is_working_day(datetime(2025, 12, 22))

    def test_feriados_moveis_2025(self):
        """Verifica cálculo de feriados móveis (Carnaval, Corpus Christi)"""
        calendario = SPBusinessCalendar()

        # Corpus Christi 2025: 19 de junho
        assert not calendario.is_working_day(datetime(2025, 6, 19))

        # Segunda-feira de Carnaval 2025: 3 de março
        assert not calendario.is_working_day(datetime(2025, 3, 3))

    def test_calculo_dias_uteis(self):
        """Testa cálculo de dias úteis entre datas"""
        calendario = SPBusinessCalendar()

        # Semana cheia sem feriados no meio (5 dias úteis)
        # Obs: Usamos uma janela que não cruza 25/12 para evitar ambiguidade.
        inicio = datetime(2025, 12, 1)   # Segunda
        fim = datetime(2025, 12, 8)      # Segunda seguinte
        dias = calendario.get_working_days_delta(inicio, fim)
        assert dias == 5

        # Com feriado no meio
        inicio = datetime(2025, 12, 22)  # Segunda
        fim = datetime(2025, 12, 26)     # Sexta (25/12 é Natal)
        dias = calendario.get_working_days_delta(inicio, fim)
        assert dias == 3  # 22, 23, 24 (25 é feriado, 26 é sexta)

    def test_cache_lru(self):
        """Verifica se cache LRU está funcionando"""
        calendario = SPBusinessCalendar()

        # Primeira chamada (cacheia)
        holidays_2025 = calendario.get_variable_days(2025)

        # Segunda chamada (usa cache)
        holidays_2025_cached = calendario.get_variable_days(2025)

        assert holidays_2025 == holidays_2025_cached
        assert len(holidays_2025) >= 2  # Pelo menos Carnaval e Corpus Christi


class TestModelsToSheetsRow:
    """Testes para conversão de modelos para formato PAF (18 colunas)"""

    def test_invoice_to_sheets_row_completo(self):
        """Testa conversão de NFSe com todos os campos preenchidos"""
        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            fornecedor_nome="EMPRESA TESTE LTDA",
            valor_total=1500.50,
            data_emissao="2025-12-15",
            vencimento="2025-12-30",
            numero_pedido="PED-001",
            valor_ir=15.00,
            valor_inss=25.00,
            valor_csll=10.00,
            valor_iss=50.00,
            valor_icms=0.0,
            data_processamento="2025-12-22",
            setor="TI",
            empresa="MASTER",
            dt_classificacao="2025-12-22",
            tipo_doc_paf="NF",
            trat_paf="SISTEMA_AUTO",
            lanc_sistema="PENDENTE",
            forma_pagamento="TRANSFERENCIA",
            observacoes="Teste NFSe",
            obs_interna="Validação PAF"
        )

        row = invoice.to_sheets_row()

        # Valida estrutura (18 colunas)
        assert len(row) == 18

        # Valida conversão de datas (ISO -> DD/MM/YYYY)
        assert row[0] == "22/12/2025"  # DATA processamento
        assert row[5] == "15/12/2025"  # EMISSÃO
        assert row[8] == "30/12/2025"  # VENCIMENTO
        assert row[11] == "22/12/2025" # DT CLASS

        # Valida valores numéricos
        assert row[6] == 1500.50  # VALOR total

        # Valida campos texto
        assert row[1] == "TI"      # SETOR
        assert row[3] == "EMPRESA TESTE LTDA"  # FORNECEDOR
        # Coluna NF agora exporta numero_nota extraído do PDF
        assert row[4] == "12345"   # Número da NF
        assert row[13] == "NF"     # TP DOC
        assert row[14] == "SISTEMA_AUTO"  # TRAT PAF
        assert row[15] == "PENDENTE"      # LANC SISTEMA

    def test_invoice_to_sheets_row_campos_vazios(self):
        """Testa conversão com campos opcionais vazios"""
        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            valor_total=1000.00,
            data_processamento="2025-12-22"
        )

        row = invoice.to_sheets_row()

        # Campos vazios devem ser "" ou 0.0
        assert row[1] == ""     # SETOR vazio
        assert row[3] == ""     # FORNECEDOR vazio
        assert row[5] == ""     # EMISSÃO vazia
        assert row[8] == ""     # VENCIMENTO vazio

    def test_boleto_to_sheets_row_completo(self):
        """Testa conversão de Boleto com todos os campos"""
        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            valor_documento=2500.75,
            data_vencimento="2025-12-31",
            linha_digitavel="34191.79001 01043.510047 91020.150008 1 96610000250075",
            fornecedor_nome="FORNECEDOR BOLETO SA",
            banco_nome="BANCO DO BRASIL S.A.",
            agencia="1234-5",
            conta_corrente="98765-4",
            numero_pedido="BOL-999",
            data_processamento="2025-12-22",
            setor="FINANCEIRO",
            empresa="MASTER",
            dt_classificacao="2025-12-22",
            tipo_doc_paf="FT",
            trat_paf="SISTEMA_AUTO",
            lanc_sistema="PENDENTE",
            forma_pagamento="BOLETO"
        )

        row = boleto.to_sheets_row()

        assert len(row) == 18
        assert row[3] == "FORNECEDOR BOLETO SA"
        assert row[6] == 2500.75
        assert row[8] == "31/12/2025"  # VENCIMENTO convertido
        assert row[9] == "BOLETO"      # FORMA PAGTO
        assert row[13] == "FT"         # TP DOC (boleto = FT)

    def test_total_retencoes_property(self):
        """Testa cálculo de retenções totais (IR+INSS+CSLL)"""
        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            valor_total=1000.00,
            valor_ir=15.00,
            valor_inss=25.00,
            valor_csll=10.00
        )

        assert invoice.total_retencoes == 50.00

        # Com campos None
        invoice2 = InvoiceData(
            arquivo_origem="teste.pdf",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            valor_total=1000.00,
            valor_ir=15.00
        )

        assert invoice2.total_retencoes == 15.00


class TestExtractors:
    """Testes para extractors com dados PAF"""

    def test_generic_extractor_fornecedor(self):
        """Testa extração de razão social em NFSe"""
        extractor = NfseGenericExtractor()

        texto_nfse = """
        NOTA FISCAL DE SERVIÇOS ELETRÔNICA - NFS-e
        Número: 12345
        Data de Emissão: 15/12/2025

        PRESTADOR DE SERVIÇOS
        Razão Social: EMPRESA DE TECNOLOGIA LTDA
        CNPJ: 12.345.678/0001-90

        Valor Total: R$ 1.500,00
        """

        fornecedor = extractor._extract_fornecedor_nome(texto_nfse)
        assert fornecedor == "EMPRESA DE TECNOLOGIA LTDA"

    def test_generic_extractor_impostos(self):
        """Testa extração de impostos individuais"""
        extractor = NfseGenericExtractor()

        texto_nfse = """
        VALORES FISCAIS
        Valor dos Serviços: R$ 10.000,00

        TRIBUTOS RETIDOS NA FONTE
        IR Retido: R$ 150,00
        INSS: R$ 1.100,00
        CSLL: R$ 100,00
        ISS: R$ 500,00
        """

        ir = extractor._extract_ir(texto_nfse)
        inss = extractor._extract_inss(texto_nfse)
        csll = extractor._extract_csll(texto_nfse)
        iss = extractor._extract_valor_iss(texto_nfse)

        assert ir == 150.00
        assert inss == 1100.00
        assert csll == 100.00
        assert iss == 500.00

    def test_boleto_extractor_banco(self):
        """Testa identificação de banco pela linha digitável"""
        extractor = BoletoExtractor()

        # Banco do Brasil (001)
        linha_bb = "00190.00009 01234.567890 12345.678901 1 96610000100000"
        banco = extractor._extract_banco_nome("", linha_bb)
        assert banco == "BANCO DO BRASIL S.A."

        # Itaú (341)
        linha_itau = "34191.79001 01234.567890 12345.678901 1 96610000100000"
        banco = extractor._extract_banco_nome("", linha_itau)
        assert banco == "ITAÚ UNIBANCO S.A."

        # Banco não mapeado (999)
        linha_desconhecido = "99990.00009 01234.567890 12345.678901 1 96610000100000"
        banco = extractor._extract_banco_nome("", linha_desconhecido)
        assert banco == "BANCO_999"

    def test_boleto_extractor_normalizacao_agencia(self):
        """Testa normalização de agência"""
        extractor = BoletoExtractor()

        texto = """
        Agência/Código Beneficiário
        1234-5
        """

        agencia = extractor._extract_agencia(texto)
        assert agencia == "1234-5"

        # Com espaços e pontos
        texto2 = """
        Agência: 1.234 - 5
        """
        agencia2 = extractor._extract_agencia(texto2)
        assert agencia2 == "1234-5"

    def test_boleto_extractor_normalizacao_conta(self):
        """Testa normalização de conta corrente"""
        extractor = BoletoExtractor()

        texto = """
        Conta Corrente: 98765-4
        """

        conta = extractor._extract_conta_corrente(texto)
        assert conta == "98765-4"


class TestDiagnostics:
    """Testes para validações de diagnóstico (Policy 5.9)"""

    def test_validar_prazo_vencimento_suficiente(self):
        """Testa validação com prazo >= 4 dias úteis"""
        diagnostico = ExtractionDiagnostics()

        # Segunda 22/12 para segunda 29/12 (4 dias úteis: 23, 24, 26, 29 - 25 é Natal)
        dt_classificacao = datetime(2025, 12, 22)
        vencimento = datetime(2025, 12, 29)

        prazo_ok, dias_uteis = diagnostico.validar_prazo_vencimento(
            dt_classificacao.strftime('%Y-%m-%d'),
            vencimento.strftime('%Y-%m-%d')
        )

        assert prazo_ok is True
        assert dias_uteis >= 4

    def test_validar_prazo_vencimento_insuficiente(self):
        """Testa validação com prazo < 4 dias úteis"""
        diagnostico = ExtractionDiagnostics()

        # Segunda 22/12 para quarta 24/12 (2 dias úteis)
        dt_classificacao = datetime(2025, 12, 22)
        vencimento = datetime(2025, 12, 24)

        prazo_ok, dias_uteis = diagnostico.validar_prazo_vencimento(
            dt_classificacao.strftime('%Y-%m-%d'),
            vencimento.strftime('%Y-%m-%d')
        )

        assert prazo_ok is False
        assert dias_uteis < 4

    def test_classificar_nfse_sucesso(self):
        """Testa classificação de NFSe com todos os campos corretos"""
        diagnostico = ExtractionDiagnostics()

        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            fornecedor_nome="EMPRESA TESTE LTDA",
            valor_total=1500.00,
            vencimento="2025-12-30",
            dt_classificacao="2025-12-22"
        )

        sucesso, motivos = diagnostico.classificar_nfse(invoice)

        assert sucesso is True
        assert len(motivos) == 0

    def test_classificar_nfse_sem_razao_social(self):
        """Testa classificação de NFSe sem razão social"""
        diagnostico = ExtractionDiagnostics()

        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            valor_total=1500.00,
            vencimento="2025-12-30",
            dt_classificacao="2025-12-22"
        )

        sucesso, motivos = diagnostico.classificar_nfse(invoice)

        assert sucesso is False
        assert 'SEM_RAZAO_SOCIAL' in motivos

    def test_classificar_nfse_prazo_insuficiente(self):
        """Testa classificação de NFSe com prazo < 4 dias úteis"""
        diagnostico = ExtractionDiagnostics()

        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            fornecedor_nome="EMPRESA TESTE LTDA",
            valor_total=1500.00,
            vencimento="2025-12-24",  # Apenas 2 dias úteis
            dt_classificacao="2025-12-22"
        )

        sucesso, motivos = diagnostico.classificar_nfse(invoice)

        assert sucesso is False
        assert any('PRAZO_INSUFICIENTE' in motivo for motivo in motivos)

    def test_classificar_boleto_sucesso(self):
        """Testa classificação de Boleto com todos os campos corretos"""
        diagnostico = ExtractionDiagnostics()

        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            valor_documento=2500.00,
            data_vencimento="2025-12-30",
            linha_digitavel="34191.79001 01234.567890 12345.678901 1 96610000250000",
            fornecedor_nome="FORNECEDOR TESTE SA",
            dt_classificacao="2025-12-22"
        )

        sucesso, motivos = diagnostico.classificar_boleto(boleto)

        assert sucesso is True
        assert len(motivos) == 0

    def test_classificar_boleto_prazo_insuficiente(self):
        """Testa classificação de Boleto com prazo < 4 dias úteis"""
        diagnostico = ExtractionDiagnostics()

        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            valor_documento=2500.00,
            data_vencimento="2025-12-24",  # Apenas 2 dias úteis
            linha_digitavel="34191.79001 01234.567890 12345.678901 1 96610000250000",
            fornecedor_nome="FORNECEDOR TESTE SA",
            dt_classificacao="2025-12-22"
        )

        sucesso, motivos = diagnostico.classificar_boleto(boleto)

        assert sucesso is False
        assert any('PRAZO_INSUFICIENTE' in motivo for motivo in motivos)


class TestBancos:
    """Testes para mapeamento de bancos"""

    def test_bancos_principais_mapeados(self):
        """Verifica se os principais bancos brasileiros estão mapeados"""
        assert "001" in NOMES_BANCOS  # Banco do Brasil
        assert "237" in NOMES_BANCOS  # Bradesco
        assert "341" in NOMES_BANCOS  # Itaú
        assert "104" in NOMES_BANCOS  # Caixa
        assert "033" in NOMES_BANCOS  # Santander

        assert NOMES_BANCOS["001"] == "BANCO DO BRASIL S.A."
        assert NOMES_BANCOS["341"] == "ITAÚ UNIBANCO S.A."

    def test_total_bancos_mapeados(self):
        """Verifica se temos pelo menos 20 bancos mapeados"""
        assert len(NOMES_BANCOS) >= 20


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
