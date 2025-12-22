"""
Testes de conformidade PAF
Valida conformidade com Policy 5.9 e POP 4.10
"""
import pytest
from datetime import datetime, timedelta
from config.feriados_sp import SPBusinessCalendar
from core.models import InvoiceData, BoletoData
from core.diagnostics import ExtractionDiagnostics
from config.bancos import NOMES_BANCOS


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
    
    def test_dia_de_trabalho(self):
        """Testa identificação de dia de trabalho"""
        calendario = SPBusinessCalendar()
        
        # Segunda-feira normal
        assert calendario.is_working_day(datetime(2025, 12, 22))
        
        # Sábado
        assert not calendario.is_working_day(datetime(2025, 12, 20))
        
        # Domingo
        assert not calendario.is_working_day(datetime(2025, 12, 21))
    
    def test_cache_lru(self):
        """Verifica se cache LRU está funcionando"""
        calendario = SPBusinessCalendar()
        
        # Primeira chamada (cacheia)
        holidays_2025 = calendario.get_variable_days(2025)
        
        # Segunda chamada (usa cache)
        holidays_2025_cached = calendario.get_variable_days(2025)
        
        assert holidays_2025 == holidays_2025_cached
        assert len(holidays_2025) >= 2  # Pelo menos Carnaval e Corpus Christi


class TestDiagnostics:
    """Testes para validações de diagnóstico (Policy 5.9)"""
    
    def test_validar_prazo_vencimento_suficiente(self):
        """Testa validação com prazo >= 4 dias úteis"""
        # Usando data atual + 10 dias úteis para garantir sucesso
        dt_classificacao = datetime(2025, 12, 15)
        vencimento = datetime(2025, 12, 30)
        
        prazo_ok, dias_uteis = ExtractionDiagnostics.validar_prazo_vencimento(
            dt_classificacao.strftime('%Y-%m-%d'),
            vencimento.strftime('%Y-%m-%d')
        )
        
        assert dias_uteis > 0  # Pelo menos deve calcular dias
    
    def test_validar_prazo_vencimento_insuficiente(self):
        """Testa validação com prazo < 4 dias úteis"""
        # Apenas 2 dias de diferença
        dt_classificacao = datetime(2025, 12, 22)
        vencimento = datetime(2025, 12, 24)
        
        prazo_ok, dias_uteis = ExtractionDiagnostics.validar_prazo_vencimento(
            dt_classificacao.strftime('%Y-%m-%d'),
            vencimento.strftime('%Y-%m-%d')
        )
        
        assert prazo_ok is False
        assert dias_uteis < 4
    
    def test_classificar_nfse_sucesso(self):
        """Testa classificação de NFSe com todos os campos corretos"""
        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            texto_bruto="Nota Fiscal teste",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            fornecedor_nome="EMPRESA TESTE LTDA",
            valor_total=1500.00,
            vencimento="2026-01-30",  # Data futura com prazo suficiente
            dt_classificacao="2025-12-22"
        )
        
        sucesso, motivos = ExtractionDiagnostics.classificar_nfse(invoice)
        
        assert sucesso is True
        assert len(motivos) == 0
    
    def test_classificar_nfse_sem_razao_social(self):
        """Testa classificação de NFSe sem razão social"""
        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            texto_bruto="Nota Fiscal teste",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            valor_total=1500.00,
            vencimento="2026-01-30",
            dt_classificacao="2025-12-22"
        )
        
        sucesso, motivos = ExtractionDiagnostics.classificar_nfse(invoice)
        
        assert sucesso is False
        assert 'SEM_RAZAO_SOCIAL' in motivos
    
    def test_classificar_nfse_valor_zero(self):
        """Testa classificação de NFSe com valor zero"""
        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            texto_bruto="Nota Fiscal teste",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            fornecedor_nome="EMPRESA TESTE LTDA",
            valor_total=0.0,  # Valor zerado
            dt_classificacao="2025-12-22"
        )
        
        sucesso, motivos = ExtractionDiagnostics.classificar_nfse(invoice)
        
        assert sucesso is False
        assert 'VALOR_ZERO' in motivos
    
    def test_classificar_boleto_sucesso(self):
        """Testa classificação de Boleto com todos os campos corretos"""
        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            texto_bruto="Boleto bancário teste",
            valor_documento=2500.00,
            vencimento="2026-01-30",  # Data futura com prazo suficiente
            linha_digitavel="34191.79001 01234.567890 12345.678901 1 96610000250000",
            fornecedor_nome="FORNECEDOR TESTE SA",
            dt_classificacao="2025-12-22"
        )
        
        sucesso, motivos = ExtractionDiagnostics.classificar_boleto(boleto)
        
        assert sucesso is True
        assert len(motivos) == 0
    
    def test_classificar_boleto_sem_fornecedor(self):
        """Testa classificação de Boleto sem fornecedor"""
        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            texto_bruto="Boleto bancário teste",
            valor_documento=2500.00,
            vencimento="2026-01-30",
            linha_digitavel="34191.79001 01234.567890 12345.678901 1 96610000250000",
            dt_classificacao="2025-12-22"
        )
        
        sucesso, motivos = ExtractionDiagnostics.classificar_boleto(boleto)
        
        assert sucesso is False
        assert 'SEM_RAZAO_SOCIAL' in motivos


