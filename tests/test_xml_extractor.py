"""
Testes para o extrator de XML de NF-e e NFS-e.

Testa:
- Detecção de tipo de documento (NF-e vs NFS-e)
- Extração de campos de NF-e
- Extração de campos de NFS-e
- Tratamento de erros
- Parsing de datas e valores
"""

import tempfile
import unittest
from pathlib import Path

from core.models import DanfeData, InvoiceData
from extractors.xml_extractor import XmlExtractionResult, XmlExtractor, extract_xml


class TestXmlExtractorDetection(unittest.TestCase):
    """Testa detecção de tipo de documento XML."""

    def setUp(self):
        self.extractor = XmlExtractor()

    def test_detect_nfe_by_nfeproc_tag(self):
        """Detecta NF-e pela tag nfeProc."""
        xml = '<nfeProc><NFe></NFe></nfeProc>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFE')

    def test_detect_nfe_by_infnfe_tag(self):
        """Detecta NF-e pela tag infNFe."""
        xml = '<NFe><infNFe Id="NFe123"></infNFe></NFe>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFE')

    def test_detect_nfe_by_namespace(self):
        """Detecta NF-e pelo namespace do portal fiscal."""
        xml = '<root xmlns="http://www.portalfiscal.inf.br/nfe"></root>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFE')

    def test_detect_nfe_by_modelo_55(self):
        """Detecta NF-e pelo modelo 55."""
        xml = '<NFe><ide><mod>55</mod></ide></NFe>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFE')

    def test_detect_nfse_by_compnfse_tag(self):
        """Detecta NFS-e pela tag CompNfse."""
        xml = '<CompNfse><Nfse></Nfse></CompNfse>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFSE')

    def test_detect_nfse_by_infnfse_tag(self):
        """Detecta NFS-e pela tag InfNfse."""
        xml = '<Nfse><InfNfse></InfNfse></Nfse>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFSE')

    def test_detect_nfse_by_abrasf_namespace(self):
        """Detecta NFS-e pelo namespace ABRASF."""
        xml = '<root xmlns="http://www.abrasf.org.br/nfse.xsd"></root>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFSE')

    def test_detect_nfse_by_prestador_tag(self):
        """Detecta NFS-e pela tag PrestadorServico."""
        xml = '<Nfse><PrestadorServico><Cnpj>123</Cnpj></PrestadorServico></Nfse>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFSE')

    def test_detect_nfse_sigiss_by_chavenfe_tag(self):
        """Detecta NFS-e SigISS pela estrutura ChaveNFe."""
        xml = '''<NFe>
            <InscricaoPrestador>12345</InscricaoPrestador>
            <CPFCNPJPrestador><CNPJ>12345678000195</CNPJ></CPFCNPJPrestador>
            <ChaveNFe><NumeroNFe>100</NumeroNFe></ChaveNFe>
            <ValorServicos>100.00</ValorServicos>
        </NFe>'''
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFSE_SIGISS')

    def test_detect_nfse_sigiss_by_tributacao_tag(self):
        """Detecta NFS-e SigISS pela tag TributacaoNFe e outras tags características."""
        xml = '''<NFe>
            <InscricaoPrestador>12345</InscricaoPrestador>
            <TributacaoNFe>Tributado</TributacaoNFe>
            <StatusNFe>Ativa</StatusNFe>
            <ValorServicos>500.00</ValorServicos>
        </NFe>'''
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFSE_SIGISS')

    def test_detect_nfse_sped_by_namespace(self):
        """Detecta NFS-e SPED pelo namespace sped.fazenda.gov.br."""
        xml = '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"><infNFSe Id="NFS123"><nNFSe>912</nNFSe></infNFSe></NFSe>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFSE_SPED')

    def test_detect_nfse_sped_by_tags(self):
        """Detecta NFS-e SPED pelas tags características."""
        xml = '''<NFSe versao="1.00">
            <infNFSe Id="NFS123">
                <nNFSe>912</nNFSe>
                <nDFSe>16442633</nDFSe>
                <emit><CNPJ>12345678000195</CNPJ></emit>
            </infNFSe>
        </NFSe>'''
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFSE_SPED')

    def test_detect_nfse_sped_by_dps_structure(self):
        """Detecta NFS-e SPED pela estrutura DPS/infDPS."""
        xml = '''<NFSe>
            <infNFSe Id="NFS123">
                <DPS versao="1.00">
                    <infDPS Id="DPS123">
                        <toma><CNPJ>38323227000140</CNPJ></toma>
                        <prest><CNPJ>17907897000134</CNPJ></prest>
                    </infDPS>
                </DPS>
            </infNFSe>
        </NFSe>'''
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, 'NFSE_SPED')

    def test_detect_unknown_document(self):
        """Retorna vazio para documento não reconhecido."""
        xml = '<root><data>test</data></root>'
        doc_type = self.extractor._detect_document_type(xml)
        self.assertEqual(doc_type, '')


