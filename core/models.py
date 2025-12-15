from dataclasses import dataclass
from typing import Optional

@dataclass
class InvoiceData:
    arquivo_origem: str
    texto_bruto: str
    cnpj_prestador: Optional[str] = None
    numero_nota: Optional[str] = None
    data_emissao: Optional[str] = None
    valor_total: float = 0.0