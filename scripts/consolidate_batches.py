"""
Script para consolidar lotes de email pelo assunto.

Este script corrige o problema de emails que foram ingeridos de forma errada,
onde cada anexo criou um lote separado ao invés de agrupar todos os anexos
do mesmo email em um único lote.

O script:
1. Lê todos os metadata.json das pastas em temp_email
2. Agrupa as pastas pelo assunto do email (email_subject)
3. Para cada grupo com mais de 1 pasta:
   - Cria uma nova pasta consolidada
   - Move todos os arquivos para a nova pasta
   - Atualiza o metadata.json com a lista completa de anexos
   - Remove as pastas originais

Uso:
    # Ver o que seria feito (dry-run)
    python scripts/consolidate_batches.py --dry-run

    # Executar consolidação
    python scripts/consolidate_batches.py

    # Especificar pasta diferente
    python scripts/consolidate_batches.py --source-dir temp_email_backup
"""

import argparse
import json
import shutil
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings


def load_metadata(batch_folder: Path) -> Optional[dict]:
    """Carrega metadata.json de uma pasta de lote."""
    metadata_path = batch_folder / "metadata.json"
    if not metadata_path.exists():
        return None

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  ⚠️ Erro ao ler {metadata_path}: {e}")
        return None


def get_attachment_files(batch_folder: Path) -> List[Path]:
    """Retorna lista de arquivos de anexo (excluindo metadata.json e pastas)."""
    files = []
    for item in batch_folder.iterdir():
        if item.is_file() and item.name != "metadata.json":
            files.append(item)
    return files


