"""Eval runner over the golden incident set.

For each incident in ``data/golden_incidents.yaml`` the runner submits
the request to a fresh Copilot and checks three things:

- ``grounded`` — every cited document was actually retrieved, and at
  least one expected document is cited.
- ``remediation_match`` — the proposed remediation is the expected one.
- ``gating_correct`` — sensitive incidents pause for human approval
  and nothing executes before approval; non-sensitive incidents run
  through without a pause.

Approved incidents are then resumed with an approval (simulating the
human) to confirm the action executes; rejected ones are resumed with
a rejection to confirm nothing executes. Results are written as JSON
and Markdown reports.
"""

from __future__ import annotations

import asyncio
import json
import os

import yaml

from .agent import Copilot
from .audit import AuditLog

DEFAULT_GOLDEN_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "golden_incidents.yaml",
)


def load_golden(path: str = DEFAULT_GOLDEN_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


async def _eval_one(copilot: Copilot, incident: dict) -> dict:
    result = await copilot.submit(incident["request"], run_id=incident["id"])
    proposal = result.proposal or {}
    citations = proposal.get("citations", [])
    retrieved_ids = [d["doc"]["id"] for d in result.state.get("docs", [])]
    expected_docs = incident["expected_docs"]

    grounded = bool(citations) and all(
        c in retrieved_ids for c in citations
    ) and any(c in expected_docs for c in citations)
    remediation_match = (
        proposal.get("remediation_id") == incident["expected_remediation"]
    )
    if incident["sensitive"]:
        gating_correct = result.status == "awaiting_approval" and not (
            result.state.get("executed")
        )
    else:
        gating_correct = result.status == "completed"

    # Resume: approve the sensitive ones, confirm execution happens;
    # then re-run a rejected copy to confirm nothing executes.
    executed_after_approval = None
    executed_after_rejection = None
    if incident["sensitive"]:
        approved = await copilot.decide(
            incident["id"], "approved", by="eval"
        )
        executed_after_approval = bool(approved.state.get("executed"))
        # Fresh run for the rejection check (same run id would collide
        # with the completed thread, so use a suffixed id).
        rejected = await copilot.submit(
            incident["request"], run_id=incident["id"] + "-reject"
        )
        if rejected.status == "awaiting_approval":
            rejected = await copilot.decide(
                incident["id"] + "-reject", "rejected", by="eval"
            )
        executed_after_rejection = bool(rejected.state.get("executed"))

    passed = grounded and remediation_match and gating_correct
    if incident["sensitive"]:
        passed = passed and executed_after_approval is True
        passed = passed and executed_after_rejection is False

    return {
        "id": incident["id"],
        "request": incident["request"],
        "expected_remediation": incident["expected_remediation"],
        "proposed_remediation": proposal.get("remediation_id"),
        "expected_action": incident["expected_action"],
        "proposed_action": proposal.get("action"),
        "sensitive": incident["sensitive"],
        "grounded": grounded,
        "remediation_match": remediation_match,
        "gating_correct": gating_correct,
        "executed_after_approval": executed_after_approval,
        "executed_after_rejection": executed_after_rejection,
        "citations": citations,
        "passed": passed,
    }


def run_eval(
    golden_path: str = DEFAULT_GOLDEN_PATH,
    audit_path: str | None = None,
) -> dict:
    """Run the golden set synchronously. Returns the summary dict."""
    incidents = load_golden(golden_path)
    audit = AuditLog(audit_path) if audit_path else AuditLog()
    copilot = Copilot(audit=audit)
    results = [asyncio.run(_eval_one(copilot, inc)) for inc in incidents]
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    summary = {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "grounded": sum(1 for r in results if r["grounded"]),
        "remediation_match": sum(
            1 for r in results if r["remediation_match"]
        ),
        "gating_correct": sum(
            1 for r in results if r["gating_correct"]
        ),
        "results": results,
    }
    return summary


def render_markdown(summary: dict) -> str:
    lines = [
        "# ai-ops-copilot eval results",
        "",
        f"Golden incidents: {summary['total']}",
        f"Passed: {summary['passed']} ({summary['pass_rate']:.0%})",
        f"Grounded citations: {summary['grounded']}/{summary['total']}",
        f"Remediation match: {summary['remediation_match']}/{summary['total']}",
        f"Approval gating correct: {summary['gating_correct']}/{summary['total']}",
        "",
        "| Incident | Proposed | Expected | Grounded | Match | Gating | Passed |",
        "|----------|----------|----------|----------|-------|--------|--------|",
    ]
    for r in summary["results"]:
        tick = lambda b: "yes" if b else "no"  # noqa: E731
        lines.append(
            f"| {r['id']} | {r['proposed_remediation']} | "
            f"{r['expected_remediation']} | {tick(r['grounded'])} | "
            f"{tick(r['remediation_match'])} | {tick(r['gating_correct'])} | "
            f"{tick(r['passed'])} |"
        )
    lines.append("")
    lines.append(
        "Sensitive incidents are resumed once with an approval (action "
        "must execute) and once with a rejection (action must not "
        "execute). Both checks are included in the pass/fail above."
    )
    return "\n".join(lines) + "\n"
