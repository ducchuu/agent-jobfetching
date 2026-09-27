import asyncio
from app.main import run_job_matching_pipeline

if __name__ == "__main__":
    print("Running the exact matching pipeline...")
    asyncio.run(run_job_matching_pipeline())
