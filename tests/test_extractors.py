"""
Testes unitários para os extratores de dados.

Este módulo contém testes automatizados para validar a lógica
de extração de NFSe e Boletos, sem dependência de arquivos reais.
"""
import sys
from pathlib import Path

# Adiciona a raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

from extractors.boleto import BoletoExtractor
from extractors.danfe import DanfeExtractor
from extractors.nfse_generic import NfseGenericExtractor
from extractors.outros import OutrosExtractor


class TestGenericExtractor(unittest.TestCase):
    """Testes unitários para o extrator genérico de NFSe."""

    def setUp(self):
        """Inicializa o extrator antes de cada teste."""
        self.extractor = NfseGenericExtractor()

    def test_can_handle_nfse(self):
        """Verifica se identifica NFSe corretamente."""
        texto_nfse = "PREFEITURA MUNICIPAL NOTA FISCAL ELETRÔNICA Número: 12345"
        self.assertTrue(NfseGenericExtractor.can_handle(texto_nfse))

    def test_reject_boleto(self):
        """Verifica se rejeita boletos corretamente."""
        texto_boleto = "BANCO BRADESCO LINHA DIGITÁVEL CÓDIGO DE BARRAS BENEFICIÁRIO"
        self.assertFalse(NfseGenericExtractor.can_handle(texto_boleto))

    def test_extract_numero_nota_success(self):
        """Testa extração bem-sucedida de número de nota."""
        texto = """
        PREFEITURA MUNICIPAL DE SÃO PAULO
        Nota Fiscal de Serviço Eletrônica
        Número: 12345
        Data de Emissão: 15/12/2025
        """
        result = self.extractor._extract_numero_nota(texto)
        self.assertEqual(result, "12345")

    def test_extract_numero_nota_with_noise(self):
        """Testa extração com ruído no texto (RPS, Lote, etc)."""
        texto = """
        RPS 999 Lote 888
        Nota Fiscal Eletrônica
        Número da Nota: 54321
        Competência: 12/2025
        """
        result = self.extractor._extract_numero_nota(texto)
        self.assertIsNotNone(result)
        # Verifica se extraiu algum número válido
        self.assertTrue(len(result) > 0)

    def test_extract_valor_monetario_formatado(self):
        """Testa conversão de valores monetários brasileiros."""
        texto = "Valor Total dos Serviços: R$ 1.234,56"
        result = self.extractor._extract_valor(texto)
        self.assertAlmostEqual(result, 1234.56, places=2)

    def test_extract_valor_sem_milhar(self):
        """Testa extração de valor sem separador de milhar."""
        texto = "Total: R$ 999,99"
        result = self.extractor._extract_valor(texto)
        self.assertAlmostEqual(result, 999.99, places=2)

    def test_extract_valor_grande(self):
        """Testa extração de valores grandes."""
        texto = "Valor: R$ 123.456,78"
        result = self.extractor._extract_valor(texto)
        self.assertAlmostEqual(result, 123456.78, places=2)

    def test_extract_cnpj_formatado(self):
        """Testa extração de CNPJ formatado."""
        texto = "Prestador: EMPRESA XYZ LTDA CNPJ: 12.345.678/0001-99"
        result = self.extractor._extract_cnpj(texto)
        self.assertEqual(result, "12.345.678/0001-99")

    def test_extract_data_emissao_formatada(self):
        """Testa conversão de data para formato ISO."""
        texto = "Data de Emissão: 15/12/2025"
        result = self.extractor._extract_data_emissao(texto)
        self.assertEqual(result, "2025-12-15")

    def test_extract_retorna_dict_completo(self):
        """Testa se o método extract retorna todos os campos."""
        texto = """
        PREFEITURA DE TESTE
        NFS-e Número: 999
        CNPJ: 11.222.333/0001-44
        Emissão: 01/01/2025
        Valor: R$ 5.000,00
        """
        result = self.extractor.extract(texto)

        self.assertIn('tipo_documento', result)
        self.assertEqual(result['tipo_documento'], 'NFSE')
        self.assertIn('numero_nota', result)
        self.assertIn('valor_total', result)
        self.assertIn('cnpj_prestador', result)
        self.assertIn('data_emissao', result)


