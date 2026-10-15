"""CLI entry point for Vacancy Research System."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from dataclasses import asdict
from typing import Optional

from .orchestrator.orchestrator import OrchestratorLimits, VacancyResearchOrchestrator
from .utils.config import ConfigLoader


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="vacancy-research",
        description="Multi-agent system for Go vacancy research and reporting",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Directory containing config files (default: project config/)",
    )
    parser.add_argument(
        "--disable-llm",
        action="store_true",
        help="Disable LLM calls (use heuristics only)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # daily command
    daily_parser = subparsers.add_parser(
        "daily", help="Run daily vacancy search and report generation"
    )
    daily_parser.add_argument(
        "--raw-query",
        type=str,
        default="Go разработчик remote",
        help="Search query text",
    )
    daily_parser.add_argument(
        "--source",
        type=str,
        default="multi",
        choices=["multi", "hh", "fixture"],
        help="Data source mode",
    )
    daily_parser.add_argument(
        "--fixture-path",
        type=Path,
        default=None,
        help="Path to fixture JSON file (for source=fixture)",
    )
    daily_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Output directory for reports",
    )
    daily_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save reports to disk",
    )
    daily_parser.add_argument(
        "--max-vacancies",
        type=int,
        default=200,
        help="Maximum vacancies to process",
    )
    daily_parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Agent timeout in seconds",
    )
    daily_parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Max retry attempts per agent",
    )

    # run command (manual run with custom query)
    run_parser = subparsers.add_parser(
        "run", help="Run single vacancy search with custom query"
    )
    run_parser.add_argument(
        "query", type=str, nargs="?", default="Go разработчик", help="Search query"
    )
    run_parser.add_argument(
        "--source",
        type=str,
        default="multi",
        choices=["multi", "hh", "fixture"],
        help="Data source mode",
    )
    run_parser.add_argument(
        "--fixture-path",
        type=Path,
        default=None,
        help="Path to fixture JSON file",
    )
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Output directory for reports",
    )
    run_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not save reports to disk",
    )

    # config command
    config_parser = subparsers.add_parser("config", help="Validate and show config")
    config_parser.add_argument(
        "--show", action="store_true", help="Print loaded candidate profile"
    )
    config_parser.add_argument(
        "--show-weights", action="store_true", help="Print scoring weights"
    )
    config_parser.add_argument(
        "--show-llm", action="store_true", help="Print LLM config"
    )
    config_parser.add_argument(
        "--validate", action="store_true", help="Validate config files"
    )

    # history command
    history_parser = subparsers.add_parser("history", help="Show run history")
    history_parser.add_argument(
        "--list", action="store_true", help="List recent runs"
    )
    history_parser.add_argument(
        "--run-id", type=str, help="Show details for specific run"
    )
    history_parser.add_argument(
        "--limit", type=int, default=10, help="Max runs to list"
    )

    # interview command
    interview_parser = subparsers.add_parser(
        "interview", help="Run interactive adaptive interview for profile completion"
    )
    interview_parser.add_argument(
        "--profile-id",
        type=str,
        default="default",
        help="Profile ID to load or create",
    )
    interview_parser.add_argument(
        "--max-questions",
        type=int,
        default=10,
        help="Maximum number of interview questions",
    )
    interview_parser.add_argument(
        "--role-pack",
        type=str,
        default="go_junior",
        help="Role pack ID for interview questions",
    )

    return parser


def cmd_daily(args: argparse.Namespace) -> int:
    """Run daily vacancy search."""
    limits = OrchestratorLimits(
        max_vacancies=args.max_vacancies,
        max_retries=args.max_retries,
        agent_timeout_seconds=args.timeout,
    )
    orch = VacancyResearchOrchestrator(
        limits=limits,
        config_loader=ConfigLoader(args.config_dir) if args.config_dir else None,
        disable_llm=args.disable_llm,
    )

    query = args.raw_query
    try:
        report = orch.run(
            raw_query=query,
            source=args.source,
            fixture_path=args.fixture_path,
            output_dir=args.output_dir,
            write_reports=not args.no_save,
        )
    except Exception as e:
        logging.error("Daily run failed: %s", e)
        return 1

    run = report.run
    print(f"Run ID: {run.run_id}")
    print(f"Found: {run.vacancies_found}")
    print(f"Checked: {run.vacancies_checked}")
    print(f"Unique: {run.vacancies_unique}")
    print(f"Suitable: {run.vacancies_suitable}")
    print(f"Needs clarification: {run.vacancies_needs_clarification}")
    print(f"Not suitable: {len(report.not_suitable)}")

    if run.errors:
        print("Errors:")
        for err in run.errors:
            print(f"  - {err}")
        return 1

    if run.metadata.get("qa_failed"):
        print("QA FAILED - report quality not confirmed")
        return 2

    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """Run single search with custom query."""
    orch = VacancyResearchOrchestrator(
        config_loader=ConfigLoader(args.config_dir) if args.config_dir else None,
        disable_llm=args.disable_llm,
    )

    try:
        report = orch.run(
            raw_query=args.query,
            source=args.source,
            fixture_path=args.fixture_path,
            output_dir=args.output_dir,
            write_reports=not args.no_save,
        )
    except Exception as e:
        logging.error("Run failed: %s", e)
        return 1

    run = report.run
    print(f"Run ID: {run.run_id}")
    print(f"Found: {run.vacancies_found}")
    print(f"Suitable: {run.vacancies_suitable}")
    print(f"Needs clarification: {run.vacancies_needs_clarification}")

    if run.errors:
        print("Errors:")
        for err in run.errors:
            print(f"  - {err}")
        return 1

    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Validate and show configuration."""
    try:
        cfg = ConfigLoader(args.config_dir) if args.config_dir else ConfigLoader()
    except Exception as e:
        print(f"Config load error: {e}")
        return 1

    if args.show:
        profile = cfg.load_candidate_profile()
        print("Candidate Profile:")
        print(f"  Profession: {profile.profession}")
        print(f"  Level: {profile.candidate_level}")
        print(f"  Experience: {profile.experience_years}")
        print(f"  Locations: {profile.locations}")
        print(f"  Work formats: {[w.value for w in profile.work_formats]}")
        print(f"  Min salary: {profile.min_salary_rub_month} {profile.min_salary_tax_basis}/{profile.min_salary_period}")
        print(f"  Salary mandatory: {profile.min_salary_is_mandatory}")
        print(f"  DMS mode: {profile.dms_mode}")
        print(f"  LLM provider: {profile.llm_provider}")
        print(f"  Cloud fallback: {profile.cloud_fallback_enabled}")
        print(f"  Search frequency: {profile.search_frequency}")
        print(f"  Language: {profile.language}")

    if args.show_weights:
        weights = cfg.load_scoring_weights()
        print("\nScoring Weights:")
        for k, v in weights.items():
            print(f"  {k}: {v}")
        print(f"  Sum: {sum(weights.values()):.2f}")

    if args.show_llm:
        llm_cfg = cfg.load_llm_config()
        print("\nLLM Config:")
        print(f"  Provider: {llm_cfg.provider}")
        print(f"  Model: {llm_cfg.model}")
        print(f"  Base URL: {llm_cfg.base_url}")
        print(f"  Enabled: {llm_cfg.enabled}")
        print(f"  Temperature: {llm_cfg.temperature}")
        print(f"  Timeout: {llm_cfg.timeout}")
        print(f"  Max retries: {llm_cfg.max_retries}")
        print(f"  Max output tokens: {llm_cfg.max_output_tokens}")

    if args.validate:
        try:
            cfg.load_candidate_profile()
            cfg.load_scoring_weights()
            cfg.load_llm_config()
            print("All configs valid.")
        except Exception as e:
            print(f"Config validation failed: {e}")
            return 1

    return 0


