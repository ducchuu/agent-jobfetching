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

@patch('app.services.scraper.scrape_jobs')
def test_fetch_daily_jobs_safe_boilerplate_slicing(mock_scrape_jobs):
    long_desc = (
        "About the Company: We are an innovative AI robotics lab in Delft.\n"
        "Requirements:\n" + ("Python, PyTorch, ROS2, Linux. " * 30) + "\n"
        "What we offer:\nFree lunch, ping pong table, healthcare benefits."
    )
    df = pd.DataFrame({
        'id': ['safe_1'],
        'title': ['Robotics Engineer'],
        'company': ['RoboTech'],
        'description': [long_desc],
        'job_url': ['https://example.com/job']
    })
    mock_scrape_jobs.return_value = df
    
    jobs = fetch_daily_jobs(target_job_titles=["Robotics Engineer"])
    assert len(jobs) == 1
    # Check that "About the Company" at start was NOT sliced
    assert "About the Company" in jobs[0].description
    assert "Requirements:" in jobs[0].description
    # Check that trailing boilerplate was sliced from description but retained in raw_description
    assert "Free lunch" not in jobs[0].description
    assert "Free lunch" in jobs[0].raw_description

@patch('app.services.scraper.scrape_jobs')
def test_fetch_daily_jobs_boilerplate_before_55_percent_not_sliced(mock_scrape_jobs):
    # If "Why join us" or "What we offer" appears in the first half of the JD, it should NOT be trimmed
    early_boilerplate_desc = (
        "Why join us: We are leading AI innovation.\n"
        "Requirements:\n" + ("Extensive distributed systems and Python experience. " * 30)
    )
    df = pd.DataFrame({
        'id': ['safe_early'],
        'title': ['Staff AI Engineer'],
        'company': ['RoboTech'],
        'description': [early_boilerplate_desc],
        'job_url': ['https://example.com/job']
    })
    mock_scrape_jobs.return_value = df
    
    jobs = fetch_daily_jobs(target_job_titles=["Staff AI Engineer"])
    assert len(jobs) == 1
    # The early heading and downstream requirements must be preserved
    assert "Why join us" in jobs[0].description
    assert "Extensive distributed systems" in jobs[0].description

@patch('app.services.scraper.scrape_jobs')
def test_fetch_daily_jobs_fingerprint_deduplication(mock_scrape_jobs):
    # Two listings with different casing/punctuation that Pandas drop_duplicates would miss
    df = pd.DataFrame({
        'id': ['job_1', 'job_2'],
        'title': ['AI Engineer - NLP', 'ai engineer nlp'],
        'company': ['TechCorp Inc.', 'techcorp inc'],
        'description': ['Description 1', 'Description 2'],
        'job_url': ['https://example.com/1', 'https://example.com/2']
    })
    mock_scrape_jobs.return_value = df
    
    jobs = fetch_daily_jobs(target_job_titles=["AI Engineer"])
    # Fingerprint deduplication at scrape time should keep only 1 posting
    assert len(jobs) == 1
    assert jobs[0].raw_description == "Description 1"

def test_resolve_country_indeed():
    from app.services.scraper import resolve_country_indeed
    assert resolve_country_indeed("Netherlands") == "Netherlands"
    assert resolve_country_indeed("Amsterdam") == "Netherlands"
    assert resolve_country_indeed("Utrecht") == "Netherlands"
    assert resolve_country_indeed("Rotterdam") == "Netherlands"
    assert resolve_country_indeed("Delft") == "Netherlands"
    assert resolve_country_indeed("Leiden") == "Netherlands"
    assert resolve_country_indeed("CustomLand") == "CustomLand"

@patch('app.services.scraper.scrape_jobs')
def test_fetch_daily_jobs_passes_correct_country_indeed(mock_scrape_jobs):
    mock_scrape_jobs.return_value = mock_df
    
    fetch_daily_jobs(target_job_titles=["AI Engineer"], location="Rotterdam")
    _, kwargs = mock_scrape_jobs.call_args
    assert kwargs.get("country_indeed") == "Netherlands"
    assert kwargs.get("location") == "Rotterdam"

    fetch_daily_jobs(target_job_titles=["AI Engineer"], location="Amsterdam")
    _, kwargs = mock_scrape_jobs.call_args
    assert kwargs.get("country_indeed") == "Netherlands"
    assert kwargs.get("location") == "Amsterdam"
