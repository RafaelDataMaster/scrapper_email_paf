# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
from core.correlation_service import CorrelationService

service = CorrelationService()

test_subjects = [
    'Sua ordem Equinix n.o 1-255425159203 agendada com sucesso',
    'Distrato - Speed Copy',
    'Rescisao contratual - OSCAR HENRIQUE',
    'Solicitacao de encerramento de contrato XYZ',
    'Relatorio de faturamento JAN 26 (MG/SP/EXATA)',
    'RES: SOLICITACAO DISTRATO DE VEICULO',
    'CEMIG FATURA ONLINE - 214687921',
    'NFS-e + Boleto No 3494',
]

print('=' * 70)
print('TESTE DE DETECCAO DE DOCUMENTOS ADMINISTRATIVOS')
print('=' * 70)

for subject in test_subjects:
    result = service._check_admin_subject(subject)
    if result:
        status = f'ADMIN: {result}'
    else:
        status = 'NORMAL'
    print(f'[{status:50}] {subject[:50]}...')
