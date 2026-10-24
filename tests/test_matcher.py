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
    academic_level="BSc",
    target_job_titles=["Test Engineer"]
)

mock_job = JobPosting(
    id="test_1",
    title="AI Engineer",
    company="Tech Corp",
    description="Python, Docker, LLMOps required.",
    url="http://example.com"
)

class MockChoice:
    def __init__(self, content):
        self.message = type('MockMessage', (), {'content': content})()

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]

@pytest.mark.asyncio
@patch('app.agent.matcher.router.acompletion')
@patch('app.agent.matcher.evaluate_language')
@patch('app.agent.matcher.evaluate_experience')
@patch('app.agent.matcher.evaluate_skills')
async def test_evaluate_job_success(mock_skills, mock_exp, mock_lang, mock_router):
    mock_lang.return_value = LanguageFilterResult(is_rejected=False, reason="")
    mock_exp.return_value = ExperienceFilterResult(is_rejected=False, reason="")
    mock_router.return_value = MockResponse('{"audit_passed": true, "critical_flaw_found": false, "reason": "", "penalty_points": 0}')
    
    mock_skills.return_value = MatchResult(
        chain_of_thought="Good match",
        score=85,
        reasoning="Fits profile",
        missing_skills=[],
        upskill_action="None",
        auto_reject=False,
        is_skills_evaluated=True
    )
    
    result = await evaluate_job(mock_cv, mock_job)
    
    mock_lang.assert_called_once()
    mock_exp.assert_called_once()
    mock_skills.assert_called_once()
    mock_router.assert_called_once()
    
    assert result.score == 85
    assert not result.auto_reject

@pytest.mark.asyncio
@patch('app.agent.matcher.evaluate_language')
@patch('app.agent.matcher.evaluate_experience')
@patch('app.agent.matcher.evaluate_skills')
async def test_evaluate_job_fails_language(mock_skills, mock_exp, mock_lang):
    mock_lang.return_value = LanguageFilterResult(is_rejected=True, reason="Requires Dutch")
    mock_exp.return_value = ExperienceFilterResult(is_rejected=False, reason="")
    
    result = await evaluate_job(mock_cv, mock_job)
    
    mock_lang.assert_called_once()
    mock_exp.assert_called_once()
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

@pytest.mark.asyncio
@patch('app.agent.matcher.router.acompletion')
@patch('app.agent.matcher.evaluate_language')
@patch('app.agent.matcher.evaluate_experience')
@patch('app.agent.matcher.evaluate_skills')
async def test_evaluate_job_devils_advocate_penalty(mock_skills, mock_exp, mock_lang, mock_router):
    mock_lang.return_value = LanguageFilterResult(is_rejected=False, reason="")
    mock_exp.return_value = ExperienceFilterResult(is_rejected=False, reason="")
    mock_router.return_value = MockResponse('{"audit_passed": false, "critical_flaw_found": true, "reason": "Requires secret clearance", "penalty_points": 10}')
    
    mock_skills.return_value = MatchResult(
        chain_of_thought="Initial high score",
        score=90,
        reasoning="Good match",
        missing_skills=[],
        upskill_action="None",
        auto_reject=False,
        is_skills_evaluated=True
    )
    
    result = await evaluate_job(mock_cv, mock_job)
    
    assert result.score == 80  # 90 - 10
    assert "Auditor -10pts" in result.reasoning

@pytest.mark.asyncio
@patch('app.agent.matcher.router.acompletion')
@patch('app.agent.matcher.evaluate_language')
@patch('app.agent.matcher.evaluate_experience')
@patch('app.agent.matcher.evaluate_skills')
async def test_evaluate_job_devils_advocate_hard_dealbreaker(mock_skills, mock_exp, mock_lang, mock_router):
    mock_lang.return_value = LanguageFilterResult(is_rejected=False, reason="")
    mock_exp.return_value = ExperienceFilterResult(is_rejected=False, reason="")
    mock_router.return_value = MockResponse('{"audit_passed": false, "hard_dealbreaker": true, "critical_flaw_found": false, "reason": "Requires active Top Secret clearance", "penalty_points": 0}')
    
    mock_skills.return_value = MatchResult(
        chain_of_thought="Initial high score",
        score=95,
        reasoning="Good match",
        missing_skills=[],
        upskill_action="None",
        auto_reject=False,
        is_skills_evaluated=True
    )
    
    result = await evaluate_job(mock_cv, mock_job)
    
    assert result.score == 0
    assert result.auto_reject is True
    assert "Auditor REJECT" in result.reasoning