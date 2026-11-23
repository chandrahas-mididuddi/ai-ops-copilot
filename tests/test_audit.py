import json

from ai_ops_copilot.audit import AuditLog


def test_append_and_verify_chain(tmp_path):
    log = AuditLog(str(tmp_path / "audit.jsonl"))
    log.append("request_received", "run-1", {"request": "x"})
    log.append("proposal_made", "run-1", {"remediation_id": "scale_checkout"})
    entries = log.entries()
    assert len(entries) == 2
    assert entries[0]["seq"] == 1
    assert entries[1]["seq"] == 2
    assert entries[1]["prev_hash"] == entries[0]["hash"]
    ok, bad = log.verify()
    assert ok is True and bad is None


def test_tampered_entry_breaks_verification(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(str(path))
    log.append("request_received", "run-1", {"request": "x"})
    log.append("proposal_made", "run-1", {"remediation_id": "scale_checkout"})
    lines = path.read_text().splitlines()
    tampered = json.loads(lines[0])
    tampered["payload"] = {"request": "tampered"}
    lines[0] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")
    fresh = AuditLog(str(path))
    ok, bad = fresh.verify()
    assert ok is False and bad == 1


def test_empty_log_verifies(tmp_path):
    log = AuditLog(str(tmp_path / "audit.jsonl"))
    assert log.entries() == []
    ok, bad = log.verify()
    assert ok is True and bad is None


def test_log_reloads_last_hash(tmp_path):
    path = str(tmp_path / "audit.jsonl")
    log = AuditLog(path)
    log.append("request_received", "run-1", {"request": "x"})
    reopened = AuditLog(path)
    reopened.append("proposal_made", "run-1", {"remediation_id": "y"})
    entries = reopened.entries()
    assert entries[1]["prev_hash"] == entries[0]["hash"]
    ok, _ = reopened.verify()
    assert ok is True
