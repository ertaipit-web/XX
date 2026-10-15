"""Candidate gap analysis and learning/interview preparation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..candidate.profile import CandidateProfile, SkillEvidence, SkillGap
from ..role_pack.go_junior import GO_JUNIOR_ROLE_PACK
from ..market.analyzer import SkillStatistics

logger = logging.getLogger(__name__)


@dataclass
class LearningPlanItem:
    """Single item in learning plan."""
    skill_id: str
    skill_name: str
    gap_type: str  # confirmed_gap, needs_assessment, matches_target, not_relevant, unknown
    priority: int  # 1 = highest
    reason: str
    estimated_effort_hours: Optional[float] = None
    learning_outcome: str = ""
    practical_exercise: Optional[str] = None
    interview_questions: List[str] = field(default_factory=list)
    resources: List[Dict[str, str]] = field(default_factory=list)  # title, url, type, access_date, skill_coverage


@dataclass
class GapAnalysisResult:
    """Complete gap analysis result."""
    target_role: str
    candidate_profile_id: str
    analysis_date: str = field(default_factory=lambda: datetime.now().isoformat())
    skill_gaps: List["SkillGap"] = field(default_factory=list)
    learning_plan: List[Any] = field(default_factory=list)
    interview_prep: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


class GapAnalyzer:
    """Analyze gaps between candidate profile and target role."""

    def __init__(self, role_pack_id: str = "go_junior") -> None:
        self.role_pack = GO_JUNIOR_ROLE_PACK

    def analyze(self, profile: Any, market_stats: List[Any]) -> Any:
        """Perform gap analysis between candidate profile and target role."""
        skill_gaps = []
        learning_plan = []
        interview_prep = []

        # Create lookup for market stats
        market_lookup = {s["skill_id"]: s for s in market_stats}

        # The profile may be core.models.CandidateProfile or the extended
        # candidate.profile.CandidateProfile; both may not expose get_skill.
        get_skill = getattr(profile, "get_skill", lambda _sid: None)

        for skill_def in GO_JUNIOR_ROLE_PACK.skills:
            skill_id = skill_def.skill_id
            market_stat = market_lookup.get(skill_id, {})
            market_freq = market_stat.get("total_vacancies", 0)
            market_pct = market_stat.get("percentage_of_vacancies", 0)

            # Get candidate's evidence for this skill (may be None)
            evidence = get_skill(skill_def.skill_id)

            # Determine gap
            gap = self._analyze_skill_gap(
                skill_def=skill_def,
                evidence=evidence,
                market_frequency=market_freq,
                market_percentage=market_pct,
                market_stat=market_stat,
            )
            skill_gaps.append(gap)

            # Generate learning plan item if gap exists
            if gap.gap_type in ("confirmed_gap", "needs_assessment"):
                plan_item = self._create_learning_plan_item(skill_def, gap, market_stat)
                if plan_item:
                    # Add to learning plan
                    pass  # Will collect below

        # Build learning plan
        learning_plan = self._build_learning_plan(skill_gaps)

        # Build interview prep
        interview_prep = self._build_interview_prep(skill_gaps)

        # Create summary
        summary = self._create_summary(skill_gaps)

        return {
            "skill_gaps": skill_gaps,
            "learning_plan": learning_plan,
            "interview_prep": interview_prep,
            "summary": summary,
        }

    def _analyze_skill_gap(
        self,
        skill_def: Any,
        evidence: Any,
        market_frequency: int,
        market_percentage: float,
        market_stat: Dict[str, Any] | None = None,
    ) -> Any:
        """Analyze gap for a single skill."""
        from ..candidate.profile import SkillGap

        # Determine target importance
        importance = skill_def.importance
        if importance == "core":
            target_importance = "core"
        elif importance == "frequent":
            target_importance = "frequent"
        elif importance == "preferred":
            target_importance = "preferred"
        elif importance == "occasional":
            target_importance = "occasional"
        else:
            target_importance = "unknown"

        # Check candidate evidence
        evidence_obj = evidence
        if evidence_obj is None:
            # No evidence at all — treat as unknown, never invent a level
            if skill_def.importance in ("core", "frequent"):
                gap_type = "needs_assessment"
                evidence_status = "unknown"
                confidence = "low"
            else:
                gap_type = "not_relevant"
                evidence_status = "unknown"
                confidence = "low"
        else:
            # Has some evidence
            if evidence_obj.confidence == "high" and evidence_obj.proficiency_level in ("advanced", "expert"):
                gap_type = "matches_target"
                evidence_status = "confirmed"
                confidence = "high"
            elif evidence_obj.confidence == "high" and evidence_obj.proficiency_level in ("intermediate",):
                if skill_def.importance in ("core", "frequent"):
                    gap_type = "confirmed_gap"
                    evidence_status = "self_reported"
                    confidence = "high"
                else:
                    gap_type = "matches_target"
                    evidence_status = "self_reported"
                    confidence = "medium"
            else:
                gap_type = "needs_assessment"
                evidence_status = evidence_obj.evidence_type.value if hasattr(evidence_obj, "evidence_type") else "unknown"
                confidence = "low"

        # Determine rationale
        rationale_parts = []
        if skill_def.importance == "core":
            rationale_parts.append("Core skill for the role")
        elif skill_def.importance == "frequent":
            rationale_parts.append(f"Requested in {skill_def.importance} of vacancies")
        rationale = "; ".join(rationale_parts) if rationale_parts else "Skill relevant to role"

        # Recommended action
        if gap_type == "confirmed_gap":
            recommended = "Изучить/практиковать навык до уровня intermediate"
        elif gap_type == "needs_assessment":
            recommended = "Пройти практическое задание или самодиагностику"
        elif gap_type == "matches_target":
            recommended = "Поддерживать уровень, готовиться к вопросам на собеседовании"
        else:
            recommended = "Не приоритетно для данной роли"

        return SkillGap(
            skill_id=skill_def.skill_id,
            skill_name=skill_def.name,
            target_importance=skill_def.importance,
            current_status=evidence_obj.proficiency_level if evidence_obj else None,
            evidence_status=evidence_status,
            confidence=confidence,
            gap_type=gap_type,
            rationale=rationale,
            supporting_sources=list((market_stat or {}).get("evidence", [])),
            recommended_action=recommended,
        )

    def _create_learning_plan_item(self, skill_def: Any, gap: Any, market_stat: Dict[str, Any]) -> Any:
        """Create a learning plan item for a skill gap."""
        from ..candidate.gap_analysis import LearningPlanItem

        # Priority based on importance and market frequency
        priority = 1
        if skill_def.importance == "core":
            priority = 1
        elif skill_def.importance == "frequent":
            priority = 2
        elif skill_def.importance == "preferred":
            priority = 3
        else:
            priority = 4

        # Adjust by market frequency
        market_pct = market_stat.get("percentage_of_vacancies", 0)
        if market_pct > 50:
            priority = max(1, priority - 1)

        # Estimate effort
        effort_map = {
            "core": 40,
            "frequent": 25,
            "preferred": 15,
            "occasional": 10,
            "unknown": 20,
        }
        effort = effort_map.get(skill_def.importance, 20)

        # Resources: only catalog entries with real URLs are emitted (never
        # invent a URL). Falls back to the role-pack catalog + practical task.
        from ..candidate.resources import DEFAULT_CATALOG

        resources = DEFAULT_CATALOG.resolve(
            skill_def.learning_resources, skill_id=skill_def.skill_id
        )
        # Ensure at least the canonical resource catalog is considered
        if not resources:
            for res_id in GO_JUNIOR_ROLE_PACK.learning_resource_catalog:
                resources.extend(
                    DEFAULT_CATALOG.resolve([res_id], skill_id=skill_def.skill_id)
                )
        # Deduplicate by url
        seen = set()
        deduped = []
        for r in resources:
            if r["url"] not in seen:
                seen.add(r["url"])
                deduped.append(r)
        resources = deduped

        # Practical exercise from role pack
        practical = None
        for assessment in GO_JUNIOR_ROLE_PACK.practical_assessments:
            if assessment.get("skill_id") == skill_def.skill_id:
                practical = assessment.get("task")
                break

        # Interview questions
        questions = []
        for q in skill_def.interview_questions:
            questions.append(q)

        return LearningPlanItem(
            skill_id=skill_def.skill_id,
            skill_name=skill_def.name,
            gap_type="",  # Will be set by caller
            priority=priority,
            reason=f"Рыночная частота: {market_stat.get('percentage_of_vacancies', 0)}% вакансий",
            estimated_effort_hours=effort,
            learning_outcome=f"Уверенное владение {skill_def.name} на уровне, достаточном для Junior Go Developer",
            practical_exercise=practical,
            interview_questions=questions,
            resources=resources,
        )

    def _build_learning_plan(self, skill_gaps: List[Any]) -> List[Any]:
        """Build prioritized learning plan from skill gaps."""
        from ..candidate.gap_analysis import LearningPlanItem

        plan_items = []

        for gap in skill_gaps:
            if gap.gap_type not in ("confirmed_gap", "needs_assessment"):
                continue

            skill_def = GO_JUNIOR_ROLE_PACK.get_skill(gap.skill_id)
            if not skill_def:
                continue

            # Determine priority
            priority = {"core": 1, "frequent": 2, "preferred": 3, "occasional": 4, "unknown": 5}.get(skill_def.importance, 5)

            # Estimate effort
            effort_map = {"core": 40, "frequent": 25, "preferred": 15, "occasional": 10, "unknown": 20}
            effort = effort_map.get(skill_def.importance, 20)

            # Resources: only catalog entries with real URLs (never invent one)
            from ..candidate.resources import DEFAULT_CATALOG

            resources = DEFAULT_CATALOG.resolve(
                skill_def.learning_resources, skill_id=skill_def.skill_id
            )
            if not resources:
                for res_id in GO_JUNIOR_ROLE_PACK.learning_resource_catalog:
                    resources.extend(
                        DEFAULT_CATALOG.resolve([res_id], skill_id=skill_def.skill_id)
                    )

            # Practical exercise
            practical = None
            for assessment in GO_JUNIOR_ROLE_PACK.practical_assessments:
                if assessment.get("skill_id") == skill_def.skill_id:
                    practical = assessment.get("task")
                    break

            # Interview questions
            questions = skill_def.interview_questions[:3]

            item = {
                "skill_id": skill_def.skill_id,
                "skill_name": skill_def.name,
                "gap_type": gap.gap_type,
                "priority": priority,
                "reason": f"Рыночная частота: {skill_def.importance} для роли",
                "estimated_effort_hours": effort_map.get(skill_def.importance, 20),
                "learning_outcome": f"Уверенное владение {skill_def.name} на уровне Junior",
                "practical_exercise": practical,
                "interview_questions": questions,
                "resources": resources,
            }
            plan_items.append(item)

        # Sort by priority
        plan_items.sort(key=lambda x: x.get("priority", 5))
        return plan_items

    def _build_interview_prep(self, skill_gaps: List[Any]) -> List[Dict[str, Any]]:
        """Build interview preparation items."""
        prep_items = []

        for gap in skill_gaps:
            skill_def = GO_JUNIOR_ROLE_PACK.get_skill(gap.skill_id)
            if not skill_def:
                continue

            questions = []
            for q in skill_def.interview_questions[:3]:
                questions.append({
                    "question": q,
                    "type": "theory",
                    "target_skill": skill_def.skill_id,
                    "rubric": f"Assess {skill_def.name} understanding",
                })

            # Add practical task if available
            for assessment in GO_JUNIOR_ROLE_PACK.practical_assessments:
                if assessment.get("skill_id") == skill_def.skill_id:
                    questions.append({
                        "question": assessment["task"],
                        "type": "practical",
                        "target_skill": skill_def.skill_id,
                        "rubric": assessment.get("rubric", ""),
                        "time_limit_minutes": assessment.get("time_limit_minutes", 30),
                    })
                    break

            if questions:
                prep_items.append({
                    "skill_id": skill_def.skill_id,
                    "skill_name": skill_def.name,
                    "gap_type": gap.gap_type,
                    "questions": questions,
                    "priority": {"core": 1, "frequent": 2, "preferred": 3}.get(skill_def.importance, 4),
                })

        # Sort by priority
        prep_items.sort(key=lambda x: x.get("priority", 5))
        return prep_items

    def _create_summary(self, skill_gaps: List[Any]) -> Dict[str, Any]:
        """Create summary of gap analysis."""
        total_skills = len(GO_JUNIOR_ROLE_PACK.skills)
        core_skills = [s for s in GO_JUNIOR_ROLE_PACK.skills if s.importance == "core"]
        frequent_skills = [s for s in GO_JUNIOR_ROLE_PACK.skills if s.importance == "frequent"]

        gaps = {"confirmed_gap": 0, "needs_assessment": 0, "matches_target": 0, "not_relevant": 0, "unknown": 0}
        for gap in skill_gaps:
            gaps[gap.gap_type] = gaps.get(gap.gap_type, 0) + 1

        return {
            "total_skills_in_role": total_skills,
            "core_skills": len(core_skills),
            "frequent_skills": len(frequent_skills),
            "gap_distribution": gaps,
            "core_gaps": sum(1 for g in skill_gaps if g.gap_type in ("confirmed_gap", "needs_assessment") and g.target_importance == "core"),
            "frequent_gaps": sum(1 for g in skill_gaps if g.gap_type in ("confirmed_gap", "needs_assessment") and g.target_importance == "frequent"),
            "ready_skills": sum(1 for g in skill_gaps if g.gap_type == "matches_target"),
        }