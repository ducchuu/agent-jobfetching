import pytest
from unittest.mock import patch, AsyncMock
from app.agent.matcher import evaluate_job
from app.models.schemas import JobPosting, MatchResult, CandidateProfile, Project, LanguageFilterResult, ExperienceFilterResult

mock_cv = CandidateProfile(
    name="Test User",
    skills=["Python", "Docker"],
    languages=["English"],
    projects=[Project(name="Test", technologies=["Python"], description="Built a testing tool")],
    experience_summary="Worked on some testing stuff",
    target_job_titles=["Test Engineer"]
)

mock_job = JobPosting(
    id="test_1",
    title="AI Engineer",
    company="Tech Corp",
    description="Python, Docker, LLMOps required.",
    url="http://example.com"
)

@pytest.mark.asyncio
@patch('app.agent.matcher.evaluate_language')
@patch('app.agent.matcher.evaluate_experience')
@patch('app.agent.matcher.evaluate_skills')
async def test_evaluate_job_success(mock_skills, mock_exp, mock_lang):
    # mock for passing the filters
    mock_lang.return_value = LanguageFilterResult(is_rejected=False, reason="")
    mock_exp.return_value = ExperienceFilterResult(is_rejected=False, reason="")
    
    mock_skills.return_value = MatchResult(
        chain_of_thought="Good match",
        score=85,
        reasoning="Fits profile",
        missing_skills=[],
        upskill_action="None",
        auto_reject=False
    )
    
    result = await evaluate_job(mock_cv, mock_job)
    
    # verify sequence
    mock_lang.assert_called_once()
    mock_exp.assert_called_once()
    mock_skills.assert_called_once()
    
    assert result.score == 85
    assert not result.auto_reject

@pytest.mark.asyncio
@patch('app.agent.matcher.evaluate_language')
@patch('app.agent.matcher.evaluate_experience')
@patch('app.agent.matcher.evaluate_skills')
async def test_evaluate_job_fails_language(mock_skills, mock_exp, mock_lang):
    # mock to fail language
    mock_lang.return_value = LanguageFilterResult(is_rejected=True, reason="Requires Dutch")
    
    result = await evaluate_job(mock_cv, mock_job)
    
    mock_lang.assert_called_once()
    mock_exp.assert_not_called()
    mock_skills.assert_not_called()
    
    assert result.auto_reject is True
    assert result.score == 0

@pytest.mark.asyncio
@patch('app.agent.matcher.evaluate_language')
@patch('app.agent.matcher.evaluate_experience')
@patch('app.agent.matcher.evaluate_skills')
async def test_evaluate_job_fails_experience(mock_skills, mock_exp, mock_lang):
    mock_lang.return_value = LanguageFilterResult(is_rejected=False, reason="")
    mock_exp.return_value = ExperienceFilterResult(is_rejected=True, reason="Requires 10 years experience")
    
    result = await evaluate_job(mock_cv, mock_job)
    
    mock_lang.assert_called_once()
    mock_exp.assert_called_once()
    mock_skills.assert_not_called()
    
    assert result.auto_reject is True
    assert result.score == 0