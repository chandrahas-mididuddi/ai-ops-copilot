import asyncio

import pytest

from ai_ops_copilot.actions import ApprovalRequiredError, execute_action


def test_sensitive_action_without_approval_raises():
    with pytest.raises(ApprovalRequiredError):
        execute_action(
            action="scale_replicas", service="checkout-api", approval=None
        )
    with pytest.raises(ApprovalRequiredError):
        execute_action(
            action="rollback_deploy",
            service="payments-gateway",
            approval="rejected",
        )


def test_sensitive_action_with_approval_executes():
    result = execute_action(
        action="scale_replicas", service="checkout-api", approval="approved"
    )
    assert result["status"] == "completed"
    assert "checkout-api" in result["detail"]


def test_non_sensitive_action_needs_no_approval():
    result = execute_action(
        action="notify_oncall", service="platform", approval=None
    )
    assert result["status"] == "completed"


def test_noop_action():
    result = execute_action(action="none", service="platform", approval=None)
    assert result["status"] == "no-op"


def test_all_sensitive_actions_are_gated():
    from ai_ops_copilot.playbook import SENSITIVE_ACTIONS

    assert SENSITIVE_ACTIONS == {
        "scale_replicas",
        "rollback_deploy",
        "restart_service",
        "purge_cache",
        "rotate_certificate",
    }
    for action in SENSITIVE_ACTIONS:
        with pytest.raises(ApprovalRequiredError):
            execute_action(action=action, service="checkout-api", approval="auto")
