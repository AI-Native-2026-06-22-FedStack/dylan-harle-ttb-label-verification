from fastapi.testclient import TestClient

from api.index import app


def test_health_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ttb-label-verification",
        "environment": "local",
    }

