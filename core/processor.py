import os
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Union

import extractors.boleto
import extractors.danfe
import extractors.net_center
import extractors.nfse_generic
import extractors.outros
import extractors.sicoob
from config.settings import TRAT_PAF_RESPONSAVEL
from core.empresa_matcher import (
    find_empresa_no_texto,
    format_cnpj,
    infer_fornecedor_from_text,
    is_cnpj_nosso,
    is_nome_nosso,
    pick_first_non_our_cnpj,
)
from core.extractors import EXTRACTOR_REGISTRY
from core.interfaces import TextExtractionStrategy
from core.models import (
    BoletoData,
    DanfeData,
    DocumentData,
    InvoiceData,
    OtherDocumentData,
)
from core.nf_candidate import extract_nf_candidate
from strategies.fallback import SmartExtractionStrategy


class BaseInvoiceProcessor(ABC):
    """
    Classe orquestradora principal do processo de extração.

    Responsável por coordenar o fluxo completo:
    1.  **Leitura**: Converte PDF em texto (via `SmartExtractionStrategy`).
    2.  **Classificação**: Identifica se é NFSe ou Boleto.
    3.  **Seleção**: Escolhe o extrator adequado para o texto.
    4.  **Extração**: Executa a mineração de dados.
    5.  **Normalização**: Retorna objeto `InvoiceData` ou `BoletoData`.

    Args:
        reader: Estratégia de extração de texto. Se None, usa SmartExtractionStrategy.
                Permite injeção de dependência para testes (DIP).
    """
    def __init__(self, reader: Optional[TextExtractionStrategy] = None):
        self.reader = reader if reader is not None else SmartExtractionStrategy()

    def _get_extractor(self, text: str):
        """Factory Method: Escolhe o extrator certo para o texto."""
        for extractor_cls in EXTRACTOR_REGISTRY:
            if extractor_cls.can_handle(text):
                # útil para debug/auditoria (não altera a lógica)
                self.last_extractor = extractor_cls.__name__
                return extractor_cls()
        raise ValueError("Nenhum extrator compatível encontrado para este documento.")

    def process(self, file_path: str) -> DocumentData:
        """
        Executa o pipeline de processamento para um único arquivo.

        Args:
            file_path (str): Caminho absoluto ou relativo do arquivo PDF.

        Returns:
            Union[InvoiceData, BoletoData]: Objeto contendo os dados extraídos.
        """
        # 1. Leitura
        raw_text = self.reader.extract(file_path)

        # Sugestão de NF (debug/auditoria): não altera o MVP
        nf_sugestao = extract_nf_candidate(raw_text or "")

        if not raw_text or "Falha" in raw_text:
            # Retorna objeto vazio de NFSe por padrão
            return InvoiceData(
                arquivo_origem=os.path.basename(file_path),
                texto_bruto="Falha na leitura"
            )

        # 2. Seleção do Extrator
        try:
            extractor = self._get_extractor(raw_text)
            extracted_data = extractor.extract(raw_text)

            # Dados comuns PAF (aplicados a todos os documentos)
            now_iso = datetime.now().strftime('%Y-%m-%d')
            common_data = {
                'data_processamento': now_iso,
                'dt_classificacao': now_iso,
                'trat_paf': TRAT_PAF_RESPONSAVEL,
                'lanc_sistema': 'PENDENTE',
            }

            # Campos opcionais (não obrigatórios) vindos do extrator
            for k in ('setor', 'empresa', 'observacoes'):
                v = extracted_data.get(k)
                if v:
                    common_data[k] = v

            # --- Regra de negócio (EMPRESA nossa) ---
            # Se existir um CNPJ do nosso cadastro no documento, ele define a coluna EMPRESA.
            # Qualquer outro CNPJ no documento tende a ser fornecedor/terceiro.
            empresa_match = find_empresa_no_texto(raw_text or "")
            if empresa_match:
                # Padroniza para um identificador curto (ex: CSC, MASTER, OP11, RBC)
                common_data['empresa'] = empresa_match.codigo

                # Se o extrator colocou uma empresa nossa como fornecedor, limpa.
                fn = extracted_data.get('fornecedor_nome')
                if fn and is_nome_nosso(fn):
                    # Só limpamos o fornecedor se houver evidência de que ele é realmente nosso.
                    # Caso contrário, evitamos falso positivo (ex: fornecedor contém token curto como "NET").
                    if extracted_data.get('tipo_documento') == 'BOLETO':
                        cnpj_ben = extracted_data.get('cnpj_beneficiario')
                        if not cnpj_ben or is_cnpj_nosso(cnpj_ben):
                            extracted_data['fornecedor_nome'] = None
                    else:
                        cnpj_prest = extracted_data.get('cnpj_prestador')
                        if not cnpj_prest or is_cnpj_nosso(cnpj_prest):
                            extracted_data['fornecedor_nome'] = None

                # Se o extrator capturou CNPJ nosso como "prestador/beneficiário" por engano,
                # tenta trocar para o primeiro CNPJ não-nosso presente no texto.
                if extracted_data.get('tipo_documento') == 'BOLETO':
                    cnpj_ben = extracted_data.get('cnpj_beneficiario')
                    if cnpj_ben and is_cnpj_nosso(cnpj_ben):
                        other = pick_first_non_our_cnpj(raw_text or "")
                        if other:
                            extracted_data['cnpj_beneficiario'] = format_cnpj(other)
                else:
                    cnpj_prest = extracted_data.get('cnpj_prestador')
                    if cnpj_prest and is_cnpj_nosso(cnpj_prest):
                        other = pick_first_non_our_cnpj(raw_text or "")
                        if other:
                            extracted_data['cnpj_prestador'] = format_cnpj(other)

            # Fallback conservador: se fornecedor ainda está vazio e temos empresa nossa,
            # tenta inferir um fornecedor por linha com CNPJ (que não seja do cadastro).
            if (not extracted_data.get('fornecedor_nome')) and empresa_match:
                inferred = infer_fornecedor_from_text(raw_text or "", empresa_match.cnpj_digits)
                if inferred:
                    extracted_data['fornecedor_nome'] = inferred

            if nf_sugestao.value:
                obs_prev = extracted_data.get('obs_interna')
                obs_nf = f"NF_CANDIDATE={nf_sugestao.value} (conf={nf_sugestao.confidence:.2f}, {nf_sugestao.reason})"
                common_data['obs_interna'] = f"{obs_prev} | {obs_nf}" if obs_prev else obs_nf

            # 3. Identifica o tipo e cria o modelo apropriado
            if extracted_data.get('tipo_documento') == 'BOLETO':
                return BoletoData(
                    arquivo_origem=os.path.basename(file_path),
                    texto_bruto=' '.join(raw_text.split())[:500],
                    # Campos PAF comuns
                    **common_data,
                    # Campos básicos do boleto
                    cnpj_beneficiario=extracted_data.get('cnpj_beneficiario'),
                    valor_documento=extracted_data.get('valor_documento', 0.0),
                    vencimento=extracted_data.get('vencimento'),
                    data_emissao=extracted_data.get('data_emissao'),
                    numero_documento=extracted_data.get('numero_documento'),
                    linha_digitavel=extracted_data.get('linha_digitavel'),
                    nosso_numero=extracted_data.get('nosso_numero'),
                    referencia_nfse=extracted_data.get('referencia_nfse'),
                    # Campos PAF (novos)
                    fornecedor_nome=extracted_data.get('fornecedor_nome'),
                    banco_nome=extracted_data.get('banco_nome'),
                    agencia=extracted_data.get('agencia'),
                    conta_corrente=extracted_data.get('conta_corrente'),
                    numero_pedido=extracted_data.get('numero_pedido'),
                )
            elif extracted_data.get('tipo_documento') == 'DANFE':
                return DanfeData(
                    arquivo_origem=os.path.basename(file_path),
                    texto_bruto=' '.join(raw_text.split())[:500],
                    # Campos PAF comuns
                    **common_data,
                    # Campos do DANFE
                    cnpj_emitente=extracted_data.get('cnpj_emitente') or extracted_data.get('cnpj_prestador'),
                    fornecedor_nome=extracted_data.get('fornecedor_nome'),
                    numero_nota=extracted_data.get('numero_nota'),
                    serie_nf=extracted_data.get('serie_nf'),
                    data_emissao=extracted_data.get('data_emissao'),
                    valor_total=extracted_data.get('valor_total', 0.0),
                    vencimento=extracted_data.get('vencimento'),
                    forma_pagamento=extracted_data.get('forma_pagamento'),
                    numero_pedido=extracted_data.get('numero_pedido'),
                    numero_fatura=extracted_data.get('numero_fatura'),
                    chave_acesso=extracted_data.get('chave_acesso'),
                )
            elif extracted_data.get('tipo_documento') == 'OUTRO':
                return OtherDocumentData(
                    arquivo_origem=os.path.basename(file_path),
                    texto_bruto=' '.join(raw_text.split())[:500],
                    # Campos PAF comuns
                    **common_data,
                    fornecedor_nome=extracted_data.get('fornecedor_nome'),
                    cnpj_fornecedor=extracted_data.get('cnpj_fornecedor'),
                    data_emissao=extracted_data.get('data_emissao'),
                    vencimento=extracted_data.get('vencimento'),
                    valor_total=extracted_data.get('valor_total', 0.0),
                    numero_documento=extracted_data.get('numero_documento'),
                    subtipo=extracted_data.get('subtipo'),
                )
            else:
                # NFSe
                return InvoiceData(
                    arquivo_origem=os.path.basename(file_path),
                    texto_bruto=' '.join(raw_text.split())[:500],
                    # Campos PAF comuns
                    **common_data,
                    # Campos básicos da NFSe
                    cnpj_prestador=extracted_data.get('cnpj_prestador'),
                    numero_nota=extracted_data.get('numero_nota'),
                    valor_total=extracted_data.get('valor_total', 0.0),
                    data_emissao=extracted_data.get('data_emissao'),
                    # Campos PAF (novos)
                    fornecedor_nome=extracted_data.get('fornecedor_nome'),
                    vencimento=extracted_data.get('vencimento'),
                    numero_pedido=extracted_data.get('numero_pedido'),
                    forma_pagamento=extracted_data.get('forma_pagamento'),
                    # Impostos individuais
                    valor_ir=extracted_data.get('valor_ir'),
                    valor_inss=extracted_data.get('valor_inss'),
                    valor_csll=extracted_data.get('valor_csll'),
                    valor_iss=extracted_data.get('valor_iss'),
                    valor_icms=extracted_data.get('valor_icms'),
                    base_calculo_icms=extracted_data.get('base_calculo_icms'),
                )

        except ValueError as e:
            print(f"Erro ao processar {file_path}: {e}")
            return InvoiceData(
                arquivo_origem=os.path.basename(file_path),
                texto_bruto=' '.join(raw_text.split())[:500]  # Remove whitespace, then take 500 chars
            )
