import re
from app.agent.llm_router import router
from app.models.schemas import JobPosting, ExperienceFilterResult

SENIOR_TITLE_PATTERN = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|head of|director|vp|manager)\b",
    re.IGNORECASE
)

async def evaluate_experience(job: JobPosting, target_yoe: int, academic_level: str = "BSc") -> ExperienceFilterResult:
    if SENIOR_TITLE_PATTERN.search(job.title):
        return ExperienceFilterResult(
            is_rejected=True,
            reason=f"Job title '{job.title}' explicitly indicates a senior or leadership role."
        )

    max_allowed_yoe = target_yoe + 2
    system_prompt = f"""You are an AI recruiter filtering job postings based on experience and academic requirements.

You MUST return a valid JSON object with EXACTLY the following keys:
{{
    "is_rejected": <true or false>,
    "reason": "<brief explanation>"
}}

TARGET YEARS OF CORPORATE EXPERIENCE: {target_yoe}
MAXIMUM ALLOWED YEARS IN JOB DESCRIPTION: {max_allowed_yoe}
CANDIDATE HIGHEST ACADEMIC LEVEL: {academic_level}

RULES:
1. If the role itself is a "Senior", "Lead", "Principal", "Staff", or "Manager" position, set 'is_rejected' to true. Do NOT reject simply because the candidate will report to a manager or collaborate with senior engineers.
2. If the job explicitly requires strictly MORE than {max_allowed_yoe} years of experience (e.g., if max is 2, reject 3+ years, 5+ years, etc.), set 'is_rejected' to true.
3. If the job is strictly an academic or research role that explicitly demands a higher degree than the candidate possesses (e.g., job requires PhD or is a "Postdoc" role, but candidate only has {academic_level}), set 'is_rejected' to true.
4. If the job asks for a range that overlaps with or is within 0-{max_allowed_yoe} years of experience and academic levels match or aren't strictly a dealbreaker, set 'is_rejected' to false.

For any 'is_rejected' = false, leave 'reason' as an empty string."""

    user_prompt = f"Title: {job.title}\nCompany: {job.company}\nDescription: {job.description}"

    response = await router.acompletion(
        model="gpt-6-luna",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"},
        max_tokens=100
    )
    return ExperienceFilterResult.model_validate_json(response.choices[0].message.content)
