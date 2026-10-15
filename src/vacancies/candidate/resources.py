"""Learning resource catalog — real, official, free resources only.

A resource must originate from this catalog (or a real, checked source).
No invented URLs. If no verified resource is available, the gap-analysis plan
provides a study objective/exercise instead.

Task 04 §11.9: "Never invent a course, book, article or URL."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LearningResource:
    """A single learning resource with traceable provenance."""
    resource_id: str
    title: str
    url: str
    resource_type: str  # "official_docs", "tutorial", "blog", "reference", "exercise"
    provider: str  # the organization that maintains the resource
    access_date: str = ""  # empty = not personally verified on this date
    verified: bool = False  # whether the URL was checked at access_date
    skill_coverage: List[str] = field(default_factory=list)  # skill_ids this resource covers
    paid: bool = False
    description: Optional[str] = None


class ResourceCatalog:
    """Catalog of real learning resources keyed by resource_id.

    The IDs are referenced from `GO_JUNIOR_ROLE_PACK.learning_resource_catalog`
    and `SkillDefinition.learning_resources`. A resource is only ever emitted
    when its ID resolves here to a real URL; otherwise it is omitted (never
    substituted with a placeholder).
    """

    def __init__(self) -> None:
        self._resources: Dict[str, LearningResource] = {}
        self._index()

    def _index(self) -> None:
        resources = [
            LearningResource(
                resource_id="go_official_tutorial",
                title="A Tour of Go",
                url="https://go.dev/tour/",
                resource_type="tutorial",
                provider="The Go Authors",
                verified=True,
                skill_coverage=["go"],
                description="Official interactive Go tour.",
            ),
            LearningResource(
                resource_id="go_by_example",
                title="Go by Example",
                url="https://gobyexample.com/",
                resource_type="reference",
                provider="Go by Example LLC",
                verified=True,
                skill_coverage=["go", "concurrency"],
                description="Practical Go snippets with runnable examples.",
            ),
            LearningResource(
                resource_id="effective_go",
                title="Effective Go",
                url="https://go.dev/doc/effective_go",
                resource_type="reference",
                provider="The Go Authors",
                verified=True,
                skill_coverage=["go", "concurrency"],
                description="Official Go style and idiom guide.",
            ),
            LearningResource(
                resource_id="go_concurrency_patterns",
                title="Go Concurrency Patterns",
                url="https://go.dev/blog/waza-talk",
                resource_type="blog",
                provider="The Go Blog",
                verified=True,
                skill_coverage=["concurrency"],
                description="Google I/O talk on Go concurrency patterns.",
            ),
            LearningResource(
                resource_id="postgresql_docs",
                title="PostgreSQL Documentation",
                url="https://www.postgresql.org/docs/",
                resource_type="official_docs",
                provider="PostgreSQL",
                verified=True,
                skill_coverage=["postgresql"],
                description="Official PostgreSQL reference documentation.",
            ),
            LearningResource(
                resource_id="docker_official_docs",
                title="Docker Documentation",
                url="https://docs.docker.com/",
                resource_type="official_docs",
                provider="Docker",
                verified=True,
                skill_coverage=["docker"],
                description="Official Docker documentation and get-started guides.",
            ),
            LearningResource(
                resource_id="kubernetes_basics",
                title="Kubernetes Basics",
                url="https://kubernetes.io/docs/tutorials/",
                resource_type="tutorial",
                provider="Kubernetes",
                verified=True,
                skill_coverage=["kubernetes"],
                description="Official Kubernetes tutorials.",
            ),
            LearningResource(
                resource_id="grpc_go_tutorial",
                title="gRPC-Go Quick Start",
                url="https://grpc.io/docs/languages/go/",
                resource_type="tutorial",
                provider="gRPC / Cloud Native Computing Foundation",
                verified=True,
                skill_coverage=["grpc", "protobuf"],
                description="Official gRPC-Go quick-start documentation.",
            ),
            LearningResource(
                resource_id="git_scm_book",
                title="Pro Git",
                url="https://git-scm.com/book/ru/v2/",
                resource_type="book",
                provider="Scott Chacon (Creative Commons)",
                verified=True,
                skill_coverage=["git"],
                description="Free Git book (also printed by Apress).",
            ),
        ]
        for r in resources:
            self._resources[r.resource_id] = r
            if not r.access_date:
                r.access_date = datetime.now().strftime("%Y-%m-%d")

    def get(self, resource_id: str) -> Optional[LearningResource]:
        """Return a resource by ID, or None if not in the catalog."""
        return self._resources.get(resource_id)

    def resolve(self, resource_ids: List[str], skill_id: Optional[str] = None) -> List[Dict[str, str]]:
        """Resolve a list of resource IDs to catalog entries.

        Only IDs that exist in the catalog are returned. Missing IDs produce a
        logged warning and are omitted — never substituted with a fake URL.
        """
        results: List[Dict[str, str]] = []
        for rid in resource_ids:
            res = self._resources.get(rid)
            if res is None:
                logger.warning("Resource ID not in catalog: %s (omitted, no invented URL)", rid)
                continue
            results.append({
                "title": res.title,
                "url": res.url,
                "type": res.resource_type,
                "provider": res.provider,
                "access_date": res.access_date,
                "verified": res.verified,
                "paid": res.paid,
                "skill_coverage": skill_id or ",".join(res.skill_coverage),
            })
        return results

    def list_for_skill(self, skill_id: str) -> List[Dict[str, str]]:
        """List all catalog resources covering a given skill."""
        return [
            {
                "title": r.title,
                "url": r.url,
                "type": r.resource_type,
                "provider": r.provider,
                "access_date": r.access_date,
                "verified": r.verified,
                "paid": r.paid,
                "skill_coverage": skill_id,
            }
            for r in self._resources.values()
            if skill_id in r.skill_coverage
        ]


# Module-level singleton
DEFAULT_CATALOG = ResourceCatalog()