class TestXmlExtractorNFe(unittest.TestCase):
    """Testa extração de NF-e."""

    def setUp(self):
        self.extractor = XmlExtractor()

    def _create_nfe_xml(self, **kwargs) -> str:
        """Cria XML de NF-e para testes."""
        defaults = {
            'chave': '35250112345678000195550010000001231234567890',
            'numero': '123',
            'serie': '1',
            'data_emissao': '2025-01-15T10:30:00-03:00',
            'cnpj': '12345678000195',
            'razao_social': 'Empresa Teste LTDA',
            'valor_nf': '1500.00',
            'valor_icms': '270.00',
            'vencimento': '2025-02-15',
            'numero_fatura': '001',
        }
        defaults.update(kwargs)

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
    <NFe>
        <infNFe Id="NFe{defaults['chave']}">
            <ide>
                <nNF>{defaults['numero']}</nNF>
                <serie>{defaults['serie']}</serie>
                <dhEmi>{defaults['data_emissao']}</dhEmi>
                <mod>55</mod>
            </ide>
            <emit>
                <CNPJ>{defaults['cnpj']}</CNPJ>
                <xNome>{defaults['razao_social']}</xNome>
            </emit>
            <total>
                <ICMSTot>
                    <vNF>{defaults['valor_nf']}</vNF>
                    <vICMS>{defaults['valor_icms']}</vICMS>
                </ICMSTot>
            </total>
            <cobr>
                <dup>
                    <dVenc>{defaults['vencimento']}</dVenc>
                    <nDup>{defaults['numero_fatura']}</nDup>
                </dup>
            </cobr>
        </infNFe>
    </NFe>
</nfeProc>'''

    def test_extract_nfe_success(self):
        """Extrai dados de NF-e com sucesso."""
        xml_content = self._create_nfe_xml()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            self.assertEqual(result.doc_type, 'NFE')
            self.assertIsInstance(result.document, DanfeData)

            doc = result.document
            self.assertEqual(doc.numero_nota, '123')
            self.assertEqual(doc.serie_nf, '1')
            self.assertEqual(doc.data_emissao, '2025-01-15')
            self.assertEqual(doc.cnpj_emitente, '12.345.678/0001-95')
            self.assertEqual(doc.fornecedor_nome, 'Empresa Teste LTDA')
            self.assertEqual(doc.valor_total, 1500.0)
            self.assertEqual(doc.vencimento, '2025-02-15')
        finally:
            Path(temp_path).unlink()

    def test_extract_nfe_chave_acesso(self):
        """Extrai chave de acesso de 44 dígitos."""
        xml_content = self._create_nfe_xml(chave='35250112345678000195550010000001231234567890')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            self.assertEqual(
                result.document.chave_acesso,
                '35250112345678000195550010000001231234567890'
            )
        finally:
            Path(temp_path).unlink()

    def test_extract_nfe_formats_cnpj(self):
        """Formata CNPJ corretamente."""
        xml_content = self._create_nfe_xml(cnpj='12345678000195')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            self.assertEqual(result.document.cnpj_emitente, '12.345.678/0001-95')
        finally:
            Path(temp_path).unlink()


class TestXmlExtractorNFSe(unittest.TestCase):
    """Testa extração de NFS-e."""

    def setUp(self):
        self.extractor = XmlExtractor()

    def _create_nfse_xml(self, **kwargs) -> str:
        """Cria XML de NFS-e (padrão ABRASF) para testes."""
        defaults = {
            'numero': '456',
            'data_emissao': '2025-01-20',
            'cnpj_prestador': '98765432000198',
            'razao_social': 'Prestador Serviços LTDA',
            'valor_servicos': '2500.00',
            'valor_iss': '50.00',
        }
        defaults.update(kwargs)

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<CompNfse xmlns="http://www.abrasf.org.br/nfse.xsd">
    <Nfse>
        <InfNfse>
            <Numero>{defaults['numero']}</Numero>
            <DataEmissao>{defaults['data_emissao']}</DataEmissao>
            <PrestadorServico>
                <IdentificacaoPrestador>
                    <Cnpj>{defaults['cnpj_prestador']}</Cnpj>
                </IdentificacaoPrestador>
                <RazaoSocial>{defaults['razao_social']}</RazaoSocial>
            </PrestadorServico>
            <Servico>
                <ValorServicos>{defaults['valor_servicos']}</ValorServicos>
                <ValorIss>{defaults['valor_iss']}</ValorIss>
            </Servico>
        </InfNfse>
    </Nfse>
</CompNfse>'''

    def test_extract_nfse_success(self):
        """Extrai dados de NFS-e com sucesso."""
        xml_content = self._create_nfse_xml()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            self.assertEqual(result.doc_type, 'NFSE')
            self.assertIsInstance(result.document, InvoiceData)

            doc = result.document
            self.assertEqual(doc.numero_nota, '456')
            self.assertEqual(doc.data_emissao, '2025-01-20')
            self.assertEqual(doc.cnpj_prestador, '98.765.432/0001-98')
            self.assertEqual(doc.fornecedor_nome, 'Prestador Serviços LTDA')
            self.assertEqual(doc.valor_total, 2500.0)
            self.assertEqual(doc.valor_iss, 50.0)
        finally:
            Path(temp_path).unlink()

    def test_extract_nfse_with_retencoes(self):
        """Extrai NFS-e com retenções (IR, INSS, CSLL)."""
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<CompNfse>
    <Nfse>
        <InfNfse>
            <Numero>789</Numero>
            <DataEmissao>2025-01-25</DataEmissao>
            <PrestadorServico>
                <Cnpj>11222333000144</Cnpj>
                <RazaoSocial>Consultoria ABC</RazaoSocial>
            </PrestadorServico>
            <Servico>
                <ValorServicos>10000.00</ValorServicos>
                <ValorIss>500.00</ValorIss>
                <ValorIr>150.00</ValorIr>
                <ValorInss>110.00</ValorInss>
                <ValorCsll>100.00</ValorCsll>
            </Servico>
        </InfNfse>
    </Nfse>
