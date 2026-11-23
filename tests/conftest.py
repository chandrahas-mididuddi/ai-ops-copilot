import pytest

from ai_ops_copilot.agent import Copilot
from ai_ops_copilot.audit import AuditLog
from ai_ops_copilot.corpus import load_docs
from ai_ops_copilot.monitoring import MonitoringStore


@pytest.fixture
def docs():
    return load_docs()


@pytest.fixture
def store():
    return MonitoringStore()


@pytest.fixture
def copilot(tmp_path):
    audit = AuditLog(str(tmp_path / "audit.jsonl"))
    return Copilot(audit=audit)
