import sys
import shutil
import pandas as pd
from pathlib import Path

# Adiciona a raiz do projeto ao path para importar config
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from config import settings

def move_failed_files():
    csv_path = settings.DIR_SAIDA / "relatorio_ingestao.csv"
    # Destino: Pasta 'nfs' na raiz do projeto (para análise manual)
    target_dir = PROJECT_ROOT / "nfs"
    source_dir = settings.DIR_TEMP
    
    if not csv_path.exists():
        print("❌ Relatório CSV não encontrado.")
        return

    target_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path, dtype={'numero_nota': str})
    
    falhas = df[
        (df['numero_nota'].isna()) | 
        (df['numero_nota'] == '') | 
        (df['valor_total'] == 0.0) | 
        (df['valor_total'].isna())
    ]

    if falhas.empty:
        print("✅ Nenhuma falha para mover.")
        return

    print(f"📦 Movendo {len(falhas)} arquivos problemáticos para: {target_dir}")
    
    moved_count = 0
    for _, row in falhas.iterrows():
        filename = row['arquivo_origem']
        src_file = source_dir / filename
        dst_file = target_dir / filename
        
        if src_file.exists():
            shutil.copy2(src_file, dst_file)
            moved_count += 1
        else:
            print(f"⚠️ Arquivo não encontrado na origem: {filename}")

    print(f"\n🏁 Concluído! {moved_count} arquivos copiados para análise em '{target_dir}'.")

if __name__ == "__main__":
    move_failed_files()