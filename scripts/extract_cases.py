#!/usr/bin/env python3
"""
Script para extrair casos específicos do relatório de análise de PDFs problemáticos.

Este script lê o arquivo de relatório detalhado e permite extrair casos
individuais ou filtrados por diversos critérios como severidade, classificação,
ou presença de problemas específicos.

Uso:
    python extract_cases.py --input data/output/analise_pdfs_detalhada.txt --case 1
    python extract_cases.py --input data/output/analise_pdfs_detalhada.txt --severity ALTA
    python extract_cases.py --input data/output/analise_pdfs_detalhada.txt --classification DESCONHECIDO
    python extract_cases.py --input data/output/analise_pdfs_detalhada.txt --has-issue "Valor Issues"
"""

import re
import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional


def parse_report(file_path: str) -> List[Dict[str, Any]]:
    """
    Parse o arquivo de relatório e extraia todos os casos.

    Args:
        file_path: Caminho para o arquivo de relatório

    Returns:
        Lista de dicionários contendo os dados de cada caso
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Erro: Arquivo não encontrado: {file_path}")
        return []
    except Exception as e:
        print(f"Erro ao ler arquivo: {e}")
        return []

    # Divide o conteúdo em casos usando a linha de 80 hífens como separador
    raw_cases = re.split(r"^-{80}", content, flags=re.MULTILINE)

    # Remove o cabeçalho (primeira parte)
    if raw_cases and "RELATÓRIO DETALHADO" in raw_cases[0]:
        raw_cases = raw_cases[1:]

    cases = []
    for raw_case in raw_cases:
        if not raw_case.strip():
            continue

        case_data = {
            "raw_text": raw_case.strip(),
            "id": None,
            "severity": None,
            "classification": None,
            "action_recommended": None,
            "issues": [],
        }

        # Extrai ID do caso
        id_match = re.search(r"^CASO #(\d+)", raw_case, re.MULTILINE)
        if id_match:
            case_data["id"] = int(id_match.group(1))

        # Extrai severidade
        severity_match = re.search(r"Nível de severidade:\s*(\w+)", raw_case)
        if severity_match:
            case_data["severity"] = severity_match.group(1).upper()

        # Extrai classificação primária
        classification_match = re.search(r"Classificação primária:\s*(\w+)", raw_case)
        if classification_match:
            case_data["classification"] = classification_match.group(1).upper()

        # Extrai ação recomendada
        action_match = re.search(r"Ação recomendada:\s*(\w+)", raw_case)
        if action_match:
            case_data["action_recommended"] = action_match.group(1).upper()

        # Detecta tipos de problemas
        issues = []
        if "Valor Issues:" in raw_case:
            issues.append("VALOR")
        if "Vencimento Issues:" in raw_case:
            issues.append("VENCIMENTO")
        if "Fornecedor Issues:" in raw_case:
            issues.append("FORNECEDOR")
        if "Numero Nota Issues:" in raw_case:
            issues.append("NUMERO_NOTA")
        if "Extrator Identification Issues:" in raw_case:
            issues.append("EXTRATOR_ID")
        if "Data Validation Issues:" in raw_case:
            issues.append("DATA_VALIDATION")

        case_data["issues"] = issues
        cases.append(case_data)

    return cases


def extract_case_by_id(
    cases: List[Dict[str, Any]], case_id: int
) -> Optional[Dict[str, Any]]:
    """
    Encontra um caso específico pelo ID.

    Args:
        cases: Lista de casos
        case_id: ID do caso desejado

    Returns:
        Dicionário do caso ou None se não encontrado
    """
    for case in cases:
        if case["id"] == case_id:
            return case
    return None


def filter_cases(
    cases: List[Dict[str, Any]],
    severity: Optional[str] = None,
    classification: Optional[str] = None,
    has_issue: Optional[str] = None,
    min_id: Optional[int] = None,
    max_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Filtra casos com base em múltiplos critérios.

    Args:
        cases: Lista de casos
        severity: Severidade para filtrar (ALTA, MEDIA, BAIXA)
        classification: Classificação para filtrar
        has_issue: Tipo de problema que deve estar presente
        min_id: ID mínimo (inclusive)
        max_id: ID máximo (inclusive)

    Returns:
        Lista filtrada de casos
    """
    filtered = cases

    if severity:
        filtered = [c for c in filtered if c["severity"] == severity.upper()]

    if classification:
        filtered = [
            c for c in filtered if c["classification"] == classification.upper()
        ]

    if has_issue:
        issue_upper = has_issue.upper()
        filtered = [
            c for c in filtered if issue_upper in [i.upper() for i in c["issues"]]
        ]

    if min_id is not None:
        filtered = [c for c in filtered if c["id"] is not None and c["id"] >= min_id]

    if max_id is not None:
        filtered = [c for c in filtered if c["id"] is not None and c["id"] <= max_id]

    return filtered