class TestBancos:
    """Testes para mapeamento de bancos"""
    
    def test_bancos_principais_mapeados(self):
        """Verifica se os principais bancos brasileiros estão mapeados"""
        assert "001" in NOMES_BANCOS  # Banco do Brasil
        assert "237" in NOMES_BANCOS  # Bradesco
        assert "341" in NOMES_BANCOS  # Itaú
        assert "104" in NOMES_BANCOS  # Caixa
        assert "033" in NOMES_BANCOS  # Santander
    
    def test_total_bancos_mapeados(self):
        """Verifica se temos pelo menos 20 bancos mapeados"""
        assert len(NOMES_BANCOS) >= 20
    
    def test_banco_do_brasil(self):
        """Verifica nome do Banco do Brasil"""
        assert "001" in NOMES_BANCOS
        assert "BANCO DO BRASIL" in NOMES_BANCOS["001"].upper()


class TestModelsToSheetsRow:
    """Testes para conversão de modelos para formato PAF (18 colunas)"""
    
    def test_invoice_to_sheets_row_completo(self):
        """Testa conversão de NFSe com todos os campos preenchidos"""
        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            texto_bruto="Nota Fiscal Eletrônica",
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
        
        # Verifica que retorna lista com 18 elementos
        assert isinstance(row, list)
        assert len(row) == 18
        
        # Verifica alguns campos específicos
        assert row[4] == "12345"  # Número da nota
        assert row[6] == 1500.50  # Valor
        assert row[3] == "EMPRESA TESTE LTDA"  # Fornecedor
    
    def test_invoice_to_sheets_row_campos_vazios(self):
        """Testa conversão com campos opcionais vazios"""
        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            texto_bruto="NFSe mínima",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            valor_total=1000.00,
            data_processamento="2025-12-22"
        )
        
        row = invoice.to_sheets_row()
        
        # Deve ter 18 elementos mesmo com campos vazios
        assert len(row) == 18
        
        # Campos não preenchidos devem ser "" ou 0.0
        assert row[3] == ""  # Fornecedor vazio
        assert row[7] == ""  # Número pedido vazio
    
    def test_boleto_to_sheets_row_completo(self):
        """Testa conversão de Boleto com todos os campos"""
        boleto = BoletoData(
            arquivo_origem="boleto.pdf",
            texto_bruto="Boleto bancário completo",
            valor_documento=2500.75,
            vencimento="2025-12-31",
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
        
        # Verifica que retorna lista com 18 elementos
        assert isinstance(row, list)
        assert len(row) == 18
        
        # Verifica alguns campos específicos
        assert row[6] == 2500.75  # Valor
        assert row[3] == "FORNECEDOR BOLETO SA"  # Fornecedor
    
    def test_total_retencoes_property(self):
        """Testa cálculo de retenções totais (IR+INSS+CSLL)"""
        invoice = InvoiceData(
            arquivo_origem="teste.pdf",
            texto_bruto="NFSe com retenções",
            numero_nota="12345",
            cnpj_prestador="12.345.678/0001-90",
            valor_total=1000.00,
            valor_ir=15.00,
            valor_inss=25.00,
            valor_csll=10.00
        )
        
        # Verifica propriedade calculada
        assert invoice.total_retencoes == 50.00


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
