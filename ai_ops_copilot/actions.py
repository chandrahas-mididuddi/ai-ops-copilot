"""Action execution — with the approval guard in exactly one place.

Sensitive actions (see ``playbook.SENSITIVE_ACTIONS``) raise
``ApprovalRequiredError`` unless the caller passes
``approval="approved"``. Nothing in the agent, API, or CLI can bypass
this: execution always goes through ``execute_action``.

Execution here is simulated: it returns a deterministic result record
describing what *would* happen. This project never touches a real
system — the point is the gating, the audit trail, and the eval, not
the side effect.
"""

from __future__ import annotations

from .playbook import is_sensitive_action


class ApprovalRequiredError(PermissionError):
    """Raised when a sensitive action is attempted without approval."""


def execute_action(
    *, action: str, service: str, approval: str | None
) -> dict:
    """Simulate executing an action, enforcing the approval gate."""
    if action == "none":
        return {
            "action": action,
            "service": service,
            "status": "no-op",
            "detail": "No system action required.",
        }
    if is_sensitive_action(action) and approval != "approved":
        raise ApprovalRequiredError(
            f"action '{action}' on '{service}' is sensitive and requires "
            "human approval; approval status is "
            f"{approval!r}."
        )
    detail = {
        "scale_replicas": f"Scaled {service} replicas (simulated).",
        "rollback_deploy": f"Rolled back {service} to the previous version (simulated).",
        "restart_service": f"Restarted {service} (simulated).",
        "purge_cache": f"Purged the {service} cache and re-warmed it (simulated).",
        "rotate_certificate": f"Rotated the {service} TLS certificate (simulated).",
        "notify_oncall": f"Paged the on-call engineer for {service} (simulated).",
    }.get(action, f"Executed {action} on {service} (simulated).")
    return {
        "action": action,
        "service": service,
        "status": "completed",
        "detail": detail,
    }
