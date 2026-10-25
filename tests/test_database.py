import pytest
import sqlite3
import os
from unittest.mock import patch
from app.core.database import init_db, is_job_processed, mark_job_processed

TEST_DB = "data/test_jobs.db"

@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        
    with patch('app.core.database.DB_PATH', TEST_DB):
        init_db()
        yield
        
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

@patch('app.core.database.DB_PATH', TEST_DB)
def test_job_processing_logic():
    job_id = "job_123"
    
    # job is not processed initially
    assert not is_job_processed(job_id)
    
    # mark it as processed
    mark_job_processed(job_id)
    
    # it is now processed
    assert is_job_processed(job_id)
    
    # check whether duplicate insertion doesn't crash (SQLite INSERT OR IGNORE / ON CONFLICT)
    mark_job_processed(job_id)

@patch('app.core.database.DB_PATH', TEST_DB)
def test_cross_platform_fingerprint_deduplication():
    from app.core.database import record_job_status, STATUS_EVALUATED, STATUS_ERROR_TRANSIENT
    
    # Simulate LinkedIn posting
    record_job_status(
        job_id="li-12345",
        company="ASML",
        title="Robotics Engineer",
        status=STATUS_EVALUATED,
        score=92,
        reasoning="Strong robotics background"
    )
    
    # Job with same title and company scraped from Indeed with different job_id
    assert is_job_processed("in-99999", company="ASML", title="Robotics Engineer")
    
    # Different title should not match
    assert not is_job_processed("in-88888", company="ASML", title="Frontend Developer")

@patch('app.core.database.DB_PATH', TEST_DB)
def test_transient_error_not_marked_processed():
    from app.core.database import record_job_status, STATUS_ERROR_TRANSIENT
    
    job_id = "job_timeout"
    record_job_status(
        job_id=job_id,
        company="StartupX",
        title="AI Engineer",
        status=STATUS_ERROR_TRANSIENT,
        reasoning="Connection timeout"
    )
    
    # Because it is a transient error, it must remain eligible for retry
    assert not is_job_processed(job_id, company="StartupX", title="AI Engineer")

@patch('app.core.database.DB_PATH', TEST_DB)
def test_get_today_evaluated_count():
    from app.core.database import record_job_status, get_today_evaluated_count, STATUS_EVALUATED, STATUS_FILTERED_LANG
    
    assert get_today_evaluated_count() == 0
    
    # Record one evaluated job
    record_job_status(job_id="job_1", status=STATUS_EVALUATED)
    assert get_today_evaluated_count() == 1
    
    # Record a filtered job (should not count as EVALUATED)
    record_job_status(job_id="job_2", status=STATUS_FILTERED_LANG)
    assert get_today_evaluated_count() == 1
    
    # Record another evaluated job
    record_job_status(job_id="job_3", status=STATUS_EVALUATED)
    assert get_today_evaluated_count() == 2