import asyncio

import pytest

from ai_ops_copilot.agent import Copilot


def _run(coro):
    return asyncio.run(coro)


def test_question_flow_completes_without_approval(copilot):
    result = _run(copilot.submit("How do I roll back a bad deploy?"))
    assert result.status == "completed"
    assert result.proposal["remediation_id"] == "answer_only"
    assert result.proposal["sensitive"] is False
    assert "doc-deploy-rollback" in result.proposal["citations"]
    assert "doc-deploy-rollback" in result.answer


def test_sensitive_incident_pauses_for_approval(copilot):
    result = _run(
        copilot.submit(
            "Checkout API p95 latency is 1.4 seconds and rising, "
            "customers are timing out at checkout."
        )
    )
    assert result.status == "awaiting_approval"
    assert result.proposal["remediation_id"] == "scale_checkout"
    assert result.proposal["sensitive"] is True
    assert result.state["executed"] == []
    assert "doc-checkout-latency" in result.proposal["citations"]


def test_approve_executes_the_action(copilot):
    result = _run(
        copilot.submit(
            "Payments gateway is returning 5xx errors at 3% since the "
            "latest deploy."
        )
    )
    assert result.status == "awaiting_approval"
    assert result.proposal["remediation_id"] == "rollback_payments"
    final = _run(copilot.decide(result.run_id, "approved", by="tester"))
    assert final.status == "completed"
    assert len(final.state["executed"]) == 1
    assert final.state["executed"][0]["action"] == "rollback_deploy"
    assert "Roll back" in final.answer


def test_reject_executes_nothing(copilot):
    result = _run(
        copilot.submit(
            "Inventory sync consumer lag is 45,000 and growing, stock "
            "levels are stale."
        )
    )
    assert result.status == "awaiting_approval"
    final = _run(copilot.decide(result.run_id, "rejected", by="tester"))
    assert final.status == "completed"
    assert final.state["executed"] == []
    assert "rejected" in final.answer.lower()
    # The audit log records the skip.
    events = [e["event"] for e in copilot.audit.entries()]
    assert "action_skipped" in events


def test_unmatched_request_escalates_without_approval(copilot):
    result = _run(
        copilot.submit("Users report the site feels slow but no service "
                       "is alerting.")
    )
    assert result.status == "completed"
    assert result.proposal["remediation_id"] == "escalate_oncall"
    assert result.proposal["sensitive"] is False
    assert result.state["executed"][0]["action"] == "notify_oncall"


def test_decide_on_unknown_run_raises(copilot):
    with pytest.raises(ValueError):
        _run(copilot.decide("no-such-run", "approved"))


def test_decide_twice_raises(copilot):
    result = _run(
        copilot.submit(
            "The TLS certificate for the pricing service expires in 3 days."
        )
    )
    assert result.proposal["remediation_id"] == "rotate_pricing_cert"
    _run(copilot.decide(result.run_id, "approved", by="tester"))
    with pytest.raises(ValueError):
        _run(copilot.decide(result.run_id, "approved", by="tester"))


def test_audit_records_full_run(copilot):
    _run(copilot.submit("How do I roll back a bad deploy?"))
    events = [e["event"] for e in copilot.audit.entries()]
    for expected in (
        "request_received",
        "docs_retrieved",
        "monitoring_fetched",
        "proposal_made",
        "run_completed",
    ):
        assert expected in events
    ok, bad = copilot.audit.verify()
    assert ok is True and bad is None


def test_status_reports_pending_approval(copilot):
    result = _run(
        copilot.submit(
            "Notification queue backlog is 80,000 messages and not draining."
        )
    )
    assert result.status == "awaiting_approval"
    status = _run(copilot.status(result.run_id))
    assert status is not None
    assert status["awaiting_approval"] is True
    assert status["proposal"]["remediation_id"] == (
        "scale_notification_consumers"
    )