def cmd_history(args: argparse.Namespace) -> int:
    """Show run history."""
    from .storage.history import RunHistory

    history = RunHistory()

    if args.list:
        runs = history.list_runs(limit=args.limit)
        if not runs:
            print("No runs found.")
            return 0
        print(f"Recent runs (limit {args.limit}):")
        for r in runs:
            print(f"  {r['run_id']} - {r['started_at']} - found:{r['vacancies_found']} unique:{r['vacancies_unique']} suitable:{r['suitable']}")
        return 0

    if args.run_id:
        run = history.get_run(args.run_id)
        if not run:
            print(f"Run {args.run_id} not found.")
            return 1
        print(f"Run ID: {run['run_id']}")
        print(f"Started: {run['started_at']}")
        print(f"Finished: {run['finished_at']}")
        print(f"Found: {run['vacancies_found']}")
        print(f"Unique: {run['vacancies_unique']}")
        print(f"Suitable: {run['vacancies_suitable']}")
        print(f"Needs clarification: {run['vacancies_needs_clarification']}")
        print(f"Errors: {run['errors']}")
        return 0

    print("Use --list or --run-id")
    return 1


def cmd_interview(args: argparse.Namespace) -> int:
    """Run interactive adaptive interview for candidate profile completion."""
    from .candidate.profile import CandidateProfile as ExtendedCandidateProfile, CandidateProfileManager
    from .candidate.interview import AdaptiveInterviewer

    cfg = ConfigLoader(args.config_dir) if args.config_dir else ConfigLoader()
    manager = CandidateProfileManager()

    profile = manager.load(args.profile_id)
    if profile is None:
        base_profile = cfg.load_candidate_profile()
        profile = ExtendedCandidateProfile(**asdict(base_profile))
        profile.resume_source = "interview"
        manager.save(profile, args.profile_id)

    interviewer = AdaptiveInterviewer(profile, role_pack_id=args.role_pack)
    interviewer.question_bank.set_max_questions(args.max_questions)

    print(
        f"=== Адаптивное интервью для Junior Go Developer "
        f"(вопросы: {args.max_questions}, 'skip' = пропустить, 'quit' = выход) ==="
    )

    try:
        while not interviewer.is_complete():
            question = interviewer.get_next_question()
            if question is None:
                print("Вопросы закончились.")
                break

            progress = len(interviewer.session.questions_asked) + 1
            print(f"\n[{progress}/{args.max_questions}] {question['text']}")

            answer = input("> ")

            if answer.strip().lower() == "quit":
                break
            if answer.strip().lower() == "skip":
                interviewer.skip_question(question["question_id"])
            else:
                interviewer.record_answer(question["question_id"], answer)
                manager.save(profile, args.profile_id)
    except KeyboardInterrupt:
        manager.save(profile, args.profile_id)
        print("\nИнтервью прервано. Прогресс сохранён.")
        return 0

    profile.interview_completed = True
    profile.interview_questions_asked = interviewer.session.questions_asked
    profile.interview_answers = interviewer.session.answers
    save_path = manager.save(profile, args.profile_id)

    answers_count = len(interviewer.session.answers)
    skipped_count = len(interviewer.session.skipped_questions)
    print("\nИнтервью завершено.")
    print(f"Ответов записано: {answers_count}")
    print(f"Пропущено: {skipped_count}")
    print(f"Профиль сохранён: {save_path}")

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)

    if args.command == "daily":
        return cmd_daily(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "config":
        return cmd_config(args)
    elif args.command == "history":
        return cmd_history(args)
    elif args.command == "interview":
        return cmd_interview(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())