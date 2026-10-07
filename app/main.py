from fastapi import FastAPI, BackgroundTasks, UploadFile, File
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import init_db, is_job_processed, mark_job_processed
from app.services.scraper import fetch_daily_jobs
from app.services.cv_parser import extract_profile_from_pdf, CACHE_PATH
from app.agent.matcher import evaluate_job
from app.services.notifier import send_discord_alert
from app.config import settings
from app.models.schemas import CandidateProfile
import logging
import os
import asyncio
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def run_job_matching_pipeline():
    logger.info("Starting job matching pipeline...")
    if not os.path.exists(CACHE_PATH):
        logger.warning("No CV profile cached. Please upload a CV first via /upload-cv.")
        return
        
    with open(CACHE_PATH, "r") as f:
        candidate_profile = CandidateProfile.model_validate_json(f.read())

    inferred_titles = candidate_profile.target_job_titles if candidate_profile.target_job_titles else ["AI Engineer", "Data Engineer"]

    # You can define multiple locations you want to fetch jobs from, but they have to match jobspy API
    locations = ["Netherlands"]
    
    jobs = []
    for loc in locations:
        jobs.extend(fetch_daily_jobs(
            target_job_titles=inferred_titles,
            location=loc,
            job_type="fulltime"
        ))
        
    logger.info(f"Scraper finished. Found {len(jobs)} total jobs to process.")
    
    sem = asyncio.Semaphore(5)

    async def process_job(job):
        if is_job_processed(job.id):
            logger.info(f"Skipping already processed job: {job.id}")
            return
            
        async with sem:
            logger.info(f"Evaluating job: {job.title} at {job.company}")
            try:
                match_result = await evaluate_job(candidate_profile, job, target_yoe=0)
                
                if getattr(match_result, 'auto_reject', False):
                    logger.info(f"Auto-rejected senior/heavy YoE role: {job.title}")
                    mark_job_processed(job.id)
                    return
                    
                if match_result.score >= settings.MATCH_THRESHOLD:
                    logger.info(f"Match found! Score: {match_result.score}. Sending Discord alert...")
                    await send_discord_alert(job, match_result)
                mark_job_processed(job.id)
            except Exception as e:
                logger.error(f"Error evaluating job {job.id}: {e}")

    await asyncio.gather(*(process_job(job) for job in jobs))

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Scrape and evaluate jobs every morning at 7:00 AM
    scheduler.add_job(run_job_matching_pipeline, 'cron', hour=7, minute=0)
    scheduler.start()
    logger.info("Scheduler started. Pipeline will run daily at 07:00 AM.")
    yield
    scheduler.shutdown()

app = FastAPI(title="Job Postings Fetching Agent", lifespan=lifespan)

@app.post("/upload-cv")
async def upload_cv(file: UploadFile = File(...)):
    os.makedirs("data", exist_ok=True)
    pdf_path = f"data/{file.filename}"
    with open(pdf_path, "wb") as f:
        f.write(await file.read())
        
    profile = await extract_profile_from_pdf(pdf_path)
    return {"message": "CV processed and cached successfully.", "profile": profile.model_dump()}

@app.post("/trigger-pipeline")
async def trigger_pipeline(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_job_matching_pipeline)
    return {"message": "Pipeline triggered in the background."}

@app.get("/profile")
async def get_profile():
    if not os.path.exists(CACHE_PATH):
        return {"status": "error", "message": "No profile found on the server."}
    with open(CACHE_PATH, "r") as f:
        candidate_profile = CandidateProfile.model_validate_json(f.read())
    return {"status": "ok", "profile": candidate_profile.model_dump()}

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Job Fetching Agent is running."}
