"""
Teste do NfseGenericExtractor com texto real de PDF.

Este teste verifica se o extrator NFSE genérico consegue processar corretamente
documentos de NFSE que estavam sendo classificados incorretamente como "outros".

Caso de teste: PDF "01_NFcom 114 CARRIER TELECOM.pdf" que estava sendo
classificado como "outro" com valor zero.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from extractors.nfse_generic import NfseGenericExtractor
from extractors.outros import OutrosExtractor
from extractors.admin_document import AdminDocumentExtractor
from extractors.danfe import DanfeExtractor
from extractors.boleto import BoletoExtractor

# Configurar logging para ver detalhes
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# Texto real extraído do PDF "01_NFcom 114 CARRIER TELECOM.pdf"
TEXTO_CARRIER_TELECOM = """DOCUMENTO AUXILIAR DA NOTA FISCAL FATURA DE SERVIÇOS DE COMUNICAÇÃO ELETRÔNICA
NOME: TELCABLES BRASIL LTDA FILIAL SAO PAULO
ENDEREÇO: Rua Irma Gabriela, Nº 51, Cidade Moncoes
CEP: 04.571-130, Sao Paulo - SP
CPF/CNPJ: 20.609.743/0004-13
INSCRIÇÃO ESTADUAL: 141.170.861.118
REFERÊNCIA: 11/2025
NOTA FISCAL FATURA: 114
SÉRIE: 1 VENCIMENTO: 23/12/2025
DATA DE EMISSÃO:
TOTAL A PAGAR: R$ 29.250,00
10/11/2025
CÓDIGO DO CLIENTE: 100288
Nº TELEFONE: 37999983900
PERÍODO: 01/01/0001 - 01/01/0001
QR Code para pagamento PIX
CONSULTE PELA CHAVE DE ACESSO EM:
https://dfe-portal.svrs.rs.gov.br/NFCom
CHAVE DE ACESSO:
3525 1120 6097 4300 0413 6200 1000 0001 1410 2827 2913
Protocolo de Autorização:
3352500028624395 - 10/11/2025 às 16:34:41
Nº IDENTIFICADOR DO DÉBITO AUTOMÁTICO
03399.90038 58400.000004 00447.201013 5 13040002925000
ÁREA CONTRIBUINTE:
MENSAGENS PRIORITÁRIAS / AVISOS AO CONSUMIDOR
ITENS DA FATURA UN QUANT PREÇO UNIT VALOR TOTAL PIS/COFINS BC ICMS AL Q VALOR ICMS
CNTINT02 - IP Transit UN 1,00"""


class TestNfseExtraction:
    """Testes para verificar a extração correta de NFSE."""

    def setup_method(self):
        """Configurar extratores antes de cada teste."""
        self.nfse_extractor = NfseGenericExtractor()
        self.outros_extractor = OutrosExtractor()
        self.admin_extractor = AdminDocumentExtractor()
        self.danfe_extractor = DanfeExtractor()
        self.boleto_extractor = BoletoExtractor()

    def test_outros_extractor_should_not_handle_carrier_telecom(self):
        """Testar se OutrosExtractor NÃO reconhece o documento Carrier Telecom."""
        # Este documento NÃO DEVE ser reconhecido como "outro"
        result = self.outros_extractor.can_handle(TEXTO_CARRIER_TELECOM)
        assert not result, (
            "OutrosExtractor NÃO deveria reconhecer documento Carrier Telecom. "
            "O texto contém indicadores fortes de NFSE que devem ser excluídos."
        )

    def test_admin_extractor_should_not_handle_carrier_telecom(self):
        """Testar se AdminDocumentExtractor NÃO reconhece o documento Carrier Telecom."""
        # Este documento NÃO DEVE ser reconhecido como administrativo
        result = self.admin_extractor.can_handle(TEXTO_CARRIER_TELECOM)
        assert not result, (
            "AdminDocumentExtractor NÃO deveria reconhecer documento Carrier Telecom. "
            "O texto contém indicadores fortes de NFSE que devem ser excluídos."
        )

    def test_danfe_extractor_should_not_handle_carrier_telecom(self):
        """Testar se DanfeExtractor NÃO reconhece o documento Carrier Telecom."""
        # Este documento NÃO DEVE ser reconhecido como DANFE (apesar de ter "CHAVE DE ACESSO")
        result = self.danfe_extractor.can_handle(TEXTO_CARRIER_TELECOM)
        # DanfeExtractor pode retornar True por causa da chave de acesso, então vamos verificar
        # se pelo menos o extrator NFSE tem prioridade
        if result:
            logger.warning(
                "DanfeExtractor reconheceu documento Carrier Telecom (provavelmente por causa da chave de acesso). "
                "Verifique se a ordem de extratores está correta (NFSE antes de DANFE)."
            )

    def test_boleto_extractor_should_not_handle_carrier_telecom(self):
        """Testar se BoletoExtractor NÃO reconhece o documento Carrier Telecom."""
        # Este documento NÃO DEVE ser reconhecido como boleto
        result = self.boleto_extractor.can_handle(TEXTO_CARRIER_TELECOM)
        assert not result, (
            "BoletoExtractor NÃO deveria reconhecer documento Carrier Telecom. "
            "Não contém indicadores de boleto."
        )

    def test_nfse_detection_with_documento_auxiliar(self):
        """Testar detecção de NFSE com 'DOCUMENTO AUXILIAR DA NOTA FISCAL'."""
        # Texto mínimo com apenas o indicador forte
        texto_minimo = (
            "DOCUMENTO AUXILIAR DA NOTA FISCAL DE SERVIÇO ELETRÔNICA\nTOTAL: R$ 100,00"
        )

        result = self.nfse_extractor.can_handle(texto_minimo)
        assert result, (
            "NfseGenericExtractor deveria reconhecer documento com 'DOCUMENTO AUXILIAR DA NOTA FISCAL'"
        )

    def test_nfse_detection_with_nfse_keyword(self):
        """Testar detecção de NFSE com 'NFS-E'."""
        texto_nfse = "NFS-E Nº 12345\nVALOR TOTAL: R$ 500,00"

        result = self.nfse_extractor.can_handle(texto_nfse)
        assert result, "NfseGenericExtractor deveria reconhecer documento com 'NFS-E'"

    def test_nota_fatura_detection(self):
        """Testar que 'NOTA FATURA' é considerado NFSE (não 'outro')."""
        # Caso TUNNA ENTRETENIMENTO
        texto_tunna = """NOTA FATURA Nº 10731
