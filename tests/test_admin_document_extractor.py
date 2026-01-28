"""
Teste do AdminDocumentExtractor - Extrator especializado para documentos administrativos.

Este script testa o funcionamento do AdminDocumentExtractor, incluindo:
1. Detecção de padrões administrativos vs. não-administrativos
2. Extração de dados específicos de diferentes tipos administrativos
3. Posicionamento correto na ordem de extratores
4. Casos reais identificados no relatório_lotes.csv

Princípios SOLID testados:
- SRP: O extrator só lida com documentos administrativos
- OCP: Pode ser estendido sem modificar extratores existentes
- LSP: Mantém compatibilidade com BaseExtractor
- ISP: Implementa apenas métodos necessários
- DIP: Depende de abstrações (BaseExtractor)

"""


import sys
from pathlib import Path

# Adicionar o diretório raiz ao path para importações
sys.path.insert(0, str(Path(__file__).parent.parent))

from extractors.admin_document import AdminDocumentExtractor
from core.extractors import EXTRACTOR_REGISTRY
from extractors.outros import OutrosExtractor
from extractors.nfse_generic import NfseGenericExtractor


def test_can_handle_patterns():
    """Testa a detecção de padrões administrativos no método can_handle()."""
    test_cases = [
        # (texto, esperado, descrição)
        # 1. Lembretes gentis
        ("LEMBRETE GENTIL: Vencimento de Fatura", True, "Lembrete administrativo"),
        ("lembrete gentil de vencimento", True, "Lembrete administrativo (minúsculas)"),
        # 2. Ordens de serviço/agendamento
        (
            "Sua ordem Equinix n.º 1-255425159203 foi agendada",
            True,
            "Ordem de serviço (Equinix)",
        ),
        ("ORDEM DE SERVIÇO Nº 12345", True, "Ordem de serviço"),
        ("Nº 1-255425159203 AGENDAMENTO", True, "Agendamento com número"),
        # 3. Distratos e rescisões
        ("Distrato - Speed Copy", True, "Distrato"),
        ("RESCISÃO CONTRATUAL", True, "Rescisão contratual"),
        ("RESCISÓRIO DO CONTRATO", True, "Rescisório"),
        # 4. Encerramentos e cancelamentos
        ("ENCERRAMENTO DE CONTRATO", True, "Encerramento de contrato"),
        (
            "SOLICITAÇÃO DE ENCERRAMENTO DE CONTRATO",
            True,
            "Solicitação de encerramento",
        ),
        ("CANCELAMENTO DE CONTRATO", True, "Cancelamento de contrato"),
        # 5. Notificações automáticas
        (
            "NOTIFICAÇÃO AUTOMÁTICA - Documento 000000135",
            True,
            "Notificação automática",
        ),
        ("DOCUMENTO 000011239 - NOTIFICAÇÃO", True, "Notificação com número"),
        # 6. Guias jurídicas/fiscais
        ("GUIA | Processo - Miralva Macedo Dias x CSC", True, "Guia jurídica"),
        ("GUIA | Execução Fiscal - Vale Telecom", True, "Guia fiscal"),
        ("GUIAS - CSC - Processo trabalhista", True, "Guias múltiplas"),
        # 7. Contratos (documentação)
        ("CONTRATO_SITE MASTER INTERNET", True, "Contrato site"),
        ("CONTRATO RENOVAÇÃO", True, "Contrato renovação"),
        ("MINUTA DE CONTRATO", True, "Minuta de contrato"),
        # 8. Invoices internacionais vazias
        ("December - 2025 Invoice for 6343 - ATIVE", True, "Invoice internacional"),
        ("January 2026 Invoice for 6342 - MOC", True, "Invoice internacional (Jan)"),
        # 9. Relatórios/planilhas
        (
            "RELATÓRIO DE FATURAMENTO JAN 26 - MASTER INTERNET",
            True,
            "Relatório de faturamento",
        ),
        ("PLANILHA DE CONFERÊNCIA", True, "Planilha de conferência"),
        # 10. Câmbio/programação TV
        ("CÂMBIO HBO RBC NOVEMBRO", True, "Câmbio HBO"),
        ("CAMBIO GLOBOSAT JANEIRO", True, "Câmbio GloboSat"),
        # 11. Condomínio
        (
            "ALVIM NOGUEIRA ( |601) - Boleto Vencimento (01/2026)",
            True,
            "Condomínio Alvim Nogueira",
        ),
        # 12. Reclamações
        ("COBRANÇA INDEVIDA 11/2025 - 4security", True, "Cobrança indevida"),
        ("COBRANCA INDEVIDA DE TARIFAS", True, "Cobrança indevida (sem acento)"),
        # 13. Reembolsos e tarifas internas
        (
            "REEMBOLSO DE TARIFAS CSC - 18/12/2025 a 31/12/2025",
            True,
            "Reembolso interno",
        ),
        (
            "TARIFAS CSC - Acerto MOC - apuração até 31/12/2025",
            True,
            "Tarifas internas",
        ),
        # 14. Processos e execuções
        ("PROCESSO FISCAL", True, "Processo fiscal"),
        ("EXECUÇÃO JUDICIAL", True, "Execução judicial"),
        # 15. Anuidades
        ("ANUIDADE CREA 2026", True, "Anuidade CREA"),
        ("ANUIDADE OAB - 2026", True, "Anuidade OAB"),
    ]

    for text, expected, description in test_cases:
        result = AdminDocumentExtractor.can_handle(text)
        assert result == expected, (
            f"Falha em: {description}\n"
            f"Texto: '{text}'\n"
            f"Esperado: {expected}, Obtido: {result}"
        )


