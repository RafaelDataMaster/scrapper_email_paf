from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from core.metadata import EmailMetadata


@dataclass
class DocumentData(ABC):
    """
    Classe base abstrata para todos os tipos de documentos processados.

    Define o contrato comum que todos os modelos de documento devem seguir,
    facilitando a extensão do sistema para novos tipos (OCP - Open/Closed Principle).

    Attributes:
        arquivo_origem (str): Nome do arquivo PDF processado.
        texto_bruto (str): Snippet do texto extraído (para debug).
        data_processamento (Optional[str]): Data de processamento no formato ISO (YYYY-MM-DD).
        setor (Optional[str]): Setor responsável (ex: 'RH', 'MKT').
        empresa (Optional[str]): Empresa (ex: 'CSC', 'MOC').
        observacoes (Optional[str]): Observações gerais para a planilha PAF.
        obs_interna (Optional[str]): Observações internas para uso do time técnico.
        doc_type (str): Tipo do documento ('NFSE', 'BOLETO', etc.).

        # Campos de contexto de lote (novos - refatoração)
        batch_id (Optional[str]): Identificador da pasta/lote de processamento.
        source_email_subject (Optional[str]): Assunto do e-mail original (para tabela MVP).
        source_email_sender (Optional[str]): Remetente do e-mail (fallback para Fornecedor).
        valor_compra (Optional[float]): Valor da compra/locação do lote.
        status_conciliacao (Optional[str]): Status da validação ('OK', 'DIVERGENTE', 'CONFERIR').
    """
    arquivo_origem: str
    texto_bruto: str = ""
    data_processamento: Optional[str] = None
    setor: Optional[str] = None
    empresa: Optional[str] = None
    observacoes: Optional[str] = None
    obs_interna: Optional[str] = None

    # Campos de contexto de lote (novos - refatoração)
    batch_id: Optional[str] = None
    source_email_subject: Optional[str] = None
    source_email_sender: Optional[str] = None
    valor_compra: Optional[float] = None
    status_conciliacao: Optional[str] = None

    @property
    @abstractmethod
    def doc_type(self) -> str:
        """Retorna o tipo do documento. Deve ser sobrescrito por subclasses."""
        pass

    @abstractmethod
    def to_dict(self) -> dict:
        """Converte o documento para dicionário. Usado para exportação."""
        pass

    @abstractmethod
    def to_sheets_row(self) -> list:
        """
        Converte o documento para lista de 18 valores na ordem da planilha PAF.

        Ordem PAF: DATA, SETOR, EMPRESA, FORNECEDOR, NF, EMISSÃO, VALOR,
        Nº PEDIDO, VENCIMENTO, FORMA PAGTO, (vazio), DT CLASS, Nº FAT,
        TP DOC, TRAT PAF, LANC SISTEMA, OBSERVAÇÕES, OBS INTERNA

        Returns:
            list: Lista com 18 elementos para inserção direta no Google Sheets
        """
        pass

