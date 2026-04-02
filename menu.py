from __future__ import annotations

from pathlib import Path

from check_python_code import run_general_check
from check_telegram_bots import run_telegram_check
from core_analyzer import Report, save_report


def print_banner() -> None:
    print("\nAuto Search Python Error")
    print("=" * 30)
    print("1. Check regular Python code")
    print("2. Check Telegram bots")
    print("3. Check both")
    print("4. Exit")


def ask_project_path() -> Path:
    raw_value = input("\nProject path (Enter = current folder): ").strip().strip('"')
    project_root = Path(raw_value).expanduser() if raw_value else Path.cwd()
    return project_root.resolve()


def run_and_show(report: Report, reports_dir: Path) -> None:
    report.print_summary()
    report_path = save_report(report, reports_dir)
    print(f"\nReport saved: {report_path}")


def main() -> None:
    while True:
        print_banner()
        choice = input("\nChoose an option: ").strip()

        if choice == "4":
            print("Exiting Auto Search Python Error.")
            break

        if choice not in {"1", "2", "3"}:
            print("Unknown option. Please choose 1, 2, 3 or 4.")
            continue

        project_root = ask_project_path()
        if not project_root.exists() or not project_root.is_dir():
            print("The specified path does not exist or is not a directory.")
            continue

        reports_dir = project_root / "reports"

        if choice == "1":
            run_and_show(run_general_check(project_root), reports_dir)
        elif choice == "2":
            run_and_show(run_telegram_check(project_root), reports_dir)
        else:
            run_and_show(run_general_check(project_root), reports_dir)
            run_and_show(run_telegram_check(project_root), reports_dir)


if __name__ == "__main__":
    main()
