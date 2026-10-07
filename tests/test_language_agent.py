import pytest
from unittest.mock import patch
from app.agent.language_agent import evaluate_language
from app.models.schemas import JobPosting, CandidateProfile, LanguageFilterResult

mock_cv = CandidateProfile(
    name="Test User",
    skills=["Python", "Docker"],
    languages=["English"],
    projects=[],
    experience_summary="",
    target_job_titles=[]
)

class MockChoice:
    def __init__(self, content):
        self.message = type('MockMessage', (), {'content': content})()

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]

@pytest.mark.asyncio
async def test_language_agent_langdetect_fast_reject():
    dutch_job = JobPosting(
        id="test_dutch",
        title="AI Engineer",
        company="Tech Corp",
        description="Dit is een vacature in het Nederlands. Wij zoeken een programmeur.",
        url=""
    )
    
    # langdetect should catch this without LLM
    result = await evaluate_language(mock_cv, dutch_job)
    assert result.is_rejected is True
    assert "Dutch" in result.reason

@pytest.mark.asyncio
@patch('app.agent.language_agent.router.acompletion')
async def test_language_agent_llm_reject(mock_acompletion):
    # mock LLM to reject based on explicit requirements
    mock_acompletion.return_value = MockResponse('{"is_rejected": true, "reason": "Requires German"}')
    
    german_req_job = JobPosting(
        id="test_de",
        title="AI Engineer",
        company="Tech Corp",
        description="This job is written in English but fluent German is strictly required.",
        url=""
    )
    
    result = await evaluate_language(mock_cv, german_req_job)
    assert result.is_rejected is True
    mock_acompletion.assert_called_once()
