import json
from app.agent.llm_router import router
from app.models.schemas import JobPosting, MatchResult, CandidateProfile

async def evaluate_job(
    candidate_profile: CandidateProfile, 
    job: JobPosting, 
    target_yoe: int = 0
) -> MatchResult:
    prompt = f"""
    You are an extremely strict AI engineering manager evaluating a candidate for a role.
    
    You MUST return a valid JSON object with EXACTLY the following keys (do not return the schema itself, return the populated data):
    {{
        "chain_of_thought": "<step-by-step reasoning evaluating language, experience, and skills>",
        "score": <integer between 0 and 100>,
        "reasoning": "<brief explanation of score>",
        "missing_skills": ["<missing skill>"],
        "upskill_action": "<concrete weekend action>",
        "auto_reject": <true or false>
    }}

    CANDIDATE PROFILE:
    {candidate_profile.model_dump_json()}

    JOB POSTING:
    Title: {job.title}
    Company: {job.company}
    Description: {job.description}

    TARGET YEARS OF CORPORATE EXPERIENCE: {target_yoe}

    EVALUATION RULES (FOLLOW STRICTLY):
    1. AUTO-REJECT: If the job description explicitly demands "Senior", "Lead", "Manager", or strictly requires more than {target_yoe + 2} years of formal corporate engineering experience, set 'auto_reject' to true and 'score' to 0.
    2. LANGUAGE AUTO-REJECT: If the job description requires a specific spoken language (e.g., Dutch) that is NOT listed in the candidate's 'languages' array, or if the job posting is written entirely in a language the candidate does not speak, set 'auto_reject' to true and 'score' to 0.
    3. EXPERIENCE EXEMPTION: If the job asks for 0-2 years of experience, DO NOT penalize the candidate. Treat the candidate's complex technical 'projects' as entirely valid experience.
    4. STRICT SCORING RUBRIC:
       - Base score is 100.
       - Deduct -15 points for every mandatory core technology the candidate completely lacks.
       - Deduct -10 points if the job domain is completely unrelated to the candidate's projects (e.g., front-end web dev vs robotics).
       - Ensure the final score never exceeds 100 or drops below 0.
    """
    
    # LiteLLM router handles load balancing, Langfuse tracing, and fallback seamlessly
    response = await router.acompletion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"} # Force JSON out
    )
    
    # Parse the LLM's raw JSON string directly into our Pydantic model
    raw_json = response.choices[0].message.content
    return MatchResult.model_validate_json(raw_json)
