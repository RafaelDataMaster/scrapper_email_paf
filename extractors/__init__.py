# IMPORT ORDER MATTERS: o registro (EXTRACTOR_REGISTRY) é uma lista e a prioridade
# é definida pela ordem em que os módulos são importados.

from .nfse_generic import NfseGenericExtractor
from .net_center import NetCenterExtractor
from .sicoob import SicoobExtractor
from .boleto import BoletoExtractor
from .danfe import DanfeExtractor
from .outros import OutrosExtractor

__all__ = [
	"BoletoExtractor",
	"DanfeExtractor",
	"NetCenterExtractor",
	"NfseGenericExtractor",
	"OutrosExtractor",
	"SicoobExtractor",
]
