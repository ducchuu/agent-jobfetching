import pytest
from unittest.mock import patch
from app.services.notifier import send_discord_alert
from app.models.schemas import JobPosting, MatchResult

# Create mock data
mock_job = JobPosting(
    id="test_1",
    title="AI Engineer",
    company="Tech Corp",
    description="Python, Docker, LLMOps required.",
    url="http://example.com"
)

mock_match = MatchResult(
    chain_of_thought="Excellent tech match",
    score=95,
    reasoning="Excellent fit.",
    missing_skills=[],
    upskill_action="None",
    auto_reject=False
)

@pytest.mark.asyncio
@patch('app.services.notifier.httpx.AsyncClient.post')
async def test_send_discord_alert(mock_post):
    # Setup mock to do nothing successfully
    mock_post.return_value.status_code = 200
    
    await send_discord_alert(mock_job, mock_match)
    
    # Assert httpx client was called
    mock_post.assert_called_once()
    
    # Assert payload contains the score
    call_args = mock_post.call_args
    assert "json" in call_args.kwargs
    payload = call_args.kwargs["json"]
    assert "Job Fetching Agent" in payload["username"]
    assert "95/100" in payload["embeds"][0]["title"]
