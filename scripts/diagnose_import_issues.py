import sys
import os
import traceback

print("🔍 DIAGNÓSTICO DE ERRO DE IMPORTAÇÃO - CarrierTelecomExtractor")
print("=" * 80)

# 1. Verificar diretório atual e sys.path
print("\n1. SYS.PATH E DIRETÓRIO ATUAL:")
print(f"   Diretório atual: {os.getcwd()}")
print(f"   Número de paths em sys.path: {len(sys.path)}")
print("\n   Primeiros 5 paths:")
for i, path in enumerate(sys.path[:5]):
    print(f"   {i + 1}. {path}")

# 2. Verificar se o diretório atual está no sys.path
current_dir = os.getcwd()
if current_dir not in sys.path:
    print(f"\n   ⚠️  Diretório atual NÃO está em sys.path")
    print(f"   Adicionando {current_dir} ao sys.path...")
    sys.path.insert(0, current_dir)
else:
    print(f"\n   ✅ Diretório atual JÁ está em sys.path")

# 3. Verificar estrutura de diretórios
print("\n2. ESTRUTURA DE DIRETÓRIOS:")
project_root = current_dir
print(f"   Diretório raiz do projeto: {project_root}")

# Verificar se existe o diretório extractors
extractors_dir = os.path.join(project_root, "extractors")
if os.path.exists(extractors_dir):
    print(f"   ✅ Diretório 'extractors' existe: {extractors_dir}")

    # Listar arquivos no diretório extractors
    try:
        files = os.listdir(extractors_dir)
        print(f"   Arquivos em extractors/ ({len(files)}):")
        py_files = [f for f in files if f.endswith(".py")]
        for i, f in enumerate(py_files[:10]):  # Mostrar primeiros 10
            print(f"     • {f}")
        if len(py_files) > 10:
            print(f"     • ... e mais {len(py_files) - 10} arquivos .py")
    except Exception as e:
        print(f"   ❌ Erro ao listar extractors/: {e}")
else:
    print(f"   ❌ Diretório 'extractors' NÃO existe!")

# 4. Tentar importação gradual
print("\n3. TESTANDO IMPORTAÇÕES:")

# Primeiro, tentar importar o módulo completo
print("\n   a) Tentando importar extractors.carrier_telecom...")
try:
    import extractors.carrier_telecom

    print("   ✅ extractors.carrier_telecom importado com sucesso!")

    # Tentar importar a classe
    print("\n   b) Tentando importar CarrierTelecomExtractor...")
    try:
        from extractors.carrier_telecom import CarrierTelecomExtractor

        print("   ✅ CarrierTelecomExtractor importado com sucesso!")

        # Testar instanciação
        print("\n   c) Tentando instanciar CarrierTelecomExtractor...")
        try:
            extractor = CarrierTelecomExtractor()
            print("   ✅ CarrierTelecomExtractor instanciado com sucesso!")
        except Exception as e:
            print(f"   ❌ Erro ao instanciar CarrierTelecomExtractor: {e}")
            print(f"   Traceback:")
            traceback.print_exc()

    except ImportError as e:
        print(f"   ❌ Erro ao importar CarrierTelecomExtractor: {e}")
        print(f"   Traceback:")
        traceback.print_exc()

except ImportError as e:
    print(f"   ❌ Erro ao importar um extrator específico: {e}")
    print(f"   Traceback:")
    traceback.print_exc()

    # Tentar verificar o arquivo diretamente
    print("\n   d) Verificando arquivos de extratores...")
    # Verificar alguns extratores comuns
    common_extractors = ["energy_bill.py", "nfse_generic.py", "boleto.py"]
    for ext_file in common_extractors:
        ext_path = os.path.join(extractors_dir, ext_file)
        if os.path.exists(ext_path):
            print(f"   ✅ {ext_file} existe: {ext_path}")
        else:
            print(f"   ⚠️  {ext_file} não encontrado")

# 5. Verificar outras importações que possam estar causando problemas
print("\n4. VERIFICANDO DEPENDÊNCIAS:")

# Listar imports comuns que podem estar faltando
dependencies = [
    "logging",
    "re",
    "typing",
    "core.extractors",
    "extractors.utils",
]

for dep in dependencies:
    try:
        if "." in dep:
            # Tentar importar módulo com partes
            parts = dep.split(".")
            module = __import__(parts[0])
            for part in parts[1:]:
                module = getattr(module, part)
            print(f"   ✅ {dep} disponível")
        else:
            __import__(dep)
            print(f"   ✅ {dep} disponível")
    except ImportError as e:
        print(f"   ❌ {dep} NÃO disponível: {e}")
    except Exception as e:
        print(f"   ⚠️  {dep} erro inesperado: {e}")

# 6. Verificar se há arquivo __init__.py
print("\n5. VERIFICANDO ARQUIVOS __init__.py:")
init_files_to_check = [
    os.path.join(project_root, "__init__.py"),
    os.path.join(extractors_dir, "__init__.py"),
]

for init_file in init_files_to_check:
    if os.path.exists(init_file):
        print(f"   ✅ {init_file} existe")
    else:
        print(f"   ⚠️  {init_file} NÃO existe (pode ser necessário)")

# 7. Sugestões de correção
print("\n6. SUGESTÕES DE CORREÇÃO:")
print("=" * 80)

print("\nSe houver erros de importação, tente as seguintes soluções:")
print("""
1. Certifique-se de que o diretório raiz do projeto está no PYTHONPATH:
   - No terminal: export PYTHONPATH=/caminho/para/scrapper:$PYTHONPATH
   - No script: sys.path.insert(0, '/caminho/para/scrapper')

2. Verifique se os arquivos __init__.py existem:
   - scrapper/__init__.py (opcional, mas recomendado)
   - scrapper/extractors/__init__.py (necessário para importações)

3. Verifique se há erros de sintaxe no arquivo carrier_telecom.py:
   - Execute: python -m py_compile extractors/carrier_telecom.py

4. Se estiver usando ambiente virtual, certifique-se de que está ativado:
   - Windows: .venv\\Scripts\\activate
   - Linux/Mac: source .venv/bin/activate

5. Verifique dependências instaladas:
   - pip install -r requirements.txt

6. Para testar importação direta no Python:
   - cd /caminho/para/scrapper
   - python -c "from extractors.carrier_telecom import CarrierTelecomExtractor; print('OK')"
""")

print("\n" + "=" * 80)
print("📁 DIAGNÓSTICO CONCLUÍDO")
print("=" * 80)
