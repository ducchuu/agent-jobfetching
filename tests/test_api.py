from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)

@patch('app.main.run_job_matching_pipeline')
def test_trigger_pipeline_endpoint(mock_pipeline):
    response = client.post("/trigger-pipeline")
    assert response.status_code == 200
    assert response.json()["message"] == "Pipeline triggered in the background."