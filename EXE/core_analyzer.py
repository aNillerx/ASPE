from __future__ import annotations

import ast
import re
import tokenize
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "env",
    "venv",
    "node_modules",
    "reports",
}

LEVEL_ORDER = {"ERROR": 0, "WARNING": 1, "IMPROVEMENT": 2}
TOKEN_PATTERN = re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")
TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK)\b", re.IGNORECASE)
TELEGRAM_MODULES = {"telegram", "aiogram", "telebot", "pyrogram"}
LONG_LINE_LIMIT = 120
LONG_FUNCTION_LIMIT = 60
LARGE_FILE_LIMIT = 400


@dataclass(slots=True)
class Finding:
    level: str
    title: str
    description: str
    suggestion: str
    file_path: Path
    line: int | None = None

    def format_for_report(self, project_root: Path) -> str:
        try:
            relative_path = self.file_path.relative_to(project_root)
        except ValueError:
            relative_path = self.file_path

        line_suffix = f":{self.line}" if self.line else ""
        return (
            f"[{self.level}] {relative_path}{line_suffix} | {self.title}\n"
            f"  Description: {self.description}\n"
            f"  Suggestion: {self.suggestion}"
        )


@dataclass(slots=True)
class Report:
    title: str
    project_root: Path
    scanned_files: list[Path] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def sorted_findings(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda item: (
                LEVEL_ORDER.get(item.level, 99),
                str(item.file_path).lower(),
                item.line or 0,
                item.title.lower(),
            ),
        )

    def count(self, level: str) -> int:
        return sum(1 for finding in self.findings if finding.level == level)

    def build_text(self) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "Auto Search Python Error",
            "=" * 30,
            f"Report: {self.title}",
            f"Generated: {timestamp}",
            f"Project: {self.project_root}",
            f"Scanned files: {len(self.scanned_files)}",
            f"Errors: {self.count('ERROR')}",
            f"Warnings: {self.count('WARNING')}",
            f"Improvements: {self.count('IMPROVEMENT')}",
        ]

        if self.notes:
            lines.append("")
            lines.append("Notes:")
            lines.extend(f"- {note}" for note in self.notes)

        lines.append("")
        lines.append("Findings:")

        sorted_findings = self.sorted_findings()
        if not sorted_findings:
            lines.append("No issues found. The checked files look good.")
            return "\n".join(lines)

        lines.extend(finding.format_for_report(self.project_root) for finding in sorted_findings)
        return "\n\n".join(lines)

    def print_summary(self) -> None:
        print("\nSummary")
        print("-" * 30)
        print(f"Checked files: {len(self.scanned_files)}")
        print(f"Errors: {self.count('ERROR')}")
        print(f"Warnings: {self.count('WARNING')}")
        print(f"Improvements: {self.count('IMPROVEMENT')}")

        if self.notes:
            print("\nNotes:")
            for note in self.notes:
                print(f"- {note}")

        sorted_findings = self.sorted_findings()
        if not sorted_findings:
            print("\nNo issues found.")
            return

        print("\nDetailed findings:")
        for finding in sorted_findings:
            print(f"- {finding.format_for_report(self.project_root)}")


def collect_python_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for file_path in project_root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in file_path.parts):
            continue
        if file_path.is_file():
            files.append(file_path)
    return sorted(files)


def read_source(file_path: Path) -> str:
    try:
        with tokenize.open(file_path) as handle:
            return handle.read()
    except (SyntaxError, UnicodeDecodeError):
        for encoding in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
            try:
                return file_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
    return file_path.read_text(encoding="utf-8", errors="replace")


def add_finding(
    findings: list[Finding],
    *,
    level: str,
    title: str,
    description: str,
    suggestion: str,
    file_path: Path,
    line: int | None = None,
) -> None:
    findings.append(
        Finding(
            level=level,
            title=title,
            description=description,
            suggestion=suggestion,
            file_path=file_path,
            line=line,
        )
    )


def analyze_common_file(file_path: Path, source: str) -> list[Finding]:
    findings: list[Finding] = []

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as error:
        add_finding(
            findings,
            level="ERROR",
            title="Syntax error",
            description=error.msg,
            suggestion="Fix the syntax and run the checker again.",
            file_path=file_path,
            line=error.lineno,
        )
        return findings

    lines = source.splitlines()
    _check_common_ast(tree, file_path, findings)
    _check_common_text(file_path, lines, findings)
    return findings


