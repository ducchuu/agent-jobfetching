import pytest
from unittest.mock import patch
from app.agent.skills_agent import evaluate_skills
from app.models.schemas import JobPosting, CandidateProfile, Project

mock_cv = CandidateProfile(
    name="Test User",
    skills=["Python", "Docker"],
    languages=["English"],
    projects=[Project(name="Test", technologies=["Python"], description="Built a testing tool")],
    experience_summary="Worked on some testing stuff",
    target_job_titles=["Test Engineer"]
)

class MockChoice:
    def __init__(self, content):
        self.message = type('MockMessage', (), {'content': content})()

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]

@pytest.mark.asyncio
@patch('app.agent.skills_agent.acompletion')
async def test_skills_agent_parsing(mock_acompletion):
    # setup for LLM to return valid JSON
    valid_json_response = '{"chain_of_thought": "Good match.", "score": 90, "reasoning": "Fits well.", "missing_skills": [], "upskill_action": "None", "recommend_archiving": false}'
    mock_acompletion.return_value = MockResponse(valid_json_response)
    
    job = JobPosting(
        id="test_job",
        title="AI Engineer",
        company="Tech Corp",
        description="Python, Docker.",
        url=""
    )
    
    result = await evaluate_skills(mock_cv, job)
    
    assert result.score == 90
    assert result.auto_reject is False
    assert result.reasoning == "Fits well."
    mock_acompletion.assert_called_once()

@pytest.mark.asyncio
@patch('app.agent.skills_agent.acompletion')
async def test_skills_agent_fallback_on_error(mock_acompletion):
    # setup for LLM to raise an exception
    mock_acompletion.side_effect = Exception("API Error")
    
    job = JobPosting(
        id="test_job",
        title="AI Engineer",
        company="Tech Corp",
        description="Python, Docker.",
        url=""
    )
    
    # should safely catch error and return 0 score rejection
    result = await evaluate_skills(mock_cv, job)
    
    assert result.score == 0
    assert result.auto_reject is True
    assert "Parse failure" in result.reasoning
