import pytest
from app.main import run_job_matching_pipeline

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.main import run_job_matching_pipeline
from app.models.schemas import JobPosting, MatchResult
from app.core.database import (
    init_db,
    get_location_daily_stats,
    mark_location_daily_exhausted,
    record_location_daily_scrape,
    get_today_date_str
)

@pytest.mark.integration
async def test_pipeline_live_smoke():
    await run_job_matching_pipeline()

@pytest.mark.asyncio
async def test_pipeline_multi_location_and_limit_switching(tmp_path):
    test_db = str(tmp_path / "test_pipeline.db")
    
    # Fake candidate profile
    fake_profile_json = '''{
        "name": "Test Candidate",
        "academic_level": "BSc",
        "skills": ["Python", "Machine Learning"],
        "languages": ["English", "Spanish"],
        "projects": [],
        "experience_summary": "Test experience",
        "target_job_titles": ["AI Engineer"]
    }'''

    sample_job = JobPosting(
        id="job_nl_1",
        title="AI Engineer",
        company="TechCo",
        description="Great AI job in Netherlands",
        url="https://example.com/job1",
        location="Netherlands"
    )

    fake_eval_result = MatchResult(
        chain_of_thought="Good match",
        score=85,
        reasoning="Good fit",
        missing_skills=[],
        upskill_action="None",
        auto_reject=False,
        is_skills_evaluated=True
    )

    # Track locations called
    fetched_locations = []

    def fake_fetch_daily_jobs(target_job_titles, location, job_type, results_wanted, offset):
        fetched_locations.append((location, offset))
        if location == "Netherlands":
            if offset == 0:
                return [sample_job]
            # Offset reached or returns empty
            return []
        elif location == "Spain":
            if offset == 0:
                return [
                    JobPosting(
                        id="job_es_1",
                        title="AI Engineer",
                        company="MadridAI",
                        description="AI role in Spain",
                        url="https://example.com/job2",
                        location="Spain"
                    )
                ]
            return []
        return []

    with patch('app.core.database.DB_PATH', test_db), \
         patch('app.main.settings.LOCATIONS', ["Netherlands", "Spain"]), \
         patch('app.main.settings.MAX_RESULTS_PER_LOCATION', 25), \
         patch('app.main.check_network_connectivity', AsyncMock(return_value=True)), \
         patch('app.main.os.path.exists', return_value=True), \
         patch('builtins.open', MagicMock(return_value=MagicMock(__enter__=lambda s: MagicMock(read=lambda: fake_profile_json)))), \
         patch('app.main.fetch_daily_jobs', side_effect=fake_fetch_daily_jobs), \
         patch('app.main.evaluate_job', AsyncMock(return_value=fake_eval_result)), \
         patch('app.main.send_discord_alert', AsyncMock()), \
         patch('asyncio.sleep', AsyncMock()):
        
        init_db()
        await run_job_matching_pipeline()

        # Both locations should have been queried
        loc_names = [loc for loc, _ in fetched_locations]
        assert "Netherlands" in loc_names
        assert "Spain" in loc_names

        # Daily stats should be tracked for both
        today = get_today_date_str()
        nl_stats = get_location_daily_stats("Netherlands", date_str=today)
        es_stats = get_location_daily_stats("Spain", date_str=today)
        assert nl_stats["results_fetched"] == 1
        assert es_stats["results_fetched"] == 1
        assert nl_stats["is_exhausted"] is True
        assert es_stats["is_exhausted"] is True

@pytest.mark.asyncio
async def test_pipeline_skips_exhausted_location_and_resumes(tmp_path):
    test_db = str(tmp_path / "test_pipeline_resume.db")
    fake_profile_json = '''{
        "name": "Test Candidate",
        "academic_level": "BSc",
        "skills": ["Python"],
        "languages": ["English"],
        "projects": [],
        "experience_summary": "Test experience",
        "target_job_titles": ["AI Engineer"]
    }'''

    fetched_locations = []

    def fake_fetch_daily_jobs(target_job_titles, location, job_type, results_wanted, offset):
        fetched_locations.append((location, offset))
        return []

    with patch('app.core.database.DB_PATH', test_db), \
         patch('app.main.settings.LOCATIONS', ["Netherlands", "Amsterdam"]), \
         patch('app.main.check_network_connectivity', AsyncMock(return_value=True)), \
         patch('app.main.os.path.exists', return_value=True), \
         patch('builtins.open', MagicMock(return_value=MagicMock(__enter__=lambda s: MagicMock(read=lambda: fake_profile_json)))), \
         patch('app.main.fetch_daily_jobs', side_effect=fake_fetch_daily_jobs), \
         patch('asyncio.sleep', AsyncMock()):
        
        init_db()
        today = get_today_date_str()
        
        # Pre-mark Netherlands as exhausted
        mark_location_daily_exhausted("Netherlands", date_str=today)
        # Pre-record Amsterdam at offset 50
        record_location_daily_scrape("Amsterdam", results_fetched=50, offset=50, is_exhausted=False, date_str=today)

        await run_job_matching_pipeline()

        # Netherlands was already exhausted today, so it must be SKIPPED
        assert not any(loc == "Netherlands" for loc, _ in fetched_locations)
        # Amsterdam should resume at offset 50
        assert any(loc == "Amsterdam" and offset == 50 for loc, offset in fetched_locations)

