import sys
import pandas as pd
from pathlib import Path

# Adiciona a raiz do projeto ao path para garantir que os caminhos funcionem
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

def analyze_failures():
    # Caminhos relativos à raiz do projeto
    csv_path = PROJECT_ROOT / "data" / "output" / "relatorio_ingestao.csv"
    output_log = PROJECT_ROOT / "data" / "output" / "diagnostico_falhas.txt"
    
    if not csv_path.exists():
        print(f"❌ Arquivo de relatório não encontrado em: {csv_path}")
        return

    # Redireciona o print para o arquivo e para o console
    class Tee(object):
        def __init__(self, *files):
            self.files = files
        def write(self, obj):
            for f in self.files:
                f.write(obj)
        def flush(self):
            for f in self.files:
                f.flush()

    output_log.parent.mkdir(parents=True, exist_ok=True)
    
    f_log = open(output_log, 'w', encoding='utf-8')
    original_stdout = sys.stdout
    sys.stdout = Tee(sys.stdout, f_log)

    try:
        df = pd.read_csv(csv_path, dtype={'numero_nota': str})
        
        falhas = df[
            (df['numero_nota'].isna()) | 
            (df['numero_nota'] == '') | 
            (df['valor_total'] == 0.0) | 
            (df['valor_total'].isna())
        ]

        print(f"=== RELATÓRIO DE DIAGNÓSTICO DE FALHAS ===")
        print(f"Data da análise: {pd.Timestamp.now()}\n")

        if falhas.empty:
            print("✅ Nenhuma falha crítica encontrada!")
        else:
            print(f"⚠️ Encontradas {len(falhas)} linhas com problemas de extração:\n")
            
            for _, row in falhas.iterrows():
                arquivo = row['arquivo_origem']
                num = row['numero_nota'] if pd.notna(row['numero_nota']) else "VAZIO"
                val = row['valor_total']
                texto_snippet = str(row['texto_bruto'])[:150].replace('\n', ' ')
                
                print(f"📄 Arquivo: {arquivo}")
                print(f"   ❌ Status: Nota: {num} | Valor: {val}")
                print(f"   👀 Texto (Início): {texto_snippet}...")
                
                if "boleto" in arquivo.lower() or "recibo" in arquivo.lower():
                    print("   💡 Diagnóstico: BOLETO/RECIBO (Ignorar se não for NF).")
                elif "locação" in texto_snippet.lower():
                    print("   💡 Diagnóstico: LOCAÇÃO (Layout atípico).")
                elif pd.isna(val) or val == 0.0:
                    print("   🔧 Ação: Regex de VALOR falhou.")
                elif num == "VAZIO":
                    print("   🔧 Ação: Regex de NÚMERO DA NOTA falhou.")
                
                print("-" * 60)
                
        print(f"\nRelatório salvo em: {output_log}")

    except Exception as e:
        print(f"Erro durante a análise: {e}")
    finally:
        sys.stdout = original_stdout
        f_log.close()

if __name__ == "__main__":
    analyze_failures()