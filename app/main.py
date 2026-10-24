from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException, Security, status, Depends
from fastapi.security import APIKeyHeader
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo
from typing import Optional
from app.core.database import (
    init_db, is_job_processed, record_job_status, mark_job_processed,
    STATUS_FILTERED_BOT, STATUS_FILTERED_LANG, STATUS_FILTERED_EXP,
    STATUS_EVALUATED, STATUS_ERROR_TRANSIENT
)
from app.services.scraper import fetch_daily_jobs, NetworkError
from app.services.cv_parser import extract_profile_from_pdf_bytes, CACHE_PATH
from app.agent.matcher import evaluate_job
from app.agent.llm_router import EvaluationTransientError
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

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)):
    if settings.API_SECRET_KEY:
        if not api_key or api_key != settings.API_SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing X-API-Key header"
            )
    return api_key

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
    def _connect():
        with socket.create_connection((host, port), timeout=timeout):
            return True

    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _connect),
            timeout=timeout + 1
        )
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
            if is_job_processed(job.id, job.company, job.title):
                logger.info(f"Skipping already processed job (ID or Fingerprint): {job.title} at {job.company}")
                return False
                
            logger.info(f"Evaluating job: {job.title} at {job.company}")
            try:
                match_result = await evaluate_job(candidate_profile, job, target_yoe=0)
                
                if getattr(match_result, 'auto_reject', False):
                    logger.info(f"Auto-rejected role: {job.title} ({match_result.reasoning})")
                    reason_lower = (match_result.reasoning or "").lower()
                    if "anti-bot" in reason_lower or "captcha" in reason_lower:
                        filter_status = STATUS_FILTERED_BOT
                    elif "language" in reason_lower:
                        filter_status = STATUS_FILTERED_LANG
                    elif "experience" in reason_lower:
                        filter_status = STATUS_FILTERED_EXP
                    else:
                        filter_status = STATUS_EVALUATED
                        
                    record_job_status(
                        job_id=job.id,
                        company=job.company,
                        title=job.title,
                        status=filter_status,
                        score=match_result.score,
                        reasoning=match_result.reasoning
                    )
                    return match_result.is_skills_evaluated
                    
                if match_result.score >= settings.MATCH_THRESHOLD:
                    matches_found_count += 1
                    pipeline_status["matches_found"] = matches_found_count
                    logger.info(f"Match found! Score: {match_result.score}. Sending Discord alert...")
                    await send_discord_alert(job, match_result)

                record_job_status(
                    job_id=job.id,
                    company=job.company,
                    title=job.title,
                    status=STATUS_EVALUATED,
                    score=match_result.score,
                    reasoning=match_result.reasoning
                )
                return match_result.is_skills_evaluated
            except EvaluationTransientError as e:
                logger.warning(f"Transient evaluation error for job {job.id} at {job.company}: {e}. Retrying on next run.")
                record_job_status(
                    job_id=job.id,
                    company=job.company,
                    title=job.title,
                    status=STATUS_ERROR_TRANSIENT,
                    reasoning=str(e)
                )
                return False
            except Exception as e:
                logger.error(f"Error evaluating job {job.id}: {e}")
                record_job_status(
                    job_id=job.id,
                    company=job.company,
                    title=job.title,
                    status=STATUS_ERROR_TRANSIENT,
                    reasoning=str(e)
                )
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
                    jobs = await asyncio.to_thread(
                        fetch_daily_jobs,
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

@app.post("/upload-cv", dependencies=[Depends(verify_api_key)])
async def upload_cv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    pdf_bytes = await file.read()
    profile = await extract_profile_from_pdf_bytes(pdf_bytes)
    return {"message": "CV processed and cached successfully.", "profile": profile.model_dump()}

@app.post("/trigger-pipeline", dependencies=[Depends(verify_api_key)])
async def trigger_pipeline(background_tasks: BackgroundTasks):
    if pipeline_lock.locked():
        return {"status": "busy", "message": "Pipeline is already currently running."}
    background_tasks.add_task(run_job_matching_pipeline)
    return {"message": "Pipeline triggered in the background."}

@app.get("/pipeline-status")
async def get_pipeline_status():
    return pipeline_status

@app.get("/profile", dependencies=[Depends(verify_api_key)])
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
