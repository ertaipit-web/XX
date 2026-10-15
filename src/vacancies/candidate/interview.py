"""Adaptive follow-up interview for candidate profile completion."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..role_pack.go_junior import GO_JUNIOR_ROLE_PACK
from ..candidate.profile import CandidateProfile, SkillEvidence, SkillEvidenceType, SkillConfidence

logger = logging.getLogger(__name__)


@dataclass
class InterviewQuestion:
    """A single interview question."""
    question_id: str
    text: str
    skill_ids: List[str] = field(default_factory=list)
    priority: int = 1  # higher = more important
    question_type: str = "open"  # open, multiple_choice, yes_no, practical
    options: List[str] = field(default_factory=list)
    expected_evidence_type: str = "interview_answer"
    rubric: Optional[str] = None
    follow_up: List[str] = field(default_factory=list)


@dataclass
class InterviewSession:
    """State of an interview session."""
    profile_id: str
    role_pack_id: str = "go_junior"
    questions_asked: List[str] = field(default_factory=list)
    answers: Dict[str, str] = field(default_factory=dict)
    current_question_index: int = 0
    max_questions: int = 10
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed: bool = False
    skipped_questions: List[str] = field(default_factory=list)


class InterviewQuestionBank:
    """Bank of interview questions for Go Junior role."""

    def __init__(self, role_pack_id: str = "go_junior") -> None:
        self.role_pack_id = role_pack_id
        self.questions = self._build_questions()
        self.max_questions = 10

    def _build_questions(self) -> List[Any]:
        """Build interview questions for Go Junior role."""
        from ..candidate.profile import SkillEvidenceType

        return [
            # Experience & Background
            {
                "question_id": "exp_total_years",
                "text": "Сколько лет коммерческого опыта разработки у вас есть? (Укажите число лет, например: 1.5)",
                "skill_ids": [],
                "priority": 10,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },
            {
                "question_id": "exp_go_years",
                "text": "Сколько лет вы пишете на Go (включая пет-проекты и обучение)?",
                "skill_ids": ["go"],
                "priority": 10,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },
            {
                "question_id": "exp_commercial_vs_learning",
                "text": "Какой опыт был коммерческим (работа за деньги), а какой — обучающим/пет-проектами? Опишите кратко.",
                "skill_ids": ["go"],
                "priority": 9,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },

            # Projects
            {
                "question_id": "proj_recent",
                "text": "Опишите 1-2 последних проекта, где вы писали на Go. Что было вашей зоной ответственности?",
                "skill_ids": ["go"],
                "priority": 9,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },
            {
                "question_id": "proj_complexity",
                "text": "Какой самый сложный технический вызов вы решали на Go? Как подходили к решению?",
                "skill_ids": ["go", "concurrency", "problem_solving"],
                "priority": 8,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },

            # Concurrency - critical for Go
            {
                "question_id": "conc_goroutines_channels",
                "text": "Как вы решаете задачи, требующие конкурентного выполнения? Приведите пример использования goroutines и channels из практики.",
                "skill_ids": ["concurrency"],
                "priority": 10,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
                "rubric": "Понимание goroutines, channels, select, context cancellation, worker pools",
            },
            {
                "question_id": "conc_sync_primitives",
                "text": "Какие примитивы синхронизации вы использовали в Go (mutex, RWMutex, WaitGroup, Once, Cond)? В каких случаях?",
                "skill_ids": ["concurrency"],
                "priority": 8,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },

            # Databases
            {
                "question_id": "db_postgresql",
                "text": "Какой опыт работы с PostgreSQL? Какие индексы использовали, как оптимизировали медленные запросы?",
                "skill_ids": ["postgresql"],
                "priority": 9,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
                "rubric": "Понимание B-tree, GIN, GiST, EXPLAIN ANALYZE, vacuum, connection pooling",
            },
            {
                "question_id": "db_redis",
                "text": "Использовали ли Redis? Для чего (кэш, сессии, pub/sub, rate limiting)? Какие структуры данных?",
                "skill_ids": ["redis"],
                "priority": 7,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },

            # APIs & Protocols
            {
                "question_id": "api_rest",
                "text": "Проектировали ли REST API? Какие принципы соблюдаете (RESTful, версионирование, ошибки, пагинация)?",
                "skill_ids": ["api"],
                "priority": 7,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },
            {
                "question_id": "api_grpc",
                "text": "Работали с gRPC? Опишите кейс: proto определение, кодогенерация, interceptors, error handling.",
                "skill_ids": ["grpc", "protobuf"],
                "priority": 8,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },

            # Infrastructure
            {
                "question_id": "infra_docker",
                "text": "Писали ли Dockerfile для Go-приложений? Что такое multi-stage build, как уменьшить размер образа?",
                "skill_ids": ["docker"],
                "priority": 7,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },
            {
                "question_id": "infra_k8s",
                "text": "Работали с Kubernetes? Знаете ли Deployment, Service, ConfigMap, Secret, Ingress, HPA?",
                "skill_ids": ["kubernetes"],
                "priority": 6,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },
            {
                "question_id": "infra_ci_cd",
                "text": "Настраивали CI/CD для Go-проектов? Какие инструменты (GitHub Actions, GitLab CI)? Что в пайплайне?",
                "skill_ids": ["ci_cd"],
                "priority": 6,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },

            # Messaging
            {
                "question_id": "msg_kafka",
                "text": "Работали с Kafka? Producer/Consumer, партиции, consumer groups, ребалансировка, exactly-once?",
                "skill_ids": ["kafka"],
                "priority": 6,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },

            # Testing
            {
                "question_id": "test_approach",
                "text": "Как тестируете Go-код? Unit тесты, интеграционные, моки (testify/mock, gomock), табличные тесты?",
                "skill_ids": ["testing"],
                "priority": 7,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },

            # Soft skills & Communication
            {
                "question_id": "soft_code_review",
                "text": "Как проходите code review? На что обращаете внимание? Как реагируете на замечания к своему коду?",
                "skill_ids": ["communication"],
                "priority": 6,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },
            {
                "question_id": "soft_problem_solving",
                "text": "Расскажите о случае, когда не могли решить задачу долго. Как действовали? К кому обращались?",
                "skill_ids": ["problem_solving", "communication"],
                "priority": 7,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },

            # Preferences & Exclusions
            {
                "question_id": "pref_tasks",
                "text": "Какие задачи вам интересны (backend, infra, highload, data, product)? Что хотите избегать?",
                "skill_ids": [],
                "priority": 5,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },
            {
                "question_id": "pref_exclusions",
                "text": "Есть ли технологии/домены, с которыми не хотите работать? (например, фронтенд, легаси, админки)",
                "skill_ids": [],
                "priority": 5,
                "question_type": "open",
                "expected_evidence_type": "interview_answer",
            },
        ]

    def get_questions(self, max_count: int = 10) -> List[Dict[str, Any]]:
        """Get prioritized questions up to max_count."""
        sorted_questions = sorted(self.questions, key=lambda q: -q["priority"])
        return sorted_questions[:self.max_questions]

    def set_max_questions(self, max_q: int) -> None:
        self.max_questions = max_q


class AdaptiveInterviewer:
    """Conducts adaptive follow-up interview to fill profile gaps."""

    def __init__(self, profile: Any, role_pack_id: str = "go_junior") -> None:
        self.profile = profile
        self.role_pack_id = role_pack_id
        self.question_bank = InterviewQuestionBank(role_pack_id)
        self.session = InterviewSession(profile_id="default")

    def get_next_question(self) -> Optional[Dict[str, Any]]:
        """Get next unanswered question based on profile gaps."""
        # Determine which skills are missing/unknown
        missing_skills = self._identify_missing_skills()

        # Filter questions by missing skills
        all_questions = self.question_bank.questions
        relevant = []

        for q in self.question_bank.questions:
            qid = q["question_id"]
            if qid in self.session.questions_asked:
                continue
            if qid in self.session.skipped_questions:
                continue

            # Check if question addresses a missing skill
            relevant_skills = [s for s in q["skill_ids"] if s in self.profile.skills or s in self.session.answers]
            # Always include general questions (no skill_ids)
            if not q["skill_ids"] or any(s in self._get_missing_skill_ids() for s in q["skill_ids"]):
                relevant.append(q)

        # Sort by priority
        relevant.sort(key=lambda q: -q["priority"])

        if relevant:
            return relevant[0]
        return None

    def _get_missing_skill_ids(self) -> set:
        """Get set of skill IDs that are missing or unknown."""
        from ..role_pack.go_junior import GO_JUNIOR_ROLE_PACK
        missing = set()

        for skill in GO_JUNIOR_ROLE_PACK.skills:
            if skill.importance in ("core", "frequent"):
                if not self.profile.has_skill(skill.skill_id):
                    missing.add(skill.skill_id)
        return missing

    def _identify_missing_skills(self) -> List[str]:
        """Identify skills that are missing or have low confidence."""
        from ..role_pack.go_junior import GO_JUNIOR_ROLE_PACK
        missing = []

        for skill in GO_JUNIOR_ROLE_PACK.skills:
            if skill.importance in ("core", "frequent"):
                evidence = self.profile.get_skill(skill.skill_id)
                if not evidence or evidence.confidence in ("low", "unknown"):
                    missing.append(skill.skill_id)
        return missing

    def ask_next(self) -> Optional[str]:
        """Get next question text."""
        q = self.get_next_question()
        if q:
            self.session.current_question_index += 1
            return q["text"]
        return None

    def record_answer(self, question_id: str, answer: str) -> None:
        """Record answer and update profile with evidence."""
        self.session.questions_asked.append(question_id)
        self.session.answers[question_id] = answer

        # Extract skill evidence from answer
        self._process_answer(question_id, answer)

    def skip_question(self, question_id: str) -> None:
        """Skip a question."""
        self.session.skipped_questions.append(question_id)
        if question_id in self.session.questions_asked:
            self.session.questions_asked.remove(question_id)

    def _process_answer(self, question_id: str, answer: str) -> None:
        """Process answer and update skill evidence."""
        from ..candidate.profile import SkillEvidence, SkillEvidenceType, SkillConfidence

        # Find question
        question = None
        for q in self.question_bank.questions:
            if q["question_id"] == question_id:
                question = q
                break

        if not question:
            return

        # Create skill evidence from answer for each relevant skill
        for skill_id in question.get("skill_ids", []):
            # Determine confidence based on answer quality
            confidence = self._assess_confidence(answer)

            evidence = SkillEvidence(
                skill_id=skill_id,
                skill_name=skill_id,  # Will be resolved later
                evidence_type=SkillEvidenceType.INTERVIEW_ANSWER,
                evidence_note=f"Interview answer to '{question_id}': {answer[:200]}",
                confidence=confidence,
                source="interview",
                assessed_at=datetime.now().isoformat(),
                next_action=self._suggest_next_action(question, answer),
            )
            self.profile.add_skill(evidence)

    def _assess_confidence(self, answer: str) -> str:
        """Assess confidence based on answer detail."""
        if not answer or len(answer.strip()) < 10:
            return "low"
        if len(answer.strip()) < 50:
            return "low"
        if len(answer.strip()) < 150:
            return "medium"
        return "high"

    def _suggest_next_action(self, question: Dict, answer: str) -> str:
        """Suggest next action based on answer."""
        if len(answer.strip()) < 50:
            return "Запросить более развернутый ответ или практическую демонстрацию"
        if "не знаю" in answer.lower() or "не знаю" in answer.lower():
            return "Предложить практическое задание или материал для изучения"
        return "Эвиденция записана, перейти к следующему вопросу"

    def is_complete(self) -> bool:
        """Check if interview is complete."""
        return (
            len(self.session.questions_asked) >= self.question_bank.max_questions
            or self.get_next_question() is None
        )

    def get_progress(self) -> Dict[str, Any]:
        """Get interview progress."""
        return {
            "asked": len(self.session.questions_asked),
            "skipped": len(self.session.skipped_questions),
            "max_questions": self.question_bank.max_questions,
            "completed": self.is_complete(),
        }