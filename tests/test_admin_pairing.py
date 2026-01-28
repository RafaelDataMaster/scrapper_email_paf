"""
Teste da integração entre detecção de documentos administrativos e pareamento.

Este script testa se os avisos de documento administrativo gerados pelo
CorrelationService são corretamente propagados para os DocumentPair
gerados pelo DocumentPairingService.
"""

import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.batch_result import BatchResult
from core.correlation_service import CorrelationService
from core.document_pairing import DocumentPairingService
from core.models import OtherDocumentData


def test_admin_detection_in_pairing():
    """Testa se documentos administrativos têm o aviso correto nos DocumentPair."""
    pairing_service = DocumentPairingService()
    correlation_service = CorrelationService()

    # Casos de teste: assuntos administrativos que DEVEM gerar aviso
    test_cases = [
        # (assunto, descrição esperada)
        ("Lembrete Gentil: Vencimento de Fatura", "Lembrete administrativo"),
        (
            "Sua ordem Equinix n.º 1-255425159203 agendada com sucesso",
            "Ordem de serviço/agendamento",
        ),
        ("GUIA | Processo - Miralva Macedo Dias x CSC", "Guia jurídica/fiscal"),
        ("Cobrança Indevida 11/2025 - 4security", "Reclamação de cobrança"),
        ("December - 2025 Invoice for 6343 - ATIVE", "Invoice internacional"),
        ("CONTRATO_SITE MASTER INTERNET", "Documento de contrato"),
        (
            "Tarifas CSC - Acerto MOC - apuração até 31/12/2025",
            "Documento de tarifas internas",
        ),
    ]

    # Assuntos que NÃO devem gerar aviso (cobranças reais)
    normal_cases = [
        "CEMIG FATURA ONLINE - 214687921",
        "NFS-e + Boleto No 3494",
        "Boleto ACIV",
        "Sua fatura chegou",
        "Nota Fiscal Eletrônica Nº 103977",
    ]

    admin_ok = 0
    _admin_fail = 0

    for subject, expected_desc in test_cases:
        # Cria batch com documento fictício
        batch = BatchResult(batch_id=f"test_admin_{subject[:20]}")
        batch.email_subject = subject

        # Adiciona um documento "outro" com valor 0 (típico de documentos administrativos)
        doc = OtherDocumentData(
            arquivo_origem=f"test_doc_{admin_ok}.pdf", valor_total=0.0
        )
        batch.add_document(doc)

        # Aplica correlação
        correlation_result = correlation_service.correlate(batch)
        batch.correlation_result = correlation_result

        # Gera pairs via DocumentPairingService
        pairs = pairing_service.pair_documents(batch)

        # Verifica se o pair contém o aviso
        assert pairs, f"Nenhum pair gerado para assunto: {subject}"
        pair = pairs[0]

        has_admin_warning = (
            pair.divergencia and "POSSÍVEL DOCUMENTO ADMINISTRATIVO" in pair.divergencia
        )
        correlation_has_warning = (
            correlation_result.divergencia
            and "POSSÍVEL DOCUMENTO ADMINISTRATIVO" in correlation_result.divergencia
        )

        assert has_admin_warning, f"Pair não tem aviso administrativo para: {subject}"
        assert correlation_has_warning, (
            f"Correlation não tem aviso administrativo para: {subject}"
        )

        # Extrai descrição para verificar se é a esperada
        match = re.search(
            r"POSSÍVEL DOCUMENTO ADMINISTRATIVO - ([^\]]+)", pair.divergencia or ""
        )
        actual_desc = match.group(1) if match else ""
        assert expected_desc in actual_desc, (
            f"Descrição diferente para {subject}: "
            f"esperado '{expected_desc}', obtido '{actual_desc}'"
        )

        admin_ok += 1

    assert admin_ok == len(test_cases), (
        f"{admin_ok}/{len(test_cases)} casos administrativos passaram"
    )

    normal_ok = 0
    _normal_fail = 0

    for subject in normal_cases:
        # Cria batch com documento normal
        batch = BatchResult(batch_id=f"test_normal_{subject[:20]}")
        batch.email_subject = subject

        # Adiciona um documento com valor (cobrança real)
        doc = OtherDocumentData(
            arquivo_origem=f"normal_doc_{normal_ok}.pdf", valor_total=150.75
        )
        batch.add_document(doc)

        # Aplica correlação
        correlation_result = correlation_service.correlate(batch)
        batch.correlation_result = correlation_result

        # Gera pairs
        pairs = pairing_service.pair_documents(batch)

        # Verifica se NÃO tem aviso administrativo
        has_admin_warning = False
        if pairs and pairs[0].divergencia:
            has_admin_warning = (
                "POSSÍVEL DOCUMENTO ADMINISTRATIVO" in pairs[0].divergencia
            )

        correlation_has_warning = (
            correlation_result.divergencia
            and "POSSÍVEL DOCUMENTO ADMINISTRATIVO" in correlation_result.divergencia
        )

        assert not has_admin_warning, f"Falso positivo em pair para: {subject}"
        assert not correlation_has_warning, (
            f"Falso positivo em correlation para: {subject}"
        )

        normal_ok += 1

    assert normal_ok == len(normal_cases), (
        f"{normal_ok}/{len(normal_cases)} casos normais passaram"
    )


def test_admin_warning_format_in_csv():
    """Testa se o aviso administrativo está formatado corretamente para exportação CSV."""
    pairing_service = DocumentPairingService()
    correlation_service = CorrelationService()

    # Testa um caso específico
    batch = BatchResult(batch_id="test_format")
    batch.email_subject = "Lembrete Gentil: Vencimento de Fatura"
    batch.add_document(
        OtherDocumentData(arquivo_origem="test_lembrete.pdf", valor_total=0.0)
    )

    correlation_result = correlation_service.correlate(batch)
    batch.correlation_result = correlation_result

    pairs = pairing_service.pair_documents(batch)

    assert pairs, "Nenhum pair gerado"
    pair = pairs[0]

    # Verifica se o aviso está presente
    assert (
        pair.divergencia and "POSSÍVEL DOCUMENTO ADMINISTRATIVO" in pair.divergencia
    ), "Aviso administrativo não encontrado no pair"
    assert (
        correlation_result.divergencia
        and "POSSÍVEL DOCUMENTO ADMINISTRATIVO" in correlation_result.divergencia
    ), "Aviso administrativo não encontrado no correlation"

    # Verifica se o formato está correto para exportação CSV
    summary = pair.to_summary()
    assert "divergencia" in summary, "Campo divergencia não encontrado no summary"
    assert (
        summary["divergencia"]
        and "POSSÍVEL DOCUMENTO ADMINISTRATIVO" in summary["divergencia"]
    ), "Aviso administrativo não presente no CSV summary"
