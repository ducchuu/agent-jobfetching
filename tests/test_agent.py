import pytest
from app.agent.skills_agent import evaluate_skills
from app.models.schemas import CandidateProfile, JobPosting, Project

@pytest.mark.integration
async def test_skills_live_integration():
    profile = CandidateProfile(
        name="Test",
        academic_level="BSc",
        skills=["Python"],
        languages=["English"],
        projects=[Project(name="Test", technologies=["Python"], description="Test")],
        experience_summary="Test",
        target_job_titles=["Software Engineer"]
    )
    job = JobPosting(
        id="123",
        title="Software Engineer",
        company="TestCo",
        description="We need a Python developer.",
        url="test.com"
    )
    res = await evaluate_skills(profile, job)
    assert res.is_skills_evaluated is True
    assert 0 <= res.score <= 100
    assert res.rubric is not None
