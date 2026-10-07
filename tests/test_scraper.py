import pytest
from unittest.mock import patch
import pandas as pd
from app.services.scraper import fetch_daily_jobs
from app.models.schemas import JobPosting

# Mock dataframe matching the jobspy API
mock_df = pd.DataFrame({
    'id': ['12345'],
    'title': ['Junior AI Engineer'],
    'company': ['Tech Corp'],
    'description': ['A great junior role in AI!'],
    'job_url': ['https://example.com/job']
})

@patch('app.services.scraper.scrape_jobs')
def test_fetch_daily_jobs(mock_scrape_jobs):
    # Set the mock to return and match our test dataframe
    mock_scrape_jobs.return_value = mock_df
    
    target_titles = ["Junior AI Engineer"]
    jobs = fetch_daily_jobs(target_job_titles=target_titles, location="Amsterdam")
    
    mock_scrape_jobs.assert_called_once()
    assert len(jobs) == 1
    assert isinstance(jobs[0], JobPosting)
    assert jobs[0].title == "Junior AI Engineer"
    assert jobs[0].company == "Tech Corp"

@patch('app.services.scraper.scrape_jobs')
def test_fetch_daily_jobs_skips_empty_description(mock_scrape_jobs):
    empty_desc_df = pd.DataFrame({
        'id': ['12345'],
        'title': ['Junior AI Engineer'],
        'company': ['Tech Corp'],
        'description': [None],
        'job_url': ['https://example.com/job']
    })
    
    mock_scrape_jobs.return_value = empty_desc_df
    
    jobs = fetch_daily_jobs(target_job_titles=["AI Engineer"])
    
    # should skip the job because it has no description
    assert len(jobs) == 0
