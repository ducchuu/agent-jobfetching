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

@patch('app.config.settings.API_SECRET_KEY', "secret-key-123")
@patch('app.main.settings.API_SECRET_KEY', "secret-key-123")
def test_upload_cv_api_key_protection():
    # Without header -> 403 Forbidden
    resp = client.post("/upload-cv", files={"file": ("cv.pdf", b"%PDF-1.4...", "application/pdf")})
    assert resp.status_code == 403

    # With invalid header -> 403 Forbidden
    resp = client.post("/upload-cv", headers={"X-API-Key": "wrong-key"}, files={"file": ("cv.pdf", b"%PDF-1.4...", "application/pdf")})
    assert resp.status_code == 403

@patch('app.config.settings.API_SECRET_KEY', "secret-key-123")
@patch('app.main.settings.API_SECRET_KEY', "secret-key-123")
def test_location_stats_api_key_protection():
    # Without header -> 403 Forbidden
    resp = client.get("/location-stats")
    assert resp.status_code == 403

    # With valid header -> 200 OK
    resp = client.get("/location-stats", headers={"X-API-Key": "secret-key-123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "date" in data
    assert "configured_locations" in data
    assert "Netherlands" in data["configured_locations"]
    assert "Spain" in data["configured_locations"]

def test_stop_pipeline_endpoint_idle():
    from app.main import pipeline_lock
    assert not pipeline_lock.locked()
    resp = client.post("/stop-pipeline")
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"

def test_stop_pipeline_endpoint_running():
    from app.main import pipeline_lock, stop_pipeline_event
    with patch.object(pipeline_lock, 'locked', return_value=True):
        stop_pipeline_event.clear()
        resp = client.post("/stop-pipeline")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopping"
        assert stop_pipeline_event.is_set()
        stop_pipeline_event.clear()

@patch('app.config.settings.API_SECRET_KEY', "secret-key-123")
@patch('app.main.settings.API_SECRET_KEY', "secret-key-123")
def test_stop_pipeline_api_key_protection():
    resp = client.post("/stop-pipeline")
    assert resp.status_code == 403

    resp = client.post("/stop-pipeline", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 403

    resp = client.post("/stop-pipeline", headers={"X-API-Key": "secret-key-123"})
    assert resp.status_code == 200

def test_settings_locations_parsing():
    from app.config import Settings, DEFAULT_LOCATIONS
    s_example = Settings(_env_file=".env.example")
    assert s_example.LOCATIONS == DEFAULT_LOCATIONS

    s_empty = Settings(LOCATIONS="")
    assert s_empty.LOCATIONS == DEFAULT_LOCATIONS

    s_csv = Settings(LOCATIONS="Netherlands, Spain, Barcelona")
    assert s_csv.LOCATIONS == ["Netherlands", "Spain", "Barcelona"]

    s_json = Settings(LOCATIONS='["Delft", "Rotterdam"]')
    assert s_json.LOCATIONS == ["Delft", "Rotterdam"]

