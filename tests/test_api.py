from fastapi.testclient import TestClient

from ai_ops_copilot.api import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_question_completes_inline():
    with TestClient(app) as client:
        response = client.post(
            "/requests", json={"text": "How do I roll back a bad deploy?"}
        )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["proposal"]["remediation_id"] == "answer_only"
    assert "doc-deploy-rollback" in body["answer"]


def test_sensitive_flow_approve():
    with TestClient(app) as client:
        created = client.post(
            "/requests",
            json={
                "text": "Checkout API p95 latency is 1.4 seconds and "
                "rising, customers are timing out at checkout."
            },
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        assert created.json()["status"] == "awaiting_approval"

        fetched = client.get(f"/requests/{run_id}")
        assert fetched.status_code == 200
        assert fetched.json()["proposal"]["remediation_id"] == "scale_checkout"

        approved = client.post(
            f"/requests/{run_id}/approve", json={"by": "tester"}
        )
        assert approved.status_code == 200
        body = approved.json()
        assert body["status"] == "completed"
        assert body["executed"][0]["action"] == "scale_replicas"


def test_sensitive_flow_reject_executes_nothing():
    with TestClient(app) as client:
        created = client.post(
            "/requests",
            json={
                "text": "Payments gateway is returning 5xx errors at 3% "
                "since the latest deploy."
            },
        )
        run_id = created.json()["run_id"]
        rejected = client.post(
            f"/requests/{run_id}/reject", json={"by": "tester"}
        )
        assert rejected.status_code == 200
        assert rejected.json()["executed"] == []
        assert "rejected" in rejected.json()["answer"].lower()


def test_unknown_run_404():
    with TestClient(app) as client:
        assert client.get("/requests/nope").status_code == 404
        assert (
            client.post("/requests/nope/approve", json={}).status_code == 404
        )


def test_audit_endpoint_lists_entries():
    with TestClient(app) as client:
        client.post(
            "/requests", json={"text": "How do I roll back a bad deploy?"}
        )
        response = client.get("/audit")
    assert response.status_code == 200
    events = [e["event"] for e in response.json()["entries"]]
    assert "request_received" in events
    assert "proposal_made" in events
