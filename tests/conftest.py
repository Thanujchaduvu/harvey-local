import pytest

from app import config, db, llm_client, network_guard
from app.llm_client import OllamaClient
from tests.fake_ollama import working_transport


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "MODEL", "")
    db.init(tmp_path / "t.db")
    calls: list = []
    llm_client.set_client(OllamaClient("http://127.0.0.1:11434", transport=working_transport(calls)))
    yield calls
    llm_client.set_client(None)
    network_guard.uninstall()