@dataclass
class InvoiceData(DocumentData):
    """
    Modelo de dados padronizado para uma Nota Fiscal de Serviço (NFSe).

    Alinhado com as 18 colunas da planilha "PAF NOVO - SETORES CSC".
    Conformidade: Política Interna 5.9 e POP 4.10 (Master Internet).

    Attributes:
        arquivo_origem (str): Nome do arquivo PDF processado.
        texto_bruto (str): Snippet do texto extraído (para fins de debug).

        # Identificação e Fornecedor
        cnpj_prestador (Optional[str]): CNPJ formatado do prestador de serviço.
        fornecedor_nome (Optional[str]): Razão Social do prestador (coluna FORNECEDOR).
        numero_nota (Optional[str]): Número da nota fiscal limpo.
        serie_nf (Optional[str]): Série da nota fiscal.
        data_emissao (Optional[str]): Data de emissão no formato ISO (YYYY-MM-DD).

        # Valores e Impostos Individuais
        valor_total (float): Valor total líquido da nota.
        valor_ir (Optional[float]): Imposto de Renda retido.
        valor_inss (Optional[float]): INSS retido.
        valor_csll (Optional[float]): CSLL retido.
        valor_iss (Optional[float]): ISS devido ou retido.
        valor_icms (Optional[float]): ICMS (quando aplicável).
        base_calculo_icms (Optional[float]): Base de cálculo do ICMS.

        # Pagamento e Classificação PAF
        vencimento (Optional[str]): Data de vencimento no formato ISO (YYYY-MM-DD).
        forma_pagamento (Optional[str]): PIX, TED, BOLETO, etc.
        numero_pedido (Optional[str]): Número do pedido/PC (coluna Nº PEDIDO).
        numero_fatura (Optional[str]): Número da fatura (coluna Nº FAT).
        tipo_doc_paf (str): Tipo de documento para PAF (default: "NF").
        dt_classificacao (Optional[str]): Data de classificação no formato ISO.
        trat_paf (Optional[str]): Responsável pela classificação (coluna TRAT PAF).
        lanc_sistema (str): Status de lançamento no ERP (default: "PENDENTE").

        # Campos Secundários (Implementação Fase 2)
        cfop (Optional[str]): Código Fiscal de Operações e Prestações.
        cst (Optional[str]): Código de Situação Tributária.
        ncm (Optional[str]): Nomenclatura Comum do Mercosul.
        natureza_operacao (Optional[str]): Natureza da operação fiscal.

        # Rastreabilidade
        link_drive (Optional[str]): URL do documento no Google Drive.
    """
    cnpj_prestador: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    numero_nota: Optional[str] = None
    serie_nf: Optional[str] = None
    data_emissao: Optional[str] = None
    valor_total: float = 0.0

    # Impostos individuais
    valor_ir: Optional[float] = None
    valor_inss: Optional[float] = None
    valor_csll: Optional[float] = None
    valor_iss: Optional[float] = None
    valor_icms: Optional[float] = None
    base_calculo_icms: Optional[float] = None

    # Campos PAF
    vencimento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    numero_pedido: Optional[str] = None
    numero_fatura: Optional[str] = None
    tipo_doc_paf: str = "NF"
    dt_classificacao: Optional[str] = None
    trat_paf: Optional[str] = None
    lanc_sistema: str = "PENDENTE"

    # TODO: Implementar em segunda fase - campos secundários para compliance fiscal completo
    cfop: Optional[str] = None
    cst: Optional[str] = None
    ncm: Optional[str] = None
    natureza_operacao: Optional[str] = None

    link_drive: Optional[str] = None

    @property
    def total_retencoes(self) -> float:
        """
        Calcula o total de retenções federais (IR + INSS + CSLL).

        Usado para exportação e validações financeiras.
        Considera apenas valores não-None para evitar erros de cálculo.

        Returns:
            float: Soma das retenções ou 0.0 se todas forem None
        """
        valores = [self.valor_ir, self.valor_inss, self.valor_csll]
        retencoes = [v for v in valores if v is not None]
        return sum(retencoes) if retencoes else 0.0

    @property
    def doc_type(self) -> str:
        """Retorna o tipo do documento."""
        return 'NFSE'

    def to_dict(self) -> dict:
        """
        Converte InvoiceData para dicionário mantendo semântica None.

        Mantém valores None para campos não extraídos (importante para debug).
        Use to_sheets_row() para exportação com conversões apropriadas.
        """
        return {
            'tipo_documento': self.doc_type,
            'arquivo_origem': self.arquivo_origem,
            'data_processamento': self.data_processamento,
            'setor': self.setor,
            'empresa': self.empresa,
            'cnpj_prestador': self.cnpj_prestador,
            'fornecedor_nome': self.fornecedor_nome,
            'numero_nota': self.numero_nota,
            'serie_nf': self.serie_nf,
            'data_emissao': self.data_emissao,
            'valor_total': self.valor_total,
            'valor_ir': self.valor_ir,
            'valor_inss': self.valor_inss,
            'valor_csll': self.valor_csll,
            'valor_iss': self.valor_iss,
            'valor_icms': self.valor_icms,
            'base_calculo_icms': self.base_calculo_icms,
            'total_retencoes': self.total_retencoes,
            'vencimento': self.vencimento,
            'forma_pagamento': self.forma_pagamento,
            'numero_pedido': self.numero_pedido,
            'numero_fatura': self.numero_fatura,
            'tipo_doc_paf': self.tipo_doc_paf,
            'dt_classificacao': self.dt_classificacao,
            'trat_paf': self.trat_paf,
            'lanc_sistema': self.lanc_sistema,
            'cfop': self.cfop,
            'cst': self.cst,
            'ncm': self.ncm,
            'natureza_operacao': self.natureza_operacao,
            'link_drive': self.link_drive,
            'observacoes': self.observacoes,
            'obs_interna': self.obs_interna,
            'texto_bruto': self.texto_bruto[:200] if self.texto_bruto else None,
            'status_conciliacao': self.status_conciliacao,
            'valor_compra': self.valor_compra,
        }

    def to_sheets_row(self) -> list:
        """
        Converte InvoiceData para lista de 18 valores na ordem da planilha PAF.

        Ordem das colunas PAF:
        1. DATA (processamento) - 2. SETOR - 3. EMPRESA - 4. FORNECEDOR
        5. NF - 6. EMISSÃO - 7. VALOR - 8. Nº PEDIDO
        9. VENCIMENTO - 10. FORMA PAGTO - 11. (vazio/índice)
        12. DT CLASS - 13. Nº FAT - 14. TP DOC - 15. TRAT PAF
        16. LANC SISTEMA - 17. OBSERVAÇÕES - 18. OBS INTERNA

        Conversões aplicadas:
        - Datas ISO (YYYY-MM-DD) → formato brasileiro (DD/MM/YYYY)
        - None numéricos → 0.0
        - None strings → ""

        Returns:
            list: Lista com 18 elementos para append no Google Sheets
        """
        def fmt_date(iso_date: Optional[str]) -> str:
            """Converte data ISO para formato brasileiro DD/MM/YYYY."""
            if not iso_date:
                return ""
            try:
                dt = datetime.strptime(iso_date, '%Y-%m-%d')
                return dt.strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                return ""

        def fmt_num(value: Optional[float]) -> float:
            """Converte None para 0.0 em campos numéricos."""
            return value if value is not None else 0.0

        def fmt_str(value: Optional[str]) -> str:
            """Converte None para string vazia."""
            return value if value is not None else ""

        # MVP: número de NF será preenchido via ingestão (e-mail), então exportamos vazio.
        try:
            from config.settings import PAF_EXPORT_NF_EMPTY
        except Exception:
            PAF_EXPORT_NF_EMPTY = False

        nf_value = "" if PAF_EXPORT_NF_EMPTY else fmt_str(self.numero_nota)
        fat_value = "" if PAF_EXPORT_NF_EMPTY else fmt_str(self.numero_fatura)

        return [
            fmt_date(self.data_processamento),  # 1. DATA
            fmt_str(self.setor),                 # 2. SETOR
            fmt_str(self.empresa),               # 3. EMPRESA
            fmt_str(self.fornecedor_nome),       # 4. FORNECEDOR
            nf_value,                            # 5. NF
            fmt_date(self.data_emissao),         # 6. EMISSÃO
            fmt_num(self.valor_total),           # 7. VALOR
            fmt_str(self.numero_pedido),         # 8. Nº PEDIDO
            fmt_date(self.vencimento),           # 9. VENCIMENTO
            fmt_str(self.forma_pagamento),       # 10. FORMA PAGTO
            "",                                  # 11. (coluna vazia/índice)
            fmt_date(self.dt_classificacao),     # 12. DT CLASS
            fat_value,                           # 13. Nº FAT
            fmt_str(self.tipo_doc_paf),           # 14. TP DOC
            fmt_str(self.trat_paf),               # 15. TRAT PAF
            fmt_str(self.lanc_sistema),           # 16. LANC SISTEMA
            fmt_str(self.observacoes),            # 17. OBSERVAÇÕES
            fmt_str(self.obs_interna),            # 18. OBS INTERNA
        ]


