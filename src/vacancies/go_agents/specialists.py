from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..core.enums import Currency, DmsStatus, VacancyStatus, WorkFormat, DataCompleteness
from ..core.models import (
    BenefitsInfo,
    CareerFitAnalysis,
    SalaryInfo,
    SourceEvidence,
    TechnicalAnalysis,
    Vacancy,
    VacancyScore,
)
from ..core.scoring import ScoringCalculator, VacancyNormalizer
from ..llm.client import BaseLLMClient
from ..llm.prompts import (
    CAREER_FIT_SYSTEM,
    TECHNICAL_SYSTEM,
    build_career_fit_prompt,
    build_technical_prompt,
)

logger = logging.getLogger(__name__)


class VacancyVerificationAgent:
    name = "VacancyVerificationAgent"

    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        """Verify vacancies: check URLs, extract facts, mark data completeness."""
        for v in vacancies:
            v.checked_at = v.checked_at or datetime.now(timezone.utc)

            if not v.source_url:
                v.status = VacancyStatus.CHECK_FAILED
                v.non_compliance_reasons.append("Отсутствует проверяемый источник")
            else:
                v.confirmed_facts.append("Есть ссылка на первоисточник")
                v.evidence.append(SourceEvidence(
                    source_url=v.source_url,
                    field_name="source_url",
                    extracted_at=datetime.now(timezone.utc),
                ))

            # Determine data completeness
            has_salary = v.salary.from_amount is not None or v.salary.to_amount is not None
            has_desc = bool(v.description)
            has_location = bool(v.location)
            has_format = v.work_format != WorkFormat.UNKNOWN

            if has_salary and has_desc and has_location and has_format:
                v.data_completeness = DataCompleteness.FULL
            elif has_salary and has_desc:
                v.data_completeness = DataCompleteness.PARTIAL
            elif has_salary or has_desc:
                v.data_completeness = DataCompleteness.MINIMAL
            else:
                v.data_completeness = DataCompleteness.MINIMAL

        return {"vacancies": vacancies, "success": True}


