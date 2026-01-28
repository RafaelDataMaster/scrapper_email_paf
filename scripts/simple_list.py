#!/usr/bin/env python3
"""
Script simples para listar IDs de lotes problemáticos.

Identifica casos onde:
- outros > 0 (documentos classificados como administrativos)
- valor_compra = 0 (nenhum valor extraído)

Saída: Lista de batch IDs para reprocessamento
"""

import csv

import sys
from pathlib import Path


def extract_batch_id(source_folder: str) -> str:
    """
    Extrai o batch ID do caminho da pasta fonte.

    Args:
        source_folder: Caminho completo da pasta (ex: 'C:\\Users\\...\\temp_email\\email_xxx')

    Returns:
        Nome da pasta (batch ID)
    """
    if not source_folder:
        return "DESCONHECIDO"

    # Normaliza separadores de caminho e pega o último componente
    normalized = source_folder.replace("\\", "/")
    parts = normalized.split("/")
    return parts[-1] if parts else "DESCONHECIDO"


def list_problematic_batches():
    """Lista todos os lotes problemáticos."""
    # Configurar caminhos - ir para diretório raiz do projeto
    base_dir = Path(__file__).parent.parent  # Ir para scrapper/
    csv_path = base_dir / "data" / "output" / "relatorio_lotes.csv"

    if not csv_path.exists():
        print(f"Erro: Arquivo não encontrado: {csv_path}")
        sys.exit(1)

    print("=" * 80)
    print("LISTA SIMPLES DE LOTES PROBLEMÁTICOS")
    print("=" * 80)

    problematic_batches = []

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            # Detectar delimitador
            sample = f.readline()
            f.seek(0)

            delimiter = ";" if ";" in sample else ","
            reader = csv.DictReader(f, delimiter=delimiter)

            for row in reader:
                # Normalizar nomes de colunas
                row = {k.strip(): v for k, v in row.items()}

                # Contar documentos 'outros'
                outros_str = row.get("outros", "0")
                outros = int(outros_str) if outros_str.strip() else 0

                # Converter valor brasileiro para float
                valor_str = row.get("valor_compra", "0")
                if valor_str:
                    valor_str = valor_str.replace(".", "").replace(",", ".")
                    try:
                        valor = float(valor_str)
                    except ValueError:
                        valor = 0.0
                else:
                    valor = 0.0

                # Critério: outros > 0 e valor == 0
                if outros > 0 and valor == 0:
                    batch_id = extract_batch_id(row.get("source_folder", ""))
                    subject = row.get("email_subject", "")[:60]

                    problematic_batches.append(
                        {
                            "batch_id": batch_id,
                            "subject": subject,
                            "outros": outros,
                            "valor": valor,
                            "status": row.get("status_conciliacao", ""),
                            "divergencia": row.get("divergencia", "")[:60] + "..."
                            if len(row.get("divergencia", "")) > 60
                            else row.get("divergencia", ""),
                        }
                    )

        # Exibir resultados
        print(f"\nTotal encontrado: {len(problematic_batches)} lotes")
        print("\nLISTA DE BATCH IDs:")
        print("-" * 80)

        for i, batch in enumerate(problematic_batches, 1):
            print(f"{i:2d}. {batch['batch_id']}")

        print("\n" + "=" * 80)
        print("COMANDOS PARA REPROCESSAR:")
        print("=" * 80)

        # Comandos individuais
        print("\n1. Comandos individuais (um por lote):")
        for batch in problematic_batches[:5]:  # Mostrar só 5 para não poluir
            if batch["batch_id"] != "DESCONHECIDO":
                print(
                    f"   python run_ingestion.py --folder temp_email/{batch['batch_id']}"
                )

        if len(problematic_batches) > 5:
            print(f"   ... e mais {len(problematic_batches) - 5} lotes")

        # Comando para todos
        if problematic_batches:
            valid_batches = [
                b["batch_id"]
                for b in problematic_batches
                if b["batch_id"] != "DESCONHECIDO"
            ]
            if valid_batches:
                print(f"\n2. Comando para todos ({len(valid_batches)} lotes):")
                folders = " ".join([f"temp_email/{bid}" for bid in valid_batches])
                print(f"   python run_ingestion.py --folder {folders}")

        # Detalhes completos (opcional)
        print("\n" + "=" * 80)
        print("DETALHES COMPLETOS:")
        print("=" * 80)

        for i, batch in enumerate(problematic_batches, 1):
            print(f"\n{i:2d}. {batch['batch_id']}")
            print(f"    Assunto: {batch['subject']}")
            print(f"    Outros: {batch['outros']}, Valor: R$ {batch['valor']:.2f}")
            print(f"    Status: {batch['status']}")
            print(f"    Divergência: {batch['divergencia']}")

        # Salvar lista em arquivo
        output_dir = Path(__file__).parent.parent / "data" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "lotes_problematicos_simples.txt"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"Total de lotes problemáticos: {len(problematic_batches)}\n")
            f.write("=" * 60 + "\n\n")
            for batch in problematic_batches:
                f.write(f"{batch['batch_id']}\n")
                f.write(f"  Assunto: {batch['subject']}\n")
                f.write(f"  Status: {batch['status']}\n")
                f.write(f"  Valor: R$ {batch['valor']:.2f}\n\n")

        print(f"\n✅ Lista salva em: {output_path}")

    except FileNotFoundError:
        print(f"Erro: Arquivo não encontrado: {csv_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Erro ao processar CSV: {e}")
        sys.exit(1)


if __name__ == "__main__":
    list_problematic_batches()
