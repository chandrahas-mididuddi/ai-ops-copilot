"""The copilot agent: a LangGraph state machine.

Flow:
    triage -> retrieve -> observe -> propose -> gate -> execute -> respond

- ``triage`` classifies the request as a question or an incident.
- ``retrieve`` runs hybrid RAG over the fictional docs corpus.
- ``observe`` pulls metrics, logs, and alerts through the MCP
  monitoring tools.
- ``propose`` drafts a remediation with evidence (mock reasoning
  backend by default; swap in a real LLM via ``llm.ReasoningBackend``).
- ``gate`` is the human approval gate. Sensitive proposals pause the
  graph with LangGraph's ``interrupt()`` until a human approves or
  rejects. Non-sensitive proposals pass through automatically.
- ``execute`` runs the action — only after approval. The guard in
  ``actions.execute_action`` is the second line of defence.
- ``respond`` composes the final answer with citations.

Every stage writes to the audit log. State is plain JSON-serialisable
data so the graph can checkpoint and resume across the approval pause.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from .actions import ApprovalRequiredError, execute_action
from .approvals import ApprovalStore
from .audit import AuditLog
from .corpus import Doc, load_docs
from .llm import MockReasoningBackend, ReasoningBackend
from .mcp_client import MonitoringClient
from .monitoring import MonitoringStore, infer_service
from .playbook import get_remediation
from .retrieval import HybridRetriever, RetrievalResult


class CopilotState(TypedDict, total=False):
    run_id: str
    request: str
    request_type: str
    docs: list[dict]
    monitoring: dict
    proposal: dict | None
    approval: str | None
    executed: list[dict]
    answer: str


class RunResult:
    """Outcome of a submit/decide call."""

    def __init__(self, run_id: str, status: str, state: dict):
        self.run_id = run_id
        self.status = status  # awaiting_approval | completed
        self.state = state

    @property
    def proposal(self) -> dict | None:
        return self.state.get("proposal")

    @property
    def answer(self) -> str:
        return self.state.get("answer", "")


class Copilot:
    """The operations copilot. Owns the graph, audit log, and approvals."""

    def __init__(
        self,
        *,
        backend: ReasoningBackend | None = None,
        audit: AuditLog | None = None,
        approvals: ApprovalStore | None = None,
        mcp_mode: str = "direct",
    ):
        self.docs = load_docs()
        self.retriever = HybridRetriever(self.docs)
        self.monitoring_store = MonitoringStore()
        self.backend = backend or MockReasoningBackend()
        self.audit = audit or AuditLog()
        self.approvals = approvals or ApprovalStore()
        self.mcp_mode = mcp_mode
        self._graph = self._build_graph()

    # -- graph construction -------------------------------------------------

    def _build_graph(self):
        graph = StateGraph(CopilotState)
        graph.add_node("triage", self._triage)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("observe", self._observe)
        graph.add_node("propose", self._propose)
        graph.add_node("gate", self._gate)
        graph.add_node("execute", self._execute)
        graph.add_node("respond", self._respond)
        graph.set_entry_point("triage")
        graph.add_edge("triage", "retrieve")
        graph.add_edge("retrieve", "observe")
        graph.add_edge("observe", "propose")
        graph.add_edge("propose", "gate")
        graph.add_edge("gate", "execute")
        graph.add_edge("execute", "respond")
        graph.add_edge("respond", END)
        return graph.compile(checkpointer=MemorySaver())

    # -- nodes --------------------------------------------------------------

    async def _triage(self, state: CopilotState) -> dict:
        from .llm import QUESTION_WORDS

        lowered = state["request"].lower()
        request_type = (
            "question"
            if any(w in lowered for w in QUESTION_WORDS)
            else "incident"
        )
        return {"request_type": request_type}

    async def _retrieve(self, state: CopilotState) -> dict:
        results = self.retriever.search(state["request"], top_k=3)
        docs = [
            {
                "doc": {
                    "id": r.doc.id,
                    "title": r.doc.title,
                    "service": r.doc.service,
                    "body": r.doc.body,
                },
                "bm25": r.bm25,
                "tfidf": r.tfidf,
                "score": r.score,
            }
            for r in results
        ]
        self.audit.append(
            "docs_retrieved",
            state["run_id"],
            {"query": state["request"], "doc_ids": [r.doc.id for r in results]},
        )
        return {"docs": docs}

    async def _observe(self, state: CopilotState) -> dict:
        service = infer_service(state["request"])
        if service is None and state["docs"]:
            service = state["docs"][0]["doc"]["service"]
        monitoring: dict = {}
        async with MonitoringClient(mode=self.mcp_mode) as client:
            if service and service != "platform":
                monitoring[service] = {
                    "metrics": await client.get_metrics(service),
                    "logs": await client.get_logs(service),
                    "alerts": await client.get_alerts(service),
                }
            else:
                monitoring["alerts"] = await client.get_alerts()
        self.audit.append(
            "monitoring_fetched",
            state["run_id"],
            {"service": service, "via": f"mcp:{self.mcp_mode}"},
        )
        return {"monitoring": monitoring}

    async def _propose(self, state: CopilotState) -> dict:
        results = [
            RetrievalResult(
                Doc(**d["doc"]), d["bm25"], d["tfidf"], d["score"]
            )
            for d in state["docs"]
        ]
        draft = self.backend.propose(
            request=state["request"],
            docs=results,
            monitoring=state["monitoring"],
        )
        entry = draft.remediation
        proposal = {
            "remediation_id": entry.id,
            "name": entry.name,
            "action": entry.action,
            "service": entry.service,
            "sensitive": entry.sensitive,
            "description": entry.description,
            "rationale": draft.rationale,
            "citations": draft.citations,
            "evidence": {
                "metrics": draft.evidence_metrics,
                "logs": draft.evidence_logs,
                "alerts": draft.evidence_alerts,
            },
        }
        self.approvals.record_proposal(
            run_id=state["run_id"],
            remediation_id=entry.id,
            action=entry.action,
            sensitive=entry.sensitive,
        )
        self.audit.append(
            "proposal_made",
            state["run_id"],
            {
                "remediation_id": entry.id,
                "action": entry.action,
                "sensitive": entry.sensitive,
                "citations": draft.citations,
            },
        )
        return {"proposal": proposal}

    async def _gate(self, state: CopilotState) -> dict:
        proposal = state["proposal"]
        if not proposal["sensitive"]:
            return {"approval": "auto"}
        # Pause here. The graph resumes only when a human decides.
        decision = interrupt(
            {
                "proposal": proposal,
                "message": (
                    "Human approval required before executing "
                    f"'{proposal['action']}' on {proposal['service']}."
                ),
            }
        )
        return {"approval": decision}

    async def _execute(self, state: CopilotState) -> dict:
        proposal = state["proposal"]
        approval = state.get("approval")
        run_id = state["run_id"]
        if approval == "rejected":
            self.audit.append(
                "action_skipped",
                run_id,
                {"action": proposal["action"], "reason": "rejected by human"},
            )
            return {"executed": []}
        try:
            result = execute_action(
                action=proposal["action"],
                service=proposal["service"],
                approval=approval,
            )
        except ApprovalRequiredError as exc:
            # Should not happen — the gate blocks this — but the guard
            # is the last line of defence, so record it and stop.
            self.audit.append(
                "action_blocked", run_id, {"error": str(exc)}
            )
            return {"executed": [], "answer": f"Blocked: {exc}"}
        self.audit.append("action_executed", run_id, result)
        return {"executed": [result]}

    async def _respond(self, state: CopilotState) -> dict:
        proposal = state["proposal"]
        citations = ", ".join(f"[{c}]" for c in proposal["citations"])
        approval = state.get("approval")
        if proposal["action"] == "none":
            answer = (
                f"{proposal['rationale']} See {citations} for the "
                "procedure."
            )
        elif approval == "rejected":
            answer = (
                f"Proposal '{proposal['name']}' was rejected by a human. "
                "No action was taken. "
                f"Evidence considered: {citations}."
            )
        elif proposal["action"] == "notify_oncall":
            answer = (
                "No runbook matches this request, so the on-call engineer "
                f"was notified. Evidence: {citations}."
            )
        else:
            detail = state["executed"][0]["detail"] if state["executed"] else ""
            answer = (
                f"{proposal['name']}: {detail} "
                f"Evidence: {citations}. {proposal['description']}"
            )
        self.audit.append(
            "run_completed",
            state["run_id"],
            {"approval": approval, "action": proposal["action"]},
        )
        return {"answer": answer}

    # -- public API ---------------------------------------------------------

    def _config(self, run_id: str) -> dict:
        return {"configurable": {"thread_id": run_id}}

    async def submit(self, request: str, run_id: str | None = None) -> RunResult:
        """Start a run. Returns awaiting_approval if a human must decide."""
        run_id = run_id or f"run-{uuid.uuid4().hex[:8]}"
        self.audit.append(
            "request_received", run_id, {"request": request}
        )
        state: CopilotState = {
            "run_id": run_id,
            "request": request,
            "proposal": None,
            "approval": None,
            "executed": [],
            "answer": "",
        }
        result = await self._graph.ainvoke(state, self._config(run_id))
        if "__interrupt__" in result:
            return RunResult(run_id, "awaiting_approval", result)
        return RunResult(run_id, "completed", result)

    async def decide(
        self, run_id: str, decision: str, *, by: str = "operator"
    ) -> RunResult:
        """Record a human decision and resume the paused run."""
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        record = self.approvals.get(run_id)
        if record is None or record.status != "pending":
            raise ValueError(f"no pending proposal for run {run_id}")
        self.approvals.decide(run_id, decision, by=by)
        self.audit.append(
            "approval_decision",
            run_id,
            {"decision": decision, "by": by},
        )
        result = await self._graph.ainvoke(
            Command(resume=decision), self._config(run_id)
        )
        return RunResult(run_id, "completed", result)

    async def status(self, run_id: str) -> dict | None:
        """Current checkpointed state for a run, or None if unknown."""
        snapshot = await self._graph.aget_state(self._config(run_id))
        if not snapshot.values:
            return None
        values = dict(snapshot.values)
        values["awaiting_approval"] = bool(snapshot.tasks and any(
            (task.interrupts for task in snapshot.tasks)
        ))
        return values