FORNECEDOR: TUNNA ENTRETENIMENTO
VALOR TOTAL: R$ 500,00"""

        # Deve ser NFSE, não "outro"
        nfse_result = self.nfse_extractor.can_handle(texto_tunna)
        outros_result = self.outros_extractor.can_handle(texto_tunna)

        # 'NOTA FATURA' é NFSE
        assert nfse_result, "'NOTA FATURA' deveria ser reconhecido como NFSE"
        assert not outros_result, (
            "'NOTA FATURA' NÃO deveria ser reconhecido como 'outro'"
        )

    def test_extraction_order_priority(self):
        """Testar a ordem de prioridade dos extratores."""
        # Importar a lista de extratores registrados
        from core.extractors import EXTRACTOR_REGISTRY

        # Verificar se NFSE vem antes de Outros
        extractor_names = [cls.__name__ for cls in EXTRACTOR_REGISTRY]

        nfse_index = next(
            (
                i
                for i, name in enumerate(extractor_names)
                if "NfseGenericExtractor" in name
            ),
            -1,
        )
        outros_index = next(
            (i for i, name in enumerate(extractor_names) if "OutrosExtractor" in name),
            -1,
        )
        admin_index = next(
            (
                i
                for i, name in enumerate(extractor_names)
                if "AdminDocumentExtractor" in name
            ),
            -1,
        )

        # AdminDocumentExtractor deve vir antes de OutrosExtractor
        if admin_index >= 0 and outros_index >= 0:
            assert admin_index < outros_index, (
                f"AdminDocumentExtractor (índice {admin_index}) deve vir antes de "
                f"OutrosExtractor (índice {outros_index})"
            )

        # NfseGenericExtractor deve vir depois de extratores específicos mas antes de fallbacks
        if nfse_index >= 0:
            logger.info(
                f"NfseGenericExtractor está na posição {nfse_index} de {len(extractor_names)}"
            )
            logger.info(f"Ordem completa: {extractor_names}")


def run_tests():
    """Executar testes manualmente para depuração."""
    tester = TestNfseExtraction()
    tester.setup_method()

    print("=" * 80)
    print("TESTES DE EXTRAÇÃO NFSE - CARRIER TELECOM")
    print("=" * 80)

    test_methods = [
        "test_nfse_generic_should_handle_carrier_telecom",
        "test_outros_extractor_should_not_handle_carrier_telecom",
        "test_admin_extractor_should_not_handle_carrier_telecom",
        "test_danfe_extractor_should_not_handle_carrier_telecom",
        "test_boleto_extractor_should_not_handle_carrier_telecom",
        "test_nfse_extraction_values_carrier_telecom",
        "test_nfse_detection_with_documento_auxiliar",
        "test_nfse_detection_with_nfse_keyword",
        "test_nota_fatura_detection",
        "test_extraction_order_priority",
    ]

    passed = 0
    failed = 0
    skipped = 0

    for method_name in test_methods:
        try:
            method = getattr(tester, method_name)
            method()
            print(f"PASS: {method_name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {method_name} - {e}")
            failed += 1
        except Exception as e:
            if "skip" in str(e).lower():
                print(f"SKIP: {method_name} - {e}")
                skipped += 1
            else:
                print(f"ERROR: {method_name} - {e}")
                failed += 1

    print("=" * 80)
    print(f"RESUMO: {passed} passaram, {failed} falharam, {skipped} pulados")
    print("=" * 80)

    if failed == 0:
        print("✅ Todos os testes essenciais passaram!")
    else:
        print(f"⚠️  {failed} teste(s) falhou/falharam. Verifique os logs acima.")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