def format_case_for_review(case: Dict[str, Any]) -> str:
    """
    Formata um caso no formato do template de análise (review.md).

    Args:
        case: Dicionário contendo os dados do caso

    Returns:
        String formatada no template de análise
    """
    raw_text = case["raw_text"]

    # Extrai informações básicas do caso
    lines = raw_text.split("\n")

    # Tenta extrair o assunto do e-mail
    assunto = ""
    for line in lines:
        if "Assunto do e-mail:" in line:
            assunto = line.replace("Assunto do e-mail:", "").strip()
            break

    # Tenta extrair o nome do PDF
    pdf_name = ""
    for line in lines:
        if "PDF:" in line and "Páginas:" not in line:
            # Formato: "PDF: 01_Comprovante Cheque Pre.pdf"
            pdf_name = line.replace("PDF:", "").strip()
            break

    # Constrói o template
    template = f"""ID: {case["id"]}
ARQUIVO: {pdf_name}
ASSUNTO EMAIL: {assunto}

DADOS EXTRAÍDOS (CSV):
- Tipo: [Extrair do relatório]
- Valor: [Extrair do relatório]
- Vencimento: [Extrair do relatório]
- Fornecedor: [Extrair do relatório]
- Nº Documento: [Extrair do relatório]

CONTEÚDO DO PDF (texto bruto extraído):
[COLE AQUI O TEXTO_EXTRAIDO ou descrição do conteúdo visual]

PROBLEMA REPORTADO:
[Descreva o que está errado: ex: "Valor aparece 0 mas PDF tem R$ 150,00",
ou "Classificado como Desconhecido mas é NFSe"]

ANÁLISE AUTOMÁTICA DO SISTEMA:
Severidade: {case["severity"]}
Classificação: {case["classification"]}
Problemas detectados: {", ".join(case["issues"]) if case["issues"] else "Nenhum"}
Ação recomendada: {case["action_recommended"]}

TEXTO COMPLETO DO CASO:
{"-" * 60}
{raw_text}
{"-" * 60}
"""
    return template


