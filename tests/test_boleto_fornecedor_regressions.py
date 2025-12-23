from extractors.boleto import BoletoExtractor


def test_boleto_fornecedor_nao_pega_linha_digitavel_como_nome():
    extractor = BoletoExtractor()

    # Caso real: linha única com cabeçalhos antes do nome + CNPJ
    text = (
        "Beneficiário Vencimento Valor do Documento MAIS CONSULTORIA E SERVICOS LTDA "
        "18.363.307/0001-12 10/08/2025 6.250,00\n"
        "756 75691.31407 01130.051202 02685.970010 3 11690000625000\n"
    )

    fornecedor = extractor._extract_fornecedor_nome(text)
    assert fornecedor == "MAIS CONSULTORIA E SERVICOS LTDA"