class TestBoletoExtractor(unittest.TestCase):
    """Testes unitários para o extrator de boletos."""

    def setUp(self):
        """Inicializa o extrator antes de cada teste."""
        self.extractor = BoletoExtractor()

    def test_can_handle_boleto(self):
        """Verifica se identifica boletos corretamente."""
        texto_boleto = """
        BANCO BRADESCO S.A.
        LINHA DIGITÁVEL: 23790.00009 12345.678901 23456.789012 3 12345678901234
        BENEFICIÁRIO: EMPRESA ABC LTDA
        VALOR DO DOCUMENTO: R$ 1.500,00
        VENCIMENTO: 31/12/2025
        """
        self.assertTrue(BoletoExtractor.can_handle(texto_boleto))

    def test_reject_nfse(self):
        """Verifica se rejeita NFSe corretamente."""
        texto_nfse = "PREFEITURA MUNICIPAL NFS-E NOTA FISCAL ELETRÔNICA"
        self.assertFalse(BoletoExtractor.can_handle(texto_nfse))

    def test_extract_linha_digitavel(self):
        """Testa extração de linha digitável."""
        texto = "LINHA DIGITÁVEL: 23790.00009 12345.678901 23456.789012 3 12345678901234"
        result = self.extractor._extract_linha_digitavel(texto)
        self.assertIsNotNone(result)
        # Verifica se contém dígitos
        self.assertTrue(any(c.isdigit() for c in result))

    def test_extract_valor_documento(self):
        """Testa extração do valor do boleto."""
        texto = "VALOR DO DOCUMENTO: R$ 2.500,75"
        result = self.extractor._extract_valor(texto)
        self.assertAlmostEqual(result, 2500.75, places=2)

    def test_extract_vencimento(self):
        """Testa extração e conversão da data de vencimento."""
        texto = "VENCIMENTO: 31/12/2025"
        result = self.extractor._extract_vencimento(texto)
        self.assertEqual(result, "2025-12-31")

    def test_extract_cnpj_beneficiario(self):
        """Testa extração do CNPJ do beneficiário."""
        texto = "BENEFICIÁRIO: EMPRESA XYZ LTDA CNPJ: 98.765.432/0001-10"
        result = self.extractor._extract_cnpj_beneficiario(texto)
        self.assertIsNotNone(result)
        self.assertIn("98.765.432/0001-10", result)

    def test_extract_retorna_dict_completo(self):
        """Testa se o método extract retorna todos os campos do boleto."""
        texto = """
        BANCO DO BRASIL
        BENEFICIÁRIO: EMPRESA ABC
        CNPJ: 11.222.333/0001-99
        VALOR DO DOCUMENTO: R$ 1.000,00
        VENCIMENTO: 15/01/2026
        LINHA DIGITÁVEL: 12345.67890 12345.678901 23456.789012 1 12345678901234
        """
        result = self.extractor.extract(texto)

        self.assertIn('tipo_documento', result)
        self.assertEqual(result['tipo_documento'], 'BOLETO')
        self.assertIn('valor_documento', result)
        self.assertIn('vencimento', result)
        self.assertIn('cnpj_beneficiario', result)
        self.assertIn('linha_digitavel', result)


class TestExtractionIntegration(unittest.TestCase):
    """Testes de integração para validar o fluxo completo."""

    def test_roteamento_nfse_vs_boleto(self):
        """Verifica se o roteamento entre NFSe e Boleto funciona corretamente."""
        texto_nfse = "PREFEITURA MUNICIPAL NOTA FISCAL ELETRÔNICA"
        texto_boleto = "BANCO BRADESCO LINHA DIGITÁVEL BENEFICIÁRIO VENCIMENTO CÓDIGO DE BARRAS"

        # NFSe deve ser aceita pelo NfseGenericExtractor e rejeitada pelo BoletoExtractor
        self.assertTrue(NfseGenericExtractor.can_handle(texto_nfse))
        self.assertFalse(BoletoExtractor.can_handle(texto_nfse))

        # Boleto deve ser rejeitado pelo NfseGenericExtractor e aceito pelo BoletoExtractor
        self.assertFalse(NfseGenericExtractor.can_handle(texto_boleto))
        self.assertTrue(BoletoExtractor.can_handle(texto_boleto))

    def test_extract_nfse_campos_minimos(self):
        """Testa se extração de NFSe retorna pelo menos número e valor."""
        texto = """
        PREFEITURA MUNICIPAL
        NFS-e 12345
        Valor: R$ 500,00
        """
        extractor = NfseGenericExtractor()
        result = extractor.extract(texto)

        # Deve ter número ou valor (critério mínimo)
        tem_numero = result.get('numero_nota') is not None
        tem_valor = result.get('valor_total', 0) > 0

        self.assertTrue(tem_numero or tem_valor,
                       "Extração deve retornar pelo menos número ou valor")

    def test_extract_boleto_campos_minimos(self):
        """Testa se extração de boleto retorna pelo menos valor e identificação."""
        texto = """
        BANCO XYZ
        VALOR: R$ 1.500,00
        VENCIMENTO: 31/12/2025
        LINHA DIGITÁVEL: 12345.67890 12345.678901
        """
        extractor = BoletoExtractor()
        result = extractor.extract(texto)

        # Deve ter valor
        tem_valor = result.get('valor_documento', 0) > 0
        # Deve ter vencimento OU linha digitável
        tem_identificacao = (result.get('vencimento') is not None or
                            result.get('linha_digitavel') is not None)

        self.assertTrue(tem_valor, "Boleto deve ter valor")
        self.assertTrue(tem_identificacao,
                       "Boleto deve ter vencimento ou linha digitável")


