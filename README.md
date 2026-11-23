# ai-ops-copilot

An **Enterprise AI Operations Copilot** — Agentic RAG with MCP monitoring
tools and human approval before any sensitive action.

Give it a support request in plain language. It searches internal
documentation with hybrid retrieval, pulls live (fictional) monitoring
data through MCP tools, investigates with a LangGraph agent, and
proposes a remediation with cited evidence. If the proposed action is
sensitive — scaling, restarting, rolling back, purging, rotating a
certificate — the run **pauses for human approval** and nothing
executes until a human says so. Every step lands in a hash-chained
audit log, and a golden-set eval measures groundedness, remediation
accuracy, and approval-gating correctness.

This is a portfolio project. It is not affiliated with any company,
it never touches a real system, and all data is fictional — the
company is "Meridian Retail", the services are invented, and every
action is simulated. It exists to show how an agentic operations
copilot is designed, built, and tested.

## What it does

- **Hybrid RAG** (`retrieval.py`): BM25 + TF-IDF cosine over 12
  fictional runbooks and service docs (`data/docs.yaml`), with
  citations in every answer.
- **MCP monitoring tools** (`mcp_server.py`, `mcp_client.py`): a real
  MCP server (MCP Python SDK v2, `MCPServer`) exposing
  `get_service_metrics`, `get_service_logs`, and `get_active_alerts`
  over fictional monitoring data (`data/monitoring.yaml`). The client
  works in two modes — `direct` (in-process, for tests and eval) and
  `stdio` (the real MCP protocol, spawning the server as a subprocess).
- **LangGraph agent** (`agent.py`): a state machine —
  `triage → retrieve → observe → propose → gate → execute → respond` —
  built on real LangGraph with a `MemorySaver` checkpointer. The
  `gate` node pauses with LangGraph's `interrupt()` until a human
  approves or rejects.
- **Human approval gate** (`approvals.py`, `actions.py`): sensitive
  actions raise `ApprovalRequiredError` unless approval is
  `"approved"`. The guard lives in `execute_action`, so no path
  through the agent, API, or CLI can bypass it.
- **Audit log** (`audit.py`): append-only JSONL, hash-chained
  (each entry carries the SHA-256 of the previous one). `verify()`
  recomputes the chain and reports the first tampered entry.
- **Eval runner** (`evaluator.py`): 8 golden incidents
  (`data/golden_incidents.yaml`) scored on groundedness of citations,
  remediation match, and approval-gating correctness. Sensitive
  incidents are resumed once with an approval (action must execute)
  and once with a rejection (action must not execute).
- **API + CLI** (`api.py`, `cli.py`): FastAPI service with
  submit/approve/reject/audit endpoints, and a CLI with
  `submit`, `eval`, `demo`, and `serve` commands.

## Architecture

```
                        ┌──────────────────────┐
                        │  CLI / FastAPI       │
                        │  submit · approve    │
                        └──────────┬───────────┘
                                   │
                        ┌──────────▼───────────┐
                        │  LangGraph agent     │
                        │  triage → retrieve   │
                        │  → observe → propose │
                        │  → gate → execute    │
                        │  → respond           │
                        └────┬───────────┬─────┘
                             │           │
              ┌──────────────▼──┐  ┌─────▼─────────────┐
              │ Hybrid RAG      │  │ MCP monitoring    │
              │ BM25 + TF-IDF   │  │ tools (MCP SDK)   │
              │ data/docs.yaml  │  │ metrics · logs    │
              └─────────────────┘  │ alerts            │
                                   └───────────────────┘
                        ┌──────────▼───────────┐
                        │ Human approval gate  │
                        │ interrupt() → resume │
                        │ on approve / reject  │
                        └──────────┬───────────┘
                                   │
              ┌────────────────────▼────────────────────┐
              │ Audit log (hash-chained JSONL)          │
              │ request · retrieval · proposal ·        │
              │ decision · action · completion          │
              └─────────────────────────────────────────┘
```

The reasoning backend is pluggable (`llm.py`): the default is a
deterministic rule-based mock so everything runs offline and the eval
reproduces exactly. Implement `ReasoningBackend.propose()` to swap in
a real LLM — the agent, gate, and audit log do not care how the draft
was produced.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# Run the demo: one approved incident, one rejected, one question
python run_demo.py

# Submit a request interactively (you will be asked to approve)
python -m ai_ops_copilot submit --text "Checkout API p95 latency is 1.4 seconds and rising"

# Same, with the approval decided on the command line
python -m ai_ops_copilot submit --text "Payments gateway is returning 5xx errors" --auto-reject

# Run the demo over the real MCP stdio protocol instead of in-process calls
python -m ai_ops_copilot --mcp-mode stdio demo

# Run the golden-set eval
python -m ai_ops_copilot eval --out reports

# Start the API server
python -m ai_ops_copilot serve
```

API example:

```bash
curl -X POST localhost:8000/requests \
  -H 'Content-Type: application/json' \
  -d '{"text": "Inventory sync consumer lag is 45,000 and growing"}'
# → 202, status "awaiting_approval", with the proposal and citations

curl -X POST localhost:8000/requests/<run_id>/approve -d '{"by": "operator"}'
# → 200, the action executes and the answer is returned

