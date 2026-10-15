"""Resume parsing utilities for candidate baseline."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedResume:
    """Result of resume parsing."""
    raw_text: str
    skills: List[str] = field(default_factory=list)
    experience_years: Optional[int] = None
    projects: List[str] = field(default_factory=list)
    education: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    contact_info: Dict[str, str] = field(default_factory=dict)
    raw_sections: Dict[str, str] = field(default_factory=dict)
    parsing_errors: List[str] = field(default_factory=list)


class ResumeParser:
    """Parse candidate resume from various formats."""

    # Common skill keywords for Go/backend development
    GO_SKILL_PATTERNS = [
        r"\bgo\b", r"golang", r"gopher",
        r"\bgRPC\b", r"grpc", r"protobuf", r"proto",
        r"kubernetes", r"k8s", r"docker", r"containerd",
        r"postgresql", r"postgres", r"mysql", r"redis", r"kafka", r"rabbitmq",
        r"microservice", r"микросервис", r"distributed", r"распредел",
        r"concurrent", r"concurrency", r"goroutine", r"channel", r"mutex",
        r"rest", r"api", r"graphql", r"openapi", r"swagger",
        r"ci/cd", r"github actions", r"gitlab ci", r"jenkins",
        r"prometheus", r"grafana", r"elk", r"logging", r"monitoring",
        r"testing", r"unit test", r"integration test", r"mock",
        r"git", r"linux", r"bash", r"shell",
        r"python", r"java", r"c\+\+", r"rust",
        r"aws", r"gcp", r"azure", r"cloud",
        r"terraform", r"ansible", r"helm",
    ]

    def __init__(self) -> None:
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.GO_SKILL_PATTERNS]

    def parse_file(self, path: Path) -> ParsedResume:
        """Parse resume from file."""
        if not path.exists():
            raise FileNotFoundError(f"Resume file not found: {path}")

        suffix = path.suffix.lower()
        if suffix in (".txt", ".md"):
            text = path.read_text(encoding="utf-8")
        elif suffix == ".pdf":
            text = self._parse_pdf(path)
        elif suffix in (".docx", ".doc"):
            text = self._parse_docx(path)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

        return self.parse_text(text, source_path=path)

    def parse_url(self, url: str, save_dir: Optional[Path] = None) -> ParsedResume:
        """Parse a public resume/profile URL with SSRF protection.

        Only HTTPS URLs pointing at non-private hosts are fetched. Content is
        saved locally (if ``save_dir`` is given) and parsed locally — never
        forwarded to a vacancy site or cloud LLM.

        Raises:
            ValueError: if the URL is rejected by SSRF/scheme validation or the
                fetch fails. The error message never echoes credentials.
        """
        from ..candidate.url_importer import fetch_resume_text, save_imported_content

        result = fetch_resume_text(url)
        if not result.success:
            raise ValueError(f"URL import rejected: {result.error}")

        saved_path: Optional[Path] = None
        if save_dir is not None and result.text:
            saved_path = save_imported_content(
                result.text,
                Path(save_dir) if save_dir else Path("data/imports"),
            )
        return self.parse_text(result.text, source_path=saved_path)

    def parse_text(self, text: str, source_path: Optional[Path] = None) -> ParsedResume:
        """Parse resume from plain text."""
        if not text or not text.strip():
            return ParsedResume(raw_text=text, parsing_errors=["Empty or whitespace-only text"])

        # Clean and normalize text
        text = self._clean_text(text)

        # Extract sections
        sections = self._extract_sections(text)

        # Extract skills from all text
        skills = self._extract_skills(text)

        # Extract experience years
        experience_years = self._extract_experience_years(text)

        # Extract projects
        projects = self._extract_projects(text, sections)

        # Extract education
        education = self._extract_education(text, sections)

        # Extract languages
        languages = self._extract_languages(text)

        # Extract contact info
        contact_info = self._extract_contact_info(text)

        return ParsedResume(
            raw_text=text,
            skills=skills,
            experience_years=experience_years,
            projects=projects,
            education=education,
            languages=languages,
            contact_info=contact_info,
            raw_sections=sections,
        )

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Replace multiple whitespace with single space
        text = re.sub(r"\s+", " ", text)
        # Remove zero-width characters
        text = text.replace("\u200b", "").replace("\ufeff", "")
        return text.strip()

    def _extract_sections(self, text: str) -> Dict[str, str]:
        """Extract common resume sections."""
        sections = {}
        # Common section headers in Russian and English
        section_patterns = {
            "experience": r"(опыт\s+работы|рабочий\s+опыт|experience|employment|work\s+history)",
            "projects": r"(проекты|projects|pet\s+projects|личные\s+проекты)",
            "education": r"(образование|education|учеба|университет)",
            "skills": r"(навыки|skills|технологии|технологический\s+стек|tech\s+stack)",
            "languages": r"(языки|languages|английский|english)",
            "summary": r"(о\s+себе|summary|about|profile|объектив)",
        }

        # Split by common section markers
        for name, pattern in section_patterns.items():
            match = re.search(rf"(?i){pattern}[:.]?\s*(.*?)(?=\n\s*(?:[A-ZА-Я][a-zа-я]+\s*:|\Z))", text)
            if match:
                sections[name] = match.group(1).strip()

        return sections

    def _extract_skills(self, text: str) -> List[str]:
        """Extract technical skills from text."""
        found_skills = set()

        for pattern in self.compiled_patterns:
            matches = pattern.findall(text)
            for match in matches:
                # Normalize skill name
                skill = match.lower().strip()
                if skill:
                    found_skills.add(skill)

        # Also look for explicit skill lists
        skill_list_pattern = r"(?:навыки|skills|технологии|tech\s*stack)[:\s]+([^\n]+)"
        for match in re.finditer(skill_list_pattern, text, re.IGNORECASE):
            skills_text = match.group(1)
            # Split by common delimiters
            for skill in re.split(r"[,;|/]\s*|\s+и\s+|\s+and\s+", skills_text):
                skill = skill.strip().lower()
                if skill and len(skill) > 1:
                    found_skills.add(skill)

        return sorted(found_skills)

    def _extract_experience_years(self, text: str) -> Optional[int]:
        """Extract years of experience from text."""
        patterns = [
            r"(?:опыт|experience)\s*(?:работы|работы\s+)?(\d+)\s*(?:лет|год|года|years?|yrs?)",
            r"(\d+)\s*(?:лет|год|года|years?|yrs?)\s*(?:опыта|experience|работы)",
            r"(?:junior|джуниор)\s*(\d*)\s*(?:лет|год|года|years?)",
            r"(\d+)\+\s*(?:лет|год|года|years?)",
        ]

        years = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    y = int(match.group(1))
                    if 0 <= y <= 50:
                        years.append(y)
                except (ValueError, IndexError):
                    pass

        return max(years) if years else None

    def _extract_projects(self, text: str, sections: Dict[str, str]) -> List[str]:
        """Extract project descriptions."""
        projects = []

        # From projects section
        if "projects" in sections:
            proj_text = sections["projects"]
            # Split by common project separators
            for proj in re.split(r"\n\s*[-•*]\s*|\n\s*\d+\.\s*", proj_text):
                proj = proj.strip()
                if len(proj) > 20:
                    projects.append(proj[:200])

        return projects[:10]  # Limit to 10 projects

    def _extract_education(self, text: str, sections: Dict[str, str]) -> List[str]:
        """Extract education information."""
        education = []

        if "education" in sections:
            edu_text = sections["education"]
            for line in edu_text.split("\n"):
                line = line.strip()
                if len(line) > 5:
                    education.append(line[:200])

        # Also search for degree keywords
        degree_patterns = [
            r"(?:высшее|higher|bachelor|master|бакалавр|магистр|специалист)\s+[^.\n]{5,100}",
            r"(?:университет|university|институт|institute)\s+[^.\n]{5,100}",
        ]
        for pattern in degree_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                education.append(match.group(0).strip()[:200])

        return list(set(education))[:5]

    def _extract_languages(self, text: str) -> List[str]:
        """Extract language proficiencies."""
        languages = []
        lang_patterns = [
            r"(?:английский|english)\s*(?:[—\-:]\s*)?([A-C]\d?|native|fluent|upper-intermediate|intermediate|pre-intermediate|elementary|beginner|b2|c1|c2|a1|a2)",
            r"(?:русский|russian)\s*(?:[—\-:]\s*)?(native|fluent|родной)",
        ]

        for pattern in lang_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                lang = match.group(0).strip()
                if lang not in languages:
                    languages.append(lang)

        return languages

    def _extract_contact_info(self, text: str) -> Dict[str, str]:
        """Extract contact information."""
        contacts = {}

        # Email
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", text)
        if email_match:
            contacts["email"] = email_match.group(0)

        # Phone
        phone_match = re.search(r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", text)
        if phone_match:
            contacts["phone"] = phone_match.group(0)

        # Telegram
        tg_match = re.search(r"(?:@|t\.me/|telegram)[\s@]*(\w+)", text, re.IGNORECASE)
        if tg_match:
            contacts["telegram"] = tg_match.group(1)

        # GitHub
        gh_match = re.search(r"(?:github\.com/|github)[\s/]*(\w+)", text, re.IGNORECASE)
        if gh_match:
            contacts["github"] = gh_match.group(1)

        # LinkedIn
        li_match = re.search(r"linkedin\.com/in/([\w\-]+)", text, re.IGNORECASE)
        if li_match:
            contacts["linkedin"] = li_match.group(1)

        return contacts

    def _parse_pdf(self, path: Path) -> str:
        """Parse PDF file."""
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts)
        except ImportError:
            logger.warning("pdfplumber not installed, cannot parse PDF")
            raise ValueError("PDF parsing requires pdfplumber package")
        except Exception as e:
            logger.error(f"PDF parsing failed: {e}")
            raise

    def _parse_docx(self, path: Path) -> str:
        """Parse DOCX file."""
        try:
            from docx import Document
            doc = Document(path)
            text_parts = [para.text for para in doc.paragraphs if para.text.strip()]
            return "\n".join(text_parts)
        except ImportError:
            logger.warning("python-docx not installed, cannot parse DOCX")
            raise ValueError("DOCX parsing requires python-docx package")
        except Exception as e:
            logger.error(f"DOCX parsing failed: {e}")
            raise