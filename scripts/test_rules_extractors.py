import sys
import os
import pandas as pd
from pathlib import Path

# Adiciona a raiz do projeto ao path para importar core e config
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from core.processor import BaseInvoiceProcessor

def main():
    # --- CONFIGURAÇÃO DE DEBUG ---
    # Pasta onde estão os arquivos problemáticos (movidos pelo script anterior)
    pasta_entrada = PROJECT_ROOT / "nfs"
    
    # Pasta de saída específica para debug
    pasta_saida = PROJECT_ROOT / "data" / "debug_output"
    arquivo_saida = pasta_saida / "carga_notas_fiscais_debug.csv"
    
    os.makedirs(pasta_saida, exist_ok=True)
    
    print(f"🧪 INICIANDO MODO DE TESTE DE REGRAS")
    print(f"📂 Lendo arquivos de: {pasta_entrada}")
    print(f"💾 Salvando resultados em: {arquivo_saida}")
    print("-" * 50)

    processor = BaseInvoiceProcessor()
    lista_resultados = []
    
    if not pasta_entrada.exists():
        print(f"❌ Pasta de entrada não existe: {pasta_entrada}")
        print("Dica: Rode 'python scripts/move_failed_files.py' primeiro.")
        return

    arquivos = [f for f in os.listdir(pasta_entrada) if f.lower().endswith('.pdf')]
    
    if not arquivos:
        print("⚠️ Nenhum PDF encontrado na pasta de testes.")
        return

    for file in arquivos:
        caminho = os.path.join(pasta_entrada, file)
        print(f"⚙️ Processando: {file}...")
        
        try:
            # Processa usando as regras atuais
            result = processor.process(caminho)
            
            # Adiciona ao relatório
            lista_resultados.append(result.__dict__)
            
            # Feedback visual imediato no terminal
            status_num = "✅" if result.numero_nota else "❌"
            status_val = "✅" if result.valor_total > 0 else "❌"
            print(f"   -> Nota: {result.numero_nota} {status_num} | Valor: {result.valor_total} {status_val}")

        except Exception as e:
            print(f"   ❌ Erro crítico: {e}")

    # Gerar CSV de Debug
    if lista_resultados:
        df = pd.DataFrame(lista_resultados)
        # Usa vírgula como separador, igual ao arquivo final
        df.to_csv(arquivo_saida, index=False, sep=',', encoding='utf-8-sig')
        print("-" * 50)
        print(f"🚀 Teste concluído! Verifique o CSV: {arquivo_saida}")
    else:
        print("Nenhum resultado gerado.")

if __name__ == "__main__":
    main()