def _check_common_ast(tree: ast.AST, file_path: Path, findings: list[Finding]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _check_mutable_defaults(node, file_path, findings)
            _check_long_function(node, file_path, findings)

        if isinstance(node, ast.ExceptHandler):
            _check_except_handler(node, file_path, findings)

        if isinstance(node, ast.Call):
            _check_dangerous_calls(node, file_path, findings)

        if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
            add_finding(
                findings,
                level="WARNING",
                title="Wildcard import",
                description="Using 'from module import *' makes the code harder to read and debug.",
                suggestion="Import only the names that the file really uses.",
                file_path=file_path,
                line=node.lineno,
            )


def _check_mutable_defaults(
    node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: Path, findings: list[Finding]
) -> None:
    defaults = [default for default in list(node.args.defaults) + list(node.args.kw_defaults) if default]
    for default in defaults:
        if isinstance(default, (ast.List, ast.Dict, ast.Set)):
            add_finding(
                findings,
                level="WARNING",
                title="Mutable default argument",
                description=(
                    f"Function '{node.name}' uses a mutable object as a default value. "
                    "This value is shared between calls."
                ),
                suggestion="Use None as the default and create a new object inside the function.",
                file_path=file_path,
                line=getattr(default, "lineno", node.lineno),
            )


def _check_long_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: Path, findings: list[Finding]
) -> None:
    end_lineno = getattr(node, "end_lineno", node.lineno)
    size = max(0, end_lineno - node.lineno + 1)
    if size > LONG_FUNCTION_LIMIT:
        add_finding(
            findings,
            level="IMPROVEMENT",
            title="Long function",
            description=f"Function '{node.name}' has {size} lines, which makes maintenance harder.",
            suggestion="Split the logic into smaller helper functions with focused responsibilities.",
            file_path=file_path,
            line=node.lineno,
        )


def _check_except_handler(node: ast.ExceptHandler, file_path: Path, findings: list[Finding]) -> None:
    handler_type = _exception_name(node.type)
    if handler_type is None:
        add_finding(
            findings,
            level="WARNING",
            title="Bare except",
            description="The handler catches every possible exception, including system interrupts.",
            suggestion="Catch a specific exception type instead of using a bare except block.",
            file_path=file_path,
            line=node.lineno,
        )
    elif handler_type in {"Exception", "BaseException"}:
        add_finding(
            findings,
            level="WARNING",
            title="Too broad exception handler",
            description=f"The handler catches '{handler_type}', which can hide real bugs.",
            suggestion="Catch a narrower exception type and handle it explicitly.",
            file_path=file_path,
            line=node.lineno,
        )

    if any(isinstance(statement, ast.Pass) for statement in node.body):
        add_finding(
            findings,
            level="IMPROVEMENT",
            title="Silent exception handling",
            description="The exception handler contains 'pass', so failures may be lost without any trace.",
            suggestion="Log the exception or return a clear error path for easier debugging.",
            file_path=file_path,
            line=node.lineno,
        )


def _check_dangerous_calls(node: ast.Call, file_path: Path, findings: list[Finding]) -> None:
    if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
        add_finding(
            findings,
            level="WARNING",
            title=f"Use of {node.func.id}",
            description=f"Call to '{node.func.id}' can execute dynamic code and increase security risk.",
            suggestion="Replace dynamic execution with safer explicit logic if possible.",
            file_path=file_path,
            line=node.lineno,
        )


def _check_common_text(file_path: Path, lines: list[str], findings: list[Finding]) -> None:
    if len(lines) > LARGE_FILE_LIMIT:
        add_finding(
            findings,
            level="IMPROVEMENT",
            title="Large file",
            description=f"The file contains {len(lines)} lines, which is more difficult to navigate.",
            suggestion="Split the module into smaller files by responsibility.",
            file_path=file_path,
            line=1,
        )

    for line_number, line in enumerate(lines, start=1):
        if len(line) > LONG_LINE_LIMIT:
            add_finding(
                findings,
                level="IMPROVEMENT",
                title="Long line",
                description=f"Line length is {len(line)} characters.",
                suggestion="Break the expression into several lines to improve readability.",
                file_path=file_path,
                line=line_number,
            )

        comment_index = line.find("#")
        comment_text = line[comment_index:] if comment_index >= 0 else ""
        if comment_text and TODO_PATTERN.search(comment_text):
            add_finding(
                findings,
                level="IMPROVEMENT",
                title="Pending work marker",
                description="The file contains a TODO/FIXME/HACK marker.",
                suggestion="Review the unfinished note and decide whether it should be implemented now.",
                file_path=file_path,
                line=line_number,
            )


def exception_name(node: ast.AST | None) -> str | None:
    return _exception_name(node)


def _exception_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Tuple):
        names = [name for name in (_exception_name(item) for item in node.elts) if name]
        return ", ".join(names) if names else "tuple"
    return None