</CompNfse>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            doc = result.document
            self.assertEqual(doc.valor_total, 10000.0)
            self.assertEqual(doc.valor_iss, 500.0)
            self.assertEqual(doc.valor_ir, 150.0)
            self.assertEqual(doc.valor_inss, 110.0)
            self.assertEqual(doc.valor_csll, 100.0)
        finally:
            Path(temp_path).unlink()


class TestXmlExtractorNFSeSPED(unittest.TestCase):
    """Testa extração de NFS-e no padrão SPED/SEFIN Nacional."""

    def setUp(self):
        self.extractor = XmlExtractor()

    def _create_sped_xml(self, numero_nfse="912", cnpj_emit="17907897000134",
                         nome_emit="4SECURITY TECNOLOGIA LTDA", valor="561.47",
                         data_emissao="2025-11-01T03:35:38-03:00",
                         vencimento_desc="18/11/2025"):
        """Cria XML de NFS-e SPED para testes."""
        return f'''<?xml version="1.0" encoding="utf-8"?>
        <NFSe versao="1.00" xmlns="http://www.sped.fazenda.gov.br/nfse">
            <infNFSe Id="NFS123">
                <nNFSe>{numero_nfse}</nNFSe>
                <nDFSe>16442633</nDFSe>
                <dhProc>{data_emissao}</dhProc>
                <emit>
                    <CNPJ>{cnpj_emit}</CNPJ>
                    <xNome>{nome_emit}</xNome>
                </emit>
                <valores>
                    <vLiq>{valor}</vLiq>
                </valores>
                <DPS versao="1.00">
                    <infDPS Id="DPS123">
                        <dhEmi>2025-11-01T03:35:17-03:00</dhEmi>
                        <toma>
                            <CNPJ>38323227000140</CNPJ>
                            <xNome>CSC Gestão Integrada S/A</xNome>
                        </toma>
                        <prest>
                            <CNPJ>{cnpj_emit}</CNPJ>
                        </prest>
                        <serv>
                            <cServ>
                                <xDescServ>Gestão de Firewall R${valor}
                                    Ref: Parcela com vencimento {vencimento_desc}
                                </xDescServ>
                            </cServ>
                        </serv>
                    </infDPS>
                </DPS>
            </infNFSe>
        </NFSe>'''

    def test_extract_nfse_sped_success(self):
        """Testa extração de NFS-e SPED com sucesso."""
        xml = self._create_sped_xml()

        # Salva em arquivo temporário
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            self.assertEqual(result.doc_type, 'NFSE')
            self.assertIsNotNone(result.document)

            doc = result.document
            self.assertEqual(doc.numero_nota, '912')
            self.assertEqual(doc.fornecedor_nome, '4SECURITY TECNOLOGIA LTDA')
            self.assertEqual(doc.cnpj_prestador, '17.907.897/0001-34')
            self.assertEqual(doc.data_emissao, '2025-11-01')
            self.assertAlmostEqual(doc.valor_total, 561.47, places=2)
        finally:
            import os
            os.unlink(temp_path)

    def test_extract_nfse_sped_vencimento_from_description(self):
        """Testa extração de vencimento da descrição do serviço."""
        xml = self._create_sped_xml(vencimento_desc="25/12/2025")

        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            doc = result.document
            self.assertEqual(doc.vencimento, '2025-12-25')
        finally:
            import os
            os.unlink(temp_path)

    def test_extract_nfse_sped_formats_cnpj(self):
        """Testa formatação de CNPJ em NFS-e SPED."""
        xml = self._create_sped_xml(cnpj_emit="12345678000195")

        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            self.assertEqual(result.document.cnpj_prestador, '12.345.678/0001-95')
        finally:
            import os
            os.unlink(temp_path)


