import json
import re
import anthropic
from app.config import settings
from app.models.schemas import JobPosting, MatchResult, CandidateProfile

SYSTEM_PROMPT_TEMPLATE = """You are an extremely strict AI engineering manager evaluating a candidate for a role.
This job has already passed language and experience filters. Your job is ONLY to evaluate skill and project match.

You MUST return a valid JSON object with EXACTLY the following keys (do not return the schema itself, return the populated data):
{{
    "chain_of_thought": "<step-by-step reasoning evaluating skills and projects>",
    "score": <integer between 0 and 100>,
    "reasoning": "<brief explanation of score>",
    "missing_skills": ["<missing skill>"],
    "upskill_action": "<concrete weekend action>",
    "auto_reject": false
}}

EVALUATION RULES:
1. Treat the candidate's complex technical 'projects' as entirely valid engineering experience.
2. STRICT SCORING RUBRIC:
   - Base score is 100.
   - Deduct -15 points for every mandatory core technology in the job description that the candidate completely lacks.
   - Deduct -10 points if the job domain is completely unrelated to the candidate's projects (e.g., front-end web dev vs robotics).
   - Ensure the final score never exceeds 100 or drops below 0.
   - If no skills are missing, return an empty list [] for "missing_skills".

CANDIDATE PROFILE:
{candidate_json}"""

async def evaluate_skills(candidate_profile: CandidateProfile, job: JobPosting) -> MatchResult:
    candidate_data = {
        "skills": candidate_profile.skills,
        "projects": [p.model_dump() for p in candidate_profile.projects],
        "experience_summary": candidate_profile.experience_summary
    }
    
    static_system_content = SYSTEM_PROMPT_TEMPLATE.format(
        candidate_json=json.dumps(candidate_data, indent=2)
    )
    
    dynamic_job_content = (
        f"JOB POSTING:\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Description: {job.description}"
    )

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = await client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": static_system_content,
                "cache_control": {"type": "ephemeral"}
            }
        ],
        messages=[
            {
                "role": "user",
                "content": dynamic_job_content
            }
        ]
    )

    import logging
    logging.info(f"RAW ANTHROPIC RESPONSE: stop_reason={response.stop_reason}, usage={response.usage}")
    logging.info(f"RAW ANTHROPIC BLOCKS: {response.content}")

    text_content = ""
    for block in response.content:
        if block.type == "text":
            text_content = block.text
            break

    content = text_content.strip()
    
    logging.info(f"EXTRACTED TEXT CONTENT: {repr(content)}")

    match = re.search(r"\{[\s\S]*\}", content)
    if match:
        content = match.group(0)

    return MatchResult.model_validate_json(content)
