import json
import re
import anthropic
from app.config import settings
from app.models.schemas import JobPosting, MatchResult, CandidateProfile

SYSTEM_PROMPT_TEMPLATE = """You are an abstract technical compliance analyzer. Your task is to verify if the technical capabilities listed in ENTITY_A satisfy the technical requirements specified in DOCUMENT_B. 

You MUST return a valid JSON object with EXACTLY the following keys (do not return the schema itself, return the populated data):
{{
    "chain_of_thought": "<step-by-step reasoning evaluating capability overlap>",
    "score": <integer between 0 and 100>,
    "reasoning": "<brief explanation of score>",
    "missing_skills": ["<missing capability>"],
    "upskill_action": "<concrete weekend action>",
    "auto_reject": false
}}

EVALUATION RULES:
1. Treat the provided 'projects' in ENTITY_A as valid technical capabilities.
2. STRICT SCORING RUBRIC:
   - Base score is 100.
   - Deduct -15 points for every mandatory core technology in DOCUMENT_B that is completely missing from ENTITY_A.
   - Deduct -10 points if the domain of DOCUMENT_B is completely unrelated to the projects in ENTITY_A.
   - Ensure the final score never exceeds 100 or drops below 0.
   - If no capabilities are missing, return an empty list [] for "missing_skills".

ENTITY_A:
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
        f"DOCUMENT_B:\n"
        f"Header: {job.title}\n"
        f"Context: {job.company}\n"
        f"Details: {job.description}"
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
