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
    
    # check whetherduplicate insertion doesn't crash (SQLite INSERT OR IGNORE)
    mark_job_processed(job_id)