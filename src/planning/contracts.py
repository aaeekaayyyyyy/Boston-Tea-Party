from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol


# ---------------------------
# Retrieval-side contracts
# ---------------------------

@dataclass
class RetrievalChunkMetadata:
    source_type: str
    citation: str
    section: Optional[str] = None
    publication_year: Optional[int] = None
    case_name: Optional[str] = None
    page_index: Optional[int] = None
    subsection: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalChunk:
    text: str
    metadata: RetrievalChunkMetadata
    score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = self.metadata.to_dict()
        return payload


@dataclass
class RetrievalResponse:
    chunks: List[RetrievalChunk] = field(default_factory=list)
    strategy: str = "tree"
    sources_queried: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "strategy": self.strategy,
            "sources_queried": list(self.sources_queried),
        }


class RetrievalClientProtocol(Protocol):
    """
    Matches the retrieval contract in docs/retrieval_interface_spec.md.
    """

    def retrieve(
        self,
        query: str,
        source_hint: Optional[str] = None,
        top_k: int = 5,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...


# ---------------------------
# Constraint-side contracts
# ---------------------------

@dataclass
class UnresolvedConstraint:
    constraint_id: str
    field: str
    reason: str
    priority: int
    blocking: bool = True
    question_hint: Optional[str] = None
    source_hint: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConstraintResult:
    status: str = "needs_more_info"
    active_rules: List[str] = field(default_factory=list)
    unresolved_constraints: List[UnresolvedConstraint] = field(default_factory=list)
    explanation_goals: List[str] = field(default_factory=list)
    valid_paths: List[str] = field(default_factory=list)
    invalid_paths: List[str] = field(default_factory=list)
    documentation_requirements: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "active_rules": list(self.active_rules),
            "unresolved_constraints": [
                item.to_dict() for item in self.unresolved_constraints
            ],
            "explanation_goals": list(self.explanation_goals),
            "valid_paths": list(self.valid_paths),
            "invalid_paths": list(self.invalid_paths),
            "documentation_requirements": list(self.documentation_requirements),
        }


class ConstraintEngineProtocol(Protocol):
    """
    Anthony's planner only relies on one method. Jonathan's real engine can
    swap in later if it returns the same shape.
    """

    def evaluate(self, facts: Dict[str, Any]) -> ConstraintResult:
        ...


# ---------------------------
# Planning output contract
# ---------------------------

@dataclass
class PlanningAction:
    action: str
    message: str
    target_field: Optional[str] = None
    reason: Optional[str] = None
    question: Optional[str] = None
    retrieval_calls: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_results: List[Dict[str, Any]] = field(default_factory=list)
    normalized_facts: Dict[str, Any] = field(default_factory=dict)
    constraint_result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "message": self.message,
            "target_field": self.target_field,
            "reason": self.reason,
            "question": self.question,
            "retrieval_calls": list(self.retrieval_calls),
            "retrieval_results": list(self.retrieval_results),
            "normalized_facts": dict(self.normalized_facts),
            "constraint_result": dict(self.constraint_result),
        }
