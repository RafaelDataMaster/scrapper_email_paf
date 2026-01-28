#!/usr/bin/env python3
"""
Script to convert pyright JSON report to markdown format.

This script reads the JSON output from pyright/basedpyright and generates
a comprehensive markdown report with organized diagnostics.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple


def load_json_report(json_path: str) -> Dict[str, Any]:
    """Load JSON report from file."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: JSON report file not found: {json_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in {json_path}: {e}")
        sys.exit(1)


def organize_diagnostics(
    diagnostics: List[Dict[str, Any]],
) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """
    Organize diagnostics by file and severity.

    Returns: {
        "file_path": {
            "error": [...],
            "warning": [...]
        }
    }
    """
    organized: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: {"error": [], "warning": []}
    )

    for diagnostic in diagnostics:
        file_path = diagnostic.get("file", "unknown")
        severity = diagnostic.get("severity", "information").lower()

        if severity not in organized[file_path]:
            organized[file_path][severity] = []

        organized[file_path][severity].append(diagnostic)

    return dict(organized)


def format_location(range_data: Dict[str, Any]) -> str:
    """Format location information from range data."""
    if not range_data or "start" not in range_data:
        return "Unknown location"

    start = range_data.get("start", {})
    line = start.get("line", 0) + 1  # Convert to 1-based for display
    character = start.get("character", 0) + 1  # Convert to 1-based

    return f"Line {line}, Column {character}"


def generate_markdown_report(
    data: Dict[str, Any],
    organized_diagnostics: Dict[str, Dict[str, List[Dict[str, Any]]]],
) -> str:
    """Generate markdown report from organized diagnostics."""

    version = data.get("version", "Unknown")
    timestamp = data.get("time", "")

    # Convert timestamp if available
    if timestamp:
        try:
            timestamp_dt = datetime.fromtimestamp(int(timestamp) / 1000)
            timestamp_str = timestamp_dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            timestamp_str = timestamp
    else:
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Count statistics
    total_diagnostics = len(data.get("generalDiagnostics", []))
    files_count = len(organized_diagnostics)

    error_count = sum(
        len(diags.get("error", [])) for diags in organized_diagnostics.values()
    )
    warning_count = sum(
        len(diags.get("warning", [])) for diags in organized_diagnostics.values()
    )

    # Start building markdown
    lines = []

    # Header
    lines.append("# Pyright/Basedpyright Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Generated**: {timestamp_str}")
    lines.append(f"- **Pyright Version**: {version}")
    lines.append(f"- **Total Diagnostics**: {total_diagnostics}")
    lines.append(f"- **Files Analyzed**: {files_count}")
    lines.append(f"- **Errors**: {error_count}")
    lines.append(f"- **Warnings**: {warning_count}")
    lines.append("")

    # Files organized by error count (most problematic first)
    sorted_files = sorted(
        organized_diagnostics.items(),
        key=lambda x: (len(x[1].get("error", [])), len(x[1].get("warning", []))),
        reverse=True,
    )

    for file_path, diagnostics in sorted_files:
        file_errors = len(diagnostics.get("error", []))
        file_warnings = len(diagnostics.get("warning", []))

        if file_errors == 0 and file_warnings == 0:
            continue

        # File header
        lines.append(f"## File: `{os.path.basename(file_path)}`")
        lines.append(f"**Path**: {file_path}")
        lines.append(f"**Issues**: {file_errors} errors, {file_warnings} warnings")
        lines.append("")

        # Errors section
        if file_errors > 0:
            lines.append("### Errors")
            lines.append("")
            for i, diagnostic in enumerate(diagnostics.get("error", []), 1):
                message = diagnostic.get("message", "No message")
                rule = diagnostic.get("rule", "Unknown rule")
                location = format_location(diagnostic.get("range", {}))

                lines.append(f"#### Error {i}")
                lines.append(f"- **Message**: {message}")
                lines.append(f"- **Rule**: `{rule}`")
                lines.append(f"- **Location**: {location}")
                lines.append("")

        # Warnings section
        if file_warnings > 0:
            lines.append("### Warnings")
            lines.append("")
            for i, diagnostic in enumerate(diagnostics.get("warning", []), 1):
                message = diagnostic.get("message", "No message")
                rule = diagnostic.get("rule", "Unknown rule")
                location = format_location(diagnostic.get("range", {}))

                lines.append(f"#### Warning {i}")
                lines.append(f"- **Message**: {message}")
                lines.append(f"- **Rule**: `{rule}`")
                lines.append(f"- **Location**: {location}")
                lines.append("")

        lines.append("---")
        lines.append("")

    # Diagnostic rules summary
    lines.append("## Diagnostic Rules Summary")
    lines.append("")

    rule_counts: Dict[str, Tuple[int, int]] = defaultdict(
        lambda: (0, 0)
    )  # (errors, warnings)

    for diagnostic in data.get("generalDiagnostics", []):
        rule = diagnostic.get("rule", "Unknown")
        severity = diagnostic.get("severity", "information").lower()

        errors, warnings = rule_counts[rule]
        if severity == "error":
            rule_counts[rule] = (errors + 1, warnings)
        elif severity == "warning":
            rule_counts[rule] = (errors, warnings + 1)

    if rule_counts:
        lines.append("| Rule | Errors | Warnings | Total |")
        lines.append("|------|--------|----------|-------|")

        sorted_rules = sorted(
            rule_counts.items(), key=lambda x: (x[1][0], x[1][1]), reverse=True
        )

        for rule, (errors, warnings) in sorted_rules:
            total = errors + warnings
            lines.append(f"| `{rule}` | {errors} | {warnings} | {total} |")
    else:
        lines.append("*No diagnostic rules found*")

    lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert pyright JSON report to markdown format"
    )
    parser.add_argument(
        "-i",
        "--input",
        default="data/output/pyright_report.json",
        help="Input JSON file (default: data/output/pyright_report.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="data/output/pyright_report.md",
        help="Output markdown file (default: data/output/pyright_report.md)",
    )
    parser.add_argument(
        "--no-stats", action="store_true", help="Skip statistics summary"
    )

    args = parser.parse_args()

    # Load JSON report
    print(f"Loading JSON report from: {args.input}")
    data = load_json_report(args.input)

    # Check for required structure
    if "generalDiagnostics" not in data:
        print("Error: JSON report missing 'generalDiagnostics' field")
        sys.exit(1)

    # Organize diagnostics
    print(f"Organizing {len(data['generalDiagnostics'])} diagnostics...")
    organized_diagnostics = organize_diagnostics(data["generalDiagnostics"])

    # Generate markdown
    print("Generating markdown report...")
    markdown_content = generate_markdown_report(data, organized_diagnostics)

    # Write output
    print(f"Writing report to: {args.output}")
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print("Done!")
    except IOError as e:
        print(f"Error writing output file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
