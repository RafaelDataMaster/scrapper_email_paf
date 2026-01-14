#!/usr/bin/env python
"""
Script de limpeza para desenvolvimento.

Limpa todos os dados temporários para permitir rodar run_ingestion.py do zero:
- temp_email/ (emails baixados e checkpoints)
- data/output/ (relatórios gerados)
- logs/ (arquivos de log)

Uso:
    python scripts/clean_dev.py
"""

import shutil
import sys
from pathlib import Path

# Configura path para imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))


# Arquivos para preservar (não são dados de ingestão)
PRESERVE_FILES = {
    ".gitkeep",
    "inbox_patterns.json",
    "inbox_patterns_stats.json",
    "inbox_body.json"
}


def clean_directory(path: Path, preserve_files: set = PRESERVE_FILES) -> int:
    """
    Limpa conteúdo de um diretório.

    Args:
        path: Caminho do diretório
        preserve_files: Conjunto de nomes de arquivos para preservar

    Returns:
        Número de itens removidos
    """
    if not path.exists():
        print(f"  ⚠️  {path} não existe, pulando...")
        return 0

    removed = 0
    for item in path.iterdir():
        if item.name in preserve_files:
            print(f"  ⏭️  Preservando {item.name}")
            continue

        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed += 1
        except Exception as e:
            print(f"  ❌ Erro ao remover {item}: {e}")

    return removed


def main():
    print("🧹 Limpeza de desenvolvimento")
    print("=" * 50)

    # Diretórios para limpar
    dirs_to_clean = [
        PROJECT_ROOT / "temp_email",
        PROJECT_ROOT / "data" / "output",
        PROJECT_ROOT / "data" / "debug_output",
        PROJECT_ROOT / "logs",
    ]

    total_removed = 0

    for dir_path in dirs_to_clean:
        print(f"\n📁 Limpando {dir_path.relative_to(PROJECT_ROOT)}/")
        removed = clean_directory(dir_path)
        total_removed += removed
        print(f"  ✅ {removed} itens removidos")

    print("\n" + "=" * 50)
    print(f"🎉 Limpeza concluída! {total_removed} itens removidos no total.")
    print("\nAgora você pode rodar: python run_ingestion.py")


if __name__ == "__main__":
    main()
