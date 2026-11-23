"""Human approval store.

Tracks each run's proposal and its approval decision: ``pending``,
``approved``, or ``rejected``. The agent pauses at the approval gate
until a human records a decision; the API and CLI write through here.
A rejected proposal can never execute — ``actions.execute_action``
enforces that independently, so the store is a record, not the only
line of defence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Approval:
    run_id: str
    remediation_id: str
    action: str
    sensitive: bool
    status: str = "pending"  # pending | approved | rejected
    decided_by: str | None = None
    decided_at: str | None = None
    reason: str | None = None


class ApprovalStore:
    """In-memory approval records, keyed by run id."""

    def __init__(self):
        self._records: dict[str, Approval] = {}

    def record_proposal(
        self, *, run_id: str, remediation_id: str, action: str, sensitive: bool
    ) -> Approval:
        record = Approval(
            run_id=run_id,
            remediation_id=remediation_id,
            action=action,
            sensitive=sensitive,
        )
        self._records[run_id] = record
        return record

    def decide(
        self, run_id: str, decision: str, *, by: str, reason: str | None = None
    ) -> Approval:
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        record = self._records[run_id]
        record.status = decision
        record.decided_by = by
        record.decided_at = datetime.now(timezone.utc).isoformat()
        record.reason = reason
        return record

    def get(self, run_id: str) -> Approval | None:
        return self._records.get(run_id)

    def all(self) -> list[Approval]:
        return list(self._records.values())
