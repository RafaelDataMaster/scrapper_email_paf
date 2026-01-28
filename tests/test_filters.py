"""
Testes para o módulo core/filters.py

Testa a lógica de filtragem de e-mails incluindo:
- Regra de Ouro (anexos sempre processados)
- Blacklist de assuntos
- Whitelist de assuntos
- Blacklist de remetentes
- Whitelist de remetentes
- Combinações de regras

Autor: Sistema de Ingestão
Versão: 1.0.0
"""

import pytest

from core.filters import (
    EmailFilter,
    FilterDecision,
    FilterResult,
    get_default_filter,
    get_filter_decision,
    should_process_email,
)


class TestFilterDecision:
    """Testes para o enum FilterDecision."""

    def test_all_decisions_exist(self):
        """Verifica que todas as decisões esperadas existem."""
        assert FilterDecision.PROCESS.value == "PROCESS"
        assert FilterDecision.SKIP_BLACKLIST.value == "SKIP_BLACKLIST"
        assert FilterDecision.SKIP_NO_CONTENT.value == "SKIP_NO_CONTENT"
        assert FilterDecision.SKIP_NO_SUBJECT_MATCH.value == "SKIP_NO_SUBJECT_MATCH"
        assert FilterDecision.SKIP_SENDER_BLACKLIST.value == "SKIP_SENDER_BLACKLIST"


class TestFilterResult:
    """Testes para a dataclass FilterResult."""

    def test_should_process_true(self):
        """Testa que PROCESS retorna should_process=True."""
        result = FilterResult(
            decision=FilterDecision.PROCESS,
            reason="Teste",
            subject="Nota Fiscal"
        )
        assert result.should_process is True

    def test_should_process_false_for_skip(self):
        """Testa que decisões SKIP retornam should_process=False."""
        for decision in [
            FilterDecision.SKIP_BLACKLIST,
            FilterDecision.SKIP_NO_CONTENT,
            FilterDecision.SKIP_NO_SUBJECT_MATCH,
            FilterDecision.SKIP_SENDER_BLACKLIST,
        ]:
            result = FilterResult(decision=decision, reason="Teste")
            assert result.should_process is False

    def test_str_representation(self):
        """Testa representação em string."""
        result = FilterResult(
            decision=FilterDecision.PROCESS,
            reason="E-mail possui anexo",
            subject="NF-e"
        )
        assert "PROCESS" in str(result)
        assert "anexo" in str(result)


