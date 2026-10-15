# Task 04 Report — Personal Career Assistant (Junior Go Developer)

> **Canonical report location:** [`tasks/task04_report.md`](tasks/task04_report.md)
>
> The repository stores task reports under `tasks/` (`tasks/task02_report.md`,
> `tasks/task03_report.md`). This root-level file exists because Task 04 §15
> explicitly requires a `task04_report.md` at the repository root. It documents
> the convention and points to the canonical report; it does not duplicate
> the full contents.

## Quick summary

| Item | Value |
|---|---|
| Base branch | `dev` |
| Base commit | `70fe5e3` (`feat: complete Task 03 corrective pass`) |
| Changes committed | **No** — work remains uncommitted on `dev` |
| Tests passing | 142 passed (`.venv` Python 3.13.14; 108 pre-existing + 34 new Task 04) |
| Live sources verified | None — all adapters mock/fixture; no API keys present |
| Deterministic path | Verified end-to-end with fixture single vacancy |

## What was implemented

- Candidate baseline: `resume_parser.py` (TXT/MD/PDF/DOCX + SSRF-safe URL import), `profile.py` (local storage, enum-safe), `interview.py`
- Universal Role Packs: `go_junior.py` (22 skills), `registry.py`
- Market skill intelligence: `market/analyzer.py` (two datasets, unique-vacancy denominators, evidence)
- Gap analysis: `candidate/gap_analysis.py` (gap matrix, learning plan, interview prep)
- Cross-source deduplication: `deduplication/deduplicator.py` (3 stages)
- Real learning resource catalog: `candidate/resources.py` (official docs only, no invented URLs)
- Source adapters: SuperJob, Rabota.ru, Habr Career (all credential-gated)
- 34 acceptance tests: `tests/vacancies/test_task04.py`
- Orchestrator integration: `orchestrator.py` stage 8b + `career_report.md`
- Documentation: `docs/architecture.md`, `docs/operations.md`, `docs/agents.md`, `README.md`

## Known limitations

- Live source integrations are `blocked_by_credentials` (no API keys in this environment).
- URL resume import is SSRF-safe (HTTPS-only, private-host rejection) but not tested against a live public endpoint.
- LLM customization tested with local Ollama (`qwen2.5-coder:3b`); deterministic-vs-LLM comparison run (F1 1.00 vs 0.91).
- Interactive interview loop wired to the `interview` CLI subcommand (`python -m src.vacancies.cli interview`) with skip/quit and progress persistence.
- Learning resources use the catalog with verified real URLs; catalog is small but extensible.

## Full report

See [`tasks/task04_report.md`](tasks/task04_report.md) for the complete report covering
git state, features, test counts, source status, evaluation metrics, local setup,
daily-run instructions, and known limitations.