@dataclass
class DanfeData(DocumentData):
    """Modelo para DANFE / NF-e (produto) - modelo 55.

    Mantém compatibilidade com exportação PAF (18 colunas) usando os mesmos
    campos principais: fornecedor, NF, emissão, valor, vencimento.
    """

    cnpj_emitente: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    numero_nota: Optional[str] = None
    serie_nf: Optional[str] = None
    data_emissao: Optional[str] = None
    valor_total: float = 0.0
    vencimento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    numero_pedido: Optional[str] = None
    numero_fatura: Optional[str] = None
    tipo_doc_paf: str = "NF"
    dt_classificacao: Optional[str] = None
    trat_paf: Optional[str] = None
    lanc_sistema: str = "PENDENTE"

    chave_acesso: Optional[str] = None

    @property
    def doc_type(self) -> str:
        return 'DANFE'

    def to_dict(self) -> dict:
        return {
            'tipo_documento': self.doc_type,
            'arquivo_origem': self.arquivo_origem,
            'data_processamento': self.data_processamento,
            'setor': self.setor,
            'empresa': self.empresa,
            'observacoes': self.observacoes,
            'obs_interna': self.obs_interna,
            'cnpj_emitente': self.cnpj_emitente,
            'fornecedor_nome': self.fornecedor_nome,
            'numero_nota': self.numero_nota,
            'serie_nf': self.serie_nf,
            'data_emissao': self.data_emissao,
            'valor_total': self.valor_total,
            'vencimento': self.vencimento,
            'forma_pagamento': self.forma_pagamento,
            'numero_pedido': self.numero_pedido,
            'numero_fatura': self.numero_fatura,
            'tipo_doc_paf': self.tipo_doc_paf,
            'dt_classificacao': self.dt_classificacao,
            'trat_paf': self.trat_paf,
            'lanc_sistema': self.lanc_sistema,
            'chave_acesso': self.chave_acesso,
            'texto_bruto': self.texto_bruto[:200] if self.texto_bruto else None,
            'status_conciliacao': self.status_conciliacao,
            'valor_compra': self.valor_compra,
        }

    def to_sheets_row(self) -> list:
        def fmt_date(iso_date: Optional[str]) -> str:
            if not iso_date:
                return ""
            try:
                dt = datetime.strptime(iso_date, '%Y-%m-%d')
                return dt.strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                return ""

        def fmt_num(value: Optional[float]) -> float:
            return value if value is not None else 0.0

        def fmt_str(value: Optional[str]) -> str:
            return value if value is not None else ""

        try:
            from config.settings import PAF_EXPORT_NF_EMPTY
        except Exception:
            PAF_EXPORT_NF_EMPTY = False

        nf_value = "" if PAF_EXPORT_NF_EMPTY else fmt_str(self.numero_nota)
        fat_value = "" if PAF_EXPORT_NF_EMPTY else fmt_str(self.numero_fatura)

        return [
            fmt_date(self.data_processamento),  # 1. DATA
            fmt_str(self.setor),                 # 2. SETOR
            fmt_str(self.empresa),               # 3. EMPRESA
            fmt_str(self.fornecedor_nome),       # 4. FORNECEDOR
            nf_value,                            # 5. NF
            fmt_date(self.data_emissao),         # 6. EMISSÃO
            fmt_num(self.valor_total),           # 7. VALOR
            fmt_str(self.numero_pedido),         # 8. Nº PEDIDO
            fmt_date(self.vencimento),           # 9. VENCIMENTO
            fmt_str(self.forma_pagamento),       # 10. FORMA PAGTO
            "",                                  # 11. (vazio)
            fmt_date(self.dt_classificacao),     # 12. DT CLASS
            fat_value,                           # 13. Nº FAT
            "NF",                                # 14. TP DOC
            fmt_str(self.trat_paf),              # 15. TRAT PAF
            fmt_str(self.lanc_sistema),          # 16. LANC SISTEMA
            fmt_str(self.observacoes),           # 17. OBSERVAÇÕES
            fmt_str(self.obs_interna),           # 18. OBS INTERNA
        ]


