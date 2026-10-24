import pytest
from app.main import run_job_matching_pipeline

@pytest.mark.integration
async def test_pipeline_live_smoke():
    await run_job_matching_pipeline()

if __name__ == "__main__":
    import asyncio
    print("Running the exact matching pipeline...")
    asyncio.run(run_job_matching_pipeline())
