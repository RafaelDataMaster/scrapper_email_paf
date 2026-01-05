# IMPORT ORDER MATTERS: o registro (EXTRACTOR_REGISTRY) é uma lista e a prioridade
# é definida pela ordem em que os módulos são importados.

from .boleto import BoletoExtractor
from .danfe import DanfeExtractor
from .emc_fatura import EmcFaturaExtractor
from .net_center import NetCenterExtractor
from .nfse_generic import NfseGenericExtractor
from .outros import OutrosExtractor
from .sicoob import SicoobExtractor
from .xml_extractor import XmlExtractionResult, XmlExtractor, extract_xml

__all__ = [
	"BoletoExtractor",
	"DanfeExtractor",
	"EmcFaturaExtractor",
	"NetCenterExtractor",
	"NfseGenericExtractor",
	"OutrosExtractor",
	"SicoobExtractor",
	"XmlExtractor",
	"XmlExtractionResult",
	"extract_xml",
]