@dataclass
class OtherDocumentData(DocumentData):
    """Modelo genérico para documentos que não são NFSe nem Boleto nem DANFE."""

    fornecedor_nome: Optional[str] = None
    cnpj_fornecedor: Optional[str] = None
    data_emissao: Optional[str] = None
    vencimento: Optional[str] = None
    valor_total: float = 0.0
    numero_documento: Optional[str] = None

    tipo_doc_paf: str = "OT"
    dt_classificacao: Optional[str] = None
    trat_paf: Optional[str] = None
    lanc_sistema: str = "PENDENTE"

    subtipo: Optional[str] = None

    @property
    def doc_type(self) -> str:
        return 'OUTRO'

    def to_dict(self) -> dict:
        return {
            'tipo_documento': self.doc_type,
            'arquivo_origem': self.arquivo_origem,
            'data_processamento': self.data_processamento,
            'setor': self.setor,
            'empresa': self.empresa,
            'observacoes': self.observacoes,
            'obs_interna': self.obs_interna,
            'fornecedor_nome': self.fornecedor_nome,
            'cnpj_fornecedor': self.cnpj_fornecedor,
            'data_emissao': self.data_emissao,
            'vencimento': self.vencimento,
            'valor_total': self.valor_total,
            'numero_documento': self.numero_documento,
            'numero_pedido': self.numero_documento,
            'tipo_doc_paf': self.tipo_doc_paf,
            'dt_classificacao': self.dt_classificacao,
            'trat_paf': self.trat_paf,
            'lanc_sistema': self.lanc_sistema,
            'subtipo': self.subtipo,
            'texto_bruto': self.texto_bruto[:200] if self.texto_bruto else None,
            'status_conciliacao': self.status_conciliacao,
            'valor_compra': self.valor_compra,
        }

    def to_sheets_row(self) -> list:
        def fmt_date(iso_date: Optional[str]) -> str:
            if not iso_date:
                return ""
            try:
                dt = datetime.strptime(iso_date, '%Y-%m-%d')
                return dt.strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                return ""

        def fmt_num(value: Optional[float]) -> float:
            return value if value is not None else 0.0

        def fmt_str(value: Optional[str]) -> str:
            return value if value is not None else ""

        return [
            fmt_date(self.data_processamento),  # 1. DATA
            fmt_str(self.setor),                 # 2. SETOR
            fmt_str(self.empresa),               # 3. EMPRESA
            fmt_str(self.fornecedor_nome),       # 4. FORNECEDOR
            fmt_str(self.numero_documento),                                  # 5. NF (não aplicável)
            fmt_date(self.data_emissao),         # 6. EMISSÃO
            fmt_num(self.valor_total),           # 7. VALOR
            "",                                  # 8. Nº PEDIDO
            fmt_date(self.vencimento),           # 9. VENCIMENTO
            "",                                  # 10. FORMA PAGTO
            "",                                  # 11. (vazio)
            fmt_date(self.dt_classificacao),     # 12. DT CLASS
            "",                                  # 13. Nº FAT
            fmt_str(self.tipo_doc_paf),          # 14. TP DOC
            fmt_str(self.trat_paf),              # 15. TRAT PAF
            fmt_str(self.lanc_sistema),          # 16. LANC SISTEMA
            fmt_str(self.observacoes),           # 17. OBSERVAÇÕES
            fmt_str(self.obs_interna),           # 18. OBS INTERNA
        ]