def generate_batch_id() -> str:
    """Gera ID único para o lote consolidado."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    short_uuid = uuid.uuid4().hex[:8]
    return f"email_{timestamp}_{short_uuid}"


def consolidate_batches(
    source_dir: Path,
    dry_run: bool = True,
    verbose: bool = True
) -> dict:
    """
    Consolida lotes de email pelo assunto.

    Args:
        source_dir: Diretório com as pastas de lote
        dry_run: Se True, apenas mostra o que seria feito
        verbose: Se True, mostra detalhes

    Returns:
        Dict com estatísticas da operação
    """
    stats = {
        "total_batches": 0,
        "groups_found": 0,
        "groups_to_consolidate": 0,
        "batches_consolidated": 0,
        "files_moved": 0,
        "batches_removed": 0,
        "errors": [],
    }

    # 1. Encontra todas as pastas de lote
    batch_folders = [
        d for d in source_dir.iterdir()
        if d.is_dir() and d.name.startswith("email_")
    ]
    stats["total_batches"] = len(batch_folders)

    if verbose:
        print(f"\n📂 Encontradas {len(batch_folders)} pastas de lote em {source_dir}")

    # 2. Agrupa por assunto do email
    groups: Dict[str, List[Tuple[Path, dict]]] = defaultdict(list)

    for folder in batch_folders:
        metadata = load_metadata(folder)
        if metadata:
            subject = metadata.get("email_subject", "") or ""
            # Normaliza o assunto para agrupamento (remove espaços extras)
            normalized_subject = " ".join(subject.split())
            groups[normalized_subject].append((folder, metadata))

    stats["groups_found"] = len(groups)

    # 3. Identifica grupos que precisam ser consolidados (mais de 1 pasta)
    groups_to_consolidate = {
        subject: folders
        for subject, folders in groups.items()
        if len(folders) > 1
    }
    stats["groups_to_consolidate"] = len(groups_to_consolidate)

    if verbose:
        print(f"📊 {len(groups)} assuntos únicos encontrados")
        print(f"🔄 {len(groups_to_consolidate)} grupos precisam consolidação")

    if not groups_to_consolidate:
        print("\n✅ Nenhuma consolidação necessária!")
        return stats

    # 4. Mostra detalhes dos grupos
    print("\n" + "=" * 60)
    print("GRUPOS A CONSOLIDAR:")
    print("=" * 60)

    for subject, folders in groups_to_consolidate.items():
        display_subject = subject[:60] + "..." if len(subject) > 60 else subject
        print(f"\n📧 {display_subject}")
        print(f"   {len(folders)} pastas encontradas:")

        total_attachments = []
        for folder, metadata in folders:
            attachments = metadata.get("attachments", [])
            total_attachments.extend(attachments)
            print(f"   - {folder.name}: {len(attachments)} anexo(s)")
            for att in attachments:
                print(f"     • {att}")

        print(f"   → Total de anexos a consolidar: {len(total_attachments)}")

    # 5. Se dry-run, para aqui
    if dry_run:
        print("\n" + "=" * 60)
        print("🔍 MODO DRY-RUN - Nenhuma alteração foi feita")
        print("   Execute sem --dry-run para aplicar as mudanças")
        print("=" * 60)
        return stats

    # 6. Executa consolidação
    print("\n" + "=" * 60)
    print("🔧 EXECUTANDO CONSOLIDAÇÃO...")
    print("=" * 60)

    for subject, folders in groups_to_consolidate.items():
        display_subject = subject[:50] + "..." if len(subject) > 50 else subject
        print(f"\n📧 Consolidando: {display_subject}")

        try:
            # Usa o primeiro folder como base para metadados
            _, base_metadata = folders[0]

            # Cria nova pasta consolidada
            new_batch_id = generate_batch_id()
            new_folder = source_dir / new_batch_id
            new_folder.mkdir(parents=True, exist_ok=True)
            print(f"   📁 Nova pasta: {new_batch_id}")

            # Coleta todos os anexos
            all_attachments = []
            file_counter = 1

            for folder, metadata in folders:
                files = get_attachment_files(folder)

                for file_path in files:
                    # Renomeia com prefixo numérico
                    new_filename = f"{file_counter:02d}_{file_path.name.lstrip('0123456789_')}"
                    new_path = new_folder / new_filename

                    # Move arquivo
                    shutil.copy2(file_path, new_path)
                    all_attachments.append(new_filename)
                    file_counter += 1
                    stats["files_moved"] += 1
                    print(f"   📄 {file_path.name} → {new_filename}")

            # Cria novo metadata.json consolidado
            new_metadata = {
                "batch_id": new_batch_id,
                "email_subject": base_metadata.get("email_subject"),
                "email_sender_name": base_metadata.get("email_sender_name"),
                "email_sender_address": base_metadata.get("email_sender_address"),
                "email_body_text": base_metadata.get("email_body_text"),
                "received_date": base_metadata.get("received_date"),
                "attachments": all_attachments,
                "created_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
                "extra": {
                    "consolidated_from": [f.name for f, _ in folders],
                    "consolidation_date": datetime.now().isoformat(),
                }
            }

            metadata_path = new_folder / "metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(new_metadata, f, indent=2, ensure_ascii=False)

            print(f"   ✅ Consolidado {len(all_attachments)} anexos")
            stats["batches_consolidated"] += 1

            # Remove pastas originais
            for folder, _ in folders:
                shutil.rmtree(folder)
                stats["batches_removed"] += 1
                print(f"   🗑️ Removida: {folder.name}")

        except Exception as e:
            error_msg = f"Erro ao consolidar '{subject}': {e}"
            stats["errors"].append(error_msg)
            print(f"   ❌ {error_msg}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Consolida lotes de email pelo assunto",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Ver o que seria feito (recomendado primeiro)
  python scripts/consolidate_batches.py --dry-run

  # Executar consolidação
  python scripts/consolidate_batches.py

  # Usar pasta diferente
  python scripts/consolidate_batches.py --source-dir temp_email_backup
        """
    )

    parser.add_argument(
        '--source-dir',
        type=str,
        default=str(settings.DIR_TEMP),
        help=f'Diretório com as pastas de lote (padrão: {settings.DIR_TEMP})'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Apenas mostra o que seria feito, sem alterar nada'
    )

    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Modo silencioso (menos output)'
    )

    args = parser.parse_args()

    source_dir = Path(args.source_dir)

    if not source_dir.exists():
        print(f"❌ Diretório não encontrado: {source_dir}")
        sys.exit(1)

    print("=" * 60)
    print("🔧 CONSOLIDAÇÃO DE LOTES DE EMAIL")
    print("=" * 60)
    print(f"📂 Diretório: {source_dir}")
    print(f"🔍 Modo: {'DRY-RUN (simulação)' if args.dry_run else 'EXECUÇÃO REAL'}")

    if not args.dry_run:
        print("\n⚠️  ATENÇÃO: Este script irá mover arquivos e deletar pastas!")
        response = input("   Deseja continuar? (s/N): ")
        if response.lower() != 's':
            print("   Operação cancelada.")
            sys.exit(0)

    # Executa consolidação
    stats = consolidate_batches(
        source_dir=source_dir,
        dry_run=args.dry_run,
        verbose=not args.quiet
    )

    # Mostra resumo
    print("\n" + "=" * 60)
    print("📊 RESUMO:")
    print("=" * 60)
    print(f"   Total de pastas analisadas: {stats['total_batches']}")
    print(f"   Grupos únicos (por assunto): {stats['groups_found']}")
    print(f"   Grupos que precisavam consolidação: {stats['groups_to_consolidate']}")

    if not args.dry_run:
        print(f"   Lotes consolidados: {stats['batches_consolidated']}")
        print(f"   Arquivos movidos: {stats['files_moved']}")
        print(f"   Pastas removidas: {stats['batches_removed']}")

        if stats['errors']:
            print(f"\n   ⚠️ Erros encontrados: {len(stats['errors'])}")
            for error in stats['errors']:
                print(f"      - {error}")

    print("=" * 60)

    if args.dry_run and stats['groups_to_consolidate'] > 0:
        print("\n💡 Para executar a consolidação, rode sem --dry-run")


if __name__ == "__main__":
    main()
