# IMPORT ORDER MATTERS: o registro (EXTRACTOR_REGISTRY) é uma lista e a prioridade
# é definida pela ordem em que os módulos são importados.
# REGRA: Extractors ESPECÍFICOS devem vir ANTES dos GENÉRICOS

from .boleto import BoletoExtractor
from .boleto_repromaq import BoletoRepromaqExtractor  # Específico: antes do genérico
from .danfe import DanfeExtractor

# Extrator de corpo de e-mail (não usa EXTRACTOR_REGISTRY, é chamado diretamente)
from .email_body_extractor import (
    EmailBodyExtractionResult,
    EmailBodyExtractor,
    extract_from_email_body,
)
from .emc_fatura import EmcFaturaExtractor
from .net_center import NetCenterExtractor
from .nfse_custom_montes_claros import NfseCustomMontesClarosExtractor
from .nfse_custom_vila_velha import NfseCustomVilaVelhaExtractor
from .nfse_generic import NfseGenericExtractor
from .outros import OutrosExtractor
from .sicoob import SicoobExtractor
from .xml_extractor import XmlExtractionResult, XmlExtractor, extract_xml

__all__ = [
	"BoletoRepromaqExtractor",
	"BoletoExtractor",
	"DanfeExtractor",
	"EmcFaturaExtractor",
	"NetCenterExtractor",
	"NfseCustomMontesClarosExtractor",
	"NfseCustomVilaVelhaExtractor",
	"NfseGenericExtractor",
	"OutrosExtractor",
	"SicoobExtractor",
	"XmlExtractor",
	"XmlExtractionResult",
	"extract_xml",
	# Extrator de corpo de e-mail
	"EmailBodyExtractor",
	"EmailBodyExtractionResult",
	"extract_from_email_body",
]
