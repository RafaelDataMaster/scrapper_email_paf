"""
Extrator de dados de arquivos XML de NF-e e NFS-e.

Este módulo processa arquivos XML de notas fiscais eletrônicas,
extraindo dados estruturados de forma muito mais confiável que PDFs.

Suporta:
- NF-e (Nota Fiscal Eletrônica de Produto) - Modelo 55
- NFS-e (Nota Fiscal de Serviço Eletrônica) - Padrão ABRASF e variantes

Estrutura XML NF-e:
    <nfeProc>
        <NFe>
            <infNFe>
                <ide>...</ide>      # Identificação (número, série, data)
                <emit>...</emit>    # Emitente (CNPJ, razão social)
                <dest>...</dest>    # Destinatário
                <total>...</total>  # Valores totais
                <cobr>...</cobr>    # Cobrança (duplicatas, vencimento)
            </infNFe>
        </NFe>
    </nfeProc>

Estrutura XML NFS-e (ABRASF):
    <CompNfse>
        <Nfse>
            <InfNfse>
                <Numero>...</Numero>
                <PrestadorServico>...</PrestadorServico>
                <TomadorServico>...</TomadorServico>
                <Servico>...</Servico>
            </InfNfse>
        </Nfse>
    </CompNfse>
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.models import DanfeData, DocumentData, InvoiceData

# Namespaces comuns em XMLs de NF-e e NFS-e
NAMESPACES = {
    'nfe': 'http://www.portalfiscal.inf.br/nfe',
    'nfse': 'http://www.abrasf.org.br/nfse.xsd',
    # Variantes de namespace NFS-e por município
    'nfse_sp': 'http://www.prefeitura.sp.gov.br/nfe',
    'nfse_rj': 'http://notacarioca.rio.gov.br/WSNacional/XSD/1/nfse_municipal_v01.xsd',
}


@dataclass
class XmlExtractionResult:
    """Resultado da extração de XML."""
    success: bool
    document: Optional[DocumentData] = None
    doc_type: str = ""  # 'NFE' ou 'NFSE'
    error: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


class XmlExtractor:
    """
    Extrator de dados de arquivos XML de NF-e e NFS-e.

    Detecta automaticamente o tipo de documento e extrai os campos
    relevantes para o modelo de dados do sistema.
    """

    def __init__(self):
        self.namespaces = NAMESPACES.copy()

    def extract(self, xml_path: str) -> XmlExtractionResult:
        """
        Extrai dados de um arquivo XML.

        Args:
            xml_path: Caminho do arquivo XML

        Returns:
            XmlExtractionResult com o documento extraído ou erro
        """
        path = Path(xml_path)

        if not path.exists():
            return XmlExtractionResult(
                success=False,
                error=f"Arquivo não encontrado: {xml_path}"
            )

        if path.suffix.lower() != '.xml':
            return XmlExtractionResult(
                success=False,
                error=f"Arquivo não é XML: {xml_path}"
            )

        try:
            # Lê o conteúdo do arquivo
            with open(path, 'r', encoding='utf-8') as f:
                xml_content = f.read()
        except UnicodeDecodeError:
            # Tenta com encoding alternativo
            try:
                with open(path, 'r', encoding='latin-1') as f:
                    xml_content = f.read()
            except Exception as e:
                return XmlExtractionResult(
                    success=False,
                    error=f"Erro ao ler arquivo: {e}"
                )
        except Exception as e:
            return XmlExtractionResult(
                success=False,
                error=f"Erro ao ler arquivo: {e}"
            )

        # Detecta o tipo de documento e extrai
        doc_type = self._detect_document_type(xml_content)

        if doc_type == 'NFE':
            return self._extract_nfe(xml_content, path.name)
        elif doc_type == 'NFSE':
            return self._extract_nfse(xml_content, path.name)
        elif doc_type == 'NFSE_SIGISS':
            return self._extract_nfse_sigiss(xml_content, path.name)
        elif doc_type == 'NFSE_SPED':
            return self._extract_nfse_sped(xml_content, path.name)
        else:
            return XmlExtractionResult(
                success=False,
                error="Tipo de documento XML não reconhecido (esperado NF-e ou NFS-e)"
            )

    def _detect_document_type(self, xml_content: str) -> str:
        """
        Detecta se o XML é NF-e ou NFS-e.

        Args:
            xml_content: Conteúdo do XML

        Returns:
            'NFE', 'NFSE', 'NFSE_SIGISS', 'NFSE_SPED' ou '' se não reconhecido
        """
        # Padrões para NFS-e SPED/SEFIN Nacional (novo padrão federal)
        # Namespace: http://www.sped.fazenda.gov.br/nfse
        # Tags: <NFSe>, <infNFSe>, <emit>, <DPS>, <infDPS>, <prest>, <toma>
        # IMPORTANTE: Verificar ANTES de NF-e porque usa <NFSe> (não <NFe>)
        nfse_sped_patterns = [
            r'sped\.fazenda\.gov\.br/nfse',
            r'<infNFSe\s',
            r'<nNFSe>',
            r'<nDFSe>',
            r'<DPS\s',
            r'<infDPS\s',
            r'<toma>',
            r'<prest>',
        ]

        # Verifica NFS-e SPED Nacional primeiro (padrão mais específico)
        sped_score = sum(1 for p in nfse_sped_patterns if re.search(p, xml_content, re.IGNORECASE | re.DOTALL))
        if sped_score >= 2:
            return 'NFSE_SPED'

        # Padrões para NF-e (modelo 55) - nota fiscal de produtos
        # IMPORTANTE: <NFe> com namespace do portal fiscal, ou com <infNFe>, ou com <mod>55</mod>
        nfe_patterns = [
            r'<nfeProc',
            r'<infNFe',
            r'portalfiscal\.inf\.br/nfe',
            r'<mod>55</mod>',
        ]

        # Padrões para NFS-e ABRASF (padrão nacional antigo)
        nfse_patterns = [
            r'<CompNfse',
            r'<Nfse>',
            r'<InfNfse',
            r'<ListaNfse',
            r'<ConsultarNfseResposta',
            r'abrasf\.org\.br',
            r'<Rps>',
            r'<InfRps',
            r'nfse\.xsd',
            r'<NumeroNfse',
            r'<PrestadorServico',
            r'<TomadorServico',
        ]

        # Padrões para NFS-e SigISS (formato municipal - Marília, etc.)
        # Formato: <NFe><ChaveNFe><NumeroNFe>...<ValorServicos>
        # NOTA: Este formato usa <NFe> como tag raiz mas NÃO é NF-e modelo 55!
        sigiss_patterns = [
            r'<NumeroNFe>',
            r'<InscricaoPrestador>',
            r'<CPFCNPJPrestador>',
            r'<TributacaoNFe>',
            r'<StatusNFe>',
            r'<ChaveNFe>',
            r'<RazaoSocialPrestador>',
        ]

        # IMPORTANTE: Verificar SigISS ANTES de NFe genérico
        # porque SigISS usa <NFe> como tag mas não é nota fiscal modelo 55
        sigiss_score = sum(1 for p in sigiss_patterns if re.search(p, xml_content, re.IGNORECASE | re.DOTALL))
        if sigiss_score >= 3:
            return 'NFSE_SIGISS'

        # Verifica NF-e (modelo 55)
        for pattern in nfe_patterns:
            if re.search(pattern, xml_content, re.IGNORECASE):
                return 'NFE'

        # Verifica NFS-e ABRASF
        for pattern in nfse_patterns:
            if re.search(pattern, xml_content, re.IGNORECASE):
                return 'NFSE'

        return ''

    def _extract_nfe(self, xml_content: str, filename: str) -> XmlExtractionResult:
        """
        Extrai dados de XML de NF-e (modelo 55).

        Args:
            xml_content: Conteúdo do XML
            filename: Nome do arquivo de origem

        Returns:
            XmlExtractionResult com DanfeData
        """
        try:
            # Remove BOM se presente
            xml_content = xml_content.lstrip('\ufeff')

            # Remove namespaces do XML para facilitar parsing
            xml_content = self._remove_namespaces(xml_content)

            # Parse do XML
            root = ET.fromstring(xml_content)

            # Busca os elementos principais (sem namespace agora)
            inf_nfe = root.find('.//infNFe')
            if inf_nfe is None:
                inf_nfe = root.find('.//InfNFe')

            if inf_nfe is None:
                return XmlExtractionResult(
                    success=False,
                    error="Elemento infNFe não encontrado no XML"
                )

            # Namespace vazio após remoção
            ns = {}

            # Extrai dados
            raw_data = {}

            # Chave de acesso (44 dígitos)
            chave = inf_nfe.get('Id', '')
            if chave.startswith('NFe'):
                chave = chave[3:]
            raw_data['chave_acesso'] = chave

            # Identificação (ide)
            ide = inf_nfe.find('.//ide')
            if ide is not None:
                raw_data['numero_nota'] = self._get_element_text(ide, 'nNF')
                raw_data['serie_nf'] = self._get_element_text(ide, 'serie')
                raw_data['data_emissao'] = self._parse_date(self._get_element_text(ide, 'dhEmi'))
                raw_data['natureza_operacao'] = self._get_element_text(ide, 'natOp')

            # Emitente (emit)
            emit = inf_nfe.find('.//emit')
            if emit is not None:
                raw_data['cnpj_emitente'] = self._format_cnpj(self._get_element_text(emit, 'CNPJ'))
                raw_data['fornecedor_nome'] = self._get_element_text(emit, 'xNome')

            # Totais (total/ICMSTot)
            total = inf_nfe.find('.//total')
            if total is not None:
                icms_tot = total.find('.//ICMSTot')
                if icms_tot is not None:
                    raw_data['valor_total'] = self._parse_float(self._get_element_text(icms_tot, 'vNF'))
                    raw_data['valor_icms'] = self._parse_float(self._get_element_text(icms_tot, 'vICMS'))
                    raw_data['base_calculo_icms'] = self._parse_float(self._get_element_text(icms_tot, 'vBC'))

            # Cobrança (cobr) - vencimentos
            cobr = inf_nfe.find('.//cobr')
            if cobr is not None:
                # Pega a primeira duplicata
                dup = cobr.find('.//dup')
                if dup is not None:
                    raw_data['vencimento'] = self._parse_date(self._get_element_text(dup, 'dVenc'))
                    raw_data['numero_fatura'] = self._get_element_text(dup, 'nDup')

                # Fatura
                fat = cobr.find('.//fat')
                if fat is not None:
                    raw_data['numero_fatura'] = raw_data.get('numero_fatura') or self._get_element_text(fat, 'nFat')

            # Pagamento (pag) - forma de pagamento
            pag = inf_nfe.find('.//pag')
            if pag is not None:
                det_pag = pag.find('.//detPag')
                if det_pag is not None:
                    tp_pag = self._get_element_text(det_pag, 'tPag')
                    raw_data['forma_pagamento'] = self._map_forma_pagamento(tp_pag)

            # Informações complementares (podem conter número do pedido)
            inf_adic = inf_nfe.find('.//infAdic')
            if inf_adic is not None:
                inf_cpl = self._get_element_text(inf_adic, 'infCpl')
                if inf_cpl:
                    raw_data['info_complementar'] = inf_cpl
                    # Tenta extrair número do pedido
                    pedido = self._extract_numero_pedido(inf_cpl)
                    if pedido:
                        raw_data['numero_pedido'] = pedido

            # Cria DanfeData
            document = DanfeData(
                arquivo_origem=filename,
                texto_bruto=f"XML NF-e - Chave: {raw_data.get('chave_acesso', '')}",
                cnpj_emitente=raw_data.get('cnpj_emitente'),
                fornecedor_nome=raw_data.get('fornecedor_nome'),
                numero_nota=raw_data.get('numero_nota'),
                serie_nf=raw_data.get('serie_nf'),
                data_emissao=raw_data.get('data_emissao'),
                valor_total=raw_data.get('valor_total', 0.0),
                vencimento=raw_data.get('vencimento'),
                forma_pagamento=raw_data.get('forma_pagamento'),
                numero_pedido=raw_data.get('numero_pedido'),
                numero_fatura=raw_data.get('numero_fatura'),
                chave_acesso=raw_data.get('chave_acesso'),
            )

            return XmlExtractionResult(
                success=True,
                document=document,
                doc_type='NFE',
                raw_data=raw_data
            )

        except ET.ParseError as e:
            return XmlExtractionResult(
                success=False,
                error=f"Erro ao fazer parse do XML: {e}"
            )
        except Exception as e:
            return XmlExtractionResult(
                success=False,
                error=f"Erro ao processar NF-e: {e}"
            )

    def _extract_nfse_sigiss(self, xml_content: str, filename: str) -> XmlExtractionResult:
        """
        Extrai dados de XML de NFS-e no formato SigISS (municipal).

        Usado por prefeituras como Marília-SP, entre outras que usam o sistema SigCorp/SigISS.

        Estrutura típica:
        <NFe>
            <Prefeitura>...</Prefeitura>
            <CPFCNPJPrestador><CNPJ>...</CNPJ></CPFCNPJPrestador>
            <ChaveNFe><NumeroNFe>...</NumeroNFe><DataEmissaoNFe>...</DataEmissaoNFe></ChaveNFe>
            <RazaoSocialPrestador>...</RazaoSocialPrestador>
            <ValorServicos>...</ValorServicos>
            ...
        </NFe>

        Args:
            xml_content: Conteúdo do XML
            filename: Nome do arquivo de origem

        Returns:
            XmlExtractionResult com InvoiceData
        """
        try:
            # Remove BOM se presente
            xml_content = xml_content.lstrip('\ufeff')

            # Remove namespaces do XML para facilitar parsing
            xml_content = self._remove_namespaces(xml_content)

            # Parse do XML
            root = ET.fromstring(xml_content)

            raw_data = {}

            # Se a raiz é NFe, usa ela diretamente
            local_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag
            nfe_elem = root if local_tag == 'NFe' else root.find('.//NFe')

            if nfe_elem is None:
                return XmlExtractionResult(
                    success=False,
                    error="Estrutura de NFS-e SigISS não reconhecida no XML"
                )

            # Número da NFS-e (dentro de ChaveNFe)
            chave_nfe = nfe_elem.find('ChaveNFe')
            if chave_nfe is not None:
                raw_data['numero_nota'] = self._get_element_text(chave_nfe, 'NumeroNFe')
                raw_data['serie'] = self._get_element_text(chave_nfe, 'SerieNFe')
                raw_data['codigo_verificacao'] = self._get_element_text(chave_nfe, 'CodigoVerificacao')

                # Data de emissão
                data_emissao_raw = self._get_element_text(chave_nfe, 'DataEmissaoNFe')
                raw_data['data_emissao'] = self._parse_date(data_emissao_raw)

            # CNPJ do prestador
            cnpj_prestador_elem = nfe_elem.find('CPFCNPJPrestador')
            if cnpj_prestador_elem is not None:
                cnpj = self._get_element_text(cnpj_prestador_elem, 'CNPJ')
                if not cnpj:
                    cnpj = self._get_element_text(cnpj_prestador_elem, 'CPF')
                raw_data['cnpj_prestador'] = self._format_cnpj(cnpj)

            # Razão social do prestador
            raw_data['fornecedor_nome'] = self._get_element_text(nfe_elem, 'RazaoSocialPrestador')

            # Valores
            raw_data['valor_total'] = self._parse_float(
                self._get_element_text(nfe_elem, 'ValorServicos')
            )
            raw_data['valor_base'] = self._parse_float(
                self._get_element_text(nfe_elem, 'ValorBase')
            )
            raw_data['valor_iss'] = self._parse_float(
                self._get_element_text(nfe_elem, 'ValorISS')
            )
            raw_data['valor_ir'] = self._parse_float(
                self._get_element_text(nfe_elem, 'ValorIR')
            )
            raw_data['valor_inss'] = self._parse_float(
                self._get_element_text(nfe_elem, 'ValorINSS')
            )
            raw_data['valor_pis'] = self._parse_float(
                self._get_element_text(nfe_elem, 'ValorPIS')
            )
            raw_data['valor_cofins'] = self._parse_float(
                self._get_element_text(nfe_elem, 'ValorCOFINS')
            )
            raw_data['valor_csll'] = self._parse_float(
                self._get_element_text(nfe_elem, 'ValorCSLL')
            )
            raw_data['aliquota'] = self._parse_float(
                self._get_element_text(nfe_elem, 'AliquotaServicos')
            )

            # Status da NFe
            raw_data['status'] = self._get_element_text(nfe_elem, 'StatusNFe')

            # Prefeitura/Município
            raw_data['prefeitura'] = self._get_element_text(nfe_elem, 'Prefeitura')

            # Tomador de serviço
            cnpj_tomador_elem = nfe_elem.find('CPFCNPJTomador')
            if cnpj_tomador_elem is not None:
                cnpj = self._get_element_text(cnpj_tomador_elem, 'CNPJ')
                if not cnpj:
                    cnpj = self._get_element_text(cnpj_tomador_elem, 'CPF')
                raw_data['cnpj_tomador'] = self._format_cnpj(cnpj)

            raw_data['tomador_nome'] = self._get_element_text(nfe_elem, 'RazaoSocialTomador')

            # Discriminação do serviço
            discriminacao = self._get_element_text(nfe_elem, 'Discriminacao')
            if discriminacao:
                raw_data['info_complementar'] = discriminacao
                pedido = self._extract_numero_pedido(discriminacao)
                if pedido:
                    raw_data['numero_pedido'] = pedido

            # Cria InvoiceData
            document = InvoiceData(
                arquivo_origem=filename,
                texto_bruto=f"XML NFS-e SigISS - Número: {raw_data.get('numero_nota', '')} - {raw_data.get('prefeitura', '')}",
                cnpj_prestador=raw_data.get('cnpj_prestador'),
                fornecedor_nome=raw_data.get('fornecedor_nome'),
                numero_nota=raw_data.get('numero_nota'),
                serie_nf=raw_data.get('serie'),
                data_emissao=raw_data.get('data_emissao'),
                valor_total=raw_data.get('valor_total', 0.0),
                valor_iss=raw_data.get('valor_iss'),
                valor_ir=raw_data.get('valor_ir'),
                valor_inss=raw_data.get('valor_inss'),
                valor_csll=raw_data.get('valor_csll'),
                numero_pedido=raw_data.get('numero_pedido'),
            )

            return XmlExtractionResult(
                success=True,
                document=document,
                doc_type='NFSE_SIGISS',
                raw_data=raw_data
            )

        except ET.ParseError as e:
            return XmlExtractionResult(
                success=False,
                error=f"Erro ao fazer parse do XML SigISS: {e}"
            )
        except Exception as e:
            return XmlExtractionResult(
                success=False,
                error=f"Erro ao processar NFS-e SigISS: {e}"
            )

    def _extract_nfse_sped(self, xml_content: str, filename: str) -> XmlExtractionResult:
        """
        Extrai dados de XML de NFS-e no padrão SPED/SEFIN Nacional.

        Formato novo federal com namespace http://www.sped.fazenda.gov.br/nfse
        Tags principais: <NFSe>, <infNFSe>, <emit>, <DPS>, <infDPS>, <prest>, <toma>

        Args:
            xml_content: Conteúdo do XML
            filename: Nome do arquivo de origem

        Returns:
            XmlExtractionResult com InvoiceData
        """
        try:
            # Remove BOM se presente
            xml_content = xml_content.lstrip('\ufeff')

            # Remove namespaces do XML para facilitar parsing
            xml_content = self._remove_namespaces(xml_content)

            # Parse do XML
            root = ET.fromstring(xml_content)

            raw_data = {}

            # Busca infNFSe (elemento principal)
            inf_nfse = root.find('.//infNFSe')
            if inf_nfse is None:
                inf_nfse = root

            # Número da NFS-e
            raw_data['numero_nota'] = self._find_text_in_paths(inf_nfse, [
                'nNFSe', 'nDFSe', 'Numero'
            ])

            # Data de emissão (busca em infNFSe ou DPS/infDPS)
            data_emissao_raw = self._find_text_in_paths(inf_nfse, [
                'dhProc', 'dhEmi'
            ])
            # Também tenta no DPS
            if not data_emissao_raw:
                dps = inf_nfse.find('.//DPS')
                if dps is not None:
                    inf_dps = dps.find('.//infDPS')
                    if inf_dps is not None:
                        data_emissao_raw = self._find_text_in_paths(inf_dps, [
                            'dhEmi', 'dCompet'
                        ])
            raw_data['data_emissao'] = self._parse_date(data_emissao_raw)

            # Emitente/Prestador (emit)
            emit = inf_nfse.find('.//emit')
            if emit is not None:
                raw_data['cnpj_prestador'] = self._format_cnpj(
                    self._get_element_text(emit, 'CNPJ')
                )
                raw_data['fornecedor_nome'] = self._get_element_text(emit, 'xNome')

            # Valores
            valores = inf_nfse.find('.//valores')
            if valores is not None:
                # Valor líquido
                raw_data['valor_total'] = self._parse_float(
                    self._find_text_in_paths(valores, [
                        'vLiq', 'vServ', 'vTotServ'
                    ])
                )

            # Se não achou valores na raiz, tenta no DPS
            if not raw_data.get('valor_total'):
                dps = inf_nfse.find('.//DPS')
                if dps is not None:
                    inf_dps = dps.find('.//infDPS')
                    if inf_dps is not None:
                        valores_dps = inf_dps.find('.//valores')
                        if valores_dps is not None:
                            v_serv_prest = valores_dps.find('.//vServPrest')
                            if v_serv_prest is not None:
                                raw_data['valor_total'] = self._parse_float(
                                    self._get_element_text(v_serv_prest, 'vServ')
                                )

            # Tomador (toma) - cliente que recebeu o serviço
            dps = inf_nfse.find('.//DPS')
            if dps is not None:
                inf_dps = dps.find('.//infDPS')
                if inf_dps is not None:
                    toma = inf_dps.find('.//toma')
                    if toma is not None:
                        raw_data['cnpj_tomador'] = self._format_cnpj(
                            self._get_element_text(toma, 'CNPJ')
                        )
                        raw_data['tomador_nome'] = self._get_element_text(toma, 'xNome')

                    # Descrição do serviço (pode conter número do pedido)
                    serv = inf_dps.find('.//serv')
                    if serv is not None:
                        c_serv = serv.find('.//cServ')
                        if c_serv is not None:
                            desc_serv = self._get_element_text(c_serv, 'xDescServ')
                            if desc_serv:
                                raw_data['info_complementar'] = desc_serv
                                pedido = self._extract_numero_pedido(desc_serv)
                                if pedido:
                                    raw_data['numero_pedido'] = pedido

                                # Tenta extrair vencimento da descrição
                                venc_match = re.search(
                                    r'vencimento[:\s]+(\d{2}[/\-]\d{2}[/\-]\d{4})',
                                    desc_serv,
                                    re.IGNORECASE
                                )
                                if venc_match:
                                    raw_data['vencimento'] = self._parse_date(venc_match.group(1))

            # Cria InvoiceData
            document = InvoiceData(
                arquivo_origem=filename,
                texto_bruto=f"XML NFS-e SPED - Número: {raw_data.get('numero_nota', '')}",
                cnpj_prestador=raw_data.get('cnpj_prestador'),
                fornecedor_nome=raw_data.get('fornecedor_nome'),
                numero_nota=raw_data.get('numero_nota'),
                data_emissao=raw_data.get('data_emissao'),
                valor_total=raw_data.get('valor_total', 0.0),
                numero_pedido=raw_data.get('numero_pedido'),
                vencimento=raw_data.get('vencimento'),
            )

            return XmlExtractionResult(
                success=True,
                document=document,
                doc_type='NFSE',
                raw_data=raw_data
            )

        except ET.ParseError as e:
            return XmlExtractionResult(
                success=False,
                error=f"Erro ao fazer parse do XML SPED: {e}"
            )
        except Exception as e:
            return XmlExtractionResult(
                success=False,
                error=f"Erro ao processar NFS-e SPED: {e}"
            )

    def _extract_nfse(self, xml_content: str, filename: str) -> XmlExtractionResult:
        """
        Extrai dados de XML de NFS-e.

        Suporta múltiplos padrões:
        - ABRASF (padrão nacional)
        - Variantes municipais (SP, RJ, etc.)

        Args:
            xml_content: Conteúdo do XML
            filename: Nome do arquivo de origem

        Returns:
            XmlExtractionResult com InvoiceData
        """
        try:
            # Remove BOM se presente
            xml_content = xml_content.lstrip('\ufeff')

            # Remove namespaces do XML para facilitar parsing
            xml_content = self._remove_namespaces(xml_content)

            # Parse do XML
            root = ET.fromstring(xml_content)

            raw_data = {}

            # Tenta diferentes estruturas de NFS-e (sem namespace agora)
            inf_nfse = root.find('.//InfNfse')
            if inf_nfse is None:
                inf_nfse = root.find('.//infNfse')
            if inf_nfse is None:
                inf_nfse = root.find('.//InfRps')
            if inf_nfse is None:
                inf_nfse = root.find('.//infRps')

            if inf_nfse is None:
                # Tenta estrutura raiz direta
                local_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag
                if local_tag in ('Nfse', 'CompNfse'):
                    inf_nfse = root

            if inf_nfse is None:
                return XmlExtractionResult(
                    success=False,
                    error="Estrutura de NFS-e não reconhecida no XML"
                )

            # Número da NFS-e
            raw_data['numero_nota'] = self._find_text_in_paths(inf_nfse, [
                'Numero', 'NumeroNfse', 'numero', 'numeroNfse',
                'IdentificacaoNfse/Numero'
            ])

            # Código de verificação
            raw_data['codigo_verificacao'] = self._find_text_in_paths(inf_nfse, [
                'CodigoVerificacao', 'codigoVerificacao', 'CodVerificacao'
            ])

            # Data de emissão
            data_emissao_raw = self._find_text_in_paths(inf_nfse, [
                'DataEmissao', 'dataEmissao', 'DataEmissaoNfse',
                'dtEmissao', 'DtEmissao', 'DataHoraEmissao'
            ])
            raw_data['data_emissao'] = self._parse_date(data_emissao_raw)

            # Prestador de serviço (fornecedor)
            prestador = self._find_first_element(inf_nfse, [
                'PrestadorServico', 'Prestador', 'prestadorServico', 'DadosPrestador'
            ])

            if prestador is not None:
                # CNPJ do prestador
                raw_data['cnpj_prestador'] = self._format_cnpj(
                    self._find_text_in_paths(prestador, [
                        'Cnpj', 'CNPJ', 'cnpj',
                        'IdentificacaoPrestador/Cnpj',
                        'IdentificacaoPrestador/CpfCnpj/Cnpj',
                        'CpfCnpj/Cnpj'
                    ])
                )

                # Razão social do prestador
                raw_data['fornecedor_nome'] = self._find_text_in_paths(prestador, [
                    'RazaoSocial', 'razaoSocial', 'Nome', 'nome',
                    'NomeFantasia', 'xNome'
                ])

            # Serviço (valores)
            servico = self._find_first_element(inf_nfse, [
                'Servico', 'servico', 'ValoresServico', 'DadosServico'
            ])

            if servico is not None:
                # Valor do serviço
                raw_data['valor_total'] = self._parse_float(
                    self._find_text_in_paths(servico, [
                        'ValorServicos', 'valorServicos', 'ValorLiquidoNfse',
                        'ValorNfse', 'Valores/ValorServicos', 'vServ'
                    ])
                )

                # Valor líquido (se diferente)
                valor_liquido = self._parse_float(
                    self._find_text_in_paths(servico, [
                        'ValorLiquidoNfse', 'ValorLiquido', 'valorLiquido'
                    ])
                )
                if valor_liquido and valor_liquido > 0:
                    raw_data['valor_total'] = valor_liquido

                # ISS
                raw_data['valor_iss'] = self._parse_float(
                    self._find_text_in_paths(servico, [
                        'ValorIss', 'valorIss', 'ValorISSQN', 'vISS'
                    ])
                )

                # Retenções
                raw_data['valor_ir'] = self._parse_float(
                    self._find_text_in_paths(servico, [
                        'ValorIr', 'valorIr', 'ValorIRRF', 'vIR'
                    ])
                )

                raw_data['valor_inss'] = self._parse_float(
                    self._find_text_in_paths(servico, [
                        'ValorInss', 'valorInss', 'ValorINSS', 'vINSS'
                    ])
                )

                raw_data['valor_csll'] = self._parse_float(
                    self._find_text_in_paths(servico, [
                        'ValorCsll', 'valorCsll', 'ValorCSLL', 'vCSLL'
                    ])
                )

            # Se não encontrou valores no serviço, tenta na raiz
            if not raw_data.get('valor_total'):
                raw_data['valor_total'] = self._parse_float(
                    self._find_text_in_paths(inf_nfse, [
                        'ValorServicos', 'ValorNfse', 'ValorLiquidoNfse',
                        'Valores/ValorServicos'
                    ])
                )

            # Tomador de serviço (cliente)
            tomador = self._find_first_element(inf_nfse, [
                'TomadorServico', 'Tomador', 'tomadorServico', 'DadosTomador'
            ])

            if tomador is not None:
                raw_data['cnpj_tomador'] = self._format_cnpj(
                    self._find_text_in_paths(tomador, [
                        'Cnpj', 'CNPJ', 'cnpj',
                        'IdentificacaoTomador/Cnpj',
                        'IdentificacaoTomador/CpfCnpj/Cnpj',
                        'CpfCnpj/Cnpj'
                    ])
                )
                raw_data['tomador_nome'] = self._find_text_in_paths(tomador, [
                    'RazaoSocial', 'razaoSocial', 'Nome', 'nome'
                ])

            # Tenta encontrar informações complementares/observações
            obs = self._find_text_in_paths(inf_nfse, [
                'OutrasInformacoes', 'InformacoesComplementares',
                'Observacao', 'Discriminacao'
            ])
            if obs:
                raw_data['info_complementar'] = obs
                pedido = self._extract_numero_pedido(obs)
                if pedido:
                    raw_data['numero_pedido'] = pedido

            # Cria InvoiceData
            document = InvoiceData(
                arquivo_origem=filename,
                texto_bruto=f"XML NFS-e - Número: {raw_data.get('numero_nota', '')}",
                cnpj_prestador=raw_data.get('cnpj_prestador'),
                fornecedor_nome=raw_data.get('fornecedor_nome'),
                numero_nota=raw_data.get('numero_nota'),
                data_emissao=raw_data.get('data_emissao'),
                valor_total=raw_data.get('valor_total', 0.0),
                valor_iss=raw_data.get('valor_iss'),
                valor_ir=raw_data.get('valor_ir'),
                valor_inss=raw_data.get('valor_inss'),
                valor_csll=raw_data.get('valor_csll'),
                numero_pedido=raw_data.get('numero_pedido'),
            )

            return XmlExtractionResult(
                success=True,
                document=document,
                doc_type='NFSE',
                raw_data=raw_data
            )

        except ET.ParseError as e:
            return XmlExtractionResult(
                success=False,
                error=f"Erro ao fazer parse do XML: {e}"
            )
        except Exception as e:
            return XmlExtractionResult(
                success=False,
                error=f"Erro ao processar NFS-e: {e}"
            )

    # ==================== Métodos Auxiliares ====================

    def _remove_namespaces(self, xml_content: str) -> str:
        """
        Remove namespaces do XML para facilitar o parsing.

        Isso simplifica muito a busca por elementos, já que não precisamos
        lidar com variações de namespace entre diferentes emissores.
        """
        # Remove declarações xmlns
        xml_content = re.sub(r'\sxmlns[^=]*="[^"]*"', '', xml_content)
        # Remove prefixos de namespace (ex: nfe:, ns1:)
        xml_content = re.sub(r'<(/?)[\w]+:', r'<\1', xml_content)
        return xml_content

    def _get_element_text(self, parent: ET.Element, tag: str) -> Optional[str]:
        """Obtém texto de um elemento filho direto ou descendente."""
        # Tenta filho direto primeiro
        elem = parent.find(tag)
        if elem is not None and elem.text:
            return elem.text.strip()

        # Tenta descendente
        elem = parent.find(f".//{tag}")
        if elem is not None and elem.text:
            return elem.text.strip()

        return None

    def _find_first_element(self, parent: ET.Element, tags: List[str]) -> Optional[ET.Element]:
        """Busca o primeiro elemento encontrado de uma lista de possíveis tags."""
        for tag in tags:
            # Tenta filho direto
            elem = parent.find(tag)
            if elem is not None:
                return elem
            # Tenta descendente
            elem = parent.find(f".//{tag}")
            if elem is not None:
                return elem
        return None

    def _find_text_in_paths(self, parent: ET.Element, paths: List[str]) -> Optional[str]:
        """Busca texto no primeiro caminho encontrado."""
        for path in paths:
            # Tenta caminho direto
            elem = parent.find(path)
            if elem is not None and elem.text:
                return elem.text.strip()
            # Tenta como descendente
            elem = parent.find(f".//{path}")
            if elem is not None and elem.text:
                return elem.text.strip()
        return None

    def _parse_date(self, date_str: Optional[str]) -> Optional[str]:
        """
        Converte data para formato ISO (YYYY-MM-DD).

        Suporta formatos:
        - 2025-01-15
        - 2025-01-15T10:30:00
        - 2025-01-15T10:30:00-03:00
        - 15/01/2025
        - 15-01-2025
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        # Formato ISO com timezone
        if 'T' in date_str:
            date_str = date_str.split('T')[0]

        # Já está em formato ISO
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        # Formato DD/MM/YYYY ou DD-MM-YYYY
        match = re.match(r'^(\d{2})[/-](\d{2})[/-](\d{4})$', date_str)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month}-{day}"

        # Formato YYYY-MM-DD já parcialmente processado
        match = re.match(r'^(\d{4})-(\d{2})-(\d{2})', date_str)
        if match:
            return match.group(0)

        return None

    def _parse_float(self, value_str: Optional[str]) -> Optional[float]:
        """Converte string para float."""
        if not value_str:
            return None

        try:
            # Remove espaços e caracteres não numéricos exceto ponto e vírgula
            value_str = value_str.strip()

            # Padrão brasileiro: 1.234,56 -> 1234.56
            if ',' in value_str and '.' in value_str:
                value_str = value_str.replace('.', '').replace(',', '.')
            elif ',' in value_str:
                value_str = value_str.replace(',', '.')

            return float(value_str)
        except (ValueError, TypeError):
            return None

    def _format_cnpj(self, cnpj: Optional[str]) -> Optional[str]:
        """Formata CNPJ para padrão XX.XXX.XXX/XXXX-XX."""
        if not cnpj:
            return None

        # Remove formatação existente
        cnpj = re.sub(r'\D', '', cnpj)

        if len(cnpj) != 14:
            return cnpj  # Retorna sem formatar se inválido

        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"

    def _map_forma_pagamento(self, codigo: Optional[str]) -> Optional[str]:
        """Mapeia código de forma de pagamento para texto."""
        if not codigo:
            return None

        mapa = {
            '01': 'DINHEIRO',
            '02': 'CHEQUE',
            '03': 'CARTÃO DE CRÉDITO',
            '04': 'CARTÃO DE DÉBITO',
            '05': 'CRÉDITO LOJA',
            '10': 'VALE ALIMENTAÇÃO',
            '11': 'VALE REFEIÇÃO',
            '12': 'VALE PRESENTE',
            '13': 'VALE COMBUSTÍVEL',
            '14': 'DUPLICATA MERCANTIL',
            '15': 'BOLETO',
            '16': 'DEPÓSITO BANCÁRIO',
            '17': 'PIX',
            '18': 'TRANSFERÊNCIA BANCÁRIA',
            '19': 'PROGRAMA DE FIDELIDADE',
            '90': 'SEM PAGAMENTO',
            '99': 'OUTROS',
        }

        return mapa.get(codigo, f'CODIGO_{codigo}')

    def _extract_numero_pedido(self, text: str) -> Optional[str]:
        """Extrai número de pedido do texto."""
        if not text:
            return None

        patterns = [
            r'(?:pedido|ped|ordem|oc|pc)[:\s]*[nº#]*\s*(\d{4,})',
            r'(?:ref|referencia)[:\s]*(\d{4,})',
            r'(?:ordem de compra|oc)[:\s]*(\d{4,})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None


# Função utilitária para uso direto
def extract_xml(xml_path: str) -> XmlExtractionResult:
    """
    Função de conveniência para extrair dados de XML.

    Args:
        xml_path: Caminho do arquivo XML

    Returns:
        XmlExtractionResult
    """
    extractor = XmlExtractor()
    return extractor.extract(xml_path)