class TestDanfeExtractor(unittest.TestCase):
    def test_can_handle_danfe(self):
        texto = (
            "Recebemos de EMC TECNOLOGIA LTDA os produtos constantes na Nota Fiscal NF-e. "
            "DANFE EMC TECNOLOGIA LTDA DOCUMENTO AUXILIAR DA NOTA FISCAL ELETRÔNICA "
            "CHAVE DE ACESSO 3125 1122 2610 9300 0140 5500 1000 0877 3414 6437 6981 "
            "Valor total: 6.000,00 Emissão 07/11/2025"
        )
        self.assertTrue(DanfeExtractor.can_handle(texto))
        self.assertFalse(NfseGenericExtractor.can_handle(texto))

    def test_extract_valor_total_da_nota_picking_last_value(self):
        texto = (
            "CALCULO DO IMPOSTO\n"
            "BASE DE CÁLCULO DO ICMS VALOR DO ICMS BASE DE CÁLCULO DO ICMS ST VALOR DO ICMS ST VALOR TOTAL DOS PRODUTOS\n"
            "0,00 0,00 0,00 0,00 4.800,00\n"
            "VALOR DO FRETE VALOR DO SEGURO DESCONTO OUTRAS DESPESAS ACESSÓRIAS VALOR DO IPI VALOR TOTAL DA NOTA\n"
            "0,00 0,00 0,00 0,00 0,00 4.800,00\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertAlmostEqual(float(result.get('valor_total') or 0.0), 4800.00, places=2)

    def test_extract_valor_total_da_nota_small_value(self):
        texto = (
            "VALOR DO FRETE VALOR DO SEG. DESCONTO OUT. DESP. ACESSÓRIAS FCP FCP ST VALOR DO PIS VALOR DA COFINS VALOR TOTAL DA NOTA\n"
            "0,00 0,00 0,00 0,00 0,00 0,00 0,00 0,00 22,16\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertAlmostEqual(float(result.get('valor_total') or 0.0), 22.16, places=2)

    def test_extract_chave_acesso_44_digitos(self):
        """Testa extração de chave de acesso com 44 dígitos consecutivos."""
        texto = (
            "DANFE\n"
            "31230314169885000161550010001149061661292946\n"
            "CHAVE DE ACESSO\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertEqual(result.get('chave_acesso'), '31230314169885000161550010001149061661292946')

    def test_extract_chave_acesso_espacada(self):
        """Testa extração de chave de acesso com espaços."""
        texto = (
            "DANFE\n"
            "CHAVE DE ACESSO\n"
            "3123 0314 1698 8500 0161 5500 1000 1149 0616 6129 2946\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertEqual(result.get('chave_acesso'), '31230314169885000161550010001149061661292946')

    def test_extract_data_emissao_formato_padrao(self):
        """Testa extração de data de emissão no formato padrão DANFE."""
        texto = (
            "DANFE\n"
            "NOME RAZÃO SOCIAL CNPJ/CPF DATA DA EMISSÃO\n"
            "EMPRESA ABC LTDA 38.323.230/0001-64 10/03/2025\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertEqual(result.get('data_emissao'), '2025-03-10')

    def test_extract_data_emissao_apos_cnpj(self):
        """Testa extração de data de emissão que aparece após CNPJ."""
        texto = (
            "DANFE\n"
            "CNPJ/CPF DATA DA EMISSÃO\n"
            "14.169.885/0001-61 24/03/2023\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertEqual(result.get('data_emissao'), '2023-03-24')

    def test_extract_data_emissao_formato_hifen(self):
        """Testa extração de data de emissão com hífen (dd-mm-yyyy).

        Alguns DANFEs usam formato com hífen em vez de barra.
        Ex: ZOOM COMUNICACAO, MAGAZINE ELETRONICO, LUCIMAR EUSTAQUIO.
        """
        casos = [
            ("EMISSÃO: 24-02-2025 - VALOR TOTAL: R$ 3.200,00", "2025-02-24"),
            ("EMISSÃO: 07-04-2025 - VALOR TOTAL: R$ 8.700,00", "2025-04-07"),
            ("EMISSÃO: 05-06-2025 - VALOR TOTAL: R$ 900,00", "2025-06-05"),
            ("EMISSÃO: 08-05-2024 - VALOR TOTAL: R$ 627,00", "2024-05-08"),
        ]
        extractor = DanfeExtractor()
        for texto_emissao, esperado in casos:
            texto = f"DANFE\nCHAVE DE ACESSO\n{texto_emissao}\n"
            result = extractor.extract(texto)
            self.assertEqual(
                result.get('data_emissao'), esperado,
                f"Falhou para: {texto_emissao}"
            )

    def test_extract_duplicatas_multiplas(self):
        """Testa extração de múltiplas duplicatas/faturas."""
        texto = (
            "DANFE\n"
            "31230314169885000161550010001149061661292946\n"
            "FATURAS/ DUPLICATAS\n"
            "1/3 23/04/23 2.859,34\n"
            "2/3 23/05/23 2.679,33\n"
            "3/3 22/06/23 2.679,33\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)

        # Deve capturar o primeiro vencimento
        self.assertEqual(result.get('vencimento'), '2023-04-23')

        # Deve ter duplicatas
        duplicatas = result.get('duplicatas', [])
        self.assertEqual(len(duplicatas), 3)
        self.assertEqual(duplicatas[0]['parcela'], '1/3')
        self.assertAlmostEqual(duplicatas[0]['valor'], 2859.34, places=2)

    def test_extract_duplicatas_ano_2_digitos(self):
        """Testa extração de duplicatas com ano de 2 dígitos."""
        texto = (
            "DANFE\n"
            "31250314169885000161550010001284581777781395\n"
            "FATURAS/ DUPLICATAS\n"
            "1/1 09/04/25 272,00\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertEqual(result.get('vencimento'), '2025-04-09')

    def test_extract_numero_pedido(self):
        """Testa extração do número do pedido de compra."""
        texto = (
            "DANFE\n"
            "31250114169885000595550010000303581747710000\n"
            "PEDIDO DE COMPRAS 17078.\n"
            "VALOR TOTAL DA NOTA 47.475,00\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertEqual(result.get('numero_pedido'), '17078')

    def test_extract_numero_fatura_composto(self):
        """Testa geração do número de fatura composto (nota-parcela)."""
        texto = (
            "DANFE\n"
            "Nº000114906\n"
            "31230314169885000161550010001149061661292946\n"
            "FATURAS/ DUPLICATAS\n"
            "1/3 23/04/23 2.859,34\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertEqual(result.get('numero_fatura'), '114906-1/3')

    def test_extract_numero_nota_formato_n_ponto(self):
        """Testa extração de número de nota no formato 'N. 000003595'."""
        texto = (
            "DANFE\n"
            "RECEBEMOS DE Empresa XYZ OS PRODUTOS CONSTANTES DA NOTA FISCAL INDICADA AO LADO NF-e\n"
            "DATA DE RECEBIMENTO IDENTIFICAÇÃO E ASSINATURA DO RECEBEDOR N. 000003595\n"
            "SÉRIE 1\n"
            "N. 000003595\n"
            "SÉRIE 1\n"
        )
        extractor = DanfeExtractor()
        result = extractor.extract(texto)
        self.assertEqual(result.get('numero_nota'), '3595')

    def test_extract_azul_distribuidora_completo(self):
        """Teste de integração com estrutura típica da Azul Distribuidora."""
        texto = """
        DANFE
        DOCUMENTO AUXILIAR
        DA NOTA FISCAL
        ELETRÔNICA
        31250114169885000595550010000308381189120506
        0- ENTRADA CHAVE DE ACESSO
        1
        1- SAÍDA 3125 0114 1698 8500 0595 5500 1000 0308 3811 8912 0506
        AZUL DISTRIBUIDORA E COMERCIO DE
        INFORMATICA LTDA Nº000030838
        NATUREZA DA OPERAÇÃO DADOS DA NF-e
        VENDA DE MERCADORIA. 131256427403591
        INSCRIÇÃO ESTADUAL INSC. EST. SUBST. TRIBUTÁRIO CNPJ
        0018271130439 14.169.885/0005-95
        DESTINATÁRIO / REMETENTE
        NOME RAZÃO SOCIAL CNPJ/CPF DATA DA EMISSÃO
        ATIVE TELECOMUNICACOES S.A. 33.960.847/0002-58 20/01/2025
        FATURAS/ DUPLICATAS
        1/8 19/02/25 11.868,75 4/8 20/05/25 11.868,75
        2/8 21/03/25 11.868,75 5/8 19/06/25 11.868,75
        VALOR TOTAL DA NOTA
        94.950,00
        PEDIDO DE COMPRAS 17095.
        RECEBEMOS DE AZUL DISTRIBUIDORA E COMERCIO DE INFORMATICA LTDA OS PRODUTOS
        """
        extractor = DanfeExtractor()
        result = extractor.extract(texto)

        # Verifica todos os campos críticos
        self.assertEqual(result.get('tipo_documento'), 'DANFE')
        self.assertEqual(result.get('numero_nota'), '30838')
        self.assertEqual(result.get('chave_acesso'), '31250114169885000595550010000308381189120506')
        self.assertEqual(result.get('data_emissao'), '2025-01-20')
        self.assertEqual(result.get('vencimento'), '2025-02-19')
        self.assertAlmostEqual(result.get('valor_total', 0), 94950.0, places=2)
        self.assertEqual(result.get('numero_pedido'), '17095')
        self.assertEqual(result.get('fornecedor_nome'), 'AZUL DISTRIBUIDORA E COMERCIO DE INFORMATICA LTDA')
        self.assertEqual(result.get('cnpj_emitente'), '14.169.885/0005-95')


class TestOutrosExtractor(unittest.TestCase):
    def test_can_handle_locacao(self):
        texto = (
            "DEMONSTRATIVO DE LOCAÇÃO\n"
            "VALOR DA LOCAÇÃO 2.855,00\n"
            "REPROMAQ COMERCIO E SERVICOS DE TECNOLOGIA LTDA"
        )
        self.assertTrue(OutrosExtractor.can_handle(texto))
        self.assertFalse(NfseGenericExtractor.can_handle(texto))

    def test_extract_locacao_total_a_pagar_mes(self):
        extractor = OutrosExtractor()
        texto = (
            "DEMONSTRATIVO DE LOCAÇÃO ANALÍTICO GLOBAL\n"
            "7 - Descontos 0,00\n"
            "8 - Acréscimos 0,00\n"
            "9 - Serviços 0,00000\n"
            "Total a Pagar no Mês (1 + 6 - 7 + 8 + 9) 2.855,00\n"
            "Cliente: 00003222 CSC GESTAO INTEGRADA S/A\n"
        )
        data = extractor.extract(texto)
        self.assertEqual(data.get('subtipo'), 'LOCACAO')
        self.assertAlmostEqual(data.get('valor_total', 0.0), 2855.0, places=2)


class TestEdgeCases(unittest.TestCase):
    """Testes para casos extremos e situações adversas."""

    def test_texto_vazio(self):
        """Testa comportamento com texto vazio."""
        extractor = NfseGenericExtractor()
        result = extractor.extract("")

        # Não deve lançar exceção
        self.assertIsInstance(result, dict)

    def test_texto_sem_numeros(self):
        """Testa extração quando não há números no texto."""
        extractor = NfseGenericExtractor()
        texto = "TEXTO SEM NENHUM DIGITO"
        result = extractor.extract(texto)

        # Deve retornar valores vazios/zero, mas não None para o dict
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get('valor_total', 0), 0.0)

    def test_valor_com_formato_invalido(self):
        """Testa extração de valor com formato inesperado."""
        extractor = NfseGenericExtractor()
        texto = "Valor: 1.234.567,89 reais"  # Sem R$
        result = extractor._extract_valor(texto)

        # Deve retornar 0.0 ou tentar extrair mesmo assim
        self.assertIsInstance(result, (int, float))


if __name__ == '__main__':
    # Configura o runner para mostrar resultados detalhados
    unittest.main(verbosity=2)
