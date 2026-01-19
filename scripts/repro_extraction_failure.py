import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractors.outros import OutrosExtractor

# Simulação de textos que podem ter falhado
test_texts = [
    # Caso 1: DANFE incompleto ou mal OCRizado que caiu no OutrosExtractor (tem "FATURA" mas não "DANFE")
    """
    RECEBEMOS DE TUNNA ENTRETENIMENTO
    FATURA N. 10731
    NATUREZA DA OPERACAO: PRESTACAO DE SERVICO
    DESTINATARIO: ATIVE TELECOMUNICACOES
    
    DADOS DO PRODUTO / SERVICO
    CODIGO   DESCRICAO    QTD   VALOR UNIT   VALOR TOTAL
    001      PUBLICIDADE  1     500,00       500,00
    
    CALCULO DO IMPOSTO
    BASE ICMS  VALOR ICMS   VALOR TOTAL DA NOTA
    0,00       0,00         500,00
    
    DADOS ADICIONAIS
    """,
    
    # Caso 2: Documento com "Valor Total" mas sem R$
    """
    DEMONSTRATIVO DE LOCACAO
    Locador: XYZ Ltda
    
    Descricao         Valor
    Aluguel           1.200,50
    Condominio        300,00
    
    VALOR TOTAL DA LOCACAO: 1.500,50
    Vencimento: 20/01/2026
    """,
    
    # Caso 3: AGYONET (provável Fatura de telecom)
    """
    AGYONET TELECOMUNICACOES LTDA
    Fatura de Servicos de Telecomunicacoes
    Cliente: ATIVE TELECOMUNICACOES
    Vencimento: 25/01/2026
    
    Resumo da Fatura
    Mensalidade Internet ... 150,00
    Servicos Adicionais ....  50,00
    
    Total a Pagar........... 200,00
    """
]

extractor = OutrosExtractor()

print("-" * 50)
print("TESTE DE REPRODUÇÃO - OUTROS EXTRACTOR")
print("-" * 50)

for i, text in enumerate(test_texts, 1):
    print(f"\nCaso {i}:")
    if extractor.can_handle(text):
        print("✅ Can handle: SIM")
        data = extractor.extract(text)
        print(f"Dados extraídos: {data}")
        print(f"Valor Total: {data.get('valor_total')}")
        if not data.get('valor_total') or data.get('valor_total') == 0.0:
            print("❌ FALHA: Valor total não extraído ou zero")
        else:
            print("✅ SUCESSO: Valor extraído")
    else:
        print("⚠️ Can handle: NÃO (Este teste foca na extração de valores, assumindo que foi capturado)")