def main():
    parser = argparse.ArgumentParser(
        description="Extrair casos específicos do relatório de análise de PDFs problemáticos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  %(prog)s --input relatorio.txt --case 1
  %(prog)s --input relatorio.txt --severity ALTA --output casos_alta.json
  %(prog)s --input relatorio.txt --classification DESCONHECIDO --format json
  %(prog)s --input relatorio.txt --has-issue "Valor Issues" --min-id 50 --max-id 100
  %(prog)s --input relatorio.txt --list-issues
        """,
    )

    parser.add_argument(
        "--input",
        default="data/output/analise_pdfs_detalhada.txt",
        help="Caminho para o arquivo de relatório (padrão: data/output/analise_pdfs_detalhada.txt)",
    )

    parser.add_argument("--case", type=int, help="ID específico do caso a ser extraído")

    parser.add_argument(
        "--severity", help="Filtrar por severidade (ALTA, MEDIA, BAIXA)"
    )

    parser.add_argument(
        "--classification", help="Filtrar por classificação (DESCONHECIDO, NFSE, etc)"
    )

    parser.add_argument(
        "--has-issue", help="Filtrar por presença de um tipo específico de problema"
    )

    parser.add_argument(
        "--min-id", type=int, help="ID mínimo dos casos a serem incluídos"
    )

    parser.add_argument(
        "--max-id", type=int, help="ID máximo dos casos a serem incluídos"
    )

    parser.add_argument(
        "--output", help="Arquivo de saída (se não especificado, imprime na tela)"
    )

    parser.add_argument(
        "--format",
        choices=["text", "json", "review"],
        default="text",
        help="Formato de saída (padrão: text)",
    )

    parser.add_argument(
        "--list-issues",
        action="store_true",
        help="Listar todos os tipos de problemas encontrados no relatório",
    )

    parser.add_argument(
        "--summary", action="store_true", help="Mostrar um resumo estatístico dos casos"
    )

    args = parser.parse_args()

    # Verifica se o arquivo de entrada existe
    if not Path(args.input).exists():
        print(f"Erro: Arquivo de entrada não encontrado: {args.input}")
        return 1

    # Parse o relatório
    print(f"Analisando relatório: {args.input}")
    cases = parse_report(args.input)

    if not cases:
        print("Nenhum caso encontrado no relatório.")
        return 1

    print(f"Total de casos parseados: {len(cases)}")

    # Listar problemas se solicitado
    if args.list_issues:
        all_issues = set()
        for case in cases:
            all_issues.update(case["issues"])

        print("\nTipos de problemas encontrados no relatório:")
        for issue in sorted(all_issues):
            count = sum(1 for c in cases if issue in c["issues"])
            print(f"  • {issue}: {count} casos ({count / len(cases) * 100:.1f}%)")
        return 0

    # Mostrar resumo se solicitado
    if args.summary:
        severity_counts = {"ALTA": 0, "MEDIA": 0, "BAIXA": 0}
        classification_counts = {}
        issue_counts = {}

        for case in cases:
            if case["severity"] in severity_counts:
                severity_counts[case["severity"]] += 1

            cls = case["classification"] or "DESCONHECIDO"
            classification_counts[cls] = classification_counts.get(cls, 0) + 1

            for issue in case["issues"]:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1

        print("\n📊 RESUMO ESTATÍSTICO:")
        print(f"Total de casos: {len(cases)}")

        print("\n🔴 Severidade:")
        for sev, count in severity_counts.items():
            print(f"  {sev}: {count} ({count / len(cases) * 100:.1f}%)")

        print("\n🏷️  Classificação:")
        for cls, count in sorted(classification_counts.items()):
            print(f"  {cls}: {count} ({count / len(cases) * 100:.1f}%)")

        print("\n⚠️  Problemas mais comuns:")
        for issue, count in sorted(
            issue_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]:
            print(f"  {issue}: {count} ({count / len(cases) * 100:.1f}%)")

        return 0

    # Filtrar casos
    filtered_cases = cases

    if any(
        [
            args.severity,
            args.classification,
            args.has_issue,
            args.min_id is not None,
            args.max_id is not None,
        ]
    ):
        filtered_cases = filter_cases(
            cases,
            severity=args.severity,
            classification=args.classification,
            has_issue=args.has_issue,
            min_id=args.min_id,
            max_id=args.max_id,
        )
        print(f"Casos após filtro: {len(filtered_cases)}")

    # Extrair caso específico se solicitado
    if args.case is not None:
        case = extract_case_by_id(filtered_cases, args.case)
        if not case:
            print(f"Erro: Caso #{args.case} não encontrado.")
            return 1
        filtered_cases = [case]

    if not filtered_cases:
        print("Nenhum caso corresponde aos critérios de filtro.")
        return 0

    # Preparar saída
    output_content = ""

    if args.format == "json":
        # Para JSON, removemos o raw_text se não for necessário (pode ser muito grande)
        json_cases = []
        for case in filtered_cases:
            json_case = {k: v for k, v in case.items() if k != "raw_text"}
            json_cases.append(json_case)
        output_content = json.dumps(json_cases, indent=2, ensure_ascii=False)

    elif args.format == "review":
        for i, case in enumerate(filtered_cases):
            if i > 0:
                output_content += "\n" + "=" * 80 + "\n\n"
            output_content += format_case_for_review(case)

    else:  # formato text
        for case in filtered_cases:
            output_content += f"Caso #{case['id']}\n"
            output_content += f"Severidade: {case['severity']}\n"
            output_content += f"Classificação: {case['classification']}\n"
            output_content += f"Problemas: {', '.join(case['issues']) if case['issues'] else 'Nenhum'}\n"
            output_content += f"Ação recomendada: {case['action_recommended']}\n"
            output_content += "-" * 60 + "\n"
            # Mostra apenas as primeiras linhas do raw_text para evitar sobrecarga
            preview_lines = case["raw_text"].split("\n")[:20]
            output_content += "\n".join(preview_lines)
            if len(case["raw_text"].split("\n")) > 20:
                output_content += "\n[... conteúdo truncado ...]\n"
            output_content += "\n" + "=" * 80 + "\n\n"

    # Escrever saída
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output_content)
            print(f"Saída escrita em: {args.output}")
        except Exception as e:
            print(f"Erro ao escrever arquivo de saída: {e}")
            return 1
    else:
        print(output_content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
