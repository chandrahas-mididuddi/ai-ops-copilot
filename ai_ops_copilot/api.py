"""FastAPI service for the copilot.

Endpoints:
- ``POST /requests`` — submit a request; returns the proposal and
  whether a human decision is needed.
- ``GET /requests/{run_id}`` — current state of a run.
- ``POST /requests/{run_id}/approve`` — approve and resume the run.
- ``POST /requests/{run_id}/reject`` — reject and resume the run.
- ``GET /requests`` — list known runs.
- ``GET /audit`` — audit log entries.
- ``GET /health`` — liveness.

The copilot, approval store, and audit log live in app state, so a
single server process keeps the graph checkpoints needed to resume
paused runs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .agent import Copilot
from .approvals import ApprovalStore
from .audit import AuditLog


class SubmitRequest(BaseModel):
    text: str = Field(..., min_length=1)


class DecideRequest(BaseModel):
    by: str = "operator"
    reason: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.copilot = Copilot()
    app.state.runs: dict[str, dict] = {}
    yield


app = FastAPI(title="ai-ops-copilot", lifespan=lifespan)


def _public(run_id: str, state: dict, status: str) -> dict:
    return {
        "run_id": run_id,
        "status": status,
        "request": state.get("request"),
        "request_type": state.get("request_type"),
        "proposal": state.get("proposal"),
        "approval": state.get("approval"),
        "executed": state.get("executed", []),
        "answer": state.get("answer", ""),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/requests", status_code=202)
async def submit_request(body: SubmitRequest) -> dict:
    copilot: Copilot = app.state.copilot
    result = await copilot.submit(body.text)
    app.state.runs[result.run_id] = _public(
        result.run_id, result.state, result.status
    )
    return app.state.runs[result.run_id]


@app.get("/requests")
def list_requests() -> dict:
    return {"runs": list(app.state.runs.values())}


@app.get("/requests/{run_id}")
def get_request(run_id: str) -> dict:
    run = app.state.runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return run


@app.post("/requests/{run_id}/approve")
async def approve_request(run_id: str, body: DecideRequest) -> dict:
    return await _decide(run_id, "approved", body)


@app.post("/requests/{run_id}/reject")
async def reject_request(run_id: str, body: DecideRequest) -> dict:
    return await _decide(run_id, "rejected", body)


async def _decide(run_id: str, decision: str, body: DecideRequest) -> dict:
    copilot: Copilot = app.state.copilot
    if run_id not in app.state.runs:
        raise HTTPException(status_code=404, detail="unknown run")
    try:
        result = await copilot.decide(run_id, decision, by=body.by)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    app.state.runs[run_id] = _public(
        run_id, result.state, result.status
    )
    return app.state.runs[run_id]


@app.get("/audit")
def get_audit() -> dict:
    copilot: Copilot = app.state.copilot
    return {"entries": copilot.audit.entries()}
