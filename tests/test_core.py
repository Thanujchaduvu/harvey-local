import pytest
from fastapi.testclient import TestClient

from app import config, db, hardware, llm_client, network_guard, seed, taskqueue
from app.llm_client import NonLocalEndpointError, OllamaClient, validate_endpoint
from app.main import app
from app.workflows import common, emails, replies, scoring  # noqa: F401
from tests.fake_ollama import down_transport, working_transport


def test_endpoint_guard_rejects_cloud_and_public_ips():
    for bad in ("https://api.openai.com", "http://8.8.8.8:11434", "http://example.com", "ftp://127.0.0.1"):
        with pytest.raises(NonLocalEndpointError):
            validate_endpoint(bad)
    assert validate_endpoint("http://127.0.0.1:11434/") == "http://127.0.0.1:11434"
    assert validate_endpoint("http://localhost:11434")


def test_lan_requires_explicit_opt_in(monkeypatch):
    with pytest.raises(NonLocalEndpointError):
        validate_endpoint("http://192.168.1.50:11434")
    monkeypatch.setattr(config, "ALLOW_LAN", True)
    assert validate_endpoint("http://192.168.1.50:11434")
    with pytest.raises(NonLocalEndpointError):
        validate_endpoint("http://8.8.8.8:11434")


def test_hardware_recommendations():
    base = dict(os="Linux", machine="x86_64", ram_available_gb=8, cpu_logical=8, apple_silicon=False)
    laptop = hardware.recommend({**base, "ram_total_gb": 16, "cpu_physical": 4, "gpus": []})
    assert laptop["model"] == "qwen3:4b" and laptop["profile"] == "standard"
    tiny = hardware.recommend({**base, "ram_total_gb": 4, "cpu_physical": 2, "gpus": []})
    assert tiny["model"] in ("qwen3:0.6b", "qwen3:1.7b")
    big = hardware.recommend({**base, "ram_total_gb": 64, "cpu_physical": 16, "gpus": [{"name": "x", "vram_gb": 24}]})
    assert big["model"] == "qwen3:32b" and big["profile"] == "high-performance"
    mac = hardware.recommend({**base, "ram_total_gb": 32, "cpu_physical": 10, "gpus": [], "apple_silicon": True})
    assert mac["profile"] == "high-performance"


def _setup():
    s = seed.seed_demo()
    return s["product_ids"]["dispatchly"], s["business_id"]


def test_full_pipeline_logs_local_inference(env):
    calls = env
    pid, bid = _setup()
    c = TestClient(app)
    assert c.post(f"/api/businesses/{bid}/profile").json()["status"] == "done"
    assert c.post(f"/api/products/{pid}/icp").json()["status"] == "done"
    prospects = c.get(f"/api/products/{pid}/prospects").json()
    maria = next(p for p in prospects if p["name"] == "Maria Okafor")
    out = c.post(f"/api/prospects/{maria['id']}/run-all").json()
    assert [s["status"] for s in out["steps"]] == ["done"] * 5
    p = out["prospect"]
    assert p["research_data"]["evidence"], "verified evidence kept"
    assert p["research_data"]["evidence_rejected"] == ["this quote is invented and absent"]
    sigs = {s["type"]: s for s in p["signals_data"]["signals"]}
    assert sigs["hiring"]["evidence_verified"] and not sigs["funding"]["evidence_verified"]
    assert sigs["funding"]["strength"] <= 2, "unverifiable evidence is capped"
    assert p["score_data"]["tier"] in "ABCD" and p["score_data"]["partial"] is False
    assert p["emails"][0]["body"].rstrip().endswith('won\'t follow up.')
    log = c.get("/api/inference-log").json()
    assert log and all(r["endpoint"].startswith("http://127.0.0.1:11434") for r in log)
    assert all(call["host"] == "127.0.0.1" for call in calls)


def test_ollama_down_queues_and_recovers(env):
    pid, bid = _setup()
    llm_client.set_client(OllamaClient("http://127.0.0.1:11434", transport=down_transport()))
    c = TestClient(app)
    r = c.post(f"/api/businesses/{bid}/profile").json()
    assert r["status"] == "queued" and "cloud" in r["message"].lower()
    assert taskqueue.counts()["pending"] == 1
    assert taskqueue.process()["processed"] == 0           # still down, nothing lost
    llm_client.set_client(OllamaClient("http://127.0.0.1:11434", transport=working_transport()))
    assert taskqueue.process()["processed"] == 1
    assert db.one("SELECT profile_json FROM businesses WHERE id=?", (bid,))["profile_json"]


