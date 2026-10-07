import pytest
from unittest.mock import patch
from app.agent.experience_agent import evaluate_experience
from app.models.schemas import JobPosting

class MockChoice:
    def __init__(self, content):
        self.message = type('MockMessage', (), {'content': content})()

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]

@pytest.mark.asyncio
async def test_experience_agent_regex_fast_reject():
    senior_job = JobPosting(
        id="test_sr",
        title="Senior AI Engineer",
        company="Tech Corp",
        description="Requires 10 years of experience.",
        url=""
    )
    
    # should be rejected by regex without LLM
    result = await evaluate_experience(senior_job, target_yoe=0)
    assert result.is_rejected is True
    assert "senior or leadership role" in result.reason

@pytest.mark.asyncio
@patch('app.agent.experience_agent.router.acompletion')
async def test_experience_agent_llm_reject(mock_acompletion):
    # mock LLM to reject based on Years of Experience (YoE)gap
    mock_acompletion.return_value = MockResponse('{"is_rejected": true, "reason": "Requires 5+ years"}')
    
    mid_job = JobPosting(
        id="test_mid",
        title="AI Engineer",
        company="Tech Corp",
        description="Must have 5+ years of experience in AI.",
        url=""
    )
    
    result = await evaluate_experience(mid_job, target_yoe=0)
    assert result.is_rejected is True
    mock_acompletion.assert_called_once()