def test_non_admin_patterns():
    """Testa que documentos não-administrativos NÃO são detectados."""
    non_admin_cases = [
        # Faturas normais
        ("CEMIG FATURA ONLINE - 214687921", False, "Fatura de energia"),
        ("FATURA TELEFÔNICA - R$ 150,00", False, "Fatura telefônica"),
        # Boletos normais
        ("Boleto Bancário - R$ 150,00", False, "Boleto normal"),
        (
            "75691.40330 12345.678901 98765.432101 1 12345678901234",
            False,
            "Linha digitável",
        ),
        # NFSe normais
        ("NFS-e 00012345 - R$ 1.234,56", False, "NFSe com valor"),
        (
            "NOTA FISCAL DE SERVIÇO ELETRÔNICA - Valor: R$ 500,00",
            False,
            "NFSe completa",
        ),
        # DANFEs normais
        ("DANFE 123456789 - Valor R$ 500,00", False, "DANFE normal"),
        ("NOTA FISCAL ELETRÔNICA - CHAVE: 1234...", False, "NF-e"),
        # Outros documentos financeiros
        ("COMPROVANTE DE PAGAMENTO - R$ 100,00", False, "Comprovante de pagamento"),
        ("RECIBO - Valor: R$ 50,00", False, "Recibo com valor"),
        # E-mails com valores e vencimentos
        (
            "Vencimento: 15/01/2026 - Valor: R$ 1.000,00",
            False,
            "E-mail com vencimento e valor",
        ),
        ("Fatura vencida - R$ 2.500,00", False, "Fatura vencida"),
    ]

    for text, expected, description in non_admin_cases:
        result = AdminDocumentExtractor.can_handle(text)
        assert result == expected, (
            f"Falha em: {description}\n"
            f"Texto: '{text[:80]}...'\n"
            f"Esperado: {expected}, Obtido: {result}"
        )


