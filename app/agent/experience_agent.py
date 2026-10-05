from app.agent.llm_router import router
from app.models.schemas import JobPosting, ExperienceFilterResult

async def evaluate_experience(job: JobPosting, target_yoe: int) -> ExperienceFilterResult:
    prompt = f"""
    You are an AI recruiter filtering job postings based on experience requirements.
    
    You MUST return a valid JSON object with EXACTLY the following keys:
    {{
        "is_rejected": <true or false>,
        "reason": "<brief explanation>"
    }}

    JOB POSTING:
    Title: {job.title}
    Company: {job.company}
    Description: {job.description}

    TARGET YEARS OF CORPORATE EXPERIENCE: {target_yoe}

    RULES:
    1. If the job description explicitly demands "Senior", "Lead", "Manager", set 'is_rejected' to true.
    2. If the job strictly requires more than {target_yoe + 2} years of formal corporate engineering experience, set 'is_rejected' to true.
    3. If the job asks for 0-{target_yoe + 2} years of experience or doesn't strictly specify corporate experience, set 'is_rejected' to false.
    """
    response = await router.acompletion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return ExperienceFilterResult.model_validate_json(response.choices[0].message.content)