class TestXmlExtractorNFSeSigISS(unittest.TestCase):
    """Testa extração de NFS-e no formato SigISS (municipal)."""

    def setUp(self):
        self.extractor = XmlExtractor()

    def _create_sigiss_xml(self, **kwargs) -> str:
        """Cria XML de NFS-e SigISS para testes."""
        defaults = {
            'prefeitura': 'Marília',
            'inscricao_prestador': '48390',
            'cnpj_prestador': '13863575000180',
            'numero_nfe': '10251',
            'serie': '1',
            'codigo_verificacao': 'UI3N1M60',
            'data_emissao': '2025-09-06',
            'razao_social_prestador': 'INTERFOCUS TECNOLOGIA LTDA',
            'status': 'Ativa',
            'valor_servicos': '54.54',
            'valor_iss': '1.09',
            'aliquota': '2.00',
            'cnpj_tomador': '01766744000346',
            'razao_social_tomador': 'RBC - REDE BRASILEIRA DE COMUNICAÇÃO LTDA',
            'discriminacao': 'Serviço de intermediação de API',
        }
        defaults.update(kwargs)

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<NFe>
    <Prefeitura>{defaults['prefeitura']}</Prefeitura>
    <InscricaoPrestador>{defaults['inscricao_prestador']}</InscricaoPrestador>
    <CPFCNPJPrestador><CNPJ>{defaults['cnpj_prestador']}</CNPJ></CPFCNPJPrestador>
    <ChaveNFe>
        <NumeroNFe>{defaults['numero_nfe']}</NumeroNFe>
        <SerieNFe>{defaults['serie']}</SerieNFe>
        <CodigoVerificacao>{defaults['codigo_verificacao']}</CodigoVerificacao>
        <DataEmissaoNFe>{defaults['data_emissao']}</DataEmissaoNFe>
    </ChaveNFe>
    <RazaoSocialPrestador>{defaults['razao_social_prestador']}</RazaoSocialPrestador>
    <StatusNFe>{defaults['status']}</StatusNFe>
    <TributacaoNFe>Tributado no Prestador</TributacaoNFe>
    <ValorServicos>{defaults['valor_servicos']}</ValorServicos>
    <ValorBase>{defaults['valor_servicos']}</ValorBase>
    <AliquotaServicos>{defaults['aliquota']}</AliquotaServicos>
    <ValorISS>{defaults['valor_iss']}</ValorISS>
    <ValorIR>0.00</ValorIR>
    <ValorINSS>0.00</ValorINSS>
    <ValorCSLL>0.00</ValorCSLL>
    <CPFCNPJTomador><CPF>{defaults['cnpj_tomador']}</CPF></CPFCNPJTomador>
    <RazaoSocialTomador>{defaults['razao_social_tomador']}</RazaoSocialTomador>
    <Discriminacao>{defaults['discriminacao']}</Discriminacao>