@dataclass
class EmailAvisoData(DocumentData):
    """
    Modelo para e-mails SEM anexo que contêm link de NF-e e/ou código de verificação.

    Usado para registrar e-mails que precisam de ação manual (acessar link,
    baixar documento) mas que não vieram com PDF/XML anexado.

    A coluna 'observacoes' contém o aviso formatado com link + código.

    Attributes:
        arquivo_origem (str): Identificador do e-mail (email_id ou subject).
        link_nfe (Optional[str]): Link para acesso/download da NF-e.
        codigo_verificacao (Optional[str]): Código de autenticação/verificação.
        numero_nota (Optional[str]): Número da NF extraído do link ou assunto.
        fornecedor_nome (Optional[str]): Nome do remetente (fallback).
        email_subject (Optional[str]): Assunto completo do e-mail.
        email_body_preview (Optional[str]): Preview do corpo (primeiros 500 chars).
        dominio_portal (Optional[str]): Domínio do portal de NF-e.

        tipo_doc_paf (str): Tipo para PAF (default: "AV" - Aviso).
    """
    link_nfe: Optional[str] = None
    codigo_verificacao: Optional[str] = None
    numero_nota: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    email_subject_full: Optional[str] = None
    email_body_preview: Optional[str] = None
    dominio_portal: Optional[str] = None
    vencimento: Optional[str] = None

    tipo_doc_paf: str = "AV"  # Aviso
    dt_classificacao: Optional[str] = None
    trat_paf: Optional[str] = None
    lanc_sistema: str = "PENDENTE"

    @property
    def doc_type(self) -> str:
        return 'AVISO'

    def to_dict(self) -> dict:
        return {
            'tipo_documento': self.doc_type,
            'arquivo_origem': self.arquivo_origem,
            'data_processamento': self.data_processamento,
            'setor': self.setor,
            'empresa': self.empresa,
            'link_nfe': self.link_nfe,
            'codigo_verificacao': self.codigo_verificacao,
            'numero_nota': self.numero_nota,
            'fornecedor_nome': self.fornecedor_nome,
            'email_subject': self.email_subject_full,
            'email_body_preview': self.email_body_preview,
            'dominio_portal': self.dominio_portal,
            'vencimento': self.vencimento,
            'tipo_doc_paf': self.tipo_doc_paf,
            'dt_classificacao': self.dt_classificacao,
            'trat_paf': self.trat_paf,
            'lanc_sistema': self.lanc_sistema,
            'observacoes': self.observacoes,
            'obs_interna': self.obs_interna,
            'status_conciliacao': self.status_conciliacao,
            'valor_compra': self.valor_compra,
        }

    def to_sheets_row(self) -> list:
        """
        Converte para linha PAF.

        Coluna OBSERVAÇÕES contém o aviso formatado:
        "[SEM ANEXO] Link: ... | Código: ... | NF: ..."
        """
        def fmt_date(iso_date: Optional[str]) -> str:
            if not iso_date:
                return ""
            try:
                dt = datetime.strptime(iso_date, '%Y-%m-%d')
                return dt.strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                return ""

        def fmt_str(value: Optional[str]) -> str:
            return value if value is not None else ""

        # Monta observação com link e código
        obs_parts = ["[SEM ANEXO]"]
        if self.link_nfe:
            link_display = self.link_nfe if len(self.link_nfe) <= 80 else self.link_nfe[:77] + "..."
            obs_parts.append(f"Link: {link_display}")
        if self.codigo_verificacao:
            obs_parts.append(f"Código: {self.codigo_verificacao}")
        if self.numero_nota:
            obs_parts.append(f"NF: {self.numero_nota}")

        observacao_final = self.observacoes or " | ".join(obs_parts)

        return [
            fmt_date(self.data_processamento),  # 1. DATA
            fmt_str(self.setor),                 # 2. SETOR
            fmt_str(self.empresa),               # 3. EMPRESA
            fmt_str(self.fornecedor_nome),       # 4. FORNECEDOR
            fmt_str(self.numero_nota),           # 5. NF
            "",                                  # 6. EMISSÃO
            0.0,                                 # 7. VALOR
            "",                                  # 8. Nº PEDIDO
            fmt_date(self.vencimento),           # 9. VENCIMENTO
            "",                                  # 10. FORMA PAGTO
            "",                                  # 11. (vazio)
            fmt_date(self.dt_classificacao),     # 12. DT CLASS
            "",                                  # 13. Nº FAT
            fmt_str(self.tipo_doc_paf),          # 14. TP DOC
            fmt_str(self.trat_paf),              # 15. TRAT PAF
            fmt_str(self.lanc_sistema),          # 16. LANC SISTEMA
            fmt_str(observacao_final),           # 17. OBSERVAÇÕES
            fmt_str(self.obs_interna),           # 18. OBS INTERNA
        ]

    @classmethod
    def from_metadata(cls, metadata: 'EmailMetadata', email_id: str) -> 'EmailAvisoData':
        """
        Factory method para criar EmailAvisoData a partir de EmailMetadata.

        Args:
            metadata: Metadados do e-mail
            email_id: Identificador único do e-mail

        Returns:
            EmailAvisoData preenchido
        """
        import re
        from datetime import date

        link = metadata.extract_link_nfe_from_context()
        codigo = metadata.extract_codigo_verificacao_from_link(link) or metadata.extract_codigo_verificacao_from_body()
        numero_nf = metadata.extract_numero_nf_from_link(link) or metadata.extract_numero_nota_from_context()

        # Extrai domínio do link
        dominio = None
        if link:
            match = re.search(r'https?://([^/]+)', link)
            if match:
                dominio = match.group(1).lower()

        # Extrai fornecedor do assunto ou remetente (filtrando empresas próprias)
        fornecedor = metadata.extract_fornecedor_from_context()

        return cls(
            arquivo_origem=email_id,
            data_processamento=date.today().isoformat(),
            link_nfe=link,
            codigo_verificacao=codigo,
            numero_nota=numero_nf,
            fornecedor_nome=fornecedor,
            email_subject_full=metadata.email_subject,
            email_body_preview=(metadata.email_body_text or "")[:500],
            dominio_portal=dominio,
            source_email_subject=metadata.email_subject,
            source_email_sender=metadata.email_sender_name or metadata.email_sender_address,
        )


