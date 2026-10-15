#!/usr/bin/env python
"""LLM-vs-deterministic skill extraction comparison for the go_junior role pack.

Compares deterministic extraction (SkillExtractor) against LLM-based extraction
(OllamaClient with qwen2.5-coder:3b) on a fixed, versioned fixture set of Go
Junior vacancies.  Results are written to ``reports/llm_comparison_<timestamp>.md``
and printed to stdout.

Usage::

    .venv\\Scripts\\python.exe scripts\\llm_vs_deterministic_compare.py

Environment assumptions:
- Ollama is running at http://localhost:11434 (optional — script degrades
  gracefully and reports empty LLM results if unavailable).
- ``VACANCIES_DISABLE_LLM`` is NOT set (the script builds its own LLMConfig
  with ``enabled=True`` regardless of env, so env vars do not interfere).
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Reconfigure stdout for UTF-8 (needed on Windows consoles using cp1251)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Bootstrap: ensure project root is importable so ``src.vacancies.*`` resolves
# regardless of CWD.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests  # noqa: E402  -- available in .venv

from src.vacancies.core.enums import (  # noqa: E402
    Currency,
    DataCompleteness,
    DmsStatus,
    TaxType,
    VacancyStatus,
    WorkFormat,
)
from src.vacancies.core.models import BenefitsInfo, SalaryInfo, Vacancy  # noqa: E402
from src.vacancies.llm.client import LLMConfig, LLMError, OllamaClient  # noqa: E402
from src.vacancies.llm.prompts import SECURITY_PREAMBLE  # noqa: E402
from src.vacancies.market.analyzer import SkillExtractor  # noqa: E402
from src.vacancies.role_pack.go_junior import (  # noqa: E402
    GO_JUNIOR_ROLE_PACK,
    SkillDefinition,
)

logger = logging.getLogger("llm_vs_deterministic")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5-coder:3b"
CONFIDENCE_THRESHOLD = 0.3  # skills with confidence >= this are counted as LLM-extracted

# Canonical skill IDs from the go_junior role pack — surfaced in the LLM prompt
_CANONICAL_IDS = ", ".join(s.skill_id for s in GO_JUNIOR_ROLE_PACK.skills)

# LLM system prompt — reuses SECURITY_PREAMBLE (same pattern as prompts.py)
LLM_EXTRACTION_SYSTEM_PROMPT = (
    SECURITY_PREAMBLE
    + "\n\nЗадача: извлечь навыки из текста вакансии Go Junior-разработчика.\n"
    "Возвращай строго JSON-массив объектов: "
    "[{\"skill_id\": \"идентификатор\", \"confidence\": 0.0-1.0}].\n"
    f"Допустимые skill_id: {_CANONICAL_IDS}.\n"
    "Включай навык ТОЛЬКО если он упомянут в тексте вакансии. "
    "confidence = степень уверенности (0.0–1.0). "
    "Не придумывай навыки, которых нет в тексте. "
    "Если навыков нет — верни пустой массив []."
)


# ---------------------------------------------------------------------------
# Fixtures — FIXED, versioned Go Junior vacancies
# ---------------------------------------------------------------------------

def _make_vacancy(vid: str, title: str, description: str, requirements: str) -> Vacancy:
    """Create a ``Vacancy`` fixture with minimal required fields."""
    return Vacancy(
        id=vid,
        title=title,
        employer="FixtureCorp",
        source_url=f"https://example.com/vacancy/{vid}",
        source_name="fixture",
        work_format=WorkFormat.REMOTE,
        location="Санкт-Петербург",
        salary=SalaryInfo(
            from_amount=120000,
            currency=Currency.RUB,
            tax_type=TaxType.NET,
        ),
        benefits=BenefitsInfo(dms_status=DmsStatus.CONFIRMED),
        data_completeness=DataCompleteness.FULL,
        status=VacancyStatus.NEEDS_CLARIFICATION,
        description=description,
        requirements=requirements,
        responsibilities="",
    )


FIXTURE_1: Vacancy = _make_vacancy(
    vid="fix1",
    title="Junior Go Developer (fintech startup)",
    description=(
        "Финтех-стартаб ищет Junior Go Developer для backend-команды. "
        "Строим микросервисы на Go, работаем с PostgreSQL и Docker. "
        "gRPC для межсервисного взаимодействия. "
        "Используем Kafka для event-driven архитектуры. "
        "Ценим teamwork и communication в команде."
    ),
    requirements=(
        "Обязательно: Go, PostgreSQL, Docker, Git, Linux. "
        "Желательно: gRPC, Kafka, concurrency (goroutines, channels), "
        "testing с testify. Алгоритмы и debugging."
    ),
)

FIXTURE_2: Vacancy = _make_vacancy(
    vid="fix2",
    title="Backend Developer (Go) — e-commerce",
    description=(
        "Разворачиваем высоконагруженный e-commerce на Go. "
        "Используем Gin framework, PostgreSQL, Redis. "
        "gRPC с Protocol Buffers. Docker + Kubernetes для деплоя. "
        "Kafka для event-driven архитектуры. Тестируем с gomock."
    ),
    requirements=(
        "Обязательно: Go, PostgreSQL, Linux. "
        "Желательно: Gin, Redis, gRPC, protobuf, Docker, Kubernetes, "
        "Kafka, RabbitMQ, testing. CI/CD (GitLab CI, GitHub Actions) желательно."
    ),
)

FIXTURE_3: Vacancy = _make_vacancy(
    vid="fix3",
    title="Go Developer (remote)",
    description=(
        "Удалённая позиция для Go-разработчика. "
        "Работа с PostgreSQL, Docker, Kafka. "
        "REST API на Go. Тестируем с testify. "
        "CI/CD через GitHub Actions. "
        "Требуется понимание ОС Linux и работы с Git. Bash скрипты."
    ),
    requirements=(
        "Обязательно: Go, PostgreSQL, Docker, Linux, Git. "
        "Желательно: Kafka, gRPC, Redis, testing, CI/CD, bash, concurrency."
    ),
)

ALL_FIXTURES: List[Vacancy] = [FIXTURE_1, FIXTURE_2, FIXTURE_3]


# ---------------------------------------------------------------------------
# Ground truth — manually curated based on vacancy text content
# ---------------------------------------------------------------------------

GROUND_TRUTH: Dict[str, Set[str]] = {
    "fix1": {
        # Explicitly mentioned required: Go, PostgreSQL, Docker, Git, Linux
        "go", "postgresql", "docker", "git", "linux",
        # Explicitly mentioned preferred: gRPC, Kafka, concurrency, testing
        "grpc", "kafka", "concurrency", "testing",
        # Skill-level matches: microservices -> distributed_systems,
        #   teamwork -> communication, testify -> testing,
        #   Алгоритмы/алгоритмы -> problem_solving, debugging -> problem_solving
        "distributed_systems", "communication", "problem_solving",
    },
    "fix2": {
        "go", "gin", "grpc", "protobuf", "postgresql", "redis",
        "docker", "kubernetes", "kafka", "rabbitmq",
        "testing", "ci_cd", "linux", "git",
    },
    "fix3": {
        "go", "postgresql", "docker", "kafka", "testing",
        "ci_cd", "linux", "git", "concurrency",
        "grpc", "redis",
    },
}


# ---------------------------------------------------------------------------
# Ollama availability check (uses ``requests`` from .venv)
# ---------------------------------------------------------------------------

def is_ollama_available(url: str = OLLAMA_URL, timeout: float = 5.0) -> bool:
    """Return ``True`` if an Ollama server responds at *url*."""
    try:
        resp = requests.get(f"{url.rstrip('/')}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Skill name normalization — maps free-form LLM output to canonical skill_id
# ---------------------------------------------------------------------------

def _normalize_skill(raw_name: str) -> Optional[str]:
    """Map a free-form skill name to a canonical ``go_junior`` skill_id.

    Checks skill_ids, skill names, aliases, and the role pack's
    ``normalization_rules`` dict (alias → canonical_id).
    """
    if not raw_name:
        return None

    name = raw_name.strip().lower()

    # 1. Direct skill_id match
    for skill in GO_JUNIOR_ROLE_PACK.skills:
        if skill.skill_id == name:
            return skill.skill_id

    # 2. Skill name match (case-insensitive)
    for skill in GO_JUNIOR_ROLE_PACK.skills:
        if skill.name.lower() == name:
            return skill.skill_id

    # 3. Alias match (case-insensitive)
    for skill in GO_JUNIOR_ROLE_PACK.skills:
        for alias in skill.aliases:
            if alias.lower() == name:
                return skill.skill_id

    # 4. Normalization rules (alias → canonical_id)
    canonical = GO_JUNIOR_ROLE_PACK.normalization_rules.get(name)
    if canonical:
        return canonical

    return None


def _parse_llm_response(raw: str) -> Set[str]:
    """Parse an LLM response into a set of canonical ``go_junior`` skill_ids.

    Handles JSON arrays, ``{"skills": [...]}`` dicts, and markdown-fenced
    code blocks.  Returns an empty set if parsing fails.
    """
    if not raw or not raw.strip():
        return set()

    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip("` \n\t")

    data: Any = None

    # Fast path: direct JSON parse
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Balanced-bracket scan for a JSON array
        start = cleaned.find("[")
        if start == -1:
            logger.warning("LLM response contains no JSON array: %s", cleaned[:200])
            return set()
        depth = 0
        end_idx = -1
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end_idx = i + 1
                    break
        if end_idx == -1:
            logger.warning("LLM response has unbalanced JSON array: %s", cleaned[:200])
            return set()
        try:
            data = json.loads(cleaned[start:end_idx])
        except json.JSONDecodeError:
            logger.warning("LLM response is not valid JSON after scan: %s", cleaned[:200])
            return set()

    # Normalize into a list of skill entry dicts
    items: List[Dict[str, Any]] = []
    if isinstance(data, list):
        items = [i for i in data if isinstance(i, dict)]
    elif isinstance(data, dict):
        for key in ("skills", "response", "data"):
            if key in data and isinstance(data[key], list):
                items = [i for i in data[key] if isinstance(i, dict)]
                break
        else:
            items = [data]
    else:
        return set()

    skills: Set[str] = set()
    for item in items:
        raw_id = item.get("skill_id") or item.get("name") or item.get("skill")
        if not raw_id:
            continue
        try:
            conf = float(item.get("confidence", 1.0))
        except (TypeError, ValueError):
            conf = 1.0
        if conf < CONFIDENCE_THRESHOLD:
            continue
        canonical = _normalize_skill(str(raw_id))
        if canonical:
            skills.add(canonical)
        else:
            logger.debug("LLM returned unrecognised skill: %s", raw_id)

    return skills


# ---------------------------------------------------------------------------
# Deterministic extraction
# ---------------------------------------------------------------------------

def extract_deterministic(vacancy: Vacancy) -> Set[str]:
    """Extract skill_ids using ``SkillExtractor`` (deterministic, substring-based)."""
    occurrences = list(SkillExtractor().extract_skills(vacancy))
    return {occ.skill_id for occ in occurrences}


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------

def _build_vacancy_prompt(vacancy: Vacancy) -> str:
    """Build the user prompt with vacancy text (truncated for safety)."""
    parts: List[str] = [f"Название: {vacancy.title}"]
    if vacancy.description:
        parts.append(f"Описание:\n{vacancy.description[:3000]}")
    if vacancy.requirements:
        parts.append(f"Требования:\n{vacancy.requirements[:2000]}")
    return "\n\n".join(parts)


def _make_llm_client() -> Optional[OllamaClient]:
    """Create an OllamaClient, or ``None`` if Ollama is unavailable."""
    if not is_ollama_available():
        logger.warning(
            "Ollama not reachable at %s — LLM extraction disabled", OLLAMA_URL
        )
        return None
    config = LLMConfig(
        provider="ollama",
        model=OLLAMA_MODEL,
        base_url=OLLAMA_URL,
        temperature=0.2,
        timeout=60.0,
        max_retries=2,
        retry_delay=1.0,
        max_output_tokens=512,
        enabled=True,
    )
    return OllamaClient(config)


def extract_llm(client: Optional[OllamaClient], vacancy: Vacancy) -> Set[str]:
    """Extract skill_ids using the LLM (Ollama).  Returns ``set()`` on failure."""
    if client is None:
        return set()

    user_prompt = _build_vacancy_prompt(vacancy)
    try:
        raw = client.generate(user_prompt, system=LLM_EXTRACTION_SYSTEM_PROMPT)
        return _parse_llm_response(raw)
    except (LLMError, Exception) as exc:  # noqa: BLE001
        logger.warning("LLM extraction failed for vacancy %s: %s", vacancy.id, exc)
        return set()


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _precision(found: Set[str], ground_truth: Set[str]) -> float:
    """Precision = |found ∩ GT| / |found|."""
    if not found:
        return 0.0
    return len(found & ground_truth) / len(found)


def _recall(found: Set[str], ground_truth: Set[str]) -> float:
    """Recall = |found ∩ GT| / |GT|."""
    if not ground_truth:
        return 0.0
    return len(found & ground_truth) / len(ground_truth)


def _f1(p: float, r: float) -> float:
    """F1 = harmonic mean of precision and recall."""
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------

def run_comparison() -> Dict[str, Any]:
    """Run LLM-vs-deterministic comparison on the fixed fixture set.

    Returns a dict with per-fixture results and overall metrics.
    If Ollama is unavailable, LLM results are empty sets (script still runs).
    """
    timestamp = datetime.now().isoformat()
    ollama_ok = is_ollama_available()
    llm_client = _make_llm_client() if ollama_ok else None

    fixtures_data: List[Dict[str, Any]] = []

    for vacancy in ALL_FIXTURES:
        gt = GROUND_TRUTH.get(vacancy.id, set())

        det_skills = extract_deterministic(vacancy)
        llm_skills = extract_llm(llm_client, vacancy) if llm_client else set()

        det_p, det_r = _precision(det_skills, gt), _recall(det_skills, gt)
        det_f1 = _f1(det_p, det_r)
        llm_p, llm_r = _precision(llm_skills, gt), _recall(llm_skills, gt)
        llm_f1 = _f1(llm_p, llm_r)

        overlap = det_skills & llm_skills

        fixtures_data.append({
            "id": vacancy.id,
            "title": vacancy.title,
            "description": vacancy.description or "",
            "requirements": vacancy.requirements or "",
            "ground_truth": sorted(gt),
            "deterministic_skills": sorted(det_skills),
            "llm_skills": sorted(llm_skills),
            "det_precision": round(det_p, 4),
            "det_recall": round(det_r, 4),
            "det_f1": round(det_f1, 4),
            "llm_precision": round(llm_p, 4),
            "llm_recall": round(llm_r, 4),
            "llm_f1": round(llm_f1, 4),
            "overlap": sorted(overlap),
            "det_hallucinations": sorted(det_skills - gt),
            "llm_hallucinations": sorted(llm_skills - gt),
            "det_misses": sorted(gt - det_skills),
            "llm_misses": sorted(gt - llm_skills),
        })

    # Overall (union across fixtures)
    all_det = set().union(*(d["deterministic_skills"] for d in fixtures_data))
    all_llm = set().union(*(d["llm_skills"] for d in fixtures_data))
    all_gt = set().union(*(d["ground_truth"] for d in fixtures_data))

    det_p = _precision(all_det, all_gt)
    det_r = _recall(all_det, all_gt)
    llm_p = _precision(all_llm, all_gt)
    llm_r = _recall(all_llm, all_gt)

    overall = {
        "det_precision": round(det_p, 4),
        "det_recall": round(det_r, 4),
        "det_f1": round(_f1(det_p, det_r), 4),
        "llm_precision": round(llm_p, 4),
        "llm_recall": round(llm_r, 4),
        "llm_f1": round(_f1(llm_p, llm_r), 4),
        "det_skills": sorted(all_det),
        "llm_skills": sorted(all_llm),
        "gt_skills": sorted(all_gt),
        "overlap": sorted(all_det & all_llm),
        "det_extra": sorted(all_det - all_gt),
        "llm_extra": sorted(all_llm - all_gt),
    }

    return {
        "ollama_available": ollama_ok,
        "model": OLLAMA_MODEL if ollama_ok else "N/A (Ollama unavailable)",
        "timestamp": timestamp,
        "fixtures": fixtures_data,
        "overall": overall,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _fmt_set(s: Set[str] | List[str]) -> str:
    items = sorted(s) if isinstance(s, set) else sorted(s)
    return f"`{items}`" if items else "`{}`"


def format_report(result: Dict[str, Any]) -> str:
    """Render the comparison result as a Markdown report string."""
    lines: List[str] = []
    lines.append("# LLM-vs-Deterministic Skill Extraction Comparison")
    lines.append("")
    lines.append(f"**Timestamp:** {result['timestamp']}")
    lines.append(f"**Model:** `{result['model']}`")
    lines.append(f"**Ollama available:** {result['ollama_available']}")
    lines.append(f"**Fixtures:** {len(result['fixtures'])}")
    lines.append("")

    # Per-fixture detail
    lines.append("## Fixture Results")
    lines.append("")
    for f in result["fixtures"]:
        lines.append(f"### {f['title']}")
        lines.append(f"- **ID:** `{f['id']}`")
        lines.append(f"- **Description:** {f['description'][:200]}...")
        lines.append(f"- **Requirements:** {f['requirements'][:200]}...")
        lines.append(f"- **Ground truth:** {_fmt_set(f['ground_truth'])}")
        lines.append(f"- **Deterministic:** {_fmt_set(f['deterministic_skills'])}")
        lines.append(f"- **LLM:** {_fmt_set(f['llm_skills'])}")
        lines.append("")
        lines.append("| Metric | Deterministic | LLM |")
        lines.append("|---|---|---|")
        lines.append(f"| Precision | {f['det_precision']:.2f} | {f['llm_precision']:.2f} |")
        lines.append(f"| Recall | {f['det_recall']:.2f} | {f['llm_recall']:.2f} |")
        lines.append(f"| F1 | {f['det_f1']:.2f} | {f['llm_f1']:.2f} |")
        lines.append("")
        lines.append(f"- **Overlap (det ∩ LLM):** {_fmt_set(f['overlap'])}")
        lines.append(f"- **Det hallucinations (det − GT):** {_fmt_set(f['det_hallucinations'])}")
        lines.append(f"- **LLM hallucinations (LLM − GT):** {_fmt_set(f['llm_hallucinations'])}")
        lines.append(f"- **Det misses (GT − det):** {_fmt_set(f['det_misses'])}")
        lines.append(f"- **LLM misses (GT − LLM):** {_fmt_set(f['llm_misses'])}")
        lines.append("")

    # Overall
    o = result["overall"]
    lines.append("## Overall Metrics")
    lines.append("")
    lines.append("| Metric | Deterministic | LLM |")
    lines.append("|---|---|---|")
    lines.append(f"| Precision | {o['det_precision']:.2f} | {o['llm_precision']:.2f} |")
    lines.append(f"| Recall | {o['det_recall']:.2f} | {o['llm_recall']:.2f} |")
    lines.append(f"| F1 | {o['det_f1']:.2f} | {o['llm_f1']:.2f} |")
    lines.append("")
    lines.append(f"- **Overall overlap (det ∩ LLM):** {_fmt_set(o['overlap'])}")
    lines.append(f"- **Det extra (hallucinations):** {_fmt_set(o['det_extra'])}")
    lines.append(f"- **LLM extra (hallucinations):** {_fmt_set(o['llm_extra'])}")
    lines.append("")

    # Conclusion
    lines.append("## Conclusion")
    lines.append("")
    if not result["ollama_available"]:
        lines.append(
            "Ollama was not available at `http://localhost:11434`. "
            "LLM extraction returned empty sets; deterministic results are shown above."
            " LLM metrics are zero."
        )
    else:
        det_any = o["det_precision"] > 0 or o["det_recall"] > 0
        llm_any = o["llm_precision"] > 0 or o["llm_recall"] > 0

        if llm_any and det_any:
            if o["llm_f1"] > o["det_f1"]:
                lines.append(
                    f"LLM extraction outperforms deterministic (F1 = "
                    f"{o['llm_f1']:.2f} vs {o['det_f1']:.2f})."
                )
            elif o["det_f1"] > o["llm_f1"]:
                lines.append(
                    f"Deterministic extraction outperforms LLM (F1 = "
                    f"{o['det_f1']:.2f} vs {o['llm_f1']:.2f})."
                )
            else:
                lines.append(
                    "Deterministic and LLM extraction achieve equal F1 "
                    f"({o['det_f1']:.2f})."
                )
        elif det_any and not llm_any:
            lines.append(
                "LLM extraction found no skills matching ground truth; "
                "deterministic extraction is the better path here."
            )

        if o["llm_extra"]:
            lines.append(
                f"LLM introduced hallucinations (skills not in ground truth): "
                f"`{sorted(o['llm_extra'])}`."
            )
        else:
            lines.append("LLM did not introduce hallucinations beyond ground truth.")

        if o["det_extra"]:
            lines.append(
                f"Deterministic extraction found extra skills via substring "
                f"matching: `{sorted(o['det_extra'])}`."
            )
        else:
            lines.append("Deterministic extraction found no extra skills beyond ground truth.")

        if o["overlap"]:
            lines.append(
                f"Both methods agreed on {len(o['overlap'])} skills: "
                f"`{sorted(o['overlap'])}`."
            )

        # Per-fixture LLM extras / misses
        llm_found_gt = any(
            set(f["llm_skills"]) & set(f["ground_truth"]) for f in result["fixtures"]
        )
        if llm_found_gt:
            lines.append(
                "LLM found additional relevant skills that deterministic "
                "extraction missed in some fixtures."
            )
        else:
            lines.append(
                "LLM did not find any additional relevant skills; review "
                "LLM misses for false negatives."
            )

    lines.append("")
    lines.append("---")
    lines.append(
        f"*Generated by `scripts/llm_vs_deterministic_compare.py` "
        f"on {result['timestamp']}*"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File output
# ---------------------------------------------------------------------------

def write_report(result: Dict[str, Any], output_dir: Optional[Path] = None) -> Path:
    """Write the Markdown report to ``reports/llm_comparison_<timestamp>.md``."""
    if output_dir is None:
        output_dir = PROJECT_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"llm_comparison_{ts}.md"
    path = output_dir / filename
    path.write_text(format_report(result), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the comparison, print to stdout, and write the report file."""
    result = run_comparison()

    report = format_report(result)
    print(report)

    path = write_report(result)
    print(f"\nReport written to: {path}")


if __name__ == "__main__":
    main()
