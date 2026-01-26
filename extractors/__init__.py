# IMPORT ORDER MATTERS: o registro (EXTRACTOR_REGISTRY) é uma lista e a prioridade
# é definida pela ordem em que os módulos são importados.
# REGRA: Extractors ESPECÍFICOS devem vir ANTES dos GENÉRICOS
from .boleto_repromaq import BoletoRepromaqExtractor
from .emc_fatura import EmcFaturaExtractor
from .net_center import NetCenterExtractor
from .nfse_custom_montes_claros import NfseCustomMontesClarosExtractor
from .nfse_custom_vila_velha import NfseCustomVilaVelhaExtractor
from .energy_bill import EnergyBillExtractor

# Extrator especializado para documentos administrativos (deve vir antes dos genéricos)
from .admin_document import AdminDocumentExtractor

# Extrator de corpo de e-mail (não usa EXTRACTOR_REGISTRY, é chamado diretamente)
from .email_body_extractor import (
    EmailBodyExtractionResult,
    EmailBodyExtractor,
    extract_from_email_body,
)


# Extractores genéricos (vêm depois dos específicos)
from .outros import OutrosExtractor
from .nfse_generic import NfseGenericExtractor
from .boleto import BoletoExtractor
from .sicoob import SicoobExtractor
from .danfe import DanfeExtractor
from .xml_extractor import XmlExtractionResult, XmlExtractor, extract_xml

__all__ = [
    "BoletoRepromaqExtractor",
    "BoletoExtractor",
    "DanfeExtractor",
    "EmcFaturaExtractor",
    "NetCenterExtractor",
    "OutrosExtractor",
    "SicoobExtractor",
    "EnergyBillExtractor",
    "NfseCustomMontesClarosExtractor",
    "NfseCustomVilaVelhaExtractor",
    "NfseGenericExtractor",
    "XmlExtractor",
    "XmlExtractionResult",
    "extract_xml",
    # Extrator de corpo de e-mail
    "EmailBodyExtractor",
    "EmailBodyExtractionResult",
    "extract_from_email_body",
    # Extrator especializado para documentos administrativos
    "AdminDocumentExtractor",
]