def test_extract_method():
    """Testa a extração de dados do método extract()."""
    test_documents = [
        # Documento 1: Lembrete gentil
        (
            """
        LEMBRE GENTIL: Vencimento de Fatura

        De: /CNPJ:Ê - CNPJ 20.609.743/0004-13
        Para: Financeiro CSC

        Este é um lembrete amigável de que sua fatura vencerá em 15/01/2026.

        Data: 10/01/2026
        """,
            "LEMBRETE",
            "Lembrete administrativo",
            None,
        ),
        # Documento 2: Ordem de serviço Equinix
        (
            """
        Sua ordem Equinix n.º 1-255425159203 foi agendada com sucesso

        De: Equinix Orders
        Para: CSC Gestão Integrada S/A

        Ordem: 1-255425159203
        Data de agendamento: 20/01/2026
        Serviço: Instalação de circuito
        """,
            "ORDEM_SERVICO",
            "Ordem de serviço/agendamento",
            "1-255425159203",
        ),
        # Documento 3: Distrato
        (
            """
        DISTRATO CONTRATUAL

        Contratante: CSC Gestão Integrada S/A
        Contratada: SPEEDY COPY SOLUÇÕES EM COPIADORAS LTDA
        CNPJ: 12.345.678/0001-90

        Pelo presente instrumento, as partes resolvem de comum acordo
        rescindir o contrato de locação de equipamentos.

        Data: 05/01/2026
        """,
            "DISTRATO",
            "Documento de distrato",
            None,
        ),
        # Documento 4: Contrato com valor
        (
            """
        CONTRATO_SITE MASTER INTERNET

        Contrato de prestação de serviços de internet
        Valor do Contrato: R$ 20.000,00
        Vigência: 12 meses
        Fornecedor: MASTER INTERNET TELECOMUNICAÇÕES LTDA
        CNPJ: 98.765.432/0001-10

        Data de assinatura: 15/12/2025
        Vencimento: 15/01/2026
        """,
            "CONTRATO",
            "Documento de contrato",
            20000.0,
        ),
        # Documento 5: Notificação automática
        (
            """
        NOTIFICAÇÃO AUTOMÁTICA

        Documento: 000000135
        Sistema: Ufinet
        Data: 18/01/2026

        Esta é uma notificação automática do sistema.
        Nenhuma ação é necessária.
        """,
            "NOTIFICACAO",
            "Notificação automática",
            "000000135",
        ),
    ]

    extractor = AdminDocumentExtractor()

    for (
        text,
        expected_subtype,
        expected_admin_type,
        expected_value_or_num,
    ) in test_documents:
        result = extractor.extract(text)

        # Verificar campos básicos
        assert result["tipo_documento"] == "OUTRO", (
            f"tipo_documento deveria ser 'OUTRO', mas é {result['tipo_documento']}"
        )
        assert result["subtipo"] == expected_subtype, (
            f"subtipo deveria ser '{expected_subtype}', mas é {result['subtipo']}"
        )
        assert result["admin_type"] == expected_admin_type, (
            f"admin_type deveria ser '{expected_admin_type}', mas é {result.get('admin_type')}"
        )

        # Verificar valor ou número do documento conforme esperado
        if isinstance(expected_value_or_num, (int, float)):
            assert "valor_total" in result, "Campo 'valor_total' não encontrado"
            assert abs(result["valor_total"] - expected_value_or_num) < 0.01, (
                f"valor_total deveria ser {expected_value_or_num}, mas é {result['valor_total']}"
            )
        elif isinstance(expected_value_or_num, str):
            assert "numero_documento" in result, (
                "Campo 'numero_documento' não encontrado"
            )
            assert result["numero_documento"] == expected_value_or_num, (
                f"numero_documento deveria ser '{expected_value_or_num}', mas é {result['numero_documento']}"
            )


def test_extractor_order():
    """Testa que o AdminDocumentExtractor está na posição correta no registro."""
    # Encontrar posições dos extratores relevantes
    admin_idx = None
    _nfse_idx = None
    outros_idx = None

    for i, extractor_class in enumerate(EXTRACTOR_REGISTRY):
        class_name = extractor_class.__name__
        if class_name == "AdminDocumentExtractor":
            admin_idx = i
        elif class_name == "NfseGenericExtractor":
            _nfse_idx = i
        elif class_name == "OutrosExtractor":
            outros_idx = i

    # AdminDocumentExtractor deve existir no registro
    assert admin_idx is not None, "AdminDocumentExtractor não encontrado no registro"

    # AdminDocumentExtractor deve vir ANTES de OutrosExtractor
    assert outros_idx is not None, "OutrosExtractor não encontrado no registro"
    assert admin_idx < outros_idx, (
        f"AdminDocumentExtractor (posição {admin_idx}) deve vir antes de "
        f"OutrosExtractor (posição {outros_idx}) para capturar documentos administrativos"
    )

    # Nota: AdminDocumentExtractor vem antes de OutrosExtractor para capturar
    # documentos administrativos antes que sejam classificados como "outros"
    # A ordem em relação a extratores fiscais não é crítica, pois o AdminDocumentExtractor
    # tem lógica própria para rejeitar documentos fiscais em can_handle()


