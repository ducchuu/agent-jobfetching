import httpx
import logging
from app.config import settings
from app.models.schemas import JobPosting, MatchResult

logger = logging.getLogger(__name__)

async def send_discord_alert(job: JobPosting, match: MatchResult):
    color = 0x00FF00 if match.score >= 90 else 0xFFA500 # green for >= 90, orange for <80,90)

    payload = {
        "username": "Job Fetching Agent",
        "embeds": [{
            "title": f"[{match.score}/100] {job.title} @ {job.company}",
            "url": job.url,
            "color": color,
            "fields": [
                {"name": "Reasoning", "value": match.reasoning, "inline": False},
                {"name": "Missing Skills", "value": ", ".join(match.missing_skills) or "None", "inline": True},
                {"name": "Upskill Action", "value": match.upskill_action, "inline": False}
            ]
        }]
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
            if resp.status_code >= 400:
                logger.warning(f"Discord webhook returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to send Discord alert for job {job.id}: {e}")
