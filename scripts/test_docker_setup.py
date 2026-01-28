#!/usr/bin/env python3
"""
Script de teste para validar a configuração Docker do projeto.

Verifica:
- Tesseract OCR está instalado e acessível
- Poppler está instalado e acessível
- Configurações do settings.py estão corretas
- Dependências Python estão funcionando
"""

import sys
import subprocess
import platform
from pathlib import Path

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def check_command(cmd, name):
    """Verifica se um comando está disponível no sistema."""
    try:
        result = subprocess.run([cmd, '--version'], 
                              capture_output=True, 
                              text=True, 
                              timeout=5)
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            print(f"✅ {name}: {version}")
            return True
        else:
            print(f"❌ {name}: Comando falhou")
            return False
    except FileNotFoundError:
        print(f"❌ {name}: Não encontrado no PATH")
        return False
    except Exception as e:
        print(f"❌ {name}: Erro - {e}")
        return False

def check_python_imports():
    """Verifica se as bibliotecas Python necessárias estão instaladas."""
    print_header("Verificando Bibliotecas Python")
    
    libraries = [
        ('pdfplumber', 'Extração de PDF vetorial'),
        ('pytesseract', 'Interface Python para Tesseract'),
        ('pdf2image', 'Conversão PDF para imagem'),
        ('pandas', 'Manipulação de dados'),
        ('PIL', 'Processamento de imagens (Pillow)'),
        ('dotenv', 'Leitura de variáveis de ambiente'),
    ]
    
    all_ok = True
    for lib, desc in libraries:
        try:
            __import__(lib)
            print(f"✅ {lib:15} - {desc}")
        except ImportError:
            print(f"❌ {lib:15} - NÃO INSTALADO")
            all_ok = False
    
    return all_ok

def check_settings():
    """Verifica as configurações do settings.py."""
    print_header("Verificando Configurações (settings.py)")
    
    try:
        from config import settings
        
        print(f"Sistema operacional: {platform.system()}")
        print(f"Tesseract CMD: {settings.TESSERACT_CMD}")
        print(f"Poppler PATH: {settings.POPPLER_PATH}")
        print(f"OCR Config: {settings.OCR_CONFIG}")
        print(f"OCR Lang: {settings.OCR_LANG}")
        
        # Verifica se os caminhos existem
        tesseract_exists = Path(settings.TESSERACT_CMD).exists()
        poppler_exists = Path(settings.POPPLER_PATH).exists()
        
        print("\nValidação de Paths:")
        print(f"  Tesseract existe: {'✅' if tesseract_exists else '❌'}")
        print(f"  Poppler existe: {'✅' if poppler_exists else '❌'}")
        
        return tesseract_exists and poppler_exists
        
    except Exception as e:
        print(f"❌ Erro ao carregar settings: {e}")
        return False

def check_tesseract_pytesseract():
    """Verifica se o pytesseract consegue acessar o Tesseract."""
    print_header("Verificando Integração pytesseract → Tesseract")
    
    try:
        import pytesseract
        from config import settings
        
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        
        version = pytesseract.get_tesseract_version()
        print(f"✅ pytesseract consegue acessar Tesseract v{version}")
        return True
    except Exception as e:
        print(f"❌ Erro na integração: {e}")
        return False

def check_pdf2image():
    """Verifica se o pdf2image consegue acessar o Poppler."""
    print_header("Verificando Integração pdf2image → Poppler")
    
    try:
        from pdf2image import convert_from_path  # type: ignore  # noqa: F401  # Verifica disponibilidade
        from config import settings
        
        # Testa se consegue encontrar o pdfinfo (parte do Poppler)
        import subprocess
        if platform.system() == 'Linux':
            result = subprocess.run(['which', 'pdfinfo'], 
                                  capture_output=True, 
                                  text=True)
        else:
            poppler_bin = Path(settings.POPPLER_PATH) / 'pdfinfo.exe'
            result = subprocess.run([str(poppler_bin), '-v'], 
                                  capture_output=True, 
                                  text=True)
        
        if result.returncode == 0:
            print("✅ pdf2image consegue acessar Poppler")
            return True
        else:
            print("❌ Poppler não está acessível")
            return False
            
    except Exception as e:
        print(f"❌ Erro na integração: {e}")
        return False

def check_directories():
    """Verifica se os diretórios necessários existem."""
    print_header("Verificando Estrutura de Diretórios")
    
    from config import settings
    
    dirs = [
        ('Saída', settings.DIR_SAIDA),
        ('Debug Output', settings.DIR_DEBUG_OUTPUT),
        ('Temp Email', settings.DIR_TEMP),
        ('Debug Input', settings.DIR_DEBUG_INPUT),
    ]
    
    all_ok = True
    for name, path in dirs:
        exists = path.exists()
        writable = path.is_dir() and False  # Simples check
        try:
            if exists:
                # Tenta criar um arquivo temporário
                test_file = path / '.test_write'
                test_file.touch()
                test_file.unlink()
                writable = True
        except Exception:
            writable = False
            
        status = '✅' if (exists and writable) else '⚠️' if exists else '❌'
        print(f"{status} {name:15} - {path} {'(sem permissão de escrita)' if exists and not writable else ''}")
        
        if not exists:
            all_ok = False
    
    return all_ok

def main():
    """Executa todos os testes."""
    print_header("🐳 TESTE DE CONFIGURAÇÃO DOCKER - NFSe Scrapper")
    print(f"Python: {sys.version}")
    print(f"Plataforma: {platform.system()} {platform.release()}")
    
    results = []
    
    # 1. Comandos externos
    print_header("Verificando Binários Externos")
    results.append(("Tesseract", check_command('tesseract', 'Tesseract OCR')))
    results.append(("pdfinfo", check_command('pdfinfo', 'Poppler (pdfinfo)')))
    
    # 2. Bibliotecas Python
    results.append(("Python Libs", check_python_imports()))
    
    # 3. Configurações
    results.append(("Settings", check_settings()))
    
    # 4. Integrações
    results.append(("pytesseract", check_tesseract_pytesseract()))
    results.append(("pdf2image", check_pdf2image()))
    
    # 5. Diretórios
    results.append(("Diretórios", check_directories()))
    
    # Resumo final
    print_header("📊 RESUMO")
    
    all_passed = all(result for _, result in results)
    
    for name, result in results:
        status = '✅' if result else '❌'
        print(f"{status} {name}")
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 TODOS OS TESTES PASSARAM!")
        print("O projeto está pronto para rodar no Docker.")
        return 0
    else:
        print("⚠️  ALGUNS TESTES FALHARAM")
        print("Verifique os erros acima antes de fazer o deploy.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