@dataclass
class BoletoData(DocumentData):
    """
    Modelo de dados para Boletos Bancários.

    Alinhado com as 18 colunas da planilha "PAF NOVO - SETORES CSC".
    Conformidade: Política Interna 5.9 e POP 4.10 (Master Internet).

    Attributes:
        arquivo_origem (str): Nome do arquivo PDF processado.
        texto_bruto (str): Snippet do texto extraído.

        # Identificação e Fornecedor
        cnpj_beneficiario (Optional[str]): CNPJ do beneficiário (quem recebe).
        fornecedor_nome (Optional[str]): Razão Social do beneficiário (coluna FORNECEDOR).

        # Valores
        valor_documento (float): Valor nominal do boleto.

        # Dados de Vencimento e Pagamento
        vencimento (Optional[str]): Data de vencimento no formato ISO (YYYY-MM-DD).
        forma_pagamento (str): Forma de pagamento (default: "BOLETO").

        # Identificação do Documento
        numero_documento (Optional[str]): Número do documento/fatura (coluna NF).
        linha_digitavel (Optional[str]): Linha digitável do boleto.
        nosso_numero (Optional[str]): Nosso número (identificação do banco).
        referencia_nfse (Optional[str]): Número da NFSe vinculada (se encontrado).

        # Dados Bancários
        banco_nome (Optional[str]): Nome do banco emissor (identificado via código).
        agencia (Optional[str]): Agência no formato normalizado (ex: "1234-5").
        conta_corrente (Optional[str]): Conta corrente no formato normalizado (ex: "123456-7").

        # Classificação PAF
        numero_pedido (Optional[str]): Número do pedido/PC (coluna Nº PEDIDO).
        tipo_doc_paf (str): Tipo de documento para PAF (default: "FT" - Fatura).
        dt_classificacao (Optional[str]): Data de classificação no formato ISO.
        trat_paf (Optional[str]): Responsável pela classificação (coluna TRAT PAF).
        lanc_sistema (str): Status de lançamento no ERP (default: "PENDENTE").
    """
    cnpj_beneficiario: Optional[str] = None
    fornecedor_nome: Optional[str] = None
    valor_documento: float = 0.0
    vencimento: Optional[str] = None
    data_emissao: Optional[str] = None
    # Compatibilidade com testes/scripts antigos
    data_vencimento: Optional[str] = None
    forma_pagamento: Optional[str] = None
    numero_documento: Optional[str] = None
    linha_digitavel: Optional[str] = None
    nosso_numero: Optional[str] = None
    referencia_nfse: Optional[str] = None

    # Dados bancários
    banco_nome: Optional[str] = None
    agencia: Optional[str] = None
    conta_corrente: Optional[str] = None

    # Campos PAF
    numero_pedido: Optional[str] = None
    tipo_doc_paf: str = "FT"
    dt_classificacao: Optional[str] = None
    trat_paf: Optional[str] = None
    lanc_sistema: str = "PENDENTE"

    def __post_init__(self) -> None:
        # Mantém compatibilidade: alguns chamadores usam data_vencimento.
        if not self.vencimento and self.data_vencimento:
            self.vencimento = self.data_vencimento

    @property
    def doc_type(self) -> str:
        """Retorna o tipo do documento."""
        return 'BOLETO'

    def to_dict(self) -> dict:
        """
        Converte BoletoData para dicionário mantendo semântica None.

        Mantém valores None para campos não extraídos (importante para debug).
        Use to_sheets_row() para exportação com conversões apropriadas.
        """
        return {
            'tipo_documento': self.doc_type,
            'arquivo_origem': self.arquivo_origem,
            'data_processamento': self.data_processamento,
            'setor': self.setor,
            'empresa': self.empresa,
            'cnpj_beneficiario': self.cnpj_beneficiario,
            'fornecedor_nome': self.fornecedor_nome,
            'valor_documento': self.valor_documento,
            'vencimento': self.vencimento,
            'data_emissao': self.data_emissao,
            'forma_pagamento': self.forma_pagamento,
            'numero_documento': self.numero_documento,
            'linha_digitavel': self.linha_digitavel,
            'nosso_numero': self.nosso_numero,
            'referencia_nfse': self.referencia_nfse,
            'banco_nome': self.banco_nome,
            'agencia': self.agencia,
            'conta_corrente': self.conta_corrente,
            'numero_pedido': self.numero_pedido,
            'tipo_doc_paf': self.tipo_doc_paf,
            'dt_classificacao': self.dt_classificacao,
            'trat_paf': self.trat_paf,
            'lanc_sistema': self.lanc_sistema,
            'observacoes': self.observacoes,
            'obs_interna': self.obs_interna,
            'texto_bruto': self.texto_bruto[:200] if self.texto_bruto else None,
            'status_conciliacao': self.status_conciliacao,
            'valor_compra': self.valor_compra,
        }

    def to_sheets_row(self) -> list:
        """
        Converte BoletoData para lista de 18 valores na ordem da planilha PAF.

        Mapeia campos de boleto para estrutura PAF:
        - numero_documento → coluna NF
        - valor_documento → coluna VALOR
        - forma_pagamento = None (default)  #ToDo tem que ser implementado de acordo com uma lista de contrato"
        - tipo_doc_paf = "FT" (Fatura/Título Financeiro)

        Ordem das colunas PAF:
        1. DATA (processamento) - 2. SETOR - 3. EMPRESA - 4. FORNECEDOR
        5. NF - 6. EMISSÃO - 7. VALOR - 8. Nº PEDIDO
        9. VENCIMENTO - 10. FORMA PAGTO - 11. (vazio/índice)
        12. DT CLASS - 13. Nº FAT - 14. TP DOC - 15. TRAT PAF
        16. LANC SISTEMA - 17. OBSERVAÇÕES - 18. OBS INTERNA

        Returns:
            list: Lista com 18 elementos para append no Google Sheets
        """
        def fmt_date(iso_date: Optional[str]) -> str:
            """Converte data ISO para formato brasileiro DD/MM/YYYY."""
            if not iso_date:
                return ""
            try:
                dt = datetime.strptime(iso_date, '%Y-%m-%d')
                return dt.strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                return ""

        def fmt_num(value: Optional[float]) -> float:
            """Converte None para 0.0 em campos numéricos."""
            return value if value is not None else 0.0

        def fmt_str(value: Optional[str]) -> str:
            """Converte None para string vazia."""
            return value if value is not None else ""

        # MVP: coluna NF será preenchida via ingestão (e-mail), então exportamos vazio.
        try:
            from config.settings import PAF_EXPORT_NF_EMPTY
        except Exception:
            PAF_EXPORT_NF_EMPTY = False

        # Prioriza referencia_nfse (herdado da DANFE/NFSe via correlação)
        # Fallback para numero_documento se não houver correlação
        nf_value = "" if PAF_EXPORT_NF_EMPTY else fmt_str(self.referencia_nfse or self.numero_documento)
        fat_value = "" if PAF_EXPORT_NF_EMPTY else fmt_str(self.referencia_nfse or self.numero_documento)

        return [
            fmt_date(self.data_processamento),  # 1. DATA
            fmt_str(self.setor),                 # 2. SETOR
            fmt_str(self.empresa),               # 3. EMPRESA
            fmt_str(self.fornecedor_nome),       # 4. FORNECEDOR
            nf_value,                             # 5. NF (MVP: vazio)
            fmt_date(self.data_emissao),          # 6. EMISSÃO
            fmt_num(self.valor_documento),       # 7. VALOR
            fmt_str(self.numero_pedido),         # 8. Nº PEDIDO
            fmt_date(self.vencimento),           # 9. VENCIMENTO
            fmt_str(self.forma_pagamento),       # 10. FORMA PAGTO
            "",                                  # 11. (coluna vazia/índice)
            fmt_date(self.dt_classificacao),     # 12. DT CLASS
            fat_value,                            # 13. Nº FAT (MVP: vazio)
            fmt_str(self.tipo_doc_paf),          # 14. TP DOC
            fmt_str(self.trat_paf),              # 15. TRAT PAF
            fmt_str(self.lanc_sistema),          # 16. LANC SISTEMA
            fmt_str(self.observacoes),           # 17. OBSERVAÇÕES
            fmt_str(self.obs_interna),           # 18. OBS INTERNA
        ]