def test_partial_score_when_llm_down(env):
    pid, bid = _setup()
    c = TestClient(app)
    c.post(f"/api/products/{pid}/icp")
    prospect = c.get(f"/api/products/{pid}/prospects").json()[0]
    llm_client.set_client(OllamaClient("http://127.0.0.1:11434", transport=down_transport()))
    out = c.post(f"/api/prospects/{prospect['id']}/score").json()
    assert out["status"] == "queued"
    sd = out["prospect"]["score_data"]
    assert sd["partial"] is True and "llm_fit" not in sd["components"] and out["prospect"]["score"] is not None


def test_unsubscribe_and_ooo_need_no_llm():
    llm_client.set_client(OllamaClient("http://127.0.0.1:11434", transport=down_transport()))
    c = TestClient(app)
    r = c.post("/api/replies/classify", json={"text": "Please remove me from your list."}).json()
    assert r["status"] == "done" and r["reply"]["label"] == "unsubscribe" and r["reply"]["method"] == "rule"
    r = c.post("/api/replies/classify", json={"text": "I am out of the office until Monday."}).json()
    assert r["reply"]["label"] == "out_of_office"
    r = c.post("/api/replies/classify", json={"text": "How much does it cost?"}).json()
    assert r["status"] == "queued"


def test_reply_eval_runs_all_samples():
    out = replies.eval_samples()
    assert out["total"] == 12 and len(out["results"]) == 12
    assert {r["method"] for r in out["results"]} >= {"rule", "llm"}


def test_quote_verification():
    src = "We are hiring three additional dispatchers this spring."
    ok, bad = common.verify_quotes(["hiring three additional dispatchers", "raised $50M"], src)
    assert ok == ["hiring three additional dispatchers"] and bad == ["raised $50M"]


def test_email_checks_flag_problems():
    p = {"name": "Maria Okafor", "company": "BlueRidge"}
    assert emails.check_email("s", "Hi [Name], hope this email finds you well", p)
    assert not emails.check_email("s", "Hi Maria, " + "word " * 60 + "worth a quick call?", p)


def test_rule_fit_distinguishes_good_and_poor_fit():
    icp = {"industries": ["HVAC and plumbing services"], "titles": ["Operations Manager"], "geographies": ["US"],
           "company_size": {"min_employees": 20, "max_employees": 250}}
    good = {"industry": "HVAC services", "title": "Operations Manager", "employees": 85, "location": "Denver, CO, US"}
    poor = {"industry": "Design agency", "title": "VP Marketing", "employees": 3000, "location": "Paris"}
    assert scoring.rule_fit(good, icp)[0] > 0.8 > 0.3 > scoring.rule_fit(poor, icp)[0]


def test_network_guard_blocks_external_but_not_loopback():
    config_strict = config.STRICT_LOCAL
    assert config_strict
    network_guard.install()
    with pytest.raises(network_guard.ExternalNetworkBlocked):
        network_guard._check(("93.184.216.34", 443))
    network_guard._check(("127.0.0.1", 11434))
    with network_guard.allow_external():
        network_guard._check(("93.184.216.34", 443))
    assert network_guard.violations


def test_ai_and_web_research_are_separated():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "app"
    assert "llm_client" not in (root / "webresearch.py").read_text()
    assert "webresearch" not in (root / "llm_client.py").read_text()
    for f in (root / "workflows").glob("*.py"):
        assert "webresearch" not in f.read_text() and "allow_external" not in f.read_text()


def test_path_traversal_blocked():
    with pytest.raises(ValueError):
        seed.parse_file(config.DATA_DIR / ".." / "requirements.txt")


def test_fetch_web_route_not_shadowed_and_blocks_private():
    _setup()
    c = TestClient(app)
    r = c.post("/api/prospects/1/fetch-web", json={"url": "http://127.0.0.1/x"})
    assert r.status_code == 503 and "private" in r.json()["detail"].lower()
    assert c.post("/api/prospects/1/not-a-stage").status_code == 404
