from __future__ import annotations

from pathlib import Path

from core_analyzer import (
    Report,
    analyze_common_file,
    analyze_telegram_specific,
    collect_python_files,
    is_telegram_related,
    read_source,
)


def run_telegram_check(project_root: Path) -> Report:
    report = Report(title="Telegram Bot Check", project_root=project_root)
    all_python_files = collect_python_files(project_root)

    if not all_python_files:
        report.notes.append("No Python files were found in the selected directory.")
        return report

    for file_path in all_python_files:
        source = read_source(file_path)
        if is_telegram_related(file_path, source):
            report.scanned_files.append(file_path)
            report.findings.extend(analyze_common_file(file_path, source))
            report.findings.extend(analyze_telegram_specific(file_path, source))

    if not report.scanned_files:
        report.notes.append("No Telegram bot files were detected in the selected directory.")

    return report
