"""Reasoning backend: pluggable proposal logic.

The default backend is a deterministic, rule-based mock: it scores each
playbook entry by keyword signals in the request plus overlap with the
retrieved documents, and picks the best match. It runs fully offline and
is reproducible — the eval depends on that.

Swap in a real LLM by implementing ``ReasoningBackend``: one method,
``propose(request, docs, monitoring)`` returning a ``ProposalDraft``.
The agent never depends on how the draft was produced, only on its
shape — so a real model can replace the mock without touching the
graph, the approval gate, or the audit log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .playbook import PLAYBOOK, Remediation, get_remediation
from .retrieval import RetrievalResult

QUESTION_WORDS = (
    "how do i",
    "how do you",
    "how to",
    "what is",
    "what are",
    "where is",
    "where do",
    "explain",
)


@dataclass
class ProposalDraft:
    remediation: Remediation
    rationale: str
    citations: list[str]
    evidence_metrics: dict
    evidence_logs: list[dict]
    evidence_alerts: list[dict]


class ReasoningBackend(Protocol):
    def propose(
        self,
        *,
        request: str,
        docs: list[RetrievalResult],
        monitoring: dict,
    ) -> ProposalDraft: ...


class MockReasoningBackend:
    """Deterministic keyword + retrieval-overlap matching.

    Scoring per playbook entry: +2 for each signal word in the request,
    +1 for each retrieved document that supports the entry. An entry
    only wins with a score of at least 4 — a single loose keyword (e.g.
    "slow" with no corroborating signal or document) is not enough to
    propose a system change. Questions (``how do I...`` etc.) always
    resolve to ``answer_only``; if nothing scores, the entry is
    ``escalate_oncall``.
    """

    def propose(
        self,
        *,
        request: str,
        docs: list[RetrievalResult],
        monitoring: dict,
    ) -> ProposalDraft:
        lowered = request.lower()
        retrieved_ids = [r.doc.id for r in docs]

        if any(word in lowered for word in QUESTION_WORDS):
            entry = get_remediation("answer_only")
            return self._draft(
                entry, "Request is a question; answer from documentation.",
                retrieved_ids, monitoring,
            )

        best: Remediation | None = None
        best_score = 0
        for entry in PLAYBOOK:
            if entry.id in ("answer_only", "escalate_oncall"):
                continue
            score = sum(2 for signal in entry.signals if signal in lowered)
            score += sum(1 for doc_id in entry.doc_ids if doc_id in retrieved_ids)
            if score > best_score:
                best, best_score = entry, score

        if best is None or best_score < 4:
            entry = get_remediation("escalate_oncall")
            return self._draft(
                entry,
                "No playbook entry matches the request; escalate to a human.",
                retrieved_ids,
                monitoring,
            )

        matched = [s for s in best.signals if s in lowered]
        rationale = (
            f"Matched {best.name} on signals {matched} and supporting "
            f"documentation {[d for d in best.doc_ids if d in retrieved_ids]}."
        )
        return self._draft(best, rationale, retrieved_ids, monitoring)

    def _draft(
        self,
        entry: Remediation,
        rationale: str,
        retrieved_ids: list[str],
        monitoring: dict,
    ) -> ProposalDraft:
        citations = [d for d in entry.doc_ids if d in retrieved_ids]
        if not citations and retrieved_ids:
            citations = retrieved_ids[:2]
        service = entry.service
        svc = monitoring.get(service, {})
        return ProposalDraft(
            remediation=entry,
            rationale=rationale,
            citations=citations,
            evidence_metrics=svc.get("metrics", {}),
            evidence_logs=svc.get("logs", []),
            evidence_alerts=svc.get("alerts", []),
        )
