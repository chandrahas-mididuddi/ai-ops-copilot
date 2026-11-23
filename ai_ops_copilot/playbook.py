"""Remediation playbook.

Each entry is a remediation the copilot can propose: what it does, which
action it maps to, whether that action is sensitive (needs human
approval), which fictional runbook documents support it, and the keyword
signals the mock reasoning backend matches against.

The playbook is deliberately small and explicit. A real system would
derive remediations from a model; here the mapping is transparent so
the eval can check it exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Actions that change a system. They MUST NOT run without human approval.
SENSITIVE_ACTIONS = {
    "scale_replicas",
    "rollback_deploy",
    "restart_service",
    "purge_cache",
    "rotate_certificate",
}


@dataclass(frozen=True)
class Remediation:
    id: str
    name: str
    action: str
    service: str
    sensitive: bool
    signals: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)
    description: str = ""


PLAYBOOK: list[Remediation] = [
    Remediation(
        id="scale_checkout",
        name="Scale checkout-api replicas",
        action="scale_replicas",
        service="checkout-api",
        sensitive=True,
        signals=["latency", "p95", "slow", "checkout", "timeout", "timing out"],
        doc_ids=["doc-checkout-latency", "doc-scaling-guide"],
        description=(
            "Scale checkout-api replicas from 3 to 6 to relieve CPU and "
            "connection-pool saturation, then verify p95 latency recovers "
            "below 400ms."
        ),
    ),
    Remediation(
        id="rollback_payments",
        name="Roll back payments-gateway deploy",
        action="rollback_deploy",
        service="payments-gateway",
        sensitive=True,
        signals=["5xx", "error rate", "payments", "deploy", "failed"],
        doc_ids=["doc-payments-errors", "doc-deploy-rollback"],
        description=(
            "Roll back payments-gateway to the previous known-good version "
            "and verify the 5xx error rate falls below 0.1%."
        ),
    ),
    Remediation(
        id="restart_inventory_worker",
        name="Restart inventory-sync worker",
        action="restart_service",
        service="inventory-sync",
        sensitive=True,
        signals=["lag", "stale", "inventory", "sync", "stock"],
        doc_ids=["doc-inventory-lag"],
        description=(
            "Restart the stuck inventory-sync worker and verify consumer "
            "lag drains below 1,000 within 15 minutes."
        ),
    ),
    Remediation(
        id="scale_notification_consumers",
        name="Scale notification-service consumers",
        action="scale_replicas",
        service="notification-service",
        sensitive=True,
        signals=["queue", "backlog", "notification", "draining", "dlq"],
        doc_ids=["doc-notification-queue", "doc-scaling-guide"],
        description=(
            "Scale notification-service consumers from 2 to 6 and verify "
            "queue depth drains below 5,000 within 15 minutes."
        ),
    ),
    Remediation(
        id="rotate_pricing_cert",
        name="Rotate pricing-engine TLS certificate",
        action="rotate_certificate",
        service="pricing-engine",
        sensitive=True,
        signals=["certificate", "cert", "tls", "expir", "ssl"],
        doc_ids=["doc-cert-rotation"],
        description=(
            "Issue a replacement certificate, rotate it on the edge "
            "proxies, and verify the new certificate is served."
        ),
    ),
    Remediation(
        id="purge_pricing_cache",
        name="Purge stale pricing cache",
        action="purge_cache",
        service="pricing-engine",
        sensitive=True,
        signals=["cache", "stale", "pricing", "prices", "yesterday"],
        doc_ids=["doc-pricing-stale", "doc-cache-purge"],
        description=(
            "Purge the stale pricing cache and re-warm it from the source "
            "of truth, then verify fresh prices are served."
        ),
    ),
    Remediation(
        id="escalate_oncall",
        name="Escalate to on-call engineer",
        action="notify_oncall",
        service="platform",
        sensitive=False,
        signals=[],
        doc_ids=["doc-escalation", "doc-monitoring"],
        description=(
            "No known runbook matches this request. Notify the on-call "
            "engineer and take no automated action."
        ),
    ),
    Remediation(
        id="answer_only",
        name="Answer from documentation",
        action="none",
        service="platform",
        sensitive=False,
        signals=[],
        doc_ids=[],
        description=(
            "This is a question, not an incident. Answer from the "
            "retrieved documentation with citations."
        ),
    ),
]

_BY_ID = {entry.id: entry for entry in PLAYBOOK}


def get_remediation(remediation_id: str) -> Remediation:
    return _BY_ID[remediation_id]


def is_sensitive_action(action: str) -> bool:
    return action in SENSITIVE_ACTIONS
