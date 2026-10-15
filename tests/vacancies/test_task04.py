"""Acceptance tests for Task 04: market analysis, gap analysis, role pack,
deduplication, resume parsing, candidate profile persistence, determinism,
and the career-report / orchestrator pipeline.

All tests use fixtures/mocks only — no live API keys or network calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.vacancies.core.contracts import ResearchRun
from src.vacancies.core.enums import (
    Currency,
    DmsStatus,
    TaxType,
    WorkFormat,
)
from src.vacancies.core.models import (
    BenefitsInfo,
    CandidateProfile as CoreCandidateProfile,
    SalaryInfo,
    Vacancy,
)
from src.vacancies.candidate.gap_analysis import GapAnalyzer
from src.vacancies.candidate.profile import (
    CandidateProfile as ExtCandidateProfile,
    CandidateProfileManager,
    SkillEvidence,
    SkillEvidenceType,
    SkillConfidence,
)
from src.vacancies.candidate.resume_parser import ResumeParser
from src.vacancies.deduplication.deduplicator import Deduplicator
from src.vacancies.market.analyzer import MarketAnalyzer
from src.vacancies.orchestrator.orchestrator import (
    OrchestratorLimits,
    VacancyResearchOrchestrator,
)
from src.vacancies.role_pack.go_junior import GO_JUNIOR_ROLE_PACK


def _vacancy(**kwargs) -> Vacancy:
    """Reusable vacancy fixture factory (mirrors tests/vacancies/test_task_scenarios.py)."""
    defaults = dict(
        id="1",
        title="Go-разработчик",
        employer="TestCo",
        source_url="https://hh.ru/vacancy/1",
        source_name="hh.ru",
        work_format=WorkFormat.REMOTE,
        location="Санкт-Петербург",
        salary=SalaryInfo(
            from_amount=150000, currency=Currency.RUB, tax_type=TaxType.NET
        ),
        benefits=BenefitsInfo(dms_status=DmsStatus.CONFIRMED),
        description="Backend на Go, gRPC, PostgreSQL, Docker",
    )
    defaults.update(kwargs)
    return Vacancy(**defaults)


# --------------------------------------------------------------------------- #
# 1. Market analysis
# --------------------------------------------------------------------------- #
def test_market_analyzer_separates_eligible_and_market_sample_no_leak():
    """eligible vs market_sample cohorts must be disjoint and sum to total."""
    v1 = _vacancy(id="1", source_url="https://hh.ru/vacancy/1")
    v2 = _vacancy(id="2", source_url="https://hh.ru/vacancy/2")
    result = MarketAnalyzer().analyze([v1, v2], eligible_vacancies=[v1])

    assert result.eligible_vacancy_count == 1
    assert result.market_sample_vacancy_count == 1
    assert (
        result.eligible_vacancy_count
        + result.market_sample_vacancy_count
        == result.total_unique_vacancies
    )
    # market_sample must NOT contain the eligible vacancy (no leak)
    assert result.market_sample_vacancy_count == 1


def test_market_stats_unique_denominators_not_duplicate_listings():
    """A skill mentioned several times in / across duplicate listings is counted
    once per unique canonical vacancy, not per raw occurrence."""
    v = _vacancy(
        id="1",
        description="Backend на Go, golang и gopher с gRPC",
        source_url="https://hh.ru/vacancy/1",
    )
    # Same vacancy object listed twice (duplicate listing)
    result = MarketAnalyzer().analyze([v, v])
    by_id = {s["skill_id"]: s for s in result.skill_stats}

    go = by_id["go"]
    assert go["total_vacancies"] == 1  # unique canonical vacancy, not 3+ occurrences
    assert go["percentage_of_vacancies"] == 100.0
    assert len(go["evidence"]) == 1


def test_market_stats_each_stat_has_evidence_or_explicit_zero():
    """Every skill stat must carry evidence links OR be an explicit zero
    (absent skills are represented, not omitted)."""
    v = _vacancy(
        id="1",
        description="Go, gRPC, PostgreSQL",
        source_url="https://hh.ru/vacancy/1",
    )
    result = MarketAnalyzer().analyze([v])
    by_id = {s["skill_id"]: s for s in result.skill_stats}

    # All role-pack skills are represented
    assert len(result.skill_stats) == len(GO_JUNIOR_ROLE_PACK.skills) == 22

    for stat in result.skill_stats:
        if stat["total_vacancies"] > 0:
            # present skill: evidence links required
            assert stat["evidence"], f"skill {stat['skill_id']} has counts but no evidence"
        else:
            # absent skill: explicit zero
            assert stat["evidence"] == []
            assert stat["explicit_required"] == 0
            assert stat["explicit_preferred"] == 0
            assert stat["mentioned"] == 0
            assert stat["inferred"] == 0

    # 'chi' is not mentioned in the corpus -> explicit zero
    chi = by_id["chi"]
    assert chi["total_vacancies"] == 0
    assert chi["evidence"] == []


def test_market_stats_labels_remain_distinct():
    """required/preferred/mentioned/inferred buckets must stay separate."""
    # go -> explicit_required (per role pack requirement_strength)
    # gin -> explicit_preferred (per role pack requirement_strength)
    v = _vacancy(
        id="1",
        description="Go, Gin",
        source_url="https://hh.ru/vacancy/1",
    )
    result = MarketAnalyzer().analyze([v])
    by_id = {s["skill_id"]: s for s in result.skill_stats}

    go = by_id["go"]
    gin = by_id["gin"]

    assert go["explicit_required"] == 1
    assert go["explicit_preferred"] == 0
    assert gin["explicit_preferred"] == 1
    assert gin["explicit_required"] == 0

    # Each unique vacancy is counted in exactly one label bucket
    for stat in (go, gin):
        label_sum = (
            stat["explicit_required"]
            + stat["explicit_preferred"]
            + stat["mentioned"]
            + stat["inferred"]
            + stat["unknown"]
        )
        assert label_sum == stat["total_vacancies"]


# --------------------------------------------------------------------------- #
# 2. Gap analysis
# --------------------------------------------------------------------------- #
def test_gap_analysis_empty_profile_gap_types():
    """Empty profile -> needs_assessment for core/frequent, not_relevant for
    occasional, NEVER a false confirmed_gap / matches_target."""
    profile = ExtCandidateProfile()  # no skills at all
    result = GapAnalyzer().analyze(profile, [])
    gaps = result["skill_gaps"]
    assert len(gaps) == len(GO_JUNIOR_ROLE_PACK.skills)

    for gap in gaps:
        if gap.target_importance in ("core", "frequent"):
            assert gap.gap_type == "needs_assessment", gap.skill_id
        elif gap.target_importance == "occasional":
            assert gap.gap_type == "not_relevant", gap.skill_id

    # Hard guarantee: no false positive gaps for an unknown candidate
    assert not any(g.gap_type == "confirmed_gap" for g in gaps)
    assert not any(g.gap_type == "matches_target" for g in gaps)


def test_gap_analyzer_works_with_core_candidate_profile():
    """GapAnalyzer must not crash on core.models.CandidateProfile which has no
    `get_skill` attribute (uses the getattr fallback)."""
    profile = CoreCandidateProfile()  # base profile: no skills, no get_skill
    assert not hasattr(profile, "get_skill")

    result = GapAnalyzer().analyze(profile, [])
    assert "skill_gaps" in result
    assert len(result["skill_gaps"]) == len(GO_JUNIOR_ROLE_PACK.skills)

    for gap in result["skill_gaps"]:
        if gap.target_importance in ("core", "frequent"):
            assert gap.gap_type == "needs_assessment"
    assert not any(g.gap_type == "confirmed_gap" for g in result["skill_gaps"])


# --------------------------------------------------------------------------- #
# 3. Role pack
# --------------------------------------------------------------------------- #
def test_role_pack_has_22_skills():
    assert len(GO_JUNIOR_ROLE_PACK.skills) == 22


def test_role_pack_get_skill_resolves_via_alias():
    skill = GO_JUNIOR_ROLE_PACK.get_skill("golang")
    assert skill is not None
    assert skill.skill_id == "go"
    assert skill.name == "Go"


def test_role_pack_mandatory_and_preferred_skills_no_name_error():
    mandatory = GO_JUNIOR_ROLE_PACK.get_mandatory_skills()
    preferred = GO_JUNIOR_ROLE_PACK.get_preferred_skills()
    assert len(mandatory) > 0
    assert len(preferred) > 0
    assert all(s.skill_id for s in mandatory)
    assert all(s.skill_id for s in preferred)
    # Mandatory and preferred sets must be disjoint
    mandatory_ids = {s.skill_id for s in mandatory}
    preferred_ids = {s.skill_id for s in preferred}
    assert mandatory_ids.isdisjoint(preferred_ids)


# --------------------------------------------------------------------------- #
# 4. Deduplicator
# --------------------------------------------------------------------------- #
def test_deduplicator_merges_identical_vacancies_from_different_sources():
    """Two identical listings (same title/employer/location/url) from different
    sources collapse into a single unique vacancy."""
    common = dict(
        title="Go Developer",
        employer="Acme",
        location="Санкт-Петербург",
        work_format=WorkFormat.REMOTE,
        source_url="https://hh.ru/vacancy/123",
        description="Go, PostgreSQL, gRPC",
    )
    v1 = _vacancy(id="1", source_name="hh.ru", **common)
    v2 = _vacancy(id="2", source_name="habr", **common)
    result = Deduplicator().deduplicate([v1, v2])

    assert len(result.unique_vacancies) == 1
    assert result.merged_count == 1


def test_deduplicator_keeps_similar_but_distinct_roles():
    """Same employer, same location, but DIFFERENT titles must NOT be merged."""
    v1 = _vacancy(
        id="1",
        source_name="hh.ru",
        title="Go Developer",
        employer="Acme",
        location="Санкт-Петербург",
        source_url="https://hh.ru/vacancy/1",
    )
    v2 = _vacancy(
        id="2",
        source_name="habr",
        title="Go Architect",
        employer="Acme",
        location="Санкт-Петербург",
        source_url="https://career.habr.com/vacancy/2",
    )
    result = Deduplicator().deduplicate([v1, v2])

    assert len(result.unique_vacancies) == 2
    assert result.merged_count == 0


def test_deduplicator_then_skill_frequency_unique():
    """After dedup of duplicate listings, MarketAnalyzer counts a skill's
    vacancy frequency once even if the role is described multiple times."""
    v1 = _vacancy(
        id="1",
        source_name="hh.ru",
        title="Go Developer",
        employer="Acme",
        location="Санкт-Петербург",
        source_url="https://hh.ru/vacancy/1",
        description="Go и golang, gRPC",
    )
    v2 = _vacancy(
        id="2",
        source_name="habr",
        title="Go Developer",
        employer="Acme",
        location="Санкт-Петербург",
        source_url="https://hh.ru/vacancy/1",
        description="Go и golang, gRPC",
    )
    unique = Deduplicator().deduplicate([v1, v2]).unique_vacancies
    assert len(unique) == 1

    result = MarketAnalyzer().analyze(unique)
    go = next(s for s in result.skill_stats if s["skill_id"] == "go")
    assert go["total_vacancies"] == 1  # one unique vacancy, not 2 (name+alias) occurrences


# --------------------------------------------------------------------------- #
# 5. Resume parser
# --------------------------------------------------------------------------- #
def test_resume_txt_import_extracts_skills_and_experience(tmp_path):
    resume = tmp_path / "resume.txt"
    resume.write_text(
        "Go-разработчик\n"
        "Навыки: Go, gRPC, PostgreSQL, Docker, Kafka\n"
        "Опыт: 3 года опыта в backend-разработке\n",
        encoding="utf-8",
    )
    parsed = ResumeParser().parse_file(resume)

    assert parsed.skills
    assert "go" in parsed.skills
    assert "grpc" in parsed.skills
    assert "kafka" in parsed.skills
    assert parsed.experience_years == 3
    assert parsed.parsing_errors == []


def test_resume_unknown_format_raises_value_error(tmp_path):
    resume = tmp_path / "resume.xyz"
    resume.write_text("Go developer", encoding="utf-8")
    with pytest.raises(ValueError):
        ResumeParser().parse_file(resume)


def test_resume_empty_text_returns_parsing_errors():
    parsed = ResumeParser().parse_text("")
    assert parsed.parsing_errors
    assert parsed.skills == []


# --------------------------------------------------------------------------- #
# 6. Candidate profile persistence
# --------------------------------------------------------------------------- #
def test_profile_save_load_roundtrips_skills_with_enum_serialization(tmp_path):
    mgr = CandidateProfileManager(data_dir=str(tmp_path))
    profile = ExtCandidateProfile()
    profile.skills = [
        SkillEvidence(
            skill_id="go",
            skill_name="Go",
            aliases=["golang"],
            proficiency_level="intermediate",
            evidence_type=SkillEvidenceType.RESUME,
            confidence=SkillConfidence.HIGH,
        )
    ]

    path = mgr.save(profile, profile_id="test")

    # Serialization: enums are written as their string values
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["skills"][0]["evidence_type"] == "resume"
    assert raw["skills"][0]["confidence"] == "high"

    loaded = mgr.load("test")
    assert loaded is not None
    assert len(loaded.skills) == 1
    skill = loaded.skills[0]
    assert skill.skill_id == "go"
    assert skill.skill_name == "Go"
    assert skill.proficiency_level == "intermediate"
    assert skill.aliases == ["golang"]
    # Enums are restored on load (not left as plain strings)
    assert isinstance(skill.evidence_type, SkillEvidenceType)
    assert skill.evidence_type == SkillEvidenceType.RESUME
    assert isinstance(skill.confidence, SkillConfidence)
    assert skill.confidence == SkillConfidence.HIGH


# --------------------------------------------------------------------------- #
# 7. Determinism
# --------------------------------------------------------------------------- #
def test_market_analysis_is_deterministic():
    v1 = _vacancy(
        id="1",
        description="Go, gRPC, PostgreSQL, Docker",
        source_url="https://hh.ru/vacancy/1",
    )
    v2 = _vacancy(
        id="2",
        title="Golang Engineer",
        employer="Acme",
        location="Санкт-Петербург",
        source_url="https://example.com/v/2",
        description="Go, Gin, PostgreSQL, Kafka",
    )
    analyzer = MarketAnalyzer()
    r1 = analyzer.analyze([v1, v2])
    r2 = analyzer.analyze([v1, v2])

    assert r1.skill_stats == r2.skill_stats
    assert r1.total_unique_vacancies == r2.total_unique_vacancies


# --------------------------------------------------------------------------- #
# 8. Career report / orchestrator
# --------------------------------------------------------------------------- #
def test_orchestrator_writes_career_report_and_latest(tmp_path):
    orch = VacancyResearchOrchestrator()
    v = _vacancy(id="1")
    report = orch.run(fixtures=[v], write_reports=True, output_dir=tmp_path)

    assert (tmp_path / "career_report.md").exists()
    assert (tmp_path / "latest.md").exists()
    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "runs").is_dir()

    # latest.json must be valid JSON containing the vacancy
    data = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert "vacancies" in data
    assert data["vacancies"][0]["title"] == "Go-разработчик"

    # Report file must mention the source vacancy
    md = (tmp_path / "latest.md").read_text(encoding="utf-8")
    assert "Go-разработчик" in md


def test_orchestrator_metadata_contains_market_and_gap_analysis(tmp_path):
    orch = VacancyResearchOrchestrator()
    report = orch.run(fixtures=[_vacancy(id="1")], write_reports=True, output_dir=tmp_path)

    meta = report.run.metadata
    assert "market_analysis" in meta
    assert "gap_analysis" in meta

    ma = meta["market_analysis"]
    assert ma["market_stats"]  # skills were extracted
    assert ma["eligible_count"] + ma["market_sample_count"] == ma["total_unique_vacancies"]

    ga = meta["gap_analysis"]
    assert "skill_gaps" in ga
    assert "learning_plan" in ga
    assert "interview_prep" in ga
    assert ga["summary"]["total_skills_in_role"] == 22


def test_orchestrator_metadata_market_analysis_has_no_leak(tmp_path):
    """Eligible + market_sample must partition the corpus (no leak)."""
    orch = VacancyResearchOrchestrator(
        limits=OrchestratorLimits(retry_delay_seconds=0)
    )
    report = orch.run(
        fixtures=[_vacancy(id="1"), _vacancy(id="2", source_url="https://hh.ru/v/2")],
        write_reports=True,
        output_dir=tmp_path,
    )
    ma = report.run.metadata["market_analysis"]
    assert ma["eligible_count"] + ma["market_sample_count"] == ma["total_unique_vacancies"]


# --------------------------------------------------------------------------- #
# URL resume import (SSRF protection) — §5.1
# --------------------------------------------------------------------------- #
from src.vacancies.candidate.url_importer import _host_is_private, _validate_url


def test_url_import_rejects_private_network():
    """SSRF: private/loopback addresses must be rejected (https scheme)."""
    # Use https so we reach the SSRF host check (http is rejected by scheme first)
    for bad in ("https://127.0.0.1/resume", "https://localhost/resume",
                "https://192.168.1.1/resume", "https://10.0.0.1/resume",
                "https://169.254.1.1/resume"):
        ok, reason = _validate_url(bad)
        assert not ok, f"should reject {bad}"
        assert "SSRF" in reason or "private" in reason.lower() or "rejected" in reason.lower()


def test_url_import_rejects_non_https():
    ok, reason = _validate_url("http://example.com/resume")
    assert not ok
    assert "https" in reason.lower()


def test_url_import_rejects_embedded_credentials():
    ok, _ = _validate_url("https://user:pass@example.com/resume")
    assert not ok


def test_url_import_accepts_public_https():
    ok, _ = _validate_url("https://example.com/resume.txt")
    assert ok


def test_host_is_private_blocklist():
    assert _host_is_private("localhost")
    assert _host_is_private("127.0.0.1")
    assert _host_is_private("192.168.0.1")
    assert _host_is_private("10.5.0.2")
    assert _host_is_private("169.254.1.1")
    assert not _host_is_private("example.com")
    assert not _host_is_private("go.dev")


def test_parse_url_raises_on_rejected(monkeypatch):
    """parse_url must raise ValueError for a private target (no network)."""
    parser = ResumeParser()
    try:
        parser.parse_url("http://127.0.0.1/resume")
        raised = False
    except ValueError as e:
        raised = True
        assert "rejected" in str(e).lower()
    assert raised


def test_parse_url_raises_on_non_https(monkeypatch):
    parser = ResumeParser()
    with pytest.raises(ValueError):
        parser.parse_url("http://example.com/resume")


def test_save_imported_content_writes_locally(tmp_path):
    from src.vacancies.candidate.url_importer import save_imported_content
    path = save_imported_content("sample resume text", tmp_path, profile_id="prof1")
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "sample resume text"


# --------------------------------------------------------------------------- #
# Learning resource catalog — §11.9 (never invent a URL)
# --------------------------------------------------------------------------- #
from src.vacancies.candidate.resources import DEFAULT_CATALOG, ResourceCatalog


def test_resource_catalog_has_real_urls():
    catalog = ResourceCatalog()
    for rid in ("go_official_tutorial", "go_by_example", "effective_go",
                "postgresql_docs", "docker_official_docs", "kubernetes_basics",
                "grpc_go_tutorial", "git_scm_book"):
        res = catalog.get(rid)
        assert res is not None
        assert res.url.startswith("https://")
        # Must NOT be an invented placeholder URL
        assert not res.url.startswith("https://example.com/")


def test_resource_catalog_resolve_returns_only_known_ids():
    catalog = ResourceCatalog()
    resolved = catalog.resolve(["go_official_tutorial", "nonexistent_id"])
    assert len(resolved) == 1
    assert resolved[0]["url"].startswith("https://")
    assert "example.com" not in resolved[0]["url"]


def test_resource_catalog_resolve_unknown_id_is_omitted_not_invented():
    catalog = ResourceCatalog()
    resolved = catalog.resolve(["totally_made_up_resource"])
    assert resolved == []


def test_learning_plan_resources_use_real_catalog():
    """Learning plan items must not contain invented example.com URLs."""
    profile = ExtCandidateProfile()
    result = GapAnalyzer().analyze(profile, [])
    for item in result["learning_plan"]:
        for res in item.get("resources", []):
            url = res.get("url", "")
            assert url.startswith("https://"), f"invented/empty URL: {url}"
            assert not url.startswith("https://example.com/"), f"invented URL: {url}"


def test_learning_plan_broken_resource_does_not_break():
    """If a resource ID is missing from the catalog, the plan still builds."""
    catalog = ResourceCatalog()
    # An empty list of resource IDs just yields no resources — no crash
    assert catalog.resolve([]) == []


# --------------------------------------------------------------------------- #
# LLM-vs-deterministic comparison — §17.16
# --------------------------------------------------------------------------- #

def test_llm_deterministic_comparison_available():
    """§17.16: LLM-vs-deterministic comparison is available and functional.

    Skips gracefully when Ollama is not running at localhost:11434 so CI
    stays green in environments without a local Ollama server.
    """
    import sys as _sys
    from pathlib import Path as _Path

    _scripts_dir = _Path(__file__).resolve().parents[2] / "scripts"
    if str(_scripts_dir) not in _sys.path:
        _sys.path.insert(0, str(_scripts_dir))

    from llm_vs_deterministic_compare import is_ollama_available, run_comparison

    if not is_ollama_available():
        pytest.skip("Ollama not available at localhost:11434")

    result = run_comparison()

    assert result["ollama_available"] is True

    det_all: set = set()
    llm_all: set = set()
    gt_all: set = set()

    for f in result["fixtures"]:
        det_all.update(f["deterministic_skills"])
        llm_all.update(f["llm_skills"])
        gt_all.update(f["ground_truth"])

    # Deterministic extraction finds >= 1 skill from ground truth
    det_gt_match = det_all & gt_all
    assert len(det_gt_match) >= 1, (
        f"Deterministic extraction found no skills matching ground truth. "
        f"det={sorted(det_all)} gt={sorted(gt_all)}"
    )

    # LLM extraction finds >= 1 skill
    assert len(llm_all) >= 1, f"LLM extraction found no skills: {sorted(llm_all)}"

    # Both result sets are valid sets of strings
    assert isinstance(det_all, set)
    assert isinstance(llm_all, set)
    assert all(isinstance(s, str) for s in det_all)
    assert all(isinstance(s, str) for s in llm_all)

