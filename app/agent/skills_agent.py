import json
import re
from app.config import settings
from app.models.schemas import JobPosting, MatchResult, CandidateProfile

SYSTEM_PROMPT_TEMPLATE = """You are an AI screening assistant helping a human recruiter pre-screen technical resumes.
A human recruiter will review these recommendations before any action is taken.

You MUST return a valid JSON object with EXACTLY the following keys (do not return the schema itself, return the populated data):
{{
    "chain_of_thought": "<step-by-step reasoning evaluating skills and projects, max 2 sentences>",
    "score": <integer between 0 and 100>,
    "reasoning": "<brief explanation of score, max 1 sentence>",
    "missing_skills": ["<missing skill>"],
    "upskill_action": "<concrete weekend action, max 1 sentence>",
    "recommend_archiving": false
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
        candidate_json=json.dumps(candidate_data, separators=(',', ':'))
    )
    
    dynamic_job_content = (
        f"JOB POSTING:\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Description: {job.description}"
    )

    try:
        from litellm import acompletion
        
        response = await acompletion(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": static_system_content},
                {"role": "user", "content": dynamic_job_content}
            ],
            response_format={"type": "json_object"},
            max_tokens=300
        )
        
        content = response.choices[0].message.content
        import logging
        logging.info(f"LLM RAW CONTENT: {repr(content)}")
        
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            content = match.group(0)
        
        data = json.loads(content)
        return MatchResult(
            chain_of_thought=data.get("chain_of_thought", ""),
            score=data.get("score", 0),
            reasoning=data.get("reasoning", ""),
            missing_skills=data.get("missing_skills", []),
            upskill_action=data.get("upskill_action", ""),
            auto_reject=data.get("recommend_archiving", False)
        )
    except Exception as e:
        import logging
        logging.error(f"Failed to parse MatchResult: {e}")
        return MatchResult(
            chain_of_thought="Error parsing.",
            score=0,
            reasoning="Parse failure.",
            missing_skills=[],
            upskill_action="",
            auto_reject=True
        )