curl localhost:8000/audit   # the full audit trail
```

## Sample run

`python run_demo.py` output (abridged):

```
Request: Checkout API p95 latency is 1.4 seconds and rising, customers are timing out at checkout.
Proposal: Scale checkout-api replicas
  Action: scale_replicas on checkout-api
  Sensitive: True
  Citations: doc-checkout-latency
  Metrics: {"latency_p95_ms": 1420, "error_rate_pct": 0.4, "cpu_pct": 91, ...}
  Alert: [critical] checkout-api p95 latency above 800ms for 10 minutes
Human decision: approved
Answer: Scale checkout-api replicas: Scaled checkout-api replicas (simulated).
  Evidence: [doc-checkout-latency]. ...

Request: Payments gateway is returning 5xx errors at 3% since the latest deploy.
Proposal: Roll back payments-gateway deploy
Human decision: rejected
Answer: Proposal 'Roll back payments-gateway deploy' was rejected by a human.
  No action was taken. ...

Request: How do I roll back a bad deploy?
Proposal: Answer from documentation
Answer: Request is a question; answer from documentation.
  See [doc-deploy-rollback], [doc-payments-errors] for the procedure.

Audit chain valid: True
```

## Sample eval results

Golden set: 8 fictional incidents (`data/golden_incidents.yaml`).
Full output committed in [`eval_results.md`](eval_results.md) and
[`eval_results.json`](eval_results.json).

```
Golden incidents: 8
Passed: 8 (100%)
Grounded citations: 8/8
Remediation match: 8/8
Approval gating correct: 8/8
```

| Incident | Proposed | Expected | Grounded | Match | Gating | Passed |
|----------|----------|----------|----------|-------|--------|--------|
| inc-01 | scale_checkout | scale_checkout | yes | yes | yes | yes |
| inc-02 | rollback_payments | rollback_payments | yes | yes | yes | yes |
| inc-03 | restart_inventory_worker | restart_inventory_worker | yes | yes | yes | yes |
| inc-04 | scale_notification_consumers | scale_notification_consumers | yes | yes | yes | yes |
| inc-05 | rotate_pricing_cert | rotate_pricing_cert | yes | yes | yes | yes |
| inc-06 | answer_only | answer_only | yes | yes | yes | yes |
| inc-07 | purge_pricing_cache | purge_pricing_cache | yes | yes | yes | yes |
| inc-08 | escalate_oncall | escalate_oncall | yes | yes | yes | yes |

What the metrics mean:

| Metric | Definition |
|--------|-----------|
| Grounded | Every cited document was actually retrieved, and at least one expected document is cited |
| Remediation match | The proposed remediation is the expected one for the incident |
| Gating correct | Sensitive incidents pause for approval with nothing executed; non-sensitive ones run through |
| Pass | Grounded + match + gating, plus (for sensitive incidents) the action executes after approval and does not execute after rejection |

## Tests

```bash
pytest -q        # 43 tests
```

Coverage: BM25/hybrid ranking and edge cases, the monitoring store
and both MCP client modes (including a real stdio round-trip),
the approval guard (every sensitive action, with and without
approval), the hash-chained audit log (including tamper detection),
the full agent flow (question, approve, reject, escalate, double
decision), the golden-set eval, and the API end to end. CI (GitHub
Actions, `.github/workflows/ci.yml`) runs the suite plus the eval on
Python 3.11 and 3.12.

## Design decisions

**Why a mock reasoning backend.** The point of this project is the
system around the model — retrieval, tools, the approval gate, the
audit trail, the eval — not the model itself. A deterministic mock
keeps the eval reproducible (the same run always scores the same)
and the project runnable offline. The `ReasoningBackend` protocol is
one method, so a real LLM drops in without touching anything else.

**Why LangGraph's `interrupt()` for approval.** The pause is part of
the graph, not bolted on: the run's state is checkpointed, the
proposal is returned to the human, and the same thread resumes on
their decision. There is no way for a rejected proposal to execute,
because execution only happens in a node that runs after the gate.

**Why the approval guard is duplicated.** The gate node blocks
execution, *and* `execute_action` refuses sensitive actions without
an explicit `"approved"`. Defence in depth: a bug in the graph
cannot become an unauthorised action.

**Why the mock backend needs a score threshold.** A single loose
keyword ("slow") is not enough to propose a system change. An entry
needs a score of at least 4 — two signal matches, or a signal plus
supporting documentation — otherwise the copilot escalates to a
human. That is a deliberate bias toward doing nothing over doing
the wrong thing.

**Why hash-chain the audit log.** An audit trail you can silently
rewrite is not an audit trail. The chain makes tampering detectable
with one command (`verify()`), which the demo prints.

## Limitations

- **Mock reasoning.** The backend matches keywords and retrieval
  overlap against a small playbook. It will not understand novel
  incidents — that is what the `escalate_oncall` fallback is for.
  A real model would behave differently; the eval measures the
  system, not general agent capability.
- **Simulated actions.** "Executing" an action returns a record
  describing what would happen. Nothing here restarts, scales, or
  rolls back anything real — by design.
- **In-memory state.** The API keeps runs and approvals in memory;
  restarting the server loses paused runs. A production version
  would persist checkpoints (LangGraph supports Postgres/SQLite
  checkpointers) and the approval store.
- **Fictional data.** Twelve docs, five services, eight golden
  incidents. Enough to demonstrate the loop honestly; not a
  benchmark of retrieval quality at scale.
- **Single-threaded eval.** Incidents run sequentially. Fine for
  eight incidents; a larger suite would want workers.

## License

MIT — see [LICENSE](LICENSE).
