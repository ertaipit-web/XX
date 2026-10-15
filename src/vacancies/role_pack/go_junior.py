"""Role Pack abstraction for job role profiles."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillDefinition:
    """Definition of a skill in a role pack."""
    skill_id: str
    name: str
    aliases: List[str] = field(default_factory=list)
    category: str = "unknown"  # language, framework, database, infrastructure, testing, method, domain, soft_skill
    importance: str = "unknown"  # core, frequent, preferred, occasional, unknown
    requirement_strength: str = "explicit_required"  # explicit_required, explicit_preferred, mentioned, inferred
    description: Optional[str] = None
    learning_resources: List[str] = field(default_factory=list)
    interview_questions: List[str] = field(default_factory=list)
    practical_tasks: List[str] = field(default_factory=list)


@dataclass
class RolePack:
    """Role pack definition for a specific role profile."""
    role_id: str
    role_name: str
    role_family: str  # e.g., "backend", "frontend", "devops", "fullstack", "data"
    seniority: str  # junior, middle, senior, lead, staff, principal
    title_aliases_ru: List[str] = field(default_factory=list)
    title_aliases_en: List[str] = field(default_factory=list)
    search_phrases: List[str] = field(default_factory=list)
    skills: List[SkillDefinition] = field(default_factory=list)
    mandatory_skills: List[str] = field(default_factory=list)  # skill_ids
    preferred_skills: List[str] = field(default_factory=list)
    interview_topics: List[str] = field(default_factory=list)
    practical_assessments: List[Dict[str, Any]] = field(default_factory=list)
    learning_resource_catalog: List[str] = field(default_factory=list)  # resource IDs
    normalization_rules: Dict[str, str] = field(default_factory=dict)  # alias -> canonical_skill_id
    version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    schema_version: str = "1.0"

    def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        """Get skill definition by ID or alias."""
        for skill in self.skills:
            if skill.skill_id == skill_id:
                return skill
            for alias in skill.aliases:
                if alias.lower() == skill_id.lower():
                    return skill
        return None

    def get_skills_by_category(self, category: str) -> List[SkillDefinition]:
        return [s for s in self.skills if s.category == category]

    def get_skills_by_importance(self, importance: str) -> List[SkillDefinition]:
        return [s for s in self.skills if s.importance == importance]

    def get_mandatory_skills(self) -> List[SkillDefinition]:
        return [self.get_skill(s) for s in self.mandatory_skills if self.get_skill(s)]

    def get_preferred_skills(self) -> List[SkillDefinition]:
        return [self.get_skill(s) for s in self.preferred_skills if self.get_skill(s)]


class RolePackRegistry:
    """Registry for loading and managing role packs."""

    def __init__(self, packs_dir: str = "config/role_packs") -> None:
        self.packs_dir = Path(packs_dir)
        self.packs_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, RolePack] = {}

    def load(self, role_id: str) -> Optional[RolePack]:
        """Load role pack by ID."""
        if role_id in self._cache:
            return self._cache[role_id]

        path = self.packs_dir / f"{role_id}.json"
        if not path.exists():
            logger.warning(f"Role pack not found: {path}")
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pack = self._dict_to_role_pack(data)
            self._cache[role_id] = pack
            return pack
        except Exception as e:
            logger.error(f"Failed to load role pack {role_id}: {e}")
            return None

    def save(self, pack: RolePack) -> Path:
        """Save role pack to JSON file."""
        self.packs_dir.mkdir(parents=True, exist_ok=True)
        path = self.packs_dir / f"{pack.role_id}.json"

        data = self._role_pack_to_dict(pack)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def list_packs(self) -> List[str]:
        """List available role pack IDs."""
        if not self.packs_dir.exists():
            return []
        return [f.stem for f in self.packs_dir.glob("*.json")]

    def _role_pack_to_dict(self, pack: RolePack) -> Dict[str, Any]:
        """Convert RolePack to dict for JSON serialization."""
        return {
            "role_id": pack.role_id,
            "role_name": pack.role_name,
            "role_family": pack.role_family,
            "seniority": pack.seniority,
            "title_aliases_ru": pack.title_aliases_ru,
            "title_aliases_en": pack.title_aliases_en,
            "search_phrases": pack.search_phrases,
            "skills": [asdict(s) for s in pack.skills],
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

    def _dict_to_role_pack(self, data: Dict[str, Any]) -> RolePack:
        """Convert dict to RolePack."""
        skills = [SkillDefinition(**s) for s in data.get("skills", [])]
        return RolePack(
            role_id=data["role_id"],
            role_name=data["role_name"],
            role_family=data["role_family"],
            seniority=data["seniority"],
            title_aliases_ru=data.get("title_aliases_ru", []),
            title_aliases_en=data.get("title_aliases_en", []),
            search_phrases=data.get("search_phrases", []),
            skills=skills,
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


# Default Go Junior Role Pack
GO_JUNIOR_ROLE_PACK = RolePack(
    role_id="go_junior",
    role_name="Junior Go Developer",
    role_family="backend",
    seniority="junior",
    title_aliases_ru=[
        "Go-разработчик",
        "Golang-разработчик",
        "Junior Go-разработчик",
        "Junior Golang-разработчик",
        "Младший Go-разработчик",
        "Backend-разработчик на Go",
        "Backend-разработчик на Golang",
    ],
    title_aliases_en=[
        "Junior Go Developer",
        "Junior Golang Developer",
        "Go Developer",
        "Golang Developer",
        "Junior Backend Developer (Go)",
    ],
    search_phrases=[
        "Go разработчик",
        "Golang разработчик",
        "Junior Go",
        "Junior Golang",
        "Go разработчик junior",
    ],
    skills=[
        # Core languages
        SkillDefinition(
            skill_id="go",
            name="Go",
            aliases=["golang", "go", "gopher"],
            category="language",
            importance="core",
            requirement_strength="explicit_required",
            description="Go programming language proficiency",
        ),
        # Frameworks & Libraries
        SkillDefinition(
            skill_id="gin",
            name="Gin",
            aliases=["gin-gonic", "gin framework"],
            category="framework",
            importance="frequent",
            requirement_strength="explicit_preferred",
        ),
        SkillDefinition(
            skill_id="echo",
            name="Echo",
            aliases=["echo framework", "labstack/echo"],
            category="framework",
            importance="frequent",
            requirement_strength="explicit_preferred",
        ),
        SkillDefinition(
            skill_id="chi",
            name="Chi",
            aliases=["chi router", "go-chi/chi"],
            category="framework",
            importance="occasional",
            requirement_strength="mentioned",
        ),
        # gRPC & Protocols
        SkillDefinition(
            skill_id="grpc",
            name="gRPC",
            aliases=["grpc", "grpc-go", "protobuf", "proto"],
            category="protocol",
            importance="frequent",
            requirement_strength="explicit_preferred",
        ),
        SkillDefinition(
            skill_id="protobuf",
            name="Protocol Buffers",
            aliases=["protobuf", "proto", "proto3"],
            category="protocol",
            importance="frequent",
            requirement_strength="explicit_preferred",
        ),
        # Databases
        SkillDefinition(
            skill_id="postgresql",
            name="PostgreSQL",
            aliases=["postgresql", "postgres", "pg"],
            category="database",
            importance="core",
            requirement_strength="explicit_required",
        ),
        SkillDefinition(
            skill_id="mysql",
            name="MySQL",
            aliases=["mysql", "mariadb"],
            category="database",
            importance="occasional",
            requirement_strength="mentioned",
        ),
        SkillDefinition(
            skill_id="redis",
            name="Redis",
            aliases=["redis"],
            category="database",
            importance="frequent",
            requirement_strength="explicit_preferred",
        ),
        # Infrastructure & DevOps
        SkillDefinition(
            skill_id="docker",
            name="Docker",
            aliases=["docker", "containerization"],
            category="infrastructure",
            importance="frequent",
            requirement_strength="explicit_preferred",
        ),
        SkillDefinition(
            skill_id="kubernetes",
            name="Kubernetes",
            aliases=["kubernetes", "k8s", "kube"],
            category="infrastructure",
            importance="preferred",
            requirement_strength="explicit_preferred",
        ),
        SkillDefinition(
            skill_id="ci_cd",
            name="CI/CD",
            aliases=["ci/cd", "github actions", "gitlab ci", "jenkins", "ci cd"],
            category="infrastructure",
            importance="preferred",
            requirement_strength="mentioned",
        ),
        # Messaging & Queues
        SkillDefinition(
            skill_id="kafka",
            name="Apache Kafka",
            aliases=["kafka", "apache kafka", "message queue"],
            category="messaging",
            importance="preferred",
            requirement_strength="explicit_preferred",
        ),
        SkillDefinition(
            skill_id="rabbitmq",
            name="RabbitMQ",
            aliases=["rabbitmq", "amqp", "message broker"],
            category="messaging",
            importance="occasional",
            requirement_strength="mentioned",
        ),
        # Concurrency & Systems
        SkillDefinition(
            skill_id="concurrency",
            name="Concurrency Patterns",
            aliases=["concurrency", "goroutines", "channels", "mutex", "sync", "context"],
            category="method",
            importance="core",
            requirement_strength="explicit_required",
            description="Understanding of goroutines, channels, mutexes, context cancellation",
        ),
        SkillDefinition(
            skill_id="distributed_systems",
            name="Distributed Systems Basics",
            aliases=["distributed systems", "microservices", "микросервисы", "распределенные системы"],
            category="method",
            importance="preferred",
            requirement_strength="explicit_preferred",
        ),
        # Testing
        SkillDefinition(
            skill_id="testing",
            name="Testing",
            aliases=["testing", "unit testing", "integration testing", "mock", "testify", "gomock"],
            category="testing",
            importance="frequent",
            requirement_strength="explicit_preferred",
        ),
        # Version Control & Tools
        SkillDefinition(
            skill_id="git",
            name="Git",
            aliases=["git", "version control"],
            category="tool",
            importance="core",
            requirement_strength="explicit_required",
        ),
        SkillDefinition(
            skill_id="linux",
            name="Linux/Unix",
            aliases=["linux", "unix", "bash", "shell", "terminal"],
            category="tool",
            importance="frequent",
            requirement_strength="explicit_preferred",
        ),
        # Monitoring & Observability
        SkillDefinition(
            skill_id="observability",
            name="Observability",
            aliases=["monitoring", "prometheus", "grafana", "logging", "tracing", "jaeger", "zipkin"],
            category="infrastructure",
            importance="preferred",
            requirement_strength="mentioned",
        ),
        # Soft Skills
        SkillDefinition(
            skill_id="communication",
            name="Communication",
            aliases=["communication", "teamwork", "code review", "documentation"],
            category="soft_skill",
            importance="core",
            requirement_strength="explicit_required",
        ),
        SkillDefinition(
            skill_id="problem_solving",
            name="Problem Solving",
            aliases=["problem solving", "debugging", "troubleshooting", "алгоритмы"],
            category="method",
            importance="core",
            requirement_strength="explicit_required",
        ),
    ],
    mandatory_skills=[
        "go", "concurrency", "postgresql", "git", "communication", "problem_solving",
    ],
    preferred_skills=[
        "gin", "echo", "grpc", "protobuf", "redis", "docker", "kubernetes",
        "kafka", "testing", "linux", "observability",
    ],
    interview_topics=[
        "Go fundamentals (goroutines, channels, memory model)",
        "Database design and SQL optimization",
        "API design (REST, gRPC, GraphQL)",
        "Concurrency patterns and synchronization",
        "Testing strategies (unit, integration, mocking)",
        "Docker and containerization basics",
        "CI/CD pipelines",
        "System design basics for junior level",
        "Debugging and profiling Go applications",
    ],
    practical_assessments=[
        {
            "skill_id": "go",
            "task": "Write a simple HTTP server with graceful shutdown",
            "rubric": "Correct use of context, graceful shutdown, error handling",
            "time_limit_minutes": 30,
        },
        {
            "skill_id": "concurrency",
            "task": "Implement a worker pool with bounded concurrency",
            "rubric": "Correct use of channels, wait groups, context cancellation",
            "time_limit_minutes": 25,
        },
        {
            "skill_id": "postgresql",
            "task": "Design a simple schema and write queries with JOIN",
            "rubric": "Correct normalization, indexes, query performance",
            "time_limit_minutes": 20,
        },
    ],
    learning_resource_catalog=[
        "go_official_tutorial",
        "go_by_example",
        "effective_go",
        "go_concurrency_patterns",
        "postgresql_docs",
        "docker_official_docs",
        "kubernetes_basics",
        "grpc_go_tutorial",
    ],
    normalization_rules={
        "golang": "go",
        "gopher": "go",
        "gin-gonic": "gin",
        "gin framework": "gin",
        "go-chi/chi": "chi",
        "grpc-go": "grpc",
        "protobuf": "protobuf",
        "proto3": "protobuf",
        "postgresql": "postgresql",
        "postgres": "postgresql",
        "pg": "postgresql",
        "mysql": "mysql",
        "mariadb": "mysql",
        "redis": "redis",
        "docker": "docker",
        "containerization": "docker",
        "kubernetes": "kubernetes",
        "k8s": "kubernetes",
        "kube": "kubernetes",
        "ci/cd": "ci_cd",
        "github actions": "ci_cd",
        "gitlab ci": "ci_cd",
        "kafka": "kafka",
        "apache kafka": "kafka",
        "rabbitmq": "rabbitmq",
        "amqp": "rabbitmq",
        "message broker": "rabbitmq",
        "concurrency": "concurrency",
        "goroutines": "concurrency",
        "channels": "concurrency",
        "mutex": "concurrency",
        "sync": "concurrency",
        "context": "concurrency",
        "distributed systems": "distributed_systems",
        "микросервисы": "distributed_systems",
        "распределенные системы": "distributed_systems",
        "testing": "testing",
        "unit testing": "testing",
        "integration testing": "testing",
        "mock": "testing",
        "testify": "testing",
        "gomock": "testing",
        "git": "git",
        "version control": "git",
        "linux": "linux",
        "unix": "linux",
        "bash": "linux",
        "shell": "linux",
        "terminal": "linux",
        "monitoring": "observability",
        "prometheus": "observability",
        "grafana": "observability",
        "logging": "observability",
        "tracing": "observability",
        "jaeger": "observability",
        "zipkin": "observability",
        "communication": "communication",
        "teamwork": "communication",
        "code review": "communication",
        "documentation": "communication",
        "problem solving": "problem_solving",
        "debugging": "problem_solving",
        "troubleshooting": "problem_solving",
        "алгоритмы": "problem_solving",
    },
    version="1.0",
)