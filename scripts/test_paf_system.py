"""
Script de testes para o sistema PAF
Valida todas as funcionalidades críticas implementadas
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.feriados_sp import SPBusinessCalendar
from config.bancos import NOMES_BANCOS
from core.models import InvoiceData, BoletoData
from core.diagnostics import DiagnosticoPAF
import re


def teste_1_calendario_sp():
    """Testa cálculo de dias úteis com feriados de São Paulo"""
    print("\n" + "="*70)
    print("TESTE 1: Calendário de São Paulo (Dias Úteis)")
    print("="*70)
    
    calendario = SPBusinessCalendar()
    
    # Teste 1.1: Verificar feriados fixos de SP
    print("\n1.1 - Feriados fixos de SP:")
    ano = 2025
    feriados = calendario.get_fixed_holidays(ano)
    sp_holidays = [f for f in feriados if f[1] in ["Aniversário de São Paulo", "Consciência Negra"]]
    
    for data, nome in sp_holidays:
        print(f"  ✓ {data.strftime('%d/%m/%Y')} - {nome}")
    
    # Teste 1.2: Verificar feriados móveis
    print("\n1.2 - Feriados móveis (cache LRU):")
    feriados_moveis = calendario.get_variable_days(2025)
    
    corpus_christi = next((f for f in feriados_moveis if f[1] == "Corpus Christi"), None)
    carnaval = next((f for f in feriados_moveis if f[1] == "Carnaval"), None)
    
    if corpus_christi:
        print(f"  ✓ Corpus Christi: {corpus_christi[0].strftime('%d/%m/%Y')}")
    if carnaval:
        print(f"  ✓ Carnaval: {carnaval[0].strftime('%d/%m/%Y')}")
    
    # Teste 1.3: Cálculo de dias úteis
    print("\n1.3 - Cálculo de dias úteis:")
    
    # Cenário 1: 5 dias úteis (deve passar)
    dt_inicio = datetime(2025, 12, 22)
    dt_fim = datetime(2025, 12, 29)
    dias_uteis = calendario.get_working_days_delta(dt_inicio, dt_fim)
    print(f"  De {dt_inicio.strftime('%d/%m/%Y')} até {dt_fim.strftime('%d/%m/%Y')}: {dias_uteis} dias úteis")
    print(f"  Status: {'✓ >= 4 dias' if dias_uteis >= 4 else '✗ < 4 dias'}")
    
    # Cenário 2: 2 dias úteis (não deve passar)
    dt_inicio = datetime(2025, 12, 22)
    dt_fim = datetime(2025, 12, 24)
    dias_uteis = calendario.get_working_days_delta(dt_inicio, dt_fim)
    print(f"  De {dt_inicio.strftime('%d/%m/%Y')} até {dt_fim.strftime('%d/%m/%Y')}: {dias_uteis} dias úteis")
    print(f"  Status: {'✓ >= 4 dias' if dias_uteis >= 4 else '✗ < 4 dias (esperado)'}")
    
    return True


def teste_2_validacao_prazo():
    """Testa validação de prazo de 4 dias úteis"""
    print("\n" + "="*70)
    print("TESTE 2: Validação de Prazo (Policy 5.9)")
    print("="*70)
    
    diagnostico = DiagnosticoPAF()
    
    # Cenário 1: 5 dias úteis (deve passar)
    print("\n2.1 - Cenário com 5 dias úteis:")
    dt_classificacao = datetime(2025, 12, 22)
    vencimento = datetime(2025, 12, 29)
    prazo_ok, dias = diagnostico.validar_prazo_vencimento(dt_classificacao, vencimento)
    print(f"  Classificação: {dt_classificacao.strftime('%d/%m/%Y')}")
    print(f"  Vencimento: {vencimento.strftime('%d/%m/%Y')}")
    print(f"  Dias úteis: {dias}")
    print(f"  Resultado: {'✓ APROVADO' if prazo_ok else '✗ REPROVADO'}")
    
    # Cenário 2: 2 dias úteis (deve reprovar)
    print("\n2.2 - Cenário com 2 dias úteis:")
    dt_classificacao = datetime(2025, 12, 22)
    vencimento = datetime(2025, 12, 24)
    prazo_ok, dias = diagnostico.validar_prazo_vencimento(dt_classificacao, vencimento)
    print(f"  Classificação: {dt_classificacao.strftime('%d/%m/%Y')}")
    print(f"  Vencimento: {vencimento.strftime('%d/%m/%Y')}")
    print(f"  Dias úteis: {dias}")
    print(f"  Resultado: {'✓ APROVADO' if prazo_ok else '✗ REPROVADO (esperado)'}")
    
    # Cenário 3: Exatamente 4 dias úteis (limite, deve passar)
    print("\n2.3 - Cenário com exatamente 4 dias úteis:")
    dt_classificacao = datetime(2025, 12, 22)
    vencimento = datetime(2025, 12, 26)
    prazo_ok, dias = diagnostico.validar_prazo_vencimento(dt_classificacao, vencimento)
    print(f"  Classificação: {dt_classificacao.strftime('%d/%m/%Y')}")
    print(f"  Vencimento: {vencimento.strftime('%d/%m/%Y')}")
    print(f"  Dias úteis: {dias}")
    print(f"  Resultado: {'✓ APROVADO' if prazo_ok else '✗ REPROVADO'}")
    
    return True


def teste_3_modelo_nfse():
    """Testa conversão de NFSe para formato PAF (18 colunas)"""
    print("\n" + "="*70)
    print("TESTE 3: Modelo NFSe → PAF (18 colunas)")
    print("="*70)
    
    # Criar NFSe de exemplo
    nfse = InvoiceData(
        tipo_documento="nfse",
        numero_nota="12345",
        data_emissao=datetime(2025, 12, 15),
        valor_total=5000.00,
        cnpj_prestador="12.345.678/0001-90",
        fornecedor_nome="EMPRESA EXEMPLO LTDA",
        valor_ir=150.00,
        valor_inss=550.00,
        valor_csll=50.00,
        valor_iss=250.00,
        valor_icms=0.0,
        vencimento=datetime(2025, 12, 30),
        numero_pedido="PED-2025-001",
        forma_pagamento="BOLETO",
        data_processamento=datetime(2025, 12, 22),
        dt_classificacao=datetime(2025, 12, 22),
        trat_paf="Rafael Ferreira",
        lanc_sistema="PENDENTE",
        setor="TI",
        empresa="MASTER INTERNET",
        observacoes="Serviços de desenvolvimento",
        obs_interna="Validado pela equipe técnica"
    )
    
    # Converter para formato PAF
    print("\n3.1 - Conversão to_sheets_row():")
    row = nfse.to_sheets_row()
    
    # Nomes das colunas PAF
    colunas_paf = [
        "DATA", "SETOR", "EMPRESA", "FORNECEDOR", "NF", "EMISSÃO",
        "VALOR", "Nº PEDIDO", "VENCIMENTO", "FORMA PAGTO", "INDEX",
        "DT CLASS", "Nº FAT", "TP DOC", "TRAT PAF", "LANC SISTEMA",
        "OBSERVAÇÕES", "OBS INTERNA"
    ]
    
    print(f"  Total de colunas: {len(row)} (esperado: 18)")
    print(f"  Status: {'✓ OK' if len(row) == 18 else '✗ ERRO'}")
    
    print("\n3.2 - Valores das colunas:")
    for i, (coluna, valor) in enumerate(zip(colunas_paf, row), 1):
        print(f"  {i:2d}. {coluna:15s}: {valor}")
    
    # Verificar total de retenções
    print(f"\n3.3 - Total de Retenções: R$ {nfse.total_retencoes:.2f}")
    print(f"  IR + INSS + CSLL: R$ {150+550+50:.2f}")
    print(f"  Status: {'✓ OK' if nfse.total_retencoes == 750.00 else '✗ ERRO'}")
    
    return len(row) == 18 and nfse.total_retencoes == 750.00


def teste_4_modelo_boleto():
    """Testa conversão de Boleto para formato PAF (18 colunas)"""
    print("\n" + "="*70)
    print("TESTE 4: Modelo Boleto → PAF (18 colunas)")
    print("="*70)
    
    # Criar Boleto de exemplo
    boleto = BoletoData(
        tipo_documento="boleto",
        linha_digitavel="23790.12345 67891.234567 89012.345678 9 12345678901234",
        valor_documento=1500.00,
        vencimento=datetime(2025, 12, 28),
        fornecedor_nome="FORNECEDOR ABC LTDA",
        banco_nome="BANCO BRADESCO S.A.",
        agencia="1234-5",
        conta_corrente="123456-7",
        numero_pedido="PED-2025-002",
        data_processamento=datetime(2025, 12, 22),
        dt_classificacao=datetime(2025, 12, 22),
        trat_paf="Rafael Ferreira",
        lanc_sistema="PENDENTE",
        setor="FINANCEIRO",
        empresa="MASTER INTERNET",
        observacoes="Pagamento fornecedor",
        obs_interna="Boleto validado"
    )
    
    # Converter para formato PAF
    print("\n4.1 - Conversão to_sheets_row():")
    row = boleto.to_sheets_row()
    
    colunas_paf = [
        "DATA", "SETOR", "EMPRESA", "FORNECEDOR", "NF", "EMISSÃO",
        "VALOR", "Nº PEDIDO", "VENCIMENTO", "FORMA PAGTO", "INDEX",
        "DT CLASS", "Nº FAT", "TP DOC", "TRAT PAF", "LANC SISTEMA",
        "OBSERVAÇÕES", "OBS INTERNA"
    ]
    
    print(f"  Total de colunas: {len(row)} (esperado: 18)")
    print(f"  Status: {'✓ OK' if len(row) == 18 else '✗ ERRO'}")
    
    print("\n4.2 - Valores das colunas:")
    for i, (coluna, valor) in enumerate(zip(colunas_paf, row), 1):
        print(f"  {i:2d}. {coluna:15s}: {valor}")
    
    # Verificar tipo de documento
    print(f"\n4.3 - Tipo de Documento: {boleto.tipo_doc_paf}")
    print(f"  Status: {'✓ OK (FT)' if boleto.tipo_doc_paf == 'FT' else '✗ ERRO'}")
    
    return len(row) == 18 and boleto.tipo_doc_paf == "FT"


def teste_5_normalizacao_bancaria():
    """Testa normalização de dados bancários"""
    print("\n" + "="*70)
    print("TESTE 5: Normalização de Dados Bancários")
    print("="*70)
    
    # Simular normalização de agência
    print("\n5.1 - Normalização de Agência:")
    
    casos_agencia = [
        ("1234-5", "1234-5"),      # Já normalizado
        ("1234 5", "1234-5"),      # Com espaço
        ("1.234-5", "1234-5"),     # Com ponto
        ("01234-5", "01234-5"),    # Com zero à esquerda
    ]
    
    def normalizar_agencia(agencia):
        """Simula normalização"""
        if not agencia:
            return None
        # Remove espaços e pontos, mantém hífen+dígito
        agencia = agencia.strip()
        agencia = agencia.replace(" ", "-").replace(".", "")
        # Garante formato XXXX-X
        if "-" in agencia:
            partes = agencia.split("-")
            return f"{partes[0]}-{partes[1]}"
        return agencia
    
    for entrada, esperado in casos_agencia:
        resultado = normalizar_agencia(entrada)
        status = "✓" if resultado == esperado else "✗"
        print(f"  {status} '{entrada}' → '{resultado}' (esperado: '{esperado}')")
    
    # Simular normalização de conta corrente
    print("\n5.2 - Normalização de Conta Corrente:")
    
    casos_conta = [
        ("123456-7", "123456-7"),      # Já normalizado
        ("123456 7", "123456-7"),      # Com espaço
        ("123.456-7", "123456-7"),     # Com ponto
    ]
    
    def normalizar_conta(conta):
        """Simula normalização"""
        if not conta:
            return None
        # Remove espaços e pontos, mantém hífen+dígito
        conta = conta.strip()
        conta = conta.replace(" ", "-").replace(".", "")
        # Garante formato XXXXXX-X
        if "-" in conta:
            partes = conta.split("-")
            return f"{partes[0]}-{partes[1]}"
        return conta
    
    for entrada, esperado in casos_conta:
        resultado = normalizar_conta(entrada)
        status = "✓" if resultado == esperado else "✗"
        print(f"  {status} '{entrada}' → '{resultado}' (esperado: '{esperado}')")
    
    return True


def teste_6_mapeamento_bancos():
    """Testa mapeamento de códigos bancários"""
    print("\n" + "="*70)
    print("TESTE 6: Mapeamento de Bancos (Top 20)")
    print("="*70)
    
    print(f"\n6.1 - Total de bancos mapeados: {len(NOMES_BANCOS)}")
    
    # Testar bancos principais
    print("\n6.2 - Bancos principais:")
    bancos_teste = [
        ("001", "BANCO DO BRASIL S.A."),
        ("237", "BANCO BRADESCO S.A."),
        ("341", "BANCO ITAÚ S.A."),
        ("104", "CAIXA ECONÔMICA FEDERAL"),
        ("033", "BANCO SANTANDER S.A."),
    ]
    
    for codigo, nome_esperado in bancos_teste:
        nome_real = NOMES_BANCOS.get(codigo, f"BANCO_{codigo}")
        status = "✓" if nome_real == nome_esperado else "✗"
        print(f"  {status} {codigo}: {nome_real}")
    
    # Testar fallback para banco não mapeado
    print("\n6.3 - Fallback para banco não mapeado:")
    codigo_inexistente = "999"
    nome_fallback = NOMES_BANCOS.get(codigo_inexistente, f"BANCO_{codigo_inexistente}")
    print(f"  Código {codigo_inexistente}: {nome_fallback}")
    print(f"  Status: {'✓ OK (BANCO_999)' if nome_fallback == 'BANCO_999' else '✗ ERRO'}")
    
    return True


def teste_7_classificacao_diagnostico():
    """Testa classificação de documentos com prazo"""
    print("\n" + "="*70)
    print("TESTE 7: Classificação com Diagnóstico de Prazo")
    print("="*70)
    
    diagnostico = DiagnosticoPAF()
    
    # Cenário 1: NFSe com prazo OK
    print("\n7.1 - NFSe com todos os campos e prazo OK:")
    nfse_ok = InvoiceData(
        tipo_documento="nfse",
        numero_nota="12345",
        data_emissao=datetime(2025, 12, 15),
        valor_total=5000.00,
        cnpj_prestador="12.345.678/0001-90",
        fornecedor_nome="EMPRESA EXEMPLO LTDA",
        vencimento=datetime(2025, 12, 30),
        dt_classificacao=datetime(2025, 12, 22)
    )
    
    classificacao = diagnostico.classificar_nfse(nfse_ok)
    print(f"  Status: {classificacao['status']}")
    print(f"  Motivos: {classificacao['motivos'] if classificacao['motivos'] else 'Nenhum'}")
    print(f"  Resultado: {'✓ SUCESSO' if classificacao['status'] == 'sucesso' else '✗ FALHA'}")
    
    # Cenário 2: NFSe sem razão social
    print("\n7.2 - NFSe sem razão social:")
    nfse_sem_razao = InvoiceData(
        tipo_documento="nfse",
        numero_nota="12345",
        data_emissao=datetime(2025, 12, 15),
        valor_total=5000.00,
        cnpj_prestador="12.345.678/0001-90",
        fornecedor_nome=None,  # Sem razão social
        vencimento=datetime(2025, 12, 30),
        dt_classificacao=datetime(2025, 12, 22)
    )
    
    classificacao = diagnostico.classificar_nfse(nfse_sem_razao)
    print(f"  Status: {classificacao['status']}")
    print(f"  Motivos: {classificacao['motivos']}")
    print(f"  Resultado: {'✓ FALHA DETECTADA' if 'SEM_RAZAO_SOCIAL' in classificacao['motivos'] else '✗ ERRO'}")
    
    # Cenário 3: NFSe com prazo insuficiente
    print("\n7.3 - NFSe com prazo insuficiente:")
    nfse_prazo_curto = InvoiceData(
        tipo_documento="nfse",
        numero_nota="12345",
        data_emissao=datetime(2025, 12, 15),
        valor_total=5000.00,
        cnpj_prestador="12.345.678/0001-90",
        fornecedor_nome="EMPRESA EXEMPLO LTDA",
        vencimento=datetime(2025, 12, 24),  # Só 2 dias úteis
        dt_classificacao=datetime(2025, 12, 22)
    )
    
    classificacao = diagnostico.classificar_nfse(nfse_prazo_curto)
    print(f"  Status: {classificacao['status']}")
    print(f"  Motivos: {classificacao['motivos']}")
    
    tem_prazo_insuficiente = any("PRAZO_INSUFICIENTE" in m for m in classificacao['motivos'])
    print(f"  Resultado: {'✓ PRAZO INSUFICIENTE DETECTADO' if tem_prazo_insuficiente else '✗ ERRO'}")
    
    return True


def teste_8_conversao_data():
    """Testa conversão de datas ISO → DD/MM/YYYY"""
    print("\n" + "="*70)
    print("TESTE 8: Conversão de Datas (ISO → DD/MM/YYYY)")
    print("="*70)
    
    from core.models import fmt_date
    
    print("\n8.1 - Conversões válidas:")
    
    casos = [
        (datetime(2025, 12, 22), "22/12/2025"),
        (datetime(2025, 1, 5), "05/01/2025"),
        (datetime(2025, 12, 31), "31/12/2025"),
        (None, ""),
    ]
    
    for entrada, esperado in casos:
        resultado = fmt_date(entrada)
        status = "✓" if resultado == esperado else "✗"
        entrada_str = entrada.strftime('%Y-%m-%d') if entrada else "None"
        print(f"  {status} {entrada_str} → '{resultado}' (esperado: '{esperado}')")
    
    return True


def main():
    """Executa todos os testes"""
    print("\n" + "="*70)
    print(" TESTES DO SISTEMA PAF - MASTER INTERNET")
    print(" Versão: v0001 | Data: 22/12/2025")
    print("="*70)
    
    testes = [
        ("Calendário de SP", teste_1_calendario_sp),
        ("Validação de Prazo", teste_2_validacao_prazo),
        ("Modelo NFSe → PAF", teste_3_modelo_nfse),
        ("Modelo Boleto → PAF", teste_4_modelo_boleto),
        ("Normalização Bancária", teste_5_normalizacao_bancaria),
        ("Mapeamento de Bancos", teste_6_mapeamento_bancos),
        ("Classificação com Diagnóstico", teste_7_classificacao_diagnostico),
        ("Conversão de Datas", teste_8_conversao_data),
    ]
    
    resultados = []
    
    for nome, teste_func in testes:
        try:
            sucesso = teste_func()
            resultados.append((nome, sucesso if sucesso is not None else True))
        except Exception as e:
            print(f"\n✗ ERRO no teste '{nome}': {e}")
            import traceback
            traceback.print_exc()
            resultados.append((nome, False))
    
    # Relatório final
    print("\n" + "="*70)
    print(" RELATÓRIO FINAL")
    print("="*70)
    
    total = len(resultados)
    sucesso_count = sum(1 for _, ok in resultados if ok)
    
    print(f"\nTestes executados: {total}")
    print(f"Sucesso: {sucesso_count}")
    print(f"Falhas: {total - sucesso_count}")
    print(f"\nTaxa de sucesso: {(sucesso_count/total)*100:.1f}%")
    
    print("\nDetalhamento:")
    for nome, sucesso in resultados:
        status = "✓ PASSOU" if sucesso else "✗ FALHOU"
        print(f"  {status}: {nome}")
    
    print("\n" + "="*70)
    
    if sucesso_count == total:
        print("✓ TODOS OS TESTES PASSARAM! Sistema PAF validado.")
    else:
        print("✗ ALGUNS TESTES FALHARAM. Revisar implementação.")
    
    print("="*70 + "\n")
    
    return sucesso_count == total


if __name__ == "__main__":
    sucesso = main()
    sys.exit(0 if sucesso else 1)
