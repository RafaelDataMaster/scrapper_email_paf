
from core.empresa_matcher import find_empresa_no_texto, infer_fornecedor_from_text


def test_find_empresa_no_texto_by_cnpj_digits_or_spaced():
    # CNPJ CSC (nosso cadastro) aparece com formatação normal
    txt = "CSC GESTAO INTEGRADA S/A - CPF/CNPJ: 38.323.227/0001-40"
    m = find_empresa_no_texto(txt)
    assert m is not None
    assert m.codigo == "CSC"


def test_find_empresa_no_texto_by_email_domain_fallback_master():
    # Documento não contém CNPJ nosso, mas contém e-mail/dominio corporativo.
    # Não deve associar domínio 'soumaster.com.br' à empresa MASTER (evita falso positivo).
    txt = "Login: courrier ti@soumaster.com.br VENCIMENTO TOTAL A PAGAR"
    m = find_empresa_no_texto(txt)
    assert m is None


def test_infer_fornecedor_prefers_labelled_line_and_excludes_our_company():
    # Documento contém uma empresa nossa (CSC) e um fornecedor com CNPJ em formato "espaçado".
    txt = """
    DADOS DO PAGADOR
    CSC GESTAO INTEGRADA S/A - CPF/CNPJ: 38.323.227/0001-40

    BENEFICIÁRIO
    Razão Social: FORNECEDOR EXEMPLO LTDA - CNPJ 12 . 345 . 678 / 0001 - 90
    """.strip()

    fornecedor = infer_fornecedor_from_text(txt, "38323227000140")
    assert fornecedor is not None
    assert "FORNECEDOR EXEMPLO LTDA" in fornecedor
    assert "12.345.678/0001-90" in fornecedor


def test_infer_fornecedor_does_not_pick_linha_digitavel_as_name():
    txt = """
    LINHA DIGITAVEL
    75691.31407 01130.051202 02685.970010 3 11690000625000
    CNPJ 11.690.000/6250-00
    """.strip()

    fornecedor = infer_fornecedor_from_text(txt, "38323227000140")
    assert fornecedor is None