class TestEmailFilterGoldenRule:
    """Testes para a Regra de Ouro: anexo válido = SEMPRE processar."""

    def test_email_with_pdf_attachment_always_processed(self):
        """E-mail com anexo PDF deve SEMPRE ser processado."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Feliz Natal",  # Blacklist, mas anexo tem prioridade
            "has_attachment": True,
        })
        assert result.should_process is True
        assert result.decision == FilterDecision.PROCESS

    def test_email_with_attachments_list(self):
        """E-mail com lista de anexos válidos deve ser processado."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Newsletter",  # Blacklist
            "attachments": ["nota.pdf", "danfe.xml"],
        })
        assert result.should_process is True

    def test_email_with_only_images_not_processed(self):
        """E-mail com apenas imagens não deve ser processado como anexo válido."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Fotos do evento",
            "attachments": ["foto1.jpg", "foto2.png", "logo.gif"],
        })
        # Sem anexo válido, vai para outras regras
        assert result.decision != FilterDecision.PROCESS or "anexo" not in result.reason.lower()


class TestEmailFilterSubjectBlacklist:
    """Testes para a blacklist de assuntos."""

    @pytest.mark.parametrize("subject", [
        "Feliz Natal!",
        "feliz natal e ano novo",
        "Comunicado Importante",
        "COMUNICADO: Horário de funcionamento",
        "Horário de Funcionamento - Janeiro",
        "Expediente de fim de ano",
        "Newsletter Dezembro 2024",
        "Confira nossas novidades",
        "Promoção imperdível!",
        "Oferta especial",
        "Inscreva-se já",
        "Pré-cobrança do mês",
        "RE: RE: Discussão sobre ajuste de NF",
        "Distrato de contrato",
    ])
    def test_blacklist_subjects_skipped(self, subject):
        """Assuntos na blacklist devem ser ignorados (sem anexo)."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": subject,
            "has_attachment": False,
            "has_links_nfe": True,  # Mesmo com link
        })
        assert result.decision == FilterDecision.SKIP_BLACKLIST

    def test_blacklist_with_custom_pattern(self):
        """Testa adição de padrão customizado à blacklist."""
        email_filter = EmailFilter(custom_blacklist=[r"\bspam\b"])
        result = email_filter.should_process_email({
            "subject": "Isso é SPAM puro",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.decision == FilterDecision.SKIP_BLACKLIST


class TestEmailFilterSubjectWhitelist:
    """Testes para a whitelist de assuntos."""

    @pytest.mark.parametrize("subject", [
        "Nota Fiscal Eletrônica",
        "NF-e de venda",
        "NFSe disponível",
        "DANFE - Pedido 12345",
        "Sua Fatura",
        "Boleto para pagamento",
        "Cobrança vencida",
        "Pagamento pendente",
        "Renovação de contrato",
        "Mensalidade de março",
        "Conta de energia - CEMIG",
        "Faturamento do mês",
    ])
    def test_whitelist_subjects_processed_with_indicators(self, subject):
        """Assuntos na whitelist + indicadores devem ser processados."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": subject,
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.should_process is True
        assert result.decision == FilterDecision.PROCESS

    def test_whitelist_without_indicators_skipped(self):
        """Assunto na whitelist SEM indicadores deve ser ignorado."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Nota Fiscal disponível",
            "has_attachment": False,
            "has_links_nfe": False,
            "has_verification_code": False,
        })
        assert result.decision == FilterDecision.SKIP_NO_CONTENT

    def test_custom_whitelist_pattern(self):
        """Testa adição de padrão customizado à whitelist."""
        email_filter = EmailFilter(custom_whitelist=[r"\brecibo\b"])
        result = email_filter.should_process_email({
            "subject": "Recibo de pagamento",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.should_process is True


class TestEmailFilterSenderBlacklist:
    """Testes para a blacklist de remetentes."""

    @pytest.mark.parametrize("sender", [
        "noreply@mail.mailchimp.com",
        "campaign@sendgrid.net",
        "marketing@email.hubspot.com",
        "newsletter@empresa.com.br",
        "marketing@empresa.com.br",
        "promocoes@loja.com.br",
        "ofertas@ecommerce.com",
        "notifications@github.com",
        "noreply@linkedin.com",
        "notification@facebookmail.com",
        "support@zendesk.com",
    ])
    def test_sender_blacklist_skipped(self, sender):
        """Remetentes na blacklist devem ser ignorados (sem anexo)."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Sua Fatura",  # Whitelist, mas sender tem prioridade
            "sender_address": sender,
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.decision == FilterDecision.SKIP_SENDER_BLACKLIST

    def test_sender_blacklist_ignored_when_has_attachment(self):
        """Anexo válido ignora blacklist de remetente."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Newsletter",
            "sender_address": "newsletter@mailchimp.com",
            "has_attachment": True,
        })
        assert result.should_process is True

    def test_custom_sender_blacklist(self):
        """Testa adição de padrão customizado à blacklist de sender."""
        email_filter = EmailFilter(sender_blacklist=[r"@spam\.example\.com$"])
        result = email_filter.should_process_email({
            "subject": "Fatura importante",
            "sender_address": "billing@spam.example.com",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.decision == FilterDecision.SKIP_SENDER_BLACKLIST


class TestEmailFilterSenderWhitelist:
    """Testes para a whitelist de remetentes."""

    @pytest.mark.parametrize("sender", [
        "nfe@fazenda.gov.br",
        "nfse@prefeitura.sp.gov.br",
        "faturamento@omie.com.br",
        "cobranca@bling.com.br",
        "nfe@tiny.com.br",
        "financeiro@contaazul.com",
        "nfse@enotas.com.br",
        "fatura@cemig.com.br",
        "cobranca@vivo.com.br",
        "faturamento@empresa.com.br",
        "boleto@fornecedor.com.br",
        "notafiscal@parceiro.com.br",
    ])
    def test_sender_whitelist_processed_with_indicators(self, sender):
        """Remetentes na whitelist + indicadores devem ser processados."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Assunto genérico",  # Não está na whitelist de assunto
            "sender_address": sender,
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.should_process is True
        assert "remetente confiável" in result.reason.lower()

    def test_sender_whitelist_without_indicators_skipped(self):
        """Remetente whitelist SEM indicadores deve ser ignorado."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Comunicação geral",
            "sender_address": "faturamento@empresa.com.br",
            "has_attachment": False,
            "has_links_nfe": False,
            "has_verification_code": False,
        })
        assert result.decision == FilterDecision.SKIP_NO_CONTENT

    def test_custom_sender_whitelist(self):
        """Testa adição de padrão customizado à whitelist de sender."""
        email_filter = EmailFilter(sender_whitelist=[r"@parceiro-nf\.com\.br$"])
        result = email_filter.should_process_email({
            "subject": "Documento disponível",
            "sender_address": "envio@parceiro-nf.com.br",
            "has_attachment": False,
            "has_verification_code": True,
        })
        assert result.should_process is True


