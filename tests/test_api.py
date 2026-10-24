from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)

@patch('app.main.run_job_matching_pipeline')
def test_trigger_pipeline_endpoint(mock_pipeline):
    response = client.post("/trigger-pipeline")
    assert response.status_code == 200
    assert response.json()["message"] == "Pipeline triggered in the background."

@patch('app.config.settings.API_SECRET_KEY', "secret-key-123")
@patch('app.main.settings.API_SECRET_KEY', "secret-key-123")
@patch('app.main.run_job_matching_pipeline')
def test_api_key_protection(mock_pipeline):
    # Without header -> 403 Forbidden
    resp = client.post("/trigger-pipeline")
    assert resp.status_code == 403

    # With invalid header -> 403 Forbidden
    resp = client.post("/trigger-pipeline", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 403

    # With valid header -> 200 OK
    resp = client.post("/trigger-pipeline", headers={"X-API-Key": "secret-key-123"})
    assert resp.status_code == 200

@patch('app.config.settings.API_SECRET_KEY', "secret-key-123")
@patch('app.main.settings.API_SECRET_KEY', "secret-key-123")
@patch('os.path.exists', return_value=False)
def test_profile_api_key_protection(mock_exists):
    # Without header -> 403 Forbidden
    resp = client.get("/profile")
    assert resp.status_code == 403

    # With invalid header -> 403 Forbidden
    resp = client.get("/profile", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 403

    # With valid header -> passes authentication (returns status ok or error when no file)
    resp = client.get("/profile", headers={"X-API-Key": "secret-key-123"})
    assert resp.status_code == 200