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

@patch('app.core.database.DB_PATH', TEST_DB)
def test_location_scrape_tracking():
    from app.core.database import (
        get_location_daily_stats,
        record_location_daily_scrape,
        mark_location_daily_exhausted,
        get_all_daily_location_stats,
        reset_daily_location_stats
    )
    
    date_str = "2026-10-28"
    
    # Fresh location starts with 0
    stats = get_location_daily_stats("Amsterdam", date_str=date_str)
    assert stats["results_fetched"] == 0
    assert stats["last_offset"] == 0
    assert stats["is_exhausted"] is False
    
    # Record first batch of 25 jobs at offset 25
    record_location_daily_scrape("Amsterdam", results_fetched=25, offset=25, is_exhausted=False, date_str=date_str)
    stats = get_location_daily_stats("Amsterdam", date_str=date_str)
    assert stats["results_fetched"] == 25
    assert stats["last_offset"] == 25
    assert stats["is_exhausted"] is False
    
    # Record second batch
    record_location_daily_scrape("Amsterdam", results_fetched=50, offset=50, is_exhausted=False, date_str=date_str)
    stats = get_location_daily_stats("Amsterdam", date_str=date_str)
    assert stats["results_fetched"] == 50
    assert stats["last_offset"] == 50
    assert stats["is_exhausted"] is False
    
    # Mark exhausted
    mark_location_daily_exhausted("Amsterdam", date_str=date_str)
    stats = get_location_daily_stats("Amsterdam", date_str=date_str)
    assert stats["is_exhausted"] is True
    
    # Add another location
    record_location_daily_scrape("Utrecht", results_fetched=25, offset=25, is_exhausted=False, date_str=date_str)
    
    all_stats = get_all_daily_location_stats(date_str=date_str)
    assert "Amsterdam" in all_stats
    assert "Utrecht" in all_stats
    assert all_stats["Amsterdam"]["results_fetched"] == 50
    assert all_stats["Amsterdam"]["is_exhausted"] is True
    assert all_stats["Utrecht"]["results_fetched"] == 25
    assert all_stats["Utrecht"]["is_exhausted"] is False
    
    # Date isolation: next day should be fresh
    tomorrow_stats = get_location_daily_stats("Amsterdam", date_str="2026-10-29")
    assert tomorrow_stats["results_fetched"] == 0
    assert tomorrow_stats["last_offset"] == 0
    assert tomorrow_stats["is_exhausted"] is False
    
    # Reset
    reset_daily_location_stats(date_str=date_str)
    cleared_stats = get_all_daily_location_stats(date_str=date_str)
    assert len(cleared_stats) == 0

def test_clear_db_resilient(tmp_path):
    import clear_db
    test_db = str(tmp_path / "legacy_jobs.db")
    
    # Create legacy DB without location_scrape_tracking table
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE processed_jobs (id TEXT PRIMARY KEY);")
    cursor.execute("INSERT INTO processed_jobs (id) VALUES ('job_legacy_1');")
    conn.commit()
    conn.close()

    with patch('clear_db.DB_PATH', test_db):
        clear_db.main()

    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM processed_jobs;")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 0
