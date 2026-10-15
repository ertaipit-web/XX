"""Candidate profile with skill evidence model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.enums import Currency, WorkFormat
from ..core.models import CandidateProfile as BaseCandidateProfile


class SkillEvidenceType(str, Enum):
    """Type of evidence for a skill."""
    RESUME = "resume"
    SELF_REPORT = "self_report"
    INTERVIEW_ANSWER = "interview_answer"
    PRACTICAL_ASSESSMENT = "practical_assessment"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


class SkillConfidence(str, Enum):
    """Confidence level for skill evidence."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass
class SkillEvidence:
    """Evidence for a candidate skill."""
    skill_id: str
    skill_name: str
    aliases: List[str] = field(default_factory=list)
    proficiency_level: Optional[str] = None  # e.g., "beginner", "intermediate", "advanced", "expert"
    evidence_type: SkillEvidenceType = SkillEvidenceType.UNKNOWN
    evidence_note: Optional[str] = None
    confidence: SkillConfidence = SkillConfidence.UNKNOWN
    source: Optional[str] = None  # e.g., "resume", "interview", "assessment"
    assessed_at: Optional[datetime] = None
    schema_version: str = "1.0"
    notes: Optional[str] = None
    next_action: Optional[str] = None


@dataclass
class SkillGap:
    """Gap between target and current skill level."""
    skill_id: str
    skill_name: str
    target_importance: str  # "core", "frequent", "preferred", "occasional", "unknown"
    current_status: Optional[str] = None  # candidate's current level
    evidence_status: str = "unknown"  # "confirmed", "self_reported", "inferred", "unknown", "needs_assessment"
    confidence: str = "unknown"
    gap_type: str = "unknown"  # "confirmed_gap", "needs_assessment", "matches_target", "not_relevant", "unknown"
    rationale: Optional[str] = None
    supporting_sources: List[str] = field(default_factory=list)
    recommended_action: Optional[str] = None


@dataclass
class CandidateProfile:
    """Extended candidate profile with skill evidence and role preferences."""
    # Base profile fields
    profession: str = "Go-разработчик"
    candidate_level: str = "junior"
    experience_years: Optional[int] = None
    locations: List[str] = field(default_factory=lambda: ["Санкт-Петербург", "Удалённая работа"])
    work_formats: List[WorkFormat] = field(default_factory=lambda: [WorkFormat.REMOTE, WorkFormat.HYBRID])
    min_salary_rub_month: float = 119000.0
    min_salary_tax_basis: str = "net"
    min_salary_period: str = "month"
    min_salary_is_mandatory: bool = True
    dms_mode: str = "prefer"
    language: str = "ru"
    main_currency: str = "RUB"
    search_frequency: Optional[str] = "daily"
    llm_provider: str = "ollama"
    cloud_fallback_enabled: bool = False
    additional_notes: Optional[str] = None
    contradictions: List[str] = field(default_factory=list)
    missing_data: List[str] = field(default_factory=list)

    # Extended fields for Task 04
    role_pack_id: str = "go_junior"
    skills: List[SkillEvidence] = field(default_factory=list)
    skill_gaps: List[SkillGap] = field(default_factory=list)
    resume_source: Optional[str] = None  # "file", "manual", "url", "interview"
    resume_file_path: Optional[str] = None
    resume_parsed_at: Optional[str] = None
    interview_completed: bool = False
    interview_questions_asked: List[str] = field(default_factory=list)
    interview_answers: Dict[str, str] = field(default_factory=dict)
    practical_assessments: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    schema_version: str = "1.0"

    def get_skill(self, skill_id: str) -> Optional[Any]:
        """Get skill evidence by skill ID."""
        for skill in self.skills:
            if skill.skill_id == skill_id or skill.skill_name.lower() == skill_id.lower():
                return skill
            if skill_id.lower() in [a.lower() for a in skill.aliases]:
                return skill
        return None

    def has_skill(self, skill_id: str) -> bool:
        """Check if candidate has a skill (any evidence)."""
        return self.get_skill(skill_id) is not None

    def get_skills_by_type(self, evidence_type: str) -> List[Any]:
        """Get skills filtered by evidence type."""
        return [s for s in self.skills if s.evidence_type.value == evidence_type]

    def add_skill(self, skill: Any) -> None:
        """Add or update skill evidence."""
        existing = self.get_skill(skill.skill_id)
        if existing:
            # Merge evidence - keep highest confidence
            if self._confidence_order(skill.confidence) > self._confidence_order(existing.confidence):
                existing.proficiency_level = skill.proficiency_level
                existing.evidence_type = skill.evidence_type
                existing.evidence_note = skill.evidence_note
                existing.confidence = skill.confidence
                existing.source = skill.source
                existing.assessed_at = skill.assessed_at
                existing.notes = skill.notes
        else:
            self.skills.append(skill)
        self.updated_at = datetime.now().isoformat()

    def _confidence_order(self, confidence: str) -> int:
        order = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
        return order.get(confidence.lower() if isinstance(confidence, str) else str(confidence).lower(), 0)


class CandidateProfileManager:
    """Manage candidate profiles with local storage."""

    def __init__(self, data_dir: str = "data/candidates") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, profile: CandidateProfile, profile_id: str = "default") -> Path:
        """Save profile to local JSON file."""
        import json
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / f"{profile_id}.json"

        # Convert to dict
        data = self._profile_to_dict(profile)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, profile_id: str = "default") -> Optional[CandidateProfile]:
        """Load profile from local JSON file."""
        import json
        path = self.data_dir / f"{profile_id}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        return self._dict_to_profile(data)

    def list_profiles(self) -> List[str]:
        """List available profile IDs."""
        if not self.data_dir.exists():
            return []
        return [f.stem for f in self.data_dir.glob("*.json")]

    def _profile_to_dict(self, profile: CandidateProfile) -> Dict[str, Any]:
        """Convert profile to dict for JSON serialization."""
        from dataclasses import asdict
        data = asdict(profile)
        # Convert enums to strings
        for skill in data.get("skills", []):
            if "evidence_type" in skill:
                skill["evidence_type"] = skill["evidence_type"].value if hasattr(skill["evidence_type"], "value") else skill["evidence_type"]
            if "confidence" in skill:
                skill["confidence"] = skill["confidence"].value if hasattr(skill["confidence"], "value") else skill["confidence"]
        for gap in data.get("skill_gaps", []):
            if "confidence" in gap:
                gap["confidence"] = gap["confidence"] if isinstance(gap["confidence"], str) else gap["confidence"]
        return data

    def _dict_to_profile(self, data: Dict[str, Any]) -> CandidateProfile:
        """Convert dict to CandidateProfile."""
        skills = []
        for s in data.get("skills", []):
            s = dict(s)
            # Restore enum-typed fields (stored as their .value strings in JSON)
            et = s.get("evidence_type")
            if isinstance(et, str):
                s["evidence_type"] = SkillEvidenceType(et)
            cf = s.get("confidence")
            if isinstance(cf, str):
                s["confidence"] = SkillConfidence(cf)
            skills.append(SkillEvidence(**s))

        gaps = []
        for g in data.get("skill_gaps", []):
            gaps.append(SkillGap(**g))

        # Remove skills and gaps from data before creating profile
        profile_data = {k: v for k, v in data.items() if k not in ("skills", "skill_gaps")}
        profile = CandidateProfile(**profile_data)
        profile.skills = skills
        profile.skill_gaps = gaps
        return profile