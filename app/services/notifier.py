import httpx
from app.config import settings
from app.models.schemas import JobPosting, MatchResult

async def send_discord_alert(job: JobPosting, match: MatchResult):
    color = 0x00FF00 if match.score >= 90 else 0xFFA500 # Green for >= 95, Orange for 91-94

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
    
    async with httpx.AsyncClient() as client:
        await client.post(settings.DISCORD_WEBHOOK_URL, json=payload)
