import pytest
from unittest.mock import patch
from app.agent.skills_agent import evaluate_skills
from app.agent.llm_router import EvaluationTransientError
from app.models.schemas import JobPosting, CandidateProfile, Project, SkillsRubricOutput

mock_cv = CandidateProfile(
    name="Test User",
    skills=["Python", "Docker"],
    languages=["English"],
    projects=[Project(name="Test", technologies=["Python"], description="Built a testing tool")],
    experience_summary="Worked on some testing stuff",
    academic_level="BSc",
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
    valid_json_response = '''{
        "chain_of_thought": "Good match.",
        "matched_core_skills": ["Python", "Docker"],
        "missing_core_skills": [],
        "missing_secondary_skills": [],
        "project_relevance_bonus": 5,
        "hard_dealbreaker_found": false,
        "reasoning_summary": "Fits well.",
        "upskill_recommendation": "None"
    }'''
    mock_acompletion.return_value = MockResponse(valid_json_response)
    
    job = JobPosting(
        id="test_job",
        title="AI Engineer",
        company="Tech Corp",
        description="Python, Docker.",
        url=""
    )
    
    result = await evaluate_skills(mock_cv, job)
    
    # 85 base + 5 bonus = 90
    assert result.score == 90
    assert result.auto_reject is False
    assert result.reasoning == "Fits well."
    assert result.is_skills_evaluated is True
    mock_acompletion.assert_called_once()

@pytest.mark.asyncio
@patch('app.agent.skills_agent.acompletion')
async def test_skills_agent_raises_transient_error(mock_acompletion):
    mock_acompletion.side_effect = Exception("API Connection Timeout")
    
    job = JobPosting(
        id="test_job",
        title="AI Engineer",
        company="Tech Corp",
        description="Python, Docker.",
        url=""
    )
    
    with pytest.raises(EvaluationTransientError):
        await evaluate_skills(mock_cv, job)

def test_rubric_deterministic_math():
    # Test penalty calculation: 1 core (-10), 2 secondary (-6), +10 bonus -> 85 + 10 - 16 = 79
    rubric = SkillsRubricOutput(
        chain_of_thought="Analysis",
        matched_core_skills=["Python"],
        missing_core_skills=["Kubernetes"],
        missing_secondary_skills=["AWS", "Redis"],
        project_relevance_bonus=10,
        hard_dealbreaker_found=False,
        reasoning_summary="Partial fit",
        upskill_recommendation="Learn Kubernetes"
    )
    assert rubric.computed_score == 79

    # Test dealbreaker override
    dealbreaker_rubric = SkillsRubricOutput(
        chain_of_thought="Analysis",
        matched_core_skills=[],
        missing_core_skills=["React"],
        missing_secondary_skills=[],
        project_relevance_bonus=0,
        hard_dealbreaker_found=True,
        reasoning_summary="Wrong domain",
        upskill_recommendation="None"
    )
    assert dealbreaker_rubric.computed_score == 0
