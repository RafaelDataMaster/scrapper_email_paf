from dataclasses import dataclass
from typing import Optional
from abc import ABC, abstractmethod

@dataclass
class DocumentData(ABC):
    """
    Classe base abstrata para todos os tipos de documentos processados.
    
    Define o contrato comum que todos os modelos de documento devem seguir,
    facilitando a extensão do sistema para novos tipos (OCP - Open/Closed Principle).
    
    Attributes:
        arquivo_origem (str): Nome do arquivo PDF processado.
        texto_bruto (str): Snippet do texto extraído (para debug).
        doc_type (str): Tipo do documento ('NFSE', 'BOLETO', etc.).
    """
    arquivo_origem: str
    texto_bruto: str
    
    @property
    @abstractmethod
    def doc_type(self) -> str:
        """Retorna o tipo do documento. Deve ser sobrescrito por subclasses."""
        pass
    
    @abstractmethod
    def to_dict(self) -> dict:
        """Converte o documento para dicionário. Usado para exportação."""
        pass

@dataclass
class InvoiceData(DocumentData):
    """
    Modelo de dados padronizado para uma Nota Fiscal de Serviço.

    Attributes:
        arquivo_origem (str): Nome do arquivo PDF processado.
        texto_bruto (str): Snippet do texto extraído (para fins de debug).
        cnpj_prestador (Optional[str]): CNPJ formatado do prestador de serviço.
        numero_nota (Optional[str]): Número da nota fiscal limpo.
        data_emissao (Optional[str]): Data de emissão no formato YYYY-MM-DD.
        valor_total (float): Valor total líquido da nota.
    """
    cnpj_prestador: Optional[str] = None
    numero_nota: Optional[str] = None
    data_emissao: Optional[str] = None
    valor_total: float = 0.0
    
    @property
    def doc_type(self) -> str:
        """Retorna o tipo do documento."""
        return 'NFSE'
    
    def to_dict(self) -> dict:
        """Converte InvoiceData para dicionário."""
        return {
            'tipo_documento': self.doc_type,
            'arquivo_origem': self.arquivo_origem,
            'cnpj_prestador': self.cnpj_prestador,
            'numero_nota': self.numero_nota,
            'data_emissao': self.data_emissao,
            'valor_total': self.valor_total,
            'texto_bruto': self.texto_bruto[:200] if self.texto_bruto else None
        }

@dataclass
class BoletoData(DocumentData):
    """
    Modelo de dados para Boletos Bancários.

    Attributes:
        arquivo_origem (str): Nome do arquivo PDF processado.
        texto_bruto (str): Snippet do texto extraído.
        cnpj_beneficiario (Optional[str]): CNPJ do beneficiário (quem recebe).
        valor_documento (float): Valor nominal do boleto.
        vencimento (Optional[str]): Data de vencimento no formato YYYY-MM-DD.
        numero_documento (Optional[str]): Número do documento/fatura.
        linha_digitavel (Optional[str]): Linha digitável do boleto.
        nosso_numero (Optional[str]): Nosso número (identificação do banco).
        referencia_nfse (Optional[str]): Número da NFSe vinculada (se encontrado).
    """
    cnpj_beneficiario: Optional[str] = None
    valor_documento: float = 0.0
    vencimento: Optional[str] = None
    numero_documento: Optional[str] = None
    linha_digitavel: Optional[str] = None
    nosso_numero: Optional[str] = None
    referencia_nfse: Optional[str] = None
    
    @property
    def doc_type(self) -> str:
        """Retorna o tipo do documento."""
        return 'BOLETO'
    
    def to_dict(self) -> dict:
        """Converte BoletoData para dicionário."""
        return {
            'tipo_documento': self.doc_type,
            'arquivo_origem': self.arquivo_origem,
            'cnpj_beneficiario': self.cnpj_beneficiario,
            'valor_documento': self.valor_documento,
            'vencimento': self.vencimento,
            'numero_documento': self.numero_documento,
            'linha_digitavel': self.linha_digitavel,
            'nosso_numero': self.nosso_numero,
            'referencia_nfse': self.referencia_nfse,
            'texto_bruto': self.texto_bruto[:200] if self.texto_bruto else None
        }