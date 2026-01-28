#!/usr/bin/env python3
"""
Simple script to extract a specific case by ID from the detailed PDF analysis report.

Usage:
    python extract_case_simple.py --case 1
    python extract_case_simple.py --input data/output/analise_pdfs_detalhada.txt --case 5
"""

import argparse
import re
import sys


def extract_case(input_file: str, case_id: int) -> str:
    """
    Extract a specific case by ID from the analysis report.

    Args:
        input_file: Path to the analysis report file
        case_id: ID of the case to extract

    Returns:
        The complete case text as a string

    Raises:
        FileNotFoundError: If the input file doesn't exist
        ValueError: If the case ID is not found in the report
    """
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {input_file}")

    # Split the content by the case delimiter (80 hyphens)
    # The delimiter appears on a line by itself
    cases = re.split(r"^-{80}", content, flags=re.MULTILINE)

    # The first part is the header (before the first delimiter)
    # Search for the case with the matching ID
    target_pattern = f"^CASO #{case_id}\\b"

    for case in cases:
        if re.search(target_pattern, case, flags=re.MULTILINE):
            return case.strip()

    raise ValueError(f"Case #{case_id} not found in the report")


def main():
    parser = argparse.ArgumentParser(
        description="Extract a specific case by ID from the detailed PDF analysis report"
    )
    parser.add_argument(
        "--input",
        default="data/output/analise_pdfs_detalhada.txt",
        help="Path to the analysis report file (default: data/output/analise_pdfs_detalhada.txt)",
    )
    parser.add_argument(
        "--case",
        type=int,
        required=True,
        help="ID of the case to extract (e.g., 1, 5, 98)",
    )

    args = parser.parse_args()

    try:
        case_text = extract_case(args.input, args.case)
        print(case_text)
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"Please check that the file exists: {args.input}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("The case ID might not exist in the report.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
