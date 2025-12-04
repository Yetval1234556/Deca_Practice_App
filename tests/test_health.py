import json

from app import app


def test_health():
    client = app.test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    data = json.loads(resp.data.decode("utf-8"))
    assert data.get("status") == "ok"