def test_real_cases_from_csv():
    """Testa casos reais extraídos do relatório_lotes.csv."""
    # Casos simulados baseados no CSV
    real_cases = [
        # (texto, esperado, descrição)
        ("LEMBRETE GENTIL: Vencimento de Fatura", True, "Lembrete administrativo"),
        ("Sua ordem Equinix n.º 1-255425159203 agendada", True, "Ordem de serviço"),
        ("GUIA | Processo - Miralva Macedo Dias x CSC", True, "Guia jurídica"),
        ("COBRANÇA INDEVIDA 11/2025 - 4security", True, "Cobrança indevida"),
        ("December - 2025 Invoice for 6343 - ATIVE", True, "Invoice internacional"),
        ("CONTRATO_SITE MASTER INTERNET", True, "Contrato"),
        (
            "TARIFAS CSC - Acerto MOC - apuração até 31/12/2025",
            True,
            "Tarifas internas",
        ),
        # Casos que NÃO devem ser capturados (são faturas/boletos reais)
        ("CEMIG FATURA ONLINE - 214687921", False, "Fatura de energia real"),
        ("NFS-e + Boleto No 3494", False, "NFSe com boleto"),
        ("Boleto ACIV", False, "Boleto real"),
        ("Sua fatura chegou", False, "Fatura genérica"),
        ("Nota Fiscal Eletrônica Nº 103977", False, "NFSe real"),
    ]

    for text, expected, description in real_cases:
        result = AdminDocumentExtractor.can_handle(text)
        assert result == expected, (
            f"Falha em caso real: {description}\n"
            f"Texto: '{text[:60]}...'\n"
            f"Esperado: {expected}, Obtido: {result}"
        )


def test_priority_over_other_extractors():
    """Testa que AdminDocumentExtractor tem prioridade sobre OutrosExtractor."""
    extractor_admin = AdminDocumentExtractor()
    extractor_outros = OutrosExtractor()
    extractor_nfse = NfseGenericExtractor()

    # Documento administrativo claro - Admin deve aceitar, Outros pode aceitar também,
    # mas o sistema deve priorizar Admin por estar antes no registro
    admin_text = "LEMBRETE GENTIL: Vencimento de Fatura"

    admin_can_handle = extractor_admin.can_handle(admin_text)
    _outros_can_handle = extractor_outros.can_handle(admin_text)
    nfse_can_handle = extractor_nfse.can_handle(admin_text)

    assert admin_can_handle, (
        "AdminDocumentExtractor deveria aceitar documento administrativo"
    )
    assert not nfse_can_handle, (
        "NfseGenericExtractor NÃO deveria aceitar documento administrativo"
    )

    # OutrosExtractor pode ou não aceitar, mas Admin deve ter prioridade
    # por estar antes no registro (testado em test_extractor_order)

    # Documento de locação - Outros deve aceitar, Admin NÃO
    locacao_text = "DEMONSTRATIVO DE LOCAÇÃO\nValor total a pagar: R$ 1.500,00"

    admin_can_handle_loc = extractor_admin.can_handle(locacao_text)
    outros_can_handle_loc = extractor_outros.can_handle(locacao_text)
    nfse_can_handle_loc = extractor_nfse.can_handle(locacao_text)

    assert not admin_can_handle_loc, (
        "AdminDocumentExtractor NÃO deveria aceitar locação"
    )
    assert outros_can_handle_loc, "OutrosExtractor deveria aceitar locação"
    assert not nfse_can_handle_loc, "NfseGenericExtractor NÃO deveria aceitar locação"

    # Documento fiscal - NFSe deve aceitar, Admin NÃO
    nfse_text = "NOTA FISCAL DE SERVIÇO ELETRÔNICA Nº 12345\nValor: R$ 500,00"

    admin_can_handle_nfse = extractor_admin.can_handle(nfse_text)
    outros_can_handle_nfse = extractor_outros.can_handle(nfse_text)
    nfse_can_handle_nfse = extractor_nfse.can_handle(nfse_text)

    assert not admin_can_handle_nfse, "AdminDocumentExtractor NÃO deveria aceitar NFSe"
    assert not outros_can_handle_nfse, "OutrosExtractor NÃO deveria aceitar NFSe"
    assert nfse_can_handle_nfse, "NfseGenericExtractor deveria aceitar NFSe"