@pytest.mark.asyncio
async def test_pipeline_1000_limit_transitions_to_next_location(tmp_path):
    """
    Verifies that when a location reaches the 1000 limit, the pipeline
    stops fetching for that location without wasted retries and seamlessly
    transitions to the next location in the list.
    """
    test_db = str(tmp_path / "test_1000_limit.db")
    fake_profile_json = '''{
        "name": "Test Candidate",
        "academic_level": "BSc",
        "skills": ["Python"],
        "languages": ["English"],
        "projects": [],
        "experience_summary": "Test experience",
        "target_job_titles": ["AI Engineer"]
    }'''

    call_history = []

    def fake_fetch_daily_jobs(target_job_titles, location, job_type, results_wanted, offset):
        call_history.append((location, offset))
        if location == "Netherlands":
            # Simulate Netherlands being at offset 975 (last batch before 1000)
            if offset == 975:
                return [
                    JobPosting(
                        id=f"job_nl_{i}",
                        title="AI Engineer",
                        company=f"CompanyNL_{i}",
                        description="AI job",
                        url=f"http://example.com/nl/{i}",
                        location="Netherlands"
                    )
                    for i in range(25)
                ]
            return []
        elif location == "Amsterdam":
            if offset == 0:
                return [
                    JobPosting(
                        id="job_ams_1",
                        title="AI Engineer",
                        company="CompanyAMS",
                        description="AI job in Amsterdam",
                        url="http://example.com/ams/1",
                        location="Amsterdam"
                    )
                ]
            return []
        return []

    fake_eval_result = MatchResult(
        chain_of_thought="Good match",
        score=85,
        reasoning="Good fit",
        missing_skills=[],
        upskill_action="None",
        auto_reject=False,
        is_skills_evaluated=True
    )

    with patch('app.core.database.DB_PATH', test_db), \
         patch('app.main.settings.LOCATIONS', ["Netherlands", "Amsterdam"]), \
         patch('app.main.settings.MAX_RESULTS_PER_LOCATION', 1000), \
         patch('app.main.check_network_connectivity', AsyncMock(return_value=True)), \
         patch('app.main.os.path.exists', return_value=True), \
         patch('builtins.open', MagicMock(return_value=MagicMock(__enter__=lambda s: MagicMock(read=lambda: fake_profile_json)))), \
         patch('app.main.fetch_daily_jobs', side_effect=fake_fetch_daily_jobs), \
         patch('app.main.evaluate_job', AsyncMock(return_value=fake_eval_result)), \
         patch('app.main.send_discord_alert', AsyncMock()), \
         patch('asyncio.sleep', AsyncMock()):

        init_db()
        today = get_today_date_str()

        # Simulate Netherlands already fetched 975 jobs earlier
        record_location_daily_scrape("Netherlands", results_fetched=975, offset=975, is_exhausted=False, date_str=today)

        await run_job_matching_pipeline()

        # Verify Netherlands fetched the final batch at 975
        assert ("Netherlands", 975) in call_history
        # Verify Netherlands was NEVER queried at offset 1000 (no wasted retries at hard limit)
        assert ("Netherlands", 1000) not in call_history

        # Verify Amsterdam was subsequently queried starting at offset 0
        assert ("Amsterdam", 0) in call_history

        # Check DB states
        nl_stats = get_location_daily_stats("Netherlands", date_str=today)
        ams_stats = get_location_daily_stats("Amsterdam", date_str=today)

        assert nl_stats["results_fetched"] == 1000
        assert nl_stats["last_offset"] == 1000
        assert nl_stats["is_exhausted"] is True

        assert ams_stats["results_fetched"] == 1
        assert ams_stats["is_exhausted"] is True

if __name__ == "__main__":
    import asyncio
    print("Running the exact matching pipeline...")
    asyncio.run(run_job_matching_pipeline())
