import pytest
from unittest.mock import patch
from app.agent.matcher import evaluate_job
from app.models.schemas import JobPosting, MatchResult, CandidateProfile, Project

# Create mock data
mock_job = JobPosting(
    id="test_1",
    title="AI Engineer",
    company="Tech Corp",
    description="Python, Docker, LLMOps required.",
    url="http://example.com"
)

mock_cv = CandidateProfile(
    name="Test User",
    skills=["Python", "Docker"],
    languages=["English"],
    projects=[Project(name="Test", technologies=["Python"], description="Built a testing tool")],
    experience_summary="Worked on some testing stuff",
    target_job_titles=["Test Engineer", "QA Automation Engineer", "Software Developer in Test"]
)

# Mock the LiteLLM response structure
class MockMessage:
    content = '{"chain_of_thought": "Candidate knows Python, Docker. Missing LLMOps.", "score": 85, "reasoning": "Good fit.", "missing_skills": ["LLMOps"], "upskill_action": "Learn Langfuse", "auto_reject": false}'

class MockChoice:
    message = MockMessage()

class MockResponse:
    choices = [MockChoice()]

@pytest.mark.asyncio
@patch('app.agent.matcher.router.acompletion')
async def test_evaluate_job_language_match(mock_acompletion):
    # Setup mock to return a valid match for English job
    mock_acompletion.return_value = MockResponse()
    
    english_job = JobPosting(
        id="test_eng",
        title="AI Engineer",
        company="Tech Corp",
        description="Requires fluent English. Python, Docker, LLMOps.",
        url="http://example.com"
    )
    
    result = await evaluate_job(mock_cv, english_job)
    
    assert isinstance(result, MatchResult)
    assert result.auto_reject is False
    assert result.score == 85
    mock_acompletion.assert_called_once()


class MockRejectMessage:
    content = '{"chain_of_thought": "Job is in Dutch. Candidate only speaks English.", "score": 0, "reasoning": "Job requires Dutch, candidate only speaks English.", "missing_skills": ["Dutch"], "upskill_action": "None", "auto_reject": true}'

class MockRejectChoice:
    message = MockRejectMessage()

class MockRejectResponse:
    choices = [MockRejectChoice()]

@pytest.mark.asyncio
@patch('app.agent.matcher.router.acompletion')
async def test_evaluate_job_language_reject(mock_acompletion):
    # Setup mock to return a rejection for Dutch job
    mock_acompletion.return_value = MockRejectResponse()
    
    dutch_job = JobPosting(
        id="test_dutch",
        title="AI Engineer",
        company="Tech Corp",
        description="Vloeiend Nederlands vereist. Python, Docker ervaring.",
        url="http://example.com"
    )
    
    result = await evaluate_job(mock_cv, dutch_job)
    
    assert isinstance(result, MatchResult)
    assert result.auto_reject is True
    assert result.score == 0
    mock_acompletion.assert_called_once()