class TestEmailFilterIndicators:
    """Testes para indicadores (links e códigos de verificação)."""

    def test_link_nfe_with_whitelist_subject(self):
        """Link de NF-e + assunto whitelist = processar."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Sua Nota Fiscal",
            "has_attachment": False,
            "has_links_nfe": True,
            "has_verification_code": False,
        })
        assert result.should_process is True
        assert "link" in result.reason.lower()

    def test_verification_code_with_whitelist_subject(self):
        """Código de verificação + assunto whitelist = processar."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Boleto disponível",
            "has_attachment": False,
            "has_links_nfe": False,
            "has_verification_code": True,
        })
        assert result.should_process is True
        assert "código" in result.reason.lower()

    def test_no_indicators_skipped(self):
        """Sem indicadores deve ser ignorado."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Nota Fiscal",  # Whitelist
            "has_attachment": False,
            "has_links_nfe": False,
            "has_verification_code": False,
        })
        assert result.decision == FilterDecision.SKIP_NO_CONTENT


class TestEmailFilterCombinations:
    """Testes para combinações complexas de regras."""

    def test_indicators_but_no_subject_match(self):
        """Indicadores + assunto irrelevante = ignorar."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Evolua | Confira o nosso horário",
            "has_attachment": False,
            "has_links_nfe": True,  # Tem link
        })
        # Deve ser ignorado por assunto não corresponder
        assert result.decision in [
            FilterDecision.SKIP_BLACKLIST,
            FilterDecision.SKIP_NO_SUBJECT_MATCH
        ]

    def test_blacklist_takes_precedence_over_whitelist(self):
        """Blacklist tem prioridade sobre whitelist de assunto."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Newsletter: Sua Fatura de Natal",  # Mistura
            "has_attachment": False,
            "has_links_nfe": True,
        })
        # Newsletter é blacklist
        assert result.decision == FilterDecision.SKIP_BLACKLIST

    def test_sender_whitelist_plus_subject_whitelist(self):
        """Sender whitelist + subject whitelist = processar com ambas razões."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Nota Fiscal disponível",
            "sender_address": "faturamento@fornecedor.com.br",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.should_process is True
        # Deve mencionar ambos
        assert "remetente" in result.reason.lower() or "assunto" in result.reason.lower()

    def test_strict_mode(self):
        """Testa modo estrito (para implementação futura)."""
        email_filter = EmailFilter(strict_mode=True)
        # Por enquanto strict_mode não tem efeito diferente
        result = email_filter.should_process_email({
            "subject": "Fatura",
            "has_attachment": True,
        })
        assert result.should_process is True


class TestEmailFilterAttachmentValidation:
    """Testes para validação de anexos."""

    @pytest.mark.parametrize("attachments,expected", [
        (["nota.pdf"], True),
        (["danfe.xml"], True),
        (["arquivos.zip"], True),
        (["backup.rar"], True),
        (["docs.7z"], True),
        (["NOTA.PDF"], True),  # Case insensitive
        (["foto.jpg", "logo.png"], False),
        (["documento.docx", "planilha.xlsx"], False),
        ([], False),
    ])
    def test_attachment_validation(self, attachments, expected):
        """Testa validação de tipos de anexo."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Documento",
            "attachments": attachments,
        })

        if expected:
            assert result.should_process is True
            assert "anexo" in result.reason.lower()
        else:
            # Sem anexo válido, vai para outras regras
            assert "anexo" not in result.reason.lower() or not result.should_process


class TestEmailFilterHelperFunctions:
    """Testes para funções auxiliares do módulo."""

    def test_should_process_email_function(self):
        """Testa função standalone should_process_email."""
        metadata = {
            "subject": "Nota Fiscal",
            "has_attachment": True,
        }
        result = should_process_email(metadata)
        assert result is True

    def test_get_filter_decision_function(self):
        """Testa função standalone get_filter_decision."""
        metadata = {
            "subject": "Feliz Natal",
            "has_attachment": False,
            "has_links_nfe": True,
        }
        result = get_filter_decision(metadata)
        assert isinstance(result, FilterResult)
        assert result.decision == FilterDecision.SKIP_BLACKLIST

    def test_get_default_filter(self):
        """Testa factory de filtro padrão."""
        filter1 = get_default_filter()
        filter2 = get_default_filter()

        # Deve criar novas instâncias
        assert isinstance(filter1, EmailFilter)
        assert isinstance(filter2, EmailFilter)


class TestEmailFilterResultFields:
    """Testes para campos do FilterResult."""

    def test_result_contains_sender(self):
        """Verifica que o resultado contém o sender."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Teste",
            "sender_address": "teste@exemplo.com.br",
            "has_attachment": True,
        })
        assert result.sender == "teste@exemplo.com.br"

    def test_result_contains_blacklist_match(self):
        """Verifica que o resultado contém o match da blacklist."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Newsletter de Natal",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.blacklist_match is not None

    def test_result_contains_whitelist_matches(self):
        """Verifica que o resultado contém os matches da whitelist."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Sua Nota Fiscal e Boleto",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.should_process is True
        assert len(result.whitelist_matches) > 0

    def test_result_contains_sender_blacklist_match(self):
        """Verifica que o resultado contém o match da blacklist de sender."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Fatura",
            "sender_address": "news@mail.mailchimp.com",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.decision == FilterDecision.SKIP_SENDER_BLACKLIST
        assert result.sender_blacklist_match is not None


class TestEmailFilterBatchProcessing:
    """Testes para processamento em lote."""

    def test_filter_batch(self):
        """Testa filtragem de múltiplos e-mails."""
        email_filter = EmailFilter()
        emails = [
            {"subject": "NF-e", "has_attachment": True},
            {"subject": "Newsletter", "has_attachment": False, "has_links_nfe": True},
            {"subject": "Boleto", "has_attachment": False, "has_links_nfe": True},
        ]

        # filter_batch retorna tupla (to_process, to_skip)
        to_process, to_skip = email_filter.filter_batch(emails)

        # Deve processar 2 (NF-e com anexo, Boleto com link)
        # Deve ignorar 1 (Newsletter - blacklist)
        assert len(to_process) == 2
        assert len(to_skip) == 1

        # Verifica que Newsletter foi ignorado
        assert any("Newsletter" in e.get("subject", "") for e in to_skip)


class TestEmailFilterEdgeCases:
    """Testes para casos de borda."""

    def test_empty_subject(self):
        """Testa e-mail com assunto vazio."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        # Sem assunto, não corresponde a whitelist
        assert result.decision == FilterDecision.SKIP_NO_SUBJECT_MATCH

    def test_none_subject(self):
        """Testa e-mail com assunto None."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": None,
            "has_attachment": True,
        })
        # Anexo ainda processa
        assert result.should_process is True

    def test_empty_sender(self):
        """Testa e-mail com sender vazio."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Fatura",
            "sender_address": "",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        # Sem sender, processa normalmente pela whitelist de assunto
        assert result.should_process is True

    def test_none_sender(self):
        """Testa e-mail com sender None."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Boleto",
            "sender_address": None,
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.should_process is True

    def test_unicode_subject(self):
        """Testa assunto com caracteres Unicode."""
        email_filter = EmailFilter()
        result = email_filter.should_process_email({
            "subject": "Fatura nº 12345 - Cômputo de Março",
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.should_process is True

    def test_very_long_subject(self):
        """Testa assunto muito longo."""
        email_filter = EmailFilter()
        long_subject = "Nota Fiscal " + "x" * 1000
        result = email_filter.should_process_email({
            "subject": long_subject,
            "has_attachment": False,
            "has_links_nfe": True,
        })
        assert result.should_process is True