</NFe>'''

    def test_extract_nfse_sigiss_success(self):
        """Extrai dados de NFS-e SigISS com sucesso."""
        xml_content = self._create_sigiss_xml()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            self.assertEqual(result.doc_type, 'NFSE_SIGISS')
            self.assertIsInstance(result.document, InvoiceData)

            doc = result.document
            self.assertEqual(doc.numero_nota, '10251')
            self.assertEqual(doc.data_emissao, '2025-09-06')
            self.assertEqual(doc.cnpj_prestador, '13.863.575/0001-80')
            self.assertEqual(doc.fornecedor_nome, 'INTERFOCUS TECNOLOGIA LTDA')
            self.assertEqual(doc.valor_total, 54.54)
            self.assertEqual(doc.valor_iss, 1.09)
        finally:
            Path(temp_path).unlink()

    def test_extract_nfse_sigiss_with_retencoes(self):
        """Extrai NFS-e SigISS com valores de retenções."""
        xml_content = self._create_sigiss_xml(
            valor_servicos='1000.00',
            valor_iss='50.00',
        )
        # Adiciona retenções manualmente
        xml_content = xml_content.replace(
            '<ValorIR>0.00</ValorIR>',
            '<ValorIR>15.00</ValorIR>'
        ).replace(
            '<ValorINSS>0.00</ValorINSS>',
            '<ValorINSS>11.00</ValorINSS>'
        ).replace(
            '<ValorCSLL>0.00</ValorCSLL>',
            '<ValorCSLL>10.00</ValorCSLL>'
        )

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            doc = result.document
            self.assertEqual(doc.valor_total, 1000.0)
            self.assertEqual(doc.valor_iss, 50.0)
            self.assertEqual(doc.valor_ir, 15.0)
            self.assertEqual(doc.valor_inss, 11.0)
            self.assertEqual(doc.valor_csll, 10.0)
        finally:
            Path(temp_path).unlink()

    def test_extract_nfse_sigiss_formats_cnpj(self):
        """Verifica que CNPJ é formatado corretamente no formato SigISS."""
        xml_content = self._create_sigiss_xml(cnpj_prestador='12345678000195')

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            self.assertEqual(result.document.cnpj_prestador, '12.345.678/0001-95')
        finally:
            Path(temp_path).unlink()

    def test_extract_nfse_sigiss_raw_data(self):
        """Verifica dados brutos extraídos do formato SigISS."""
        xml_content = self._create_sigiss_xml()

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertTrue(result.success)
            self.assertIn('codigo_verificacao', result.raw_data)
            self.assertEqual(result.raw_data['codigo_verificacao'], 'UI3N1M60')
            self.assertIn('tomador_nome', result.raw_data)
            self.assertEqual(result.raw_data['tomador_nome'], 'RBC - REDE BRASILEIRA DE COMUNICAÇÃO LTDA')
        finally:
            Path(temp_path).unlink()


class TestXmlExtractorHelpers(unittest.TestCase):
    """Testa métodos auxiliares do extrator."""

    def setUp(self):
        self.extractor = XmlExtractor()

    def test_parse_date_iso_format(self):
        """Converte data ISO."""
        self.assertEqual(self.extractor._parse_date('2025-01-15'), '2025-01-15')

    def test_parse_date_iso_with_time(self):
        """Converte data ISO com horário."""
        self.assertEqual(self.extractor._parse_date('2025-01-15T10:30:00'), '2025-01-15')

    def test_parse_date_iso_with_timezone(self):
        """Converte data ISO com timezone."""
        self.assertEqual(self.extractor._parse_date('2025-01-15T10:30:00-03:00'), '2025-01-15')

    def test_parse_date_brazilian_format(self):
        """Converte data formato brasileiro."""
        self.assertEqual(self.extractor._parse_date('15/01/2025'), '2025-01-15')

    def test_parse_date_brazilian_format_with_dash(self):
        """Converte data formato brasileiro com hífen."""
        self.assertEqual(self.extractor._parse_date('15-01-2025'), '2025-01-15')

    def test_parse_date_none(self):
        """Retorna None para data vazia."""
        self.assertIsNone(self.extractor._parse_date(None))
        self.assertIsNone(self.extractor._parse_date(''))

    def test_parse_float_decimal_point(self):
        """Converte valor com ponto decimal."""
        self.assertEqual(self.extractor._parse_float('1500.50'), 1500.50)

    def test_parse_float_decimal_comma(self):
        """Converte valor com vírgula decimal (BR)."""
        self.assertEqual(self.extractor._parse_float('1500,50'), 1500.50)

    def test_parse_float_thousand_separator(self):
        """Converte valor com separador de milhar (BR)."""
        self.assertEqual(self.extractor._parse_float('1.500,50'), 1500.50)

    def test_parse_float_none(self):
        """Retorna None para valor vazio."""
        self.assertIsNone(self.extractor._parse_float(None))
        self.assertIsNone(self.extractor._parse_float(''))

    def test_format_cnpj(self):
        """Formata CNPJ corretamente."""
        self.assertEqual(
            self.extractor._format_cnpj('12345678000195'),
            '12.345.678/0001-95'
        )

    def test_format_cnpj_already_formatted(self):
        """Mantém CNPJ se já formatado (remove e reformata)."""
        result = self.extractor._format_cnpj('12.345.678/0001-95')
        self.assertEqual(result, '12.345.678/0001-95')

    def test_format_cnpj_invalid_length(self):
        """Retorna sem formatar se tamanho inválido."""
        self.assertEqual(self.extractor._format_cnpj('123'), '123')

    def test_format_cnpj_none(self):
        """Retorna None para CNPJ vazio."""
        self.assertIsNone(self.extractor._format_cnpj(None))

    def test_map_forma_pagamento_boleto(self):
        """Mapeia código 15 para BOLETO."""
        self.assertEqual(self.extractor._map_forma_pagamento('15'), 'BOLETO')

    def test_map_forma_pagamento_pix(self):
        """Mapeia código 17 para PIX."""
        self.assertEqual(self.extractor._map_forma_pagamento('17'), 'PIX')

    def test_map_forma_pagamento_unknown(self):
        """Mapeia código desconhecido."""
        self.assertEqual(self.extractor._map_forma_pagamento('99'), 'OUTROS')

    def test_extract_numero_pedido(self):
        """Extrai número do pedido do texto."""
        text = 'Referente ao Pedido: 12345 - Serviços de TI'
        self.assertEqual(self.extractor._extract_numero_pedido(text), '12345')

    def test_extract_numero_pedido_oc(self):
        """Extrai número da ordem de compra."""
        text = 'OC: 67890 aprovada em 01/01/2025'
        self.assertEqual(self.extractor._extract_numero_pedido(text), '67890')

    def test_extract_numero_pedido_not_found(self):
        """Retorna None se não encontrar pedido."""
        text = 'Serviços prestados conforme contrato.'
        self.assertIsNone(self.extractor._extract_numero_pedido(text))


class TestXmlExtractorErrors(unittest.TestCase):
    """Testa tratamento de erros."""

    def setUp(self):
        self.extractor = XmlExtractor()

    def test_file_not_found(self):
        """Retorna erro para arquivo inexistente."""
        result = self.extractor.extract('/caminho/inexistente/arquivo.xml')

        self.assertFalse(result.success)
        self.assertIn('não encontrado', result.error)

    def test_not_xml_file(self):
        """Retorna erro para arquivo não-XML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
            f.write('conteudo pdf')
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertFalse(result.success)
            self.assertIn('não é XML', result.error)
        finally:
            Path(temp_path).unlink()

    def test_invalid_xml_content(self):
        """Retorna erro para XML inválido."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write('<root><unclosed>')
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertFalse(result.success)
            # Pode retornar erro de parse ou de tipo não reconhecido
            self.assertTrue(
                'parse' in result.error.lower() or 'não reconhecido' in result.error.lower()
            )
        finally:
            Path(temp_path).unlink()

    def test_unrecognized_xml_type(self):
        """Retorna erro para XML não reconhecido."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write('<?xml version="1.0"?><root><data>test</data></root>')
            temp_path = f.name

        try:
            result = self.extractor.extract(temp_path)

            self.assertFalse(result.success)
            self.assertIn('não reconhecido', result.error)
        finally:
            Path(temp_path).unlink()


class TestExtractXmlFunction(unittest.TestCase):
    """Testa função utilitária extract_xml."""

    def test_extract_xml_convenience_function(self):
        """Testa função de conveniência."""
        xml_content = '''<?xml version="1.0"?>
<CompNfse>
    <Nfse>
        <InfNfse>
            <Numero>999</Numero>
            <PrestadorServico>
                <Cnpj>11111111000111</Cnpj>
                <RazaoSocial>Teste SA</RazaoSocial>
            </PrestadorServico>
            <Servico>
                <ValorServicos>1000.00</ValorServicos>
            </Servico>
        </InfNfse>
    </Nfse>
</CompNfse>'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        try:
            result = extract_xml(temp_path)

            self.assertTrue(result.success)
            self.assertEqual(result.document.numero_nota, '999')
        finally:
            Path(temp_path).unlink()


if __name__ == '__main__':
    unittest.main()
