import re
import sys
import argparse
from pathlib import Path


def analyze_report(file_path: str) -> dict:
    """
    Analyze the detailed PDF analysis report and extract statistics.

    Args:
        file_path: Path to the analise_pdfs_detalhada.txt file

    Returns:
        Dictionary containing various statistics about the report
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        return {}
    except Exception as e:
        print(f"Error reading file: {e}")
        return {}

    # Split by case delimiter (80 hyphens)
    cases = re.split(r"^-{80}", content, flags=re.MULTILINE)

    # Initialize statistics
    stats = {
        "total_cases": len(cases) - 1,  # Subtract header
        "severity": {"ALTA": 0, "MEDIA": 0, "BAIXA": 0},
        "issues": {
            "value": 0,
            "vencimento": 0,
            "fornecedor": 0,
            "numero_nota": 0,
            "extractor_identification": 0,
            "data_validation": 0,
        },
        "classification": {
            "unknown": 0,
            "nfse": 0,
            "administrativos": 0,
            "boleto": 0,
        },
        "action_recommended": {
            "investigar_manualmente": 0,
            "melhorar_extracao": 0,
            "corrigir_valores": 0,
        },
    }

    for case in cases[1:]:  # Skip first part (header)
        # Severity
        severity_match = re.search(r"Nível de severidade:\s*(\w+)", case)
        if severity_match:
            sev = severity_match.group(1).upper()
            if sev in stats["severity"]:
                stats["severity"][sev] += 1

        # Issues
        if "Valor Issues:" in case:
            stats["issues"]["value"] += 1
        if "Vencimento Issues:" in case:
            stats["issues"]["vencimento"] += 1
        if "Fornecedor Issues:" in case:
            stats["issues"]["fornecedor"] += 1
        if "Numero Nota Issues:" in case:
            stats["issues"]["numero_nota"] += 1
        if "Extrator Identification Issues:" in case:
            stats["issues"]["extractor_identification"] += 1
        if "Data Validation Issues:" in case:
            stats["issues"]["data_validation"] += 1

        # Classification
        if "Classificação primária: DESCONHECIDO" in case:
            stats["classification"]["unknown"] += 1
        elif "Classificação primária: NFSE" in case:
            stats["classification"]["nfse"] += 1
        elif "Classificação primária:" in case and "administrativos" in case:
            stats["classification"]["administrativos"] += 1
        elif "Classificação primária: BOLETO" in case:
            stats["classification"]["boleto"] += 1

        # Action recommended
        if "Ação recomendada: INVESTIGAR_MANUALMENTE" in case:
            stats["action_recommended"]["investigar_manualmente"] += 1
        elif "Ação recomendada: MELHORAR_EXTRACAO" in case:
            stats["action_recommended"]["melhorar_extracao"] += 1
        elif "Ação recomendada: CORRIGIR_VALORES" in case:
            stats["action_recommended"]["corrigir_valores"] += 1

    return stats


def print_statistics(stats: dict):
    """Print statistics in a formatted way."""
    if not stats:
        print("No statistics to display.")
        return

    print("=" * 60)
    print("ANÁLISE ESTATÍSTICA DO RELATÓRIO DE PDFs PROBLEMÁTICOS")
    print("=" * 60)

    print(f"\n📊 CASOS ANALISADOS: {stats['total_cases']}")

    print("\n🔴 NÍVEL DE SEVERIDADE:")
    for sev, count in stats["severity"].items():
        percentage = (
            (count / stats["total_cases"] * 100) if stats["total_cases"] > 0 else 0
        )
        print(f"  {sev}: {count} ({percentage:.1f}%)")

    print("\n⚠️  PROBLEMAS IDENTIFICADOS:")
    for issue, count in stats["issues"].items():
        issue_name = issue.replace("_", " ").title()
        percentage = (
            (count / stats["total_cases"] * 100) if stats["total_cases"] > 0 else 0
        )
        print(f"  • {issue_name}: {count} ({percentage:.1f}%)")

    print("\n🏷️  CLASSIFICAÇÃO DOS DOCUMENTOS:")
    for cls, count in stats["classification"].items():
        cls_name = cls.replace("_", " ").title()
        percentage = (
            (count / stats["total_cases"] * 100) if stats["total_cases"] > 0 else 0
        )
        print(f"  • {cls_name}: {count} ({percentage:.1f}%)")

    print("\n🚀 AÇÕES RECOMENDADAS:")
    for action, count in stats["action_recommended"].items():
        action_name = action.replace("_", " ").title()
        percentage = (
            (count / stats["total_cases"] * 100) if stats["total_cases"] > 0 else 0
        )
        print(f"  • {action_name}: {count} ({percentage:.1f}%)")

    # Calculate some summary metrics
    print("\n📈 MÉTRICAS DE RESUMO:")
    if stats["total_cases"] > 0:
        high_severity_pct = stats["severity"]["ALTA"] / stats["total_cases"] * 100
        value_issues_pct = stats["issues"]["value"] / stats["total_cases"] * 100
        unknown_class_pct = (
            stats["classification"]["unknown"] / stats["total_cases"] * 100
        )

        print(f"  • Casos de alta severidade: {high_severity_pct:.1f}%")
        print(f"  • Problemas com valores: {value_issues_pct:.1f}%")
        print(f"  • Documentos não classificados: {unknown_class_pct:.1f}%")
        print(
            f"  • Problemas com vencimento: {(stats['issues']['vencimento'] / stats['total_cases'] * 100):.1f}%"
        )

    print("\n" + "=" * 60)


def main():
    """Main function to run the analysis."""
    parser = argparse.ArgumentParser(
        description="Analyze detailed PDF analysis report and extract statistics"
    )
    parser.add_argument(
        "--input",
        default="data/output/analise_pdfs_detalhada.txt",
        help="Path to the analysis report file (default: data/output/analise_pdfs_detalhada.txt)",
    )
    parser.add_argument("--output", help="Optional JSON output file to save statistics")

    args = parser.parse_args()

    # Check if input file exists
    if not Path(args.input).exists():
        print(f"Error: Input file not found: {args.input}")
        print("Please specify a valid file path with --input")
        return 1

    print(f"Analyzing report: {args.input}")
    stats = analyze_report(args.input)

    if stats:
        print_statistics(stats)

        # Save to JSON if requested
        if args.output:
            import json

            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(stats, f, indent=2, ensure_ascii=False)
                print(f"\nStatistics saved to: {args.output}")
            except Exception as e:
                print(f"Error saving to JSON: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
