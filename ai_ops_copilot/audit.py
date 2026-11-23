"""Append-only, hash-chained audit log.

Every request, retrieval, proposal, approval decision, and action is
appended as one JSON line. Each entry carries the SHA-256 hash of the
previous entry, so tampering with any line breaks the chain —
``verify()`` recomputes it and reports the first bad sequence number.

The log is a local file (``audit/audit.jsonl`` by default). It is not
a compliance system; it demonstrates the shape an audit trail needs:
immutable, ordered, and independently verifiable.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

DEFAULT_AUDIT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "audit",
    "audit.jsonl",
)


def _canonical(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"))


def _hash_entry(entry: dict) -> str:
    return hashlib.sha256(_canonical(entry).encode("utf-8")).hexdigest()


class AuditLog:
    """Append-only JSONL audit log with a hash chain."""

    def __init__(self, path: str = DEFAULT_AUDIT_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._last_hash = "0" * 64
        self._seq = 0
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    self._last_hash = entry["hash"]
                    self._seq = entry["seq"]

    def append(self, event_type: str, run_id: str, payload: dict) -> dict:
        self._seq += 1
        entry = {
            "seq": self._seq,
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "run_id": run_id,
            "payload": payload,
            "prev_hash": self._last_hash,
        }
        entry["hash"] = _hash_entry(entry)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(_canonical(entry) + "\n")
        self._last_hash = entry["hash"]
        return entry

    def entries(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def verify(self) -> tuple[bool, int | None]:
        """Recompute the hash chain. Returns (ok, first_bad_seq or None)."""
        prev = "0" * 64
        expected_seq = 0
        for entry in self.entries():
            expected_seq += 1
            if entry["seq"] != expected_seq or entry["prev_hash"] != prev:
                return False, entry["seq"]
            stored = entry.pop("hash")
            if _hash_entry(entry) != stored:
                return False, entry["seq"]
            entry["hash"] = stored
            prev = stored
        return True, None
