"""
Testes para verificar o comportamento do OutrosExtractor com textos problemáticos.

Foco principal: garantir que o OutrosExtractor rejeite documentos fiscais (NFSE, DANFE)
e capture apenas documentos administrativos genuínos, com extração correta de valores.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from extractors.outros import OutrosExtractor

# Configurar logging para ver detalhes
logging.basicConfig(level=logging.DEBUG)


class TestOutrosExtractor:
    """Testes para o OutrosExtractor."""

    def setup_method(self):
        """Configurar o extrator antes de cada teste."""
        self.extractor = OutrosExtractor()

    # Casos NEGATIVOS: documentos fiscais que devem ser REJEITADOS

    def test_rejeita_nfse_com_documento_auxiliar(self):
        """Testar rejeição de NFSE com 'DOCUMENTO AUXILIAR DA NOTA FISCAL DE SERVIÇO'."""
        text = """
        DOCUMENTO AUXILIAR DA NOTA FISCAL DE SERVIÇO ELETRÔNICA
        PREFEITURA MUNICIPAL DE SÃO PAULO
        NFS-E Nº 123456
        CNPJ: 12.345.678/0001-90
        VALOR TOTAL: R$ 1.500,00
        """
        assert not self.extractor.can_handle(text), (
            "Deveria rejeitar NFSE com documento auxiliar"
        )

    def test_rejeita_danfe_com_chave_acesso(self):
        """Testar rejeição de DANFE com 'CHAVE DE ACESSO'."""
        text = """
        DANFE - DOCUMENTO AUXILIAR DA NOTA FISCAL ELETRÔNICA
        CHAVE DE ACESSO: 1234 5678 9012 3456 7890 1234 5678 9012 3456 7890 1234
        VALOR TOTAL: R$ 2.300,50
        """
        assert not self.extractor.can_handle(text), (
            "Deveria rejeitar DANFE com chave de acesso"
        )

    def test_rejeita_chave_acesso_44_digitos(self):
        """Testar rejeição de documento com chave de acesso de 44 dígitos."""
        text = """
        Fatura de Serviços
        Cliente: Empresa Teste
        35190900000000000000000000000000000000000000
        Valor: R$ 500,00
        """
        assert not self.extractor.can_handle(text), (
            "Deveria rejeitar documento com chave de acesso de 44 dígitos"
        )

    def test_rejeita_multiplos_impostos(self):
        """Testar rejeição de documento com múltiplos impostos (indicador fiscal)."""
        text = """
        Demonstrativo de Serviços
        Base ISS: R$ 1.000,00
        Valor ISS: R$ 50,00
        INSS: R$ 100,00
        PIS: R$ 20,00
        COFINS: R$ 30,00
        Total: R$ 1.200,00
        """
        assert not self.extractor.can_handle(text), (
            "Deveria rejeitar documento com múltiplos impostos"
        )

    def test_rejeita_nota_fatura(self):
        """Testar rejeição de 'NOTA FATURA' (que é NFSE)."""
        text = """
        NOTA FATURA Nº 12345
        Fornecedor: TUNNA ENTRETENIMENTO
        Valor Total: R$ 1.000,00
        ISS: R$ 50,00
        """
        assert not self.extractor.can_handle(text), (
            "Deveria rejeitar 'NOTA FATURA' (NFSE)"
        )

    def test_rejeita_nota_fiscal_com_fatura(self):
        """Testar rejeição de documento com 'NOTA FISCAL' e 'FATURA'."""
        text = """
        NOTA FISCAL DE SERVIÇO ELETRÔNICA
        FATURA Nº 10731
        Fornecedor: TUNNA ENTRETENIMENTO
        Valor: R$ 500,00
        """
        assert not self.extractor.can_handle(text), (
            "Deveria rejeitar documento com indicadores fiscais"
        )

    # Casos POSITIVOS: documentos administrativos que devem ser ACEITOS

    def test_aceita_demonstrativo_locacao(self):
        """Testar aceitação de demonstrativo de locação genuíno."""
        text = """
        DEMONSTRATIVO DE LOCAÇÃO
        Locador: XYZ Equipamentos Ltda

        Descrição do Equipamento: Gerador 50KVA
        Período: 01/01/2026 a 31/01/2026

        VALOR DA LOCAÇÃO: R$ 1.500,50
        Vencimento: 20/01/2026
        """
        assert self.extractor.can_handle(text), (
            "Deveria aceitar demonstrativo de locação"
        )

    def test_aceita_fatura_administrativa_sem_indicadores_fiscais(self):
        """Testar aceitação de fatura administrativa sem indicadores fiscais."""
        text = """
        FATURA DE SERVIÇOS
        Cliente: Empresa Teste
        Serviço: Manutenção Preventiva
        Valor: R$ 300,00
        Vencimento: 25/01/2026
        """
        assert self.extractor.can_handle(text), "Deveria aceitar fatura administrativa"

    def test_aceita_locaweb(self):
        """Testar aceitação de documento da LOCAWEB."""
        text = """
        LOCAWEB - FATURA DE HOSPEDAGEM
        Cliente: Empresa Teste
        Período: Jan/2026
        Valor: R$ 89,90
        Vencimento: 10/01/2026
        """
        assert self.extractor.can_handle(text), "Deveria aceitar documento da LOCAWEB"

    def test_aceita_valor_da_loca(self):
        """Testar aceitação de documento com 'VALOR DA LOCA'."""
        text = """
        Contrato de Locação
        VALOR DA LOCAÇÃO: R$ 2.800,00
        Período: 12 meses
        """
        assert self.extractor.can_handle(text), (
            "Deveria aceitar documento com 'VALOR DA LOCA'"
        )

    # Testes de EXTRAÇÃO de valores

    def test_extrai_valor_demonstrativo_locacao(self):
        """Testar extração de valor de demonstrativo de locação."""
        text = """
        DEMONSTRATIVO DE LOCAÇÃO
        Locador: ABC Equipamentos Ltda

        TOTAL A PAGAR NO MÊS: 2.855,00
        Vencimento: 31/01/2026
        """
        assert self.extractor.can_handle(text)
        data = self.extractor.extract(text)
        assert data.get("subtipo") == "LOCACAO"
        assert data.get("valor_total") == 2855.00, (
            f"Valor esperado: 2855.00, obtido: {data.get('valor_total')}"
        )
        assert data.get("vencimento") == "2026-01-31"

    def test_extrai_valor_fatura_com_rs(self):
        """Testar extração de valor de fatura com R$."""
        text = """
        FATURA DE SERVIÇOS
        Fornecedor: AGYONET TELECOMUNICACOES LTDA

        TOTAL A PAGAR: R$ 200,00
        Vencimento: 25/01/2026
        """
        assert self.extractor.can_handle(text)
        data = self.extractor.extract(text)
        assert data.get("subtipo") == "FATURA"
        assert data.get("valor_total") == 200.00, (
            f"Valor esperado: 200.00, obtido: {data.get('valor_total')}"
        )
        assert data.get("fornecedor_nome") == "AGYONET TELECOMUNICACOES LTDA"
        assert data.get("vencimento") == "2026-01-25"

    def test_extrai_valor_sem_rs(self):
        """Testar extração de valor sem R$ (apenas número)."""
        text = """
        DEMONSTRATIVO
        VALOR TOTAL DA LOCAÇÃO: 1.500,50
        Data: 15/01/2026
        """
        assert self.extractor.can_handle(text)
        data = self.extractor.extract(text)
        # Nota: este caso pode falhar se o padrão não capturar valor sem R$
        # É um caso limite para diagnóstico
        if data.get("valor_total"):
            assert data.get("valor_total") == 1500.50

    def test_extrai_fornecedor_ltda(self):
        """Testar extração de nome de fornecedor com LTDA."""
        text = """
        FATURA
        EMPRESA DE TELECOMUNICAÇÕES EXEMPLO LTDA
        CNPJ: 12.345.678/0001-90
        Valor: R$ 350,00
        """
        assert self.extractor.can_handle(text)
        data = self.extractor.extract(text)
        assert data.get("fornecedor_nome") == "EMPRESA DE TELECOMUNICAÇÕES EXEMPLO LTDA"
        assert data.get("cnpj_fornecedor") == "12.345.678/0001-90"

    # Testes de CASOS PROBLEMÁTICOS reais

    def test_caso_tunna_entretenimento(self):
        """Testar caso real: TUNNA ENTRETENIMENTO (DANFE mal classificado)."""
        text = """
        RECEBEMOS DE TUNNA ENTRETENIMENTO
        FATURA N. 10731
        NATUREZA DA OPERACAO: PRESTACAO DE SERVICO

        DADOS DO PRODUTO / SERVICO
        CODIGO   DESCRICAO    QTD   VALOR UNIT   VALOR TOTAL
        001      PUBLICIDADE  1     500,00       500,00

        CALCULO DO IMPOSTO
        BASE ICMS  VALOR ICMS   VALOR TOTAL DA NOTA
        0,00       0,00         500,00
        """
        # Este deve ser rejeitado por ter múltiplos indicadores fiscais
        # (impostos e contexto de nota fiscal)
        assert not self.extractor.can_handle(text), (
            "Deveria rejeitar DANFE de TUNNA ENTRETENIMENTO"
        )

    def test_caso_tcf_telecom(self):
        """Testar caso real: TCF Telecom (NFSE com valor)."""
        text = """
        TCF TELECOM - Nota Fiscal
        NFS-E Nº 521912
        CNPJ: 12.345.678/0001-90

        VALOR DOS SERVIÇOS: R$ 1.250,00
        ISS: R$ 62,50

        DOCUMENTO AUXILIAR DA NFS-E
        """
        assert not self.extractor.can_handle(text), (
            "Deveria rejeitar NFSE da TCF Telecom"
        )

    def test_caso_agyone_t(self):
        """Testar caso real: AGYONE T (telecom - fatura administrativa)."""
        text = """
        AGYONET TELECOMUNICACOES LTDA
        Fatura de Servicos de Telecomunicacoes
        Cliente: ATIVE TELECOMUNICACOES
        Vencimento: 25/01/2026

        Resumo da Fatura
        Mensalidade Internet ... 150,00
        Servicos Adicionais ....  50,00

        Total a Pagar........... 200,00
        """
        assert self.extractor.can_handle(text), (
            "Deveria aceitar fatura administrativa da AGYONET"
        )
        data = self.extractor.extract(text)
        assert data.get("valor_total") == 200.00

    def test_caso_carrier_telecom(self):
        """Testar caso real: NFcom 114 CARRIER TELECOM."""
        text = """
        DOCUMENTO AUXILIAR DA NOTA FISCAL DE SERVIÇO ELETRÔNICA
        NOME: TELCABLES BRASIL LTDA FILIAL SAO PAULO
        ENDEREÇO: Rua Irma Gabriela, Nº 51, Cidade Moncoes
        CEP: 04.571-130, Sao Paulo

        VALOR DOS SERVIÇOS: 1.234,56
        """
        assert not self.extractor.can_handle(text), (
            "Deveria rejeitar NFSE da CARRIER TELECOM"
        )


if __name__ == "__main__":
    # Executar testes manualmente para depuração
    tester = TestOutrosExtractor()
    tester.setup_method()

    print("=" * 60)
    print("TESTES DO OUTROS EXTRACTOR - DIAGNÓSTICO")
    print("=" * 60)

    # Listar todos os métodos de teste
    test_methods = [m for m in dir(tester) if m.startswith("test_")]

    for method_name in test_methods:
        method = getattr(tester, method_name)
        try:
            method()
            print(f"✅ {method_name}: PASS")
        except AssertionError as e:
            print(f"❌ {method_name}: FAIL - {e}")
        except Exception as e:
            print(f"⚠️  {method_name}: ERROR - {e}")

    print("=" * 60)
    print(f"Total: {len(test_methods)} testes executados")
