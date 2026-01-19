# -*- coding: utf-8 -*-
"""
Teste de detecção de documentos administrativos.

Este script testa se os padrões em ADMIN_SUBJECT_PATTERNS
estão capturando corretamente os assuntos de e-mails administrativos.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from core.correlation_service import CorrelationService

service = CorrelationService()

# Assuntos que DEVEM ser detectados como administrativos
admin_subjects = [
    # Originais
    'Sua ordem Equinix n.o 1-255425159203 agendada com sucesso',
    'Distrato - Speed Copy',
    'Rescisao contratual - OSCAR HENRIQUE',
    'Solicitacao de encerramento de contrato XYZ',
    'Relatorio de faturamento JAN 26 (MG/SP/EXATA)',
    'RES: SOLICITACAO DISTRATO DE VEICULO',
    # Novos casos identificados
    'GUIA | Processo - Miralva Macedo Dias x CSC',
    'GUIA | Execução Fiscal - Vale Telecom',
    'Guia - RR - Joao Gabriel x Divtel - 0011081',
    'Fwd: ENC: GUIAS - CSC X BRUNO RAIMUNDO',
    'CONTRATO_SITE MASTER INTERNET',
    'CAMBIO HBO RBC NOVEMBRO',
    'Lembrete Gentil: Vencimento de Fatura',
    'RE: Lembrete Gentil: Vencimento de Fatura',
    'December - 2025 Invoice for 6343 - ATIVE',
    'ENC: December - 2025  Invoice for 6342 - MOC',
    'ENC: Anuidade CREA',
    'Reembolso de Tarifas CSC - 18/12/2025 a 31/12/2025',
    'Tarifas CSC - Acerto MOC - apuração até 31/12/2025',
    'ALVIM NOGUEIRA ( |601) - Boleto Vencimento (01/2026)',
    'Cobrança Indevida 11/2025 - 4security',
]

# Assuntos que NÃO devem ser detectados como administrativos (são cobranças reais)
normal_subjects = [
    'CEMIG FATURA ONLINE - 214687921',
    'NFS-e + Boleto No 3494',
    'Boleto ACIV',
    'EDP - FATURAS',
    'Sua fatura chegou',
    'Chegou sua conta por e-mail',
    'Nota Fiscal Eletrônica Nº 103977',
    'Fatura vencida - CSC GESTÃO INTEGRADA',
    'Nota Fatura - 2025-59',
]

print('=' * 80)
print('TESTE DE DETECÇÃO DE DOCUMENTOS ADMINISTRATIVOS')
print('=' * 80)

print('\n📋 ASSUNTOS QUE DEVEM SER DETECTADOS COMO ADMIN:')
print('-' * 80)
admin_ok = 0
admin_fail = 0
for subject in admin_subjects:
    result = service._check_admin_subject(subject)
    if result:
        status = f'✅ ADMIN: {result}'
        admin_ok += 1
    else:
        status = '❌ NÃO DETECTADO'
        admin_fail += 1
    print(f'{status:55} | {subject[:50]}...')

print('\n📄 ASSUNTOS QUE NÃO DEVEM SER DETECTADOS (cobranças reais):')
print('-' * 80)
normal_ok = 0
normal_fail = 0
for subject in normal_subjects:
    result = service._check_admin_subject(subject)
    if result:
        status = f'⚠️ FALSO POSITIVO: {result}'
        normal_fail += 1
    else:
        status = '✅ NORMAL'
        normal_ok += 1
    print(f'{status:55} | {subject[:50]}...')

print('\n' + '=' * 80)
print('RESUMO:')
print(f'  Adminstrativo: {admin_ok}/{len(admin_subjects)} detectados corretamente')
print(f'  Normal: {normal_ok}/{len(normal_subjects)} não-detectados corretamente')
if admin_fail > 0:
    print(f'  ⚠️ {admin_fail} assuntos admin NÃO detectados!')
if normal_fail > 0:
    print(f'  ⚠️ {normal_fail} falsos positivos!')
print('=' * 80)
