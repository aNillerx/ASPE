from __future__ import annotations

from pathlib import Path

from core_analyzer import Report, analyze_common_file, collect_python_files, read_source


def run_general_check(project_root: Path) -> Report:
    report = Report(title="General Python Check", project_root=project_root)
    report.scanned_files = collect_python_files(project_root)

    if not report.scanned_files:
        report.notes.append("No Python files were found in the selected directory.")
        return report

    for file_path in report.scanned_files:
        source = read_source(file_path)
        report.findings.extend(analyze_common_file(file_path, source))

    return report
