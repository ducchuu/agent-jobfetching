import asyncio
from app.agent.skills_agent import evaluate_skills
from app.models.schemas import CandidateProfile, JobPosting, Project

async def test_skills():
    profile = CandidateProfile(
        name="Test",
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
    print("Testing evaluate_skills...")
    try:
        res = await evaluate_skills(profile, job)
        print("Result:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_skills())