def is_telegram_related(file_path: Path, source: str) -> bool:
    lowered = source.lower()
    if TOKEN_PATTERN.search(source) is not None:
        return True

    lowered_name = file_path.stem.lower()
    if "telegram" in lowered_name and "check" not in lowered_name:
        return True

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return False

    has_api_url = "api.telegram.org" in lowered
    has_network_usage = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_name = alias.name.split(".")[0]
                if root_name in TELEGRAM_MODULES:
                    return True
                if root_name in {"requests", "httpx", "aiohttp", "urllib"}:
                    has_network_usage = True

        if isinstance(node, ast.ImportFrom):
            module_name = (node.module or "").split(".")[0]
            if module_name in TELEGRAM_MODULES:
                return True
            if module_name in {"requests", "httpx", "aiohttp", "urllib"}:
                has_network_usage = True

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "api.telegram.org" in node.value.lower():
                has_api_url = True

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id in {"requests", "httpx"}:
                has_network_usage = True

    return has_api_url and has_network_usage


def analyze_telegram_specific(file_path: Path, source: str) -> list[Finding]:
    findings: list[Finding] = []

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return findings

    lines = source.splitlines()
    _check_telegram_text(file_path, lines, findings)
    _check_telegram_ast(tree, file_path, findings)
    return findings


def _check_telegram_text(file_path: Path, lines: Iterable[str], findings: list[Finding]) -> None:
    for line_number, line in enumerate(lines, start=1):
        token_match = TOKEN_PATTERN.search(line)
        if token_match:
            add_finding(
                findings,
                level="ERROR",
                title="Hardcoded Telegram token",
                description="A Telegram bot token is stored directly in the source code.",
                suggestion="Move the token to an environment variable or a local config file outside version control.",
                file_path=file_path,
                line=line_number,
            )

        if "api.telegram.org" in line and "timeout=" not in line:
            add_finding(
                findings,
                level="WARNING",
                title="Telegram API call without visible timeout",
                description="Direct Telegram API usage appears without an explicit timeout on the same line.",
                suggestion="Add a timeout to avoid hanging network requests.",
                file_path=file_path,
                line=line_number,
            )


def _check_telegram_ast(tree: ast.AST, file_path: Path, findings: list[Finding]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and "token" in target.id.lower():
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        add_finding(
                            findings,
                            level="WARNING",
                            title="Token stored in code",
                            description=(
                                f"Variable '{target.id}' stores a string literal, which often means the bot token "
                                "is kept in source code."
                            ),
                            suggestion="Load sensitive values from environment variables or a protected config file.",
                            file_path=file_path,
                            line=node.lineno,
                        )

        if isinstance(node, ast.Call):
            _check_requests_without_timeout(node, file_path, findings)
            _check_print_usage(node, file_path, findings)

        if isinstance(node, ast.While):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                add_finding(
                    findings,
                    level="IMPROVEMENT",
                    title="Infinite loop in bot code",
                    description="A 'while True' loop can block graceful restarts and hide reconnect logic problems.",
                    suggestion="Use the Telegram framework polling/webhook facilities or add explicit stop conditions.",
                    file_path=file_path,
                    line=node.lineno,
                )


def _check_requests_without_timeout(node: ast.Call, file_path: Path, findings: list[Finding]) -> None:
    if not isinstance(node.func, ast.Attribute):
        return
    if not isinstance(node.func.value, ast.Name) or node.func.value.id != "requests":
        return
    if node.func.attr not in {"get", "post", "put", "delete", "request"}:
        return

    if any(keyword.arg == "timeout" for keyword in node.keywords):
        return

    add_finding(
        findings,
        level="WARNING",
        title="requests call without timeout",
        description="Network request can hang forever when timeout is not specified.",
        suggestion="Pass timeout=10 or another suitable value to the requests call.",
        file_path=file_path,
        line=node.lineno,
    )


def _check_print_usage(node: ast.Call, file_path: Path, findings: list[Finding]) -> None:
    if isinstance(node.func, ast.Name) and node.func.id == "print":
        add_finding(
            findings,
            level="IMPROVEMENT",
            title="print used in bot code",
            description="Console printing is harder to manage than structured logs in bot projects.",
            suggestion="Replace print with the logging module to keep diagnostics more consistent.",
            file_path=file_path,
            line=node.lineno,
        )


def save_report(report: Report, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = report.title.lower().replace(" ", "_")
    report_path = output_dir / f"{report_name}_{timestamp}.txt"
    report_path.write_text(report.build_text(), encoding="utf-8")
    return report_path
