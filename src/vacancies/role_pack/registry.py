"""Role pack registry for loading and managing role packs."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .go_junior import GO_JUNIOR_ROLE_PACK

logger = logging.getLogger(__name__)


class RolePackRegistry:
    """Registry for loading and managing role packs."""

    def __init__(self, packs_dir: str = "config/role_packs") -> None:
        self.packs_dir = Path(packs_dir)
        self.packs_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Any] = {}
        self._builtin_packs = {
            "go_junior": GO_JUNIOR_ROLE_PACK,
        }

    def load(self, role_id: str) -> Optional[Any]:
        """Load role pack by ID."""
        if role_id in self._cache:
            return self._cache[role_id]

        # Check builtin packs first
        if role_id in self._builtin_packs:
            self._cache[role_id] = self._builtin_packs[role_id]
            return self._cache[role_id]

        # Try loading from file
        path = self.packs_dir / f"{role_id}.json"
        if path.exists():
            try:
                import json
                data = json.loads(path.read_text(encoding="utf-8"))
                from .go_junior import RolePack, SkillDefinition
                skills = [SkillDefinition(**s) for s in data.get("skills", [])]
                pack = RolePack(
                    role_id=data["role_id"],
                    role_name=data["role_name"],
                    role_family=data["role_family"],
                    seniority=data["seniority"],
                    title_aliases_ru=data.get("title_aliases_ru", []),
                    title_aliases_en=data.get("title_aliases_en", []),
                    search_phrases=data.get("search_phrases", []),
                    skills=[SkillDefinition(**s) for s in data.get("skills", [])],
                    mandatory_skills=data.get("mandatory_skills", []),
                    preferred_skills=data.get("preferred_skills", []),
                    interview_topics=data.get("interview_topics", []),
                    practical_assessments=data.get("practical_assessments", []),
                    learning_resource_catalog=data.get("learning_resource_catalog", []),
                    normalization_rules=data.get("normalization_rules", {}),
                    version=data.get("version", "1.0"),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    schema_version=data.get("schema_version", "1.0"),
                )
                self._cache[role_id] = pack
                return pack
            except Exception as e:
                logger.error(f"Failed to load role pack {role_id}: {e}")
                return None

        return None

    def get_or_create_default(self, role_id: str = "go_junior") -> Any:
        """Get role pack, using Go Junior as default."""
        pack = self.load(role_id)
        if pack is None and role_id != "go_junior":
            logger.warning(f"Role pack {role_id} not found, falling back to go_junior")
            return self._builtin_packs["go_junior"]
        return pack or self._builtin_packs["go_junior"]

    def save(self, pack: Any) -> None:
        """Save role pack to JSON file."""
        import json
        self.packs_dir.mkdir(parents=True, exist_ok=True)
        path = self.packs_dir / f"{pack.role_id}.json"

        data = {
            "role_id": pack.role_id,
            "role_name": pack.role_name,
            "role_family": pack.role_family,
            "seniority": pack.seniority,
            "title_aliases_ru": pack.title_aliases_ru,
            "title_aliases_en": pack.title_aliases_en,
            "search_phrases": pack.search_phrases,
            "skills": [
                {
                    "skill_id": s.skill_id,
                    "name": s.name,
                    "aliases": s.aliases,
                    "category": s.category,
                    "importance": s.importance,
                    "requirement_strength": s.requirement_strength,
                    "description": s.description,
                    "learning_resources": s.learning_resources,
                    "interview_questions": s.interview_questions,
                    "practical_tasks": s.practical_tasks,
                }
                for s in pack.skills
            ],
            "mandatory_skills": pack.mandatory_skills,
            "preferred_skills": pack.preferred_skills,
            "interview_topics": pack.interview_topics,
            "practical_assessments": pack.practical_assessments,
            "learning_resource_catalog": pack.learning_resource_catalog,
            "normalization_rules": pack.normalization_rules,
            "version": pack.version,
            "created_at": pack.created_at,
            "updated_at": pack.updated_at,
            "schema_version": pack.schema_version,
        }
        path = self.packs_dir / f"{pack.role_id}.json"
        self.packs_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_packs(self) -> List[str]:
        """List available role pack IDs."""
        packs = set(self._builtin_packs.keys())
        if self.packs_dir.exists():
            for f in self.packs_dir.glob("*.json"):
                packs.add(f.stem)
        return sorted(packs)