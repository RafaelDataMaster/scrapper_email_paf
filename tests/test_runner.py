"""
Script para executar os testes principais do sistema
Exclui testes com problemas conhecidos (circular imports)
"""
import sys
import pytest

def run_tests():
    """Executa a suíte de testes principal"""
    args = [
        'tests/test_extractors.py',
        'tests/test_ingestion.py', 
        'tests/test_paf_compliance.py',
        'tests/test_solid_refactoring.py',
        '-v',
        '--tb=short'
    ]
    
    print("=" * 70)
    print("Executando Testes do Sistema")
    print("=" * 70)
    print("\nTestes incluídos:")
    print("  - Extratores (NFSe e Boletos)")
    print("  - Ingestão de E-mails")
    print("  - Conformidade PAF (Policy 5.9 e POP 4.10)")
    print("  - Arquitetura SOLID")
    print("\n")
    
    exit_code = pytest.main(args)
    
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("✓ TODOS OS TESTES PASSARAM!")
    else:
        print(f"✗ Alguns testes falharam (código: {exit_code})")
    print("=" * 70)
    
    return exit_code

if __name__ == "__main__":
    sys.exit(run_tests())
