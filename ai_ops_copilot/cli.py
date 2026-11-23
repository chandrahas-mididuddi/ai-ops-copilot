"""Command-line interface for ai-ops-copilot.

Commands:
- ``submit --text "..."`` — run a request; if the proposal is
  sensitive, ask for approval interactively (or use --auto-approve /
  --auto-reject for scripting).
- ``eval`` — run the golden incident set and write reports.
- ``demo`` — run three sample incidents end to end (one approved, one
  rejected, one question) and print the audit trail.
- ``serve`` — start the FastAPI service.
- ``mcp-stdio`` — run the MCP monitoring server over stdio (used by
  the stdio client mode and by external MCP clients).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from .agent import Copilot
from .audit import AuditLog
from .evaluator import render_markdown, run_eval

SAMPLE_INCIDENTS = [
    (
        "Checkout API p95 latency is 1.4 seconds and rising, customers "
        "are timing out at checkout.",
        "approved",
    ),
    (
        "Payments gateway is returning 5xx errors at 3% since the latest "
        "deploy.",
        "rejected",
    ),
    ("How do I roll back a bad deploy?", None),
]


def _print_proposal(result) -> None:
    proposal = result.proposal or {}
    print(f"Run: {result.run_id}  Status: {result.status}")
    print(f"Proposal: {proposal.get('name')}")
    print(f"  Action: {proposal.get('action')} on {proposal.get('service')}")
    print(f"  Sensitive: {proposal.get('sensitive')}")
    print(f"  Rationale: {proposal.get('rationale')}")
    print(f"  Citations: {', '.join(proposal.get('citations', []))}")
    evidence = proposal.get("evidence", {})
    if evidence.get("metrics"):
        print(f"  Metrics: {json.dumps(evidence['metrics'])}")
    if evidence.get("alerts"):
        for alert in evidence["alerts"]:
            print(f"  Alert: [{alert.get('severity')}] {alert.get('msg')}")


def _cmd_submit(args) -> int:
    copilot = Copilot(mcp_mode=args.mcp_mode)
    result = asyncio.run(copilot.submit(args.text))
    _print_proposal(result)
    if result.status != "awaiting_approval":
        print(f"\nAnswer: {result.answer}")
        return 0
    decision = (
        "approved" if args.auto_approve
        else "rejected" if args.auto_reject
        else None
    )
    if decision is None:
        print("\nThis action needs human approval.")
        while True:
            choice = input("Approve? [y/n] ").strip().lower()
            if choice in ("y", "yes"):
                decision = "approved"
                break
            if choice in ("n", "no"):
                decision = "rejected"
                break
            print("Please answer y or n.")
    final = asyncio.run(copilot.decide(result.run_id, decision, by="cli"))
    print(f"\nDecision: {decision}")
    print(f"Answer: {final.answer}")
    return 0


def _cmd_eval(args) -> int:
    summary = run_eval()
    out_dir = args.out or "reports"
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "eval_results.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    with open(os.path.join(out_dir, "eval_results.md"), "w") as fh:
        fh.write(render_markdown(summary))
    print(render_markdown(summary))
    print(f"Reports written to {out_dir}/")
    return 0 if summary["passed"] == summary["total"] else 1


def _cmd_demo(args) -> int:
    copilot = Copilot(mcp_mode=args.mcp_mode)
    for text, decision in SAMPLE_INCIDENTS:
        print("=" * 72)
        print(f"Request: {text}")
        result = asyncio.run(copilot.submit(text))
        _print_proposal(result)
        if result.status == "awaiting_approval":
            print(f"Human decision: {decision}")
            final = asyncio.run(
                copilot.decide(result.run_id, decision, by="demo")
            )
            print(f"Answer: {final.answer}")
        else:
            print(f"Answer: {result.answer}")
    print("=" * 72)
    print("\nAudit trail (last 8 entries):")
    for entry in copilot.audit.entries()[-8:]:
        print(f"  #{entry['seq']} {entry['ts']} {entry['event']} "
              f"[{entry['run_id']}]")
    ok, bad = copilot.audit.verify()
    print(f"\nAudit chain valid: {ok}" + ("" if ok else f" (bad seq {bad})"))
    return 0


def _cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run(
        "ai_ops_copilot.api:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ai-ops-copilot",
        description="Enterprise AI Operations Copilot (fictional demo).",
    )
    parser.add_argument(
        "--mcp-mode",
        choices=["direct", "stdio"],
        default="direct",
        help="how the agent reaches the MCP monitoring tools",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_submit = sub.add_parser("submit", help="submit a request")
    p_submit.add_argument("--text", required=True)
    p_submit.add_argument("--auto-approve", action="store_true")
    p_submit.add_argument("--auto-reject", action="store_true")
    p_submit.set_defaults(func=_cmd_submit)

    p_eval = sub.add_parser("eval", help="run the golden incident eval")
    p_eval.add_argument("--out", default="reports")
    p_eval.set_defaults(func=_cmd_eval)

    p_demo = sub.add_parser("demo", help="run the sample incidents")
    p_demo.set_defaults(func=_cmd_demo)

    p_serve = sub.add_parser("serve", help="start the API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