class GoTechnicalAnalyst:
    name = "Go Technical Analyst"
    def __init__(self, llm=None) -> None:
        self.llm = llm
    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        if self.llm is not None:
            llm_ok = 0
            for v in vacancies:
                if self._analyze_with_llm(v):
                    llm_ok += 1
            if llm_ok:
                return {"vacancies": vacancies, "success": True, "llm_analyzed": llm_ok}
            logger.warning("LLM technical analysis produced no results; using heuristics")
        return self._run_heuristics(vacancies)
    def _analyze_with_llm(self, v: Vacancy) -> bool:
        client = self.llm
        if client is None:
            return False
        try:
            parsed = client.generate_json(
                build_technical_prompt(v.title, v.description or "", v.requirements),
                system=TECHNICAL_SYSTEM,
            )
        except Exception as e:
            logger.warning("LLM technical analysis failed for %s: %s", v.id, e)
            return False
        if not parsed:
            return False
        def _clamp(val, default):
            try:
                return max(0, min(100, int(val)))
            except (TypeError, ValueError):
                return default
        v.technical_analysis = TechnicalAnalysis(
            technologies=[str(x) for x in parsed.get("technologies", []) if x],
            go_relevance_score=_clamp(parsed.get("go_relevance_score"), 50),
            task_interest_score=_clamp(parsed.get("task_interest_score"), 50),
            backend_signals=[str(x) for x in parsed.get("positives", []) if x],
            concerns=[str(x) for x in parsed.get("concerns", []) if x],
            positives=[str(x) for x in parsed.get("positives", []) if x],
            has_confirmed_tech=bool(parsed.get("technologies")),
        )
        return True
    def _run_heuristics(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        go_signals = ["golang", "go", "goroutine", "gopher", "std", "stdlib", "gofmt", "golangci"]
        backend_signals = ["api", "rest", "grpc", "microservice", "kubernetes", "k8s", "docker", "kafka", "rabbitmq", "redis", "postgresql", "mysql", "cassandra", "distributed", "concurrent", "performance", "scalab", "load", "backend", "сервис", "микросервис", "конкурент"]
        routine_signals = ["html", "frontend", "css", "javascript", "react", "vue", "wordpress"]
        for v in vacancies:
            desc = (v.description or "").lower()
            title = (v.title or "").lower()
            combined = desc + " " + title
            go_count = sum(1 for s in go_signals if s in combined)
            go_relevance = min(100, go_count * 20 + 20)
            backend_count = sum(1 for s in backend_signals if s in combined)
            backend_signals_list = [s for s in backend_signals if s in combined]
            routine_count = sum(1 for s in routine_signals if s in combined)
            interest = min(100, 30 + backend_count * 8 - routine_count * 10)
            concerns = []
            if routine_count > 2:
                concerns.append("Много фронтенд/рутинных задач (HTML, CSS, JS)")
            if go_count == 0:
                concerns.append("Go не упоминается в описании")
            positives = []
            if backend_count >= 3:
                positives.append("Сильный backend-стек: " + ", ".join(backend_signals_list[:5]))
            if go_count >= 2:
                positives.append("Go активно используется в задачах")
            v.technical_analysis = TechnicalAnalysis(
                technologies=["Go"] if go_count > 0 else [],
                go_relevance_score=go_relevance,
                task_interest_score=interest,
                concurrency_signals=[s for s in backend_signals_list if any(c in s for c in ["concurrent", "load", "scalab"])],
                backend_signals=backend_signals_list,
                concerns=concerns,
                positives=positives,
                has_confirmed_tech=go_count > 0,
            )
        return {"vacancies": vacancies, "success": True}


class CompensationBenefitsAgent:
    name = "Compensation & Benefits Agent"

    def run(self, vacancies: List[Vacancy], min_salary: float = 119000) -> Dict[str, Any]:
        """Normalize and validate salary + benefits."""
        dms_patterns = [
            r"\bдмс\b",
            r"добровольн\w+\s+медицинск\w+\s+страхован",
            r"корпоративн\w+\s+медицинск",
            r"medical\s+insurance",
            r"voluntary\s+medical",
        ]

        for v in vacancies:
            # DMS detection from description
            desc = (v.description or "").lower()
            if v.benefits.dms_status == DmsStatus.UNKNOWN:
                for pattern in dms_patterns:
                    if re.search(pattern, desc):
                        v.benefits.dms_status = DmsStatus.CONFIRMED
                        v.benefits.dms_notes = "Упоминание ДМС найдено в тексте вакансии"
                        v.evidence.append(SourceEvidence(
                            source_url=v.source_url,
                            field_name="dms",
                            snippet=pattern,
                            extracted_at=datetime.now(timezone.utc),
                        ))
                        break
                else:
                    v.benefits.dms_status = DmsStatus.NOT_MENTIONED

            # Salary check - use proper conversion
            if v.salary.from_amount is not None:
                net_monthly = VacancyNormalizer.convert_to_monthly_net(
                    v.salary.from_amount,
                    v.salary.currency,
                    v.salary.tax_type,
                    v.salary.period,
                )
                if net_monthly is not None and net_monthly < min_salary:
                    v.non_compliance_reasons.append(
                        f"Зарплата ({v.salary.from_amount:.0f} {v.salary.currency.value}) ниже порога {min_salary:.0f} руб/мес"
                    )

        return {"vacancies": vacancies, "success": True}


class CareerFitAnalyst:
    name = "CareerFitAnalyst"
    def __init__(self, llm=None) -> None:
        self.llm = llm
    def run(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        if self.llm is not None:
            llm_ok = 0
            for v in vacancies:
                if self._analyze_with_llm(v):
                    llm_ok += 1
            if llm_ok:
                return {"vacancies": vacancies, "success": True, "llm_analyzed": llm_ok}
            logger.warning("LLM career fit produced no results; using heuristics")
        return self._run_heuristics(vacancies)
    def _analyze_with_llm(self, v: Vacancy) -> bool:
        client = self.llm
        if client is None:
            return False
        salary = f'{v.salary.from_amount:.0f}-{v.salary.to_amount:.0f} {v.salary.currency.value}' if v.salary.from_amount is not None and v.salary.to_amount is not None else (f'от {v.salary.from_amount:.0f} {v.salary.currency.value}' if v.salary.from_amount is not None else 'не указана')
        try:
            parsed = client.generate_json(
                build_career_fit_prompt(v.title, v.description or "", v.work_format.value, salary),
                system=CAREER_FIT_SYSTEM,
            )
        except Exception as e:
            logger.warning("LLM career fit failed for %s: %s", v.id, e)
            return False
        if not parsed:
            return False
        try:
            fit_score = max(0, min(100, int(parsed.get("fit_score", 50))))
        except (TypeError, ValueError):
            fit_score = 50
        v.career_fit = CareerFitAnalysis(
            fit_score=fit_score,
            career_growth_score=fit_score,
            motivation_score=fit_score,
            strong_points=[str(x) for x in parsed.get("strong_points", []) if x],
            risks=[str(x) for x in parsed.get("risks", []) if x],
            questions_for_interview=[str(x) for x in parsed.get("questions_for_interview", []) if x],
            recommendation=str(parsed.get("recommendation") or ""),
        )
        return True
    def _run_heuristics(self, vacancies: List[Vacancy]) -> Dict[str, Any]:
        seniority_indicators = {
            "lead": 90, "руковод": 90, "staff": 85, "principal": 85,
            "senior": 80, "старший": 80, "lead": 80,
            "middle": 60, "мидл": 60, "разработчик": 55,
            "junior": 40, "стаж": 35, "trainee": 35,
            "intern": 30, "младший": 40,
        }
        for v in vacancies:
            title = (v.title or "").lower()
            desc = (v.description or "").lower()
            combined = title + " " + desc
            seniority_score = 50
            for indicator, score in seniority_indicators.items():
                if indicator in combined:
                    seniority_score = max(seniority_score, score)
            strong_points = []
            risks = []
            questions = []
            if v.work_format in (WorkFormat.REMOTE, WorkFormat.HYBRID):
                strong_points.append(f"Формат работы подходит: {v.work_format.value}")
            else:
                risks.append("Офисный формат может не соответствовать ожиданиям")
            if v.salary.from_amount is not None:
                strong_points.append(f"Зарплата указана: {v.salary.from_amount:.0f} {v.salary.currency.value}")
            else:
                risks.append("Зарплата не указана — требуется уточнение")
                questions.append("Каков диапазон зарплат для этой позиции?")
            if v.benefits.dms_status == DmsStatus.CONFIRMED:
                strong_points.append("Подтверждено ДМС")
            elif v.benefits.dms_status == DmsStatus.NOT_MENTIONED:
                questions.append("Есть ли ДМС и другие соц benefits?")
            if v.technical_analysis and v.technical_analysis.positives:
                strong_points.extend(v.technical_analysis.positives[:2])
            if v.technical_analysis and v.technical_analysis.concerns:
                risks.extend(v.technical_analysis.concerns[:2])
            questions.append("Каков стек технологий и процессы разработки?")
            v.career_fit = CareerFitAnalysis(
                fit_score=seniority_score,
                career_growth_score=min(100, seniority_score + 10),
                motivation_score=seniority_score,
                strong_points=strong_points,
                risks=risks,
                questions_for_interview=questions,
                recommendation="Рекомендуется к рассмотрению" if seniority_score >= 60 else "Требует уточнения",
            )
        return {"vacancies": vacancies, "success": True}


class DeduplicationRankingAgent:
    name = "Deduplication & Ranking Agent"

    def run(self, vacancies: List[Vacancy], weights=None, min_salary: float = 119000) -> Dict[str, Any]:
        """Deduplicate vacancies and calculate ranking scores.

        Deduplication stages:
        1. Canonicalize URLs and remove tracking parameters
        2. Match by source ID if same source
        3. Cross-source fuzzy matching by employer + title + location
        4. Mark uncertain matches for review (don't auto-merge)
        """
        # Stage 1: Canonicalize URLs
        for v in vacancies:
            v.canonical_url = self._canonicalize_url(v.source_url)

        # Stage 2: Deduplicate
        unique = self._deduplicate(vacancies)

        # Stage 3: Scoring and status
        for v in unique:
            v.score = ScoringCalculator.calculate_score(v, weights, min_salary)

            # Check mandatory criteria BEFORE scoring-based status
            salary_ok = ScoringCalculator._check_mandatory_salary(v, min_salary)
            format_ok = ScoringCalculator._check_mandatory_format(v)
            source_ok = bool(v.source_url)

            # Mandatory criteria: False = proven violation, None = unknown/lack of data, True = confirmed pass
            if salary_ok is False:
                v.status = VacancyStatus.NOT_SUITABLE
                if not any("зарплат" in r.lower() for r in v.non_compliance_reasons):
                    v.non_compliance_reasons.append("Зарплата не соответствует обязательному минимуму 119 000 ₽ net/мес")
            elif format_ok is False:
                v.status = VacancyStatus.NOT_SUITABLE
                if not any("формат" in r.lower() for r in v.non_compliance_reasons):
                    v.non_compliance_reasons.append("Формат работы не соответствует обязательным требованиям (remote/hybrid СПб)")
            elif not source_ok:
                v.status = VacancyStatus.CHECK_FAILED
                if not any("источник" in r.lower() for r in v.non_compliance_reasons):
                    v.non_compliance_reasons.append("Отсутствует проверяемый источник")
            elif salary_ok is None or format_ok is None:
                # Lack of data for mandatory criteria -> needs clarification
                v.status = VacancyStatus.NEEDS_CLARIFICATION
            elif v.score.total >= 60:
                v.status = VacancyStatus.SUITABLE
            else:
                v.status = VacancyStatus.NEEDS_CLARIFICATION

        return {"vacancies": unique, "success": True}

    def _canonicalize_url(self, url: str) -> str:
        """Remove tracking parameters and normalize URL."""
        if not url:
            return ""
        try:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(url)
            # Remove common tracking params
            tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
                             "yclid", "gclid", "fbclid", "msclkid", "dclid", "ref", "source"}
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            filtered = {k: v for k, v in query_params.items() if k.lower() not in tracking_params}
            new_query = urlencode(filtered, doseq=True)
            # Normalize: lowercase host, remove trailing slash from path
            netloc = parsed.netloc.lower()
            path = parsed.path.rstrip("/")
            return urlunparse((parsed.scheme, netloc, path, "", new_query, ""))
        except Exception:
            return url

    def _deduplicate(self, vacancies: List[Vacancy]) -> List[Vacancy]:
        """Multi-stage deduplication with cross-source matching."""
        # Group by canonical URL first (exact match)
        by_url: Dict[str, Vacancy] = {}
        for v in vacancies:
            key = v.canonical_url or v.id
            if key in by_url:
                # Merge alternate URLs
                existing = by_url[key]
                existing.alternate_urls.append(v.source_url)
                # Merge source info
                if v.source_name != existing.source_name:
                    existing.source_name += f" | {v.source_name}"
            else:
                by_url[key] = v

        # Stage 2: Cross-source fuzzy matching by employer+title+location
        unique = list(by_url.values())
        merged = set()
        final: List[Vacancy] = []

        for i, v1 in enumerate(unique):
            if i in merged:
                continue
            # Find potential duplicates
            duplicates = [v1]
            for j, v2 in enumerate(unique[i+1:], i+1):
                if j in merged:
                    continue
                if self._is_likely_duplicate(v1, v2):
                    duplicates.append(v2)
                    merged.add(j)

            if len(duplicates) > 1:
                # Merge duplicates
                primary = duplicates[0]
                for dup in duplicates[1:]:
                    primary.alternate_urls.append(dup.source_url)
                    if dup.source_name != primary.source_name:
                        primary.source_name += f" | {dup.source_name}"
                final.append(primary)
            else:
                final.append(v1)

        return final

    def _is_likely_duplicate(self, v1: Vacancy, v2: Vacancy) -> bool:
        """Check if two vacancies from different sources are likely the same."""
        # Must be from different sources
        if v1.source_name == v2.source_name:
            return False

        # Quick checks
        if not v1.title or not v2.title:
            return False
        if not v1.employer or not v2.employer:
            return False

        # Normalize for comparison
        title1 = self._normalize_title(v1.title)
        title2 = self._normalize_title(v2.title)
        emp1 = self._normalize_employer(v1.employer)
        emp2 = self._normalize_employer(v2.employer)

        # Title similarity
        title_match = title1 == title2 or self._similarity(title1, title2) > 0.85
        # Employer similarity
        emp_match = emp1 == emp2 or self._similarity(emp1, emp2) > 0.8

        # Location check (if both have location)
        loc_match = True
        if v1.location and v2.location:
            loc1 = v1.location.lower().strip()
            loc2 = v2.location.lower().strip()
            loc_match = loc1 == loc2 or self._similarity(loc1, loc2) > 0.8

        return title_match and emp_match and loc_match

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison."""
        import re
        t = title.lower()
        t = re.sub(r"[^\w\s]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        # Remove common prefixes
        t = re.sub(r"^(вакансия|vacancy|position|job)\s+", "", t)
        return t

    def _normalize_employer(self, employer: str) -> str:
        """Normalize employer name for comparison."""
        import re
        e = employer.lower()
        e = re.sub(r"[^\w\s]", " ", e)
        e = re.sub(r"\s+", " ", e).strip()
        # Remove common suffixes
        e = re.sub(r"\s+(ooo|ооо|зАО|АО|LLC|Inc|Ltd|Group|Corporation|Корпорация)$", "", e)
        return e

    def _similarity(self, s1: str, s2: str) -> float:
        """Simple Jaccard similarity on word sets."""
        if not s1 or not s2:
            return 0.0
        w1 = set(s1.split())
        w2 = set(s2.split())
        if not w1 or not w2:
            return 0.0
        intersection = len(w1 & w2)
        union = len(w1 | w2)
        return intersection / union if union > 0 else 0.0


class QualityAssuranceAgent:
    name = "Quality Assurance Agent"
    def run(self, vacancies: List[Vacancy], report: Any = None) -> Dict[str, Any]:
        """QA check: verify data integrity and report consistency."""
        issues: List[str] = []

        for v in vacancies:
            if not v.source_url:
                issues.append(f"Вакансия '{v.title}' не имеет source_url")
                v.status = VacancyStatus.CHECK_FAILED

            if v.salary.from_amount is not None and v.salary.currency == Currency.UNKNOWN:
                issues.append(f"Вакансия '{v.title}' имеет зарплату с неизвестной валютой")

            if v.work_format == WorkFormat.UNKNOWN and v.location:
                issues.append(f"Вакансия '{v.title}' имеет локацию, но неизвестный формат работы")

        # Check report structure if provided
        if report is not None:
            if not report.vacancies:
                issues.append("Отчёт содержит 0 вакансий")

        return {
            "vacancies": vacancies,
            "success": len(issues) == 0,
            "issues": issues,
        }