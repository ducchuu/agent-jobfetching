from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException, Security, status, Depends
from fastapi.security import APIKeyHeader
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo
from typing import Optional
from app.core.database import (
    init_db, is_job_processed, record_job_status, mark_job_processed,
    get_today_date_str, get_location_daily_stats, record_location_daily_scrape,
    mark_location_daily_exhausted, get_all_daily_location_stats,
    STATUS_FILTERED_BOT, STATUS_FILTERED_INTERN, STATUS_FILTERED_LANG, STATUS_FILTERED_EXP,
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
stop_pipeline_event = asyncio.Event()

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
    "current_location": None,
    "locations": settings.LOCATIONS,
    "skills_evaluated": 0,
    "target_skills": settings.TARGET_SKILLS_EVALUATIONS,
    "matches_found": 0,
    "location_stats": {},
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
        stop_pipeline_event.clear()
        start_time = datetime.now(timezone.utc)
        today_date_str = get_today_date_str()
        locations = settings.LOCATIONS
        max_results_per_loc = settings.MAX_RESULTS_PER_LOCATION
        scrape_batch_size = settings.SCRAPE_BATCH_SIZE
        scrape_delay = settings.SCRAPE_DELAY_SECONDS
        eval_batch_size = settings.EVAL_BATCH_SIZE
        max_empty_retries = 3

        pipeline_status["state"] = "running"
        pipeline_status["last_run_started"] = start_time.isoformat()
        pipeline_status["last_status_message"] = "Pipeline running..."
        pipeline_status["locations"] = locations
        pipeline_status["target_skills"] = settings.TARGET_SKILLS_EVALUATIONS
        pipeline_status["skills_evaluated"] = 0
        pipeline_status["matches_found"] = 0
        pipeline_status["location_stats"] = get_all_daily_location_stats(today_date_str)

        logger.info("=" * 60)
        logger.info(f"Starting daily job matching pipeline for date {today_date_str}...")
        logger.info(f"Target Locations: {locations}")
        logger.info(f"Max Results Per Location: {max_results_per_loc}")
        logger.info("=" * 60)
        
        aborted_message: Optional[str] = None
        skills_evaluated_count = 0
        matches_found_count = 0

        try:
            if not os.path.exists(CACHE_PATH):
                msg = "No CV profile cached. Please upload a CV first via /upload-cv."
                logger.warning(msg)
                aborted_message = msg
                return

            logger.info("Running pre-flight network connectivity check...")
            if not await check_network_connectivity():
                msg = "Pipeline aborted: network/DNS is unreachable (could not connect to 8.8.8.8:53)."
                logger.error(msg)
                aborted_message = msg
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
                        elif "internship filter" in reason_lower:
                            filter_status = STATUS_FILTERED_INTERN
                        elif "language filter" in reason_lower:
                            filter_status = STATUS_FILTERED_LANG
                        elif "experience filter" in reason_lower:
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

            consecutive_empty = {loc: 0 for loc in locations}

            while not aborted_message:
                if stop_pipeline_event.is_set():
                    aborted_message = "Stopped manually via /stop-pipeline."
                    logger.info("Stop requested via /stop-pipeline. Halting pipeline...")
                    break
                if settings.TARGET_SKILLS_EVALUATIONS and skills_evaluated_count >= settings.TARGET_SKILLS_EVALUATIONS:
                    logger.info(f"Reached overall target of {settings.TARGET_SKILLS_EVALUATIONS} skills evaluations. Stopping.")
                    break

                # Determine active locations that have not completed or exhausted for today
                active_locations = []
                for loc in locations:
                    loc_stats = get_location_daily_stats(loc, today_date_str)
                    if loc_stats["is_exhausted"]:
                        continue
                    if loc_stats["last_offset"] >= max_results_per_loc or loc_stats["results_fetched"] >= max_results_per_loc:
                        mark_location_daily_exhausted(loc, today_date_str)
                        continue
                    active_locations.append(loc)

                if not active_locations:
                    logger.info("All configured locations have completed or exhausted listings for today.")
                    break

                logger.info(f"=== Starting round-robin cycle across {len(active_locations)} active locations: {active_locations} ===")

                for loc in active_locations:
                    if aborted_message or stop_pipeline_event.is_set():
                        if stop_pipeline_event.is_set() and not aborted_message:
                            aborted_message = "Stopped manually via /stop-pipeline."
                        break
                    if settings.TARGET_SKILLS_EVALUATIONS and skills_evaluated_count >= settings.TARGET_SKILLS_EVALUATIONS:
                        break

                    pipeline_status["current_location"] = loc
                    loc_stats = get_location_daily_stats(loc, today_date_str)
                    results_fetched_today = loc_stats["results_fetched"]
                    offset = loc_stats["last_offset"]

                    if offset >= max_results_per_loc or results_fetched_today >= max_results_per_loc:
                        mark_location_daily_exhausted(loc, today_date_str)
                        continue

                    current_batch_wanted = min(scrape_batch_size, max_results_per_loc - offset)
                    logger.info(f"[{loc}] Fetching {current_batch_wanted} jobs (offset: {offset}, today: {results_fetched_today}/{max_results_per_loc})...")
                    try:
                        jobs = await asyncio.to_thread(
                            fetch_daily_jobs,
                            target_job_titles=inferred_titles,
                            location=loc,
                            job_type="fulltime",
                            results_wanted=current_batch_wanted,
                            offset=offset
                        )
                    except NetworkError as e:
                        err_msg = str(e)
                        logger.error(f"Network failure detected (not a 429). Aborting pipeline. Details: {err_msg}")
                        await send_discord_infra_alert(
                            "Network Failure During Pipeline",
                            f"The job pipeline was aborted mid-run due to a DNS/network error.\n"
                            f"**Error:** `{err_msg}`\n"
                            f"Re-trigger via `POST /trigger-pipeline` once connectivity is restored."
                        )
                        aborted_message = f"Aborted: network failure — {err_msg}"
                        break

                    if not jobs:
                        consecutive_empty[loc] += 1
                        if consecutive_empty[loc] <= max_empty_retries:
                            logger.warning(
                                f"[{loc}] No jobs returned at offset {offset} (attempt {consecutive_empty[loc]}/{max_empty_retries}). "
                                f"Will retry in next round-robin cycle..."
                            )
                        else:
                            logger.info(
                                f"[{loc}] No more jobs found at offset {offset} after {max_empty_retries} retries. Marking exhausted for today."
                            )
                            mark_location_daily_exhausted(loc, today_date_str)
                        await asyncio.sleep(scrape_delay)
                        continue

                    consecutive_empty[loc] = 0
                    results_fetched_today += len(jobs)
                    offset += scrape_batch_size

                    is_loc_now_exhausted = (offset >= max_results_per_loc or results_fetched_today >= max_results_per_loc)
                    record_location_daily_scrape(
                        location=loc,
                        results_fetched=results_fetched_today,
                        offset=offset,
                        is_exhausted=is_loc_now_exhausted,
                        date_str=today_date_str
                    )
                    pipeline_status["location_stats"] = get_all_daily_location_stats(today_date_str)

                    logger.info(f"[{loc}] Scraper returned {len(jobs)} jobs (total today: {results_fetched_today}). Evaluating...")

                    for i in range(0, len(jobs), eval_batch_size):
                        if stop_pipeline_event.is_set():
                            logger.info("Stop requested via /stop-pipeline. Halting job evaluations...")
                            aborted_message = "Stopped manually via /stop-pipeline."
                            break
                        if settings.TARGET_SKILLS_EVALUATIONS and skills_evaluated_count >= settings.TARGET_SKILLS_EVALUATIONS:
                            logger.info(f"Reached overall target of {settings.TARGET_SKILLS_EVALUATIONS} skills evaluations. Stopping.")
                            break

                        batch = jobs[i:i+eval_batch_size]
                        results = await asyncio.gather(*(process_job(job) for job in batch))

                        skills_evaluated_count += sum(bool(res) for res in results)
                        pipeline_status["skills_evaluated"] = skills_evaluated_count
                        logger.info(f"Progress: {skills_evaluated_count} skills evaluated so far across all locations.")

                    if is_loc_now_exhausted:
                        logger.info(f"[{loc}] Reached maximum results limit ({max_results_per_loc}) for today.")

                    if aborted_message or stop_pipeline_event.is_set():
                        if stop_pipeline_event.is_set() and not aborted_message:
                            aborted_message = "Stopped manually via /stop-pipeline."
                        break

                    logger.info(f"Pausing {scrape_delay}s before next location in cycle...")
                    await asyncio.sleep(scrape_delay)

        except Exception as e:
            logger.exception(f"Unexpected error in job matching pipeline: {e}")
            aborted_message = f"Pipeline failed unexpectedly: {e}"
        finally:
            end_time = datetime.now(timezone.utc)
            pipeline_status["state"] = "idle"
            pipeline_status["last_run_finished"] = end_time.isoformat()
            pipeline_status["skills_evaluated"] = skills_evaluated_count
            pipeline_status["matches_found"] = matches_found_count
            pipeline_status["current_location"] = None
            all_stats = get_all_daily_location_stats(today_date_str)
            pipeline_status["location_stats"] = all_stats

            if aborted_message:
                pipeline_status["last_status_message"] = aborted_message
            else:
                pipeline_status["last_status_message"] = (
                    f"Pipeline completed: {skills_evaluated_count} skills evaluated, "
                    f"{matches_found_count} matches sent to Discord. Waiting for next scheduled run at 07:00 AM."
                )

            logger.info("=" * 60)
            logger.info("=== Job Matching Pipeline Finished ===")
            logger.info(f"Skills Evaluated: {skills_evaluated_count}")
            logger.info(f"Matches Found: {matches_found_count}")
            logger.info(f"Locations Checked: {locations}")
            logger.info("Daily Location Scrape Summary:")
            for loc in locations:
                stat = all_stats.get(loc, {"results_fetched": 0, "last_offset": 0, "is_exhausted": False})
                state_desc = "exhausted/completed" if stat["is_exhausted"] else f"offset {stat['last_offset']}"
                logger.info(f"  - {loc}: {stat['results_fetched']} jobs fetched ({state_desc})")
            if aborted_message:
                logger.info(f"Status: {aborted_message}")
            else:
                logger.info("Status: Pipeline finished processing all configured locations.")
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

app = FastAPI(title="Job Postings Fetching Agent", version="1.1.0", lifespan=lifespan)

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

@app.post("/stop-pipeline", dependencies=[Depends(verify_api_key)])
async def stop_pipeline():
    if not pipeline_lock.locked():
        return {"status": "idle", "message": "Pipeline is not currently running."}
    stop_pipeline_event.set()
    return {"status": "stopping", "message": "Stop signal sent. Pipeline will halt after the current batch finishes."}

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

@app.get("/location-stats", dependencies=[Depends(verify_api_key)])
async def get_location_stats():
    today = get_today_date_str()
    return {
        "date": today,
        "configured_locations": settings.LOCATIONS,
        "stats": get_all_daily_location_stats(today)
    }

@app.get("/")
def read_root():
    return {
        "status": "ok",
        "message": "Job Fetching Agent is running.",
        "pipeline": pipeline_status
    }
