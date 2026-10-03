import time
import io
import pytest
import numpy as np
from fastapi.testclient import TestClient
from api.main import app
from api.core.jobs import get_job

client = TestClient(app)

def test_healthz_endpoint():
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_sign_upload_endpoint():
    response = client.post("/uploads/sign", data={"module": "thermal"})
    assert response.status_code == 200
    data = response.json()
    assert "upload_preset" in data
    assert "signature" in data
    assert "timestamp" in data

def test_run_local_thermal_job():
    # Create sample CSV
    arr = np.full((60, 60), 20.0, dtype=np.float32)
    arr[20:35, 20:35] = 55.0  # +35 C anomaly
    buf = io.BytesIO()
    np.savetxt(buf, arr, delimiter=",", fmt="%.2f")
    csv_bytes = buf.getvalue()

    response = client.post(
        "/jobs/run-local",
        data={"module": "thermal"},
        files={"file": ("sample_matrix.csv", csv_bytes, "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    job_id = data["job_id"]

    # Give the background task a moment to finish
    time.sleep(1.0)

    # Check job status endpoint
    res_job = client.get(f"/jobs/{job_id}")
    assert res_job.status_code == 200
    job_data = res_job.json()
    assert job_data["status"] == "done"
    assert len(job_data["findings"]) >= 1
    
    first_finding = job_data["findings"][0]
    assert first_finding["measurements"]["max_temp_c"] == 55.0
    assert first_finding["risk_level"] == "high"
    assert "vision" in first_finding
    assert first_finding["vision"]["classification"] is not None

def test_run_local_audio_job():
    from api.tests.test_audio import create_synthetic_wav
    wav_bytes = create_synthetic_wav(duration=1.5, inject_hum=True)

    response = client.post(
        "/jobs/run-local",
        data={"module": "audio"},
        files={"file": ("sample_test_audio.wav", wav_bytes, "audio/wav")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    job_id = data["job_id"]

    # Allow background execution to finish
    time.sleep(1.0)

    res_job = client.get(f"/jobs/{job_id}")
    assert res_job.status_code == 200
    job_data = res_job.json()
    assert job_data["status"] == "done"
    assert len(job_data["findings"]) >= 1
    assert "spectrogram" in job_data["assets"]
    assert job_data["calibration"]["kind"] == "spectrogram"

def test_run_local_print_job():
    from api.tests.test_print import create_synthetic_layers
    actual_bytes, _ = create_synthetic_layers()

    response = client.post(
        "/jobs/run-local",
        data={"module": "print"},
        files={"file": ("sample_layer.png", actual_bytes, "image/png")}
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    time.sleep(1.0)

    res_job = client.get(f"/jobs/{job_id}")
    assert res_job.status_code == 200
    job_data = res_job.json()
    assert job_data["status"] == "done"
    assert job_data["calibration"]["kind"] == "layer"

def test_run_local_specimen_job():
    from api.tests.test_specimen import create_synthetic_specimen
    specimen_bytes = create_synthetic_specimen("histology")

    response = client.post(
        "/jobs/run-local",
        data={"module": "specimen"},
        files={"file": ("sample_slide.png", specimen_bytes, "image/png")}
    )
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    time.sleep(1.0)

    res_job = client.get(f"/jobs/{job_id}")
    assert res_job.status_code == 200
    job_data = res_job.json()
    assert job_data["status"] == "done"
    assert job_data["calibration"]["kind"] == "slide"

def test_history_endpoint():
    response = client.get("/history")
    assert response.status_code == 200
    data = response.json()
    assert "resources" in data

