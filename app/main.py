from fastapi import FastAPI, BackgroundTasks, UploadFile, File
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo
from app.core.database import init_db, is_job_processed, mark_job_processed
from app.services.scraper import fetch_daily_jobs, NetworkError
from app.services.cv_parser import extract_profile_from_pdf, CACHE_PATH
from app.agent.matcher import evaluate_job
from app.services.notifier import send_discord_alert, send_discord_infra_alert
from app.config import settings
from app.models.schemas import CandidateProfile
import logging
import os
import asyncio
import socket
from contextlib import asynccontextmanager

from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AMSTERDAM_TZ = ZoneInfo("Europe/Amsterdam")
scheduler = AsyncIOScheduler(timezone=AMSTERDAM_TZ)
pipeline_lock = asyncio.Lock()

pipeline_status = {
    "state": "idle",
    "last_run_started": None,
    "last_run_finished": None,
    "skills_evaluated": 0,
    "target_skills": 25,
    "matches_found": 0,
    "last_status_message": "Pipeline initialized and ready."
}

async def check_network_connectivity(host: str = "8.8.8.8", port: int = 53, timeout: float = 5.0) -> bool:
    # True if a TCP connection to host:port succeeds
    loop = asyncio.get_event_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: socket.create_connection((host, port), timeout)),
            timeout=timeout + 1
        )
        return True
    except Exception:
        return False

async def run_job_matching_pipeline():
    if pipeline_lock.locked():
        logger.warning("Pipeline is already currently running. Skipping duplicate trigger.")
        return

    async with pipeline_lock:
        start_time = datetime.now(timezone.utc)
        pipeline_status["state"] = "running"
        pipeline_status["last_run_started"] = start_time.isoformat()
        pipeline_status["last_status_message"] = "Pipeline running..."
        logger.info("=" * 60)
        logger.info("Starting daily job matching pipeline...")
        logger.info("=" * 60)
        
        if not os.path.exists(CACHE_PATH):
            msg = "No CV profile cached. Please upload a CV first via /upload-cv."
            logger.warning(msg)
            pipeline_status["state"] = "idle"
            pipeline_status["last_status_message"] = msg
            return

        logger.info("Running pre-flight network connectivity check...")
        if not await check_network_connectivity():
            msg = "Pipeline aborted: network/DNS is unreachable (could not connect to 8.8.8.8:53)."
            logger.error(msg)
            pipeline_status["state"] = "idle"
            pipeline_status["last_status_message"] = msg
            await send_discord_infra_alert(
                "Network Down at Pipeline Start",
                f"The daily job pipeline could not start because DNS/network is unreachable.\n"
                f"Check the Docker container's network and re-trigger via `POST /trigger-pipeline` once connectivity is restored."
            )
            return
        logger.info("Network connectivity OK.")
            
        with open(CACHE_PATH, "r") as f:
            candidate_profile = CandidateProfile.model_validate_json(f.read())

        inferred_titles = candidate_profile.target_job_titles if candidate_profile.target_job_titles else ["AI Engineer", "Data Engineer"]

        target_skills_evaluations = 25 # target of daily jobs analyzed by skills agent
        skills_evaluated_count = 0
        matches_found_count = 0
        pipeline_status["target_skills"] = target_skills_evaluations
        pipeline_status["skills_evaluated"] = 0
        pipeline_status["matches_found"] = 0
        
        async def process_job(job):
            nonlocal matches_found_count
            if is_job_processed(job.id):
                logger.info(f"Skipping already processed job: {job.id}")
                return False
                
            logger.info(f"Evaluating job: {job.title} at {job.company}")
            try:
                match_result = await evaluate_job(candidate_profile, job, target_yoe=0)
                
                if getattr(match_result, 'auto_reject', False):
                    logger.info(f"Auto-rejected role: {job.title}")
                    mark_job_processed(job.id)
                    return match_result.is_skills_evaluated
                    
                if match_result.score >= settings.MATCH_THRESHOLD:
                    matches_found_count += 1
                    pipeline_status["matches_found"] = matches_found_count
                    logger.info(f"Match found! Score: {match_result.score}. Sending Discord alert...")
                    await send_discord_alert(job, match_result)
                mark_job_processed(job.id)
                return match_result.is_skills_evaluated
            except Exception as e:
                logger.error(f"Error evaluating job {job.id}: {e}")
                mark_job_processed(job.id)
                return False

        # locations to fetch jobs from
        locations = ["Netherlands"]
        scrape_batch_size = 25  # 25 matches LinkedIn's pagination window and prevents burst 429
        max_empty_retries = 3

        for loc in locations:
            if skills_evaluated_count >= target_skills_evaluations:
                break
                
            offset = 0
            consecutive_empty_batches = 0
            
            while skills_evaluated_count < target_skills_evaluations:
                logger.info(f"Fetching {scrape_batch_size} jobs for {loc} (offset: {offset})...")
                try:
                    jobs = fetch_daily_jobs(
                        target_job_titles=inferred_titles,
                        location=loc,
                        job_type="fulltime",
                        results_wanted=scrape_batch_size,
                        offset=offset
                    )
                except NetworkError as e:
                    # breaks the pipeline so that API calls are not wasted from JobSpy and triggers the network  error message to discord
                    err_msg = str(e)
                    logger.error(f"Network failure detected (not a 429). Aborting pipeline. Details: {err_msg}")
                    await send_discord_infra_alert(
                        "Network Failure During Pipeline",
                        f"The job pipeline was aborted mid-run due to a DNS/network error.\n"
                        f"**Error:** `{err_msg}`\n"
                        f"Re-trigger via `POST /trigger-pipeline` once connectivity is restored."
                    )
                    pipeline_status["last_status_message"] = f"Aborted: network failure — {err_msg}"
                    consecutive_empty_batches = max_empty_retries + 1
                    break
                
                if not jobs:
                    consecutive_empty_batches += 1
                    if consecutive_empty_batches <= max_empty_retries:
                        backoff_seconds = 60 * consecutive_empty_batches
                        logger.warning(
                            f"No jobs returned at offset {offset} (possible LinkedIn 429 rate limit or temporary cooldown). "
                            f"Waiting {backoff_seconds}s for rate-limit reset before retry {consecutive_empty_batches}/{max_empty_retries}..."
                        )
                        await asyncio.sleep(backoff_seconds)
                        continue
                    else:
                        logger.info(
                            f"No more jobs found for location {loc} at offset {offset} after {max_empty_retries} retries."
                        )
                        break

                consecutive_empty_batches = 0
                offset += scrape_batch_size
                logger.info(f"Scraper finished batch. Found {len(jobs)} jobs to process.")
                
                eval_batch_size = 5
                for i in range(0, len(jobs), eval_batch_size):
                    if skills_evaluated_count >= target_skills_evaluations:
                        logger.info(f"Reached target of {target_skills_evaluations} skills evaluations for today. Stopping.")
                        break
                        
                    batch = jobs[i:i+eval_batch_size]
                    results = await asyncio.gather(*(process_job(job) for job in batch))
                    
                    skills_evaluated_count += sum(bool(res) for res in results)
                    pipeline_status["skills_evaluated"] = skills_evaluated_count
                    logger.info(f"Progress: {skills_evaluated_count}/{target_skills_evaluations} skills evaluated.")

                if skills_evaluated_count < target_skills_evaluations:
                    logger.info("Pausing 25 seconds before fetching next scraper batch to prevent rate limiting (LinkedIn 429)...")
                    await asyncio.sleep(25)

        end_time = datetime.now(timezone.utc)
        pipeline_status["state"] = "idle"
        pipeline_status["last_run_finished"] = end_time.isoformat()
        pipeline_status["skills_evaluated"] = skills_evaluated_count
        pipeline_status["matches_found"] = matches_found_count
        status_msg = (
            f"Pipeline completed: {skills_evaluated_count}/{target_skills_evaluations} skills evaluated, "
            f"{matches_found_count} matches sent to Discord. Waiting for next scheduled run at 07:00 AM."
        )
        pipeline_status["last_status_message"] = status_msg

        logger.info("=" * 60)
        logger.info("=== Job Matching Pipeline Finished ===")
        logger.info(f"Skills Evaluated: {skills_evaluated_count}/{target_skills_evaluations}")
        logger.info(f"Matches Found: {matches_found_count}")
        if skills_evaluated_count >= target_skills_evaluations:
            logger.info("Status: Daily evaluation target reached successfully.")
        else:
            logger.info(f"Status: Finished early because available listings were exhausted for {locations}.")
        logger.info("Next automatic run scheduled for tomorrow at 07:00 AM (or via POST /trigger-pipeline).")
        logger.info("=" * 60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # scrape and evaluate jobs every morning at 7:00 am, this is automatic script, hence if the script is running (on server or locally), it will triger the pipeline (POST endpoint /trigger-pipeline) every morning at 7:00 am.
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
    if pipeline_lock.locked():
        return {"status": "busy", "message": "Pipeline is already currently running."}
    background_tasks.add_task(run_job_matching_pipeline)
    return {"message": "Pipeline triggered in the background."}

@app.get("/pipeline-status")
async def get_pipeline_status():
    return pipeline_status

@app.get("/profile")
async def get_profile():
    if not os.path.exists(CACHE_PATH):
        return {"status": "error", "message": "No profile found on the server."}
    with open(CACHE_PATH, "r") as f:
        candidate_profile = CandidateProfile.model_validate_json(f.read())
    return {"status": "ok", "profile": candidate_profile.model_dump()}

@app.get("/")
def read_root():
    return {
        "status": "ok",
        "message": "Job Fetching Agent is running.",
        "pipeline": pipeline_status
    }
