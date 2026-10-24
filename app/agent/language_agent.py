import logging
from langdetect import detect, DetectorFactory
from app.agent.llm_router import router
from app.models.schemas import JobPosting, CandidateProfile, LanguageFilterResult

DetectorFactory.seed = 0
logger = logging.getLogger(__name__)

LANGUAGE_CODE_MAP = {
    'en': 'English',
    'nl': 'Dutch',
    'fr': 'French',
    'de': 'German',
    'es': 'Spanish',
    'pl': 'Polish',
    'it': 'Italian',
    'pt': 'Portuguese',
    'zh-cn': 'Chinese',
    'ja': 'Japanese',
    'ko': 'Korean',
    'ru': 'Russian',
}

async def evaluate_language(candidate_profile: CandidateProfile, job: JobPosting) -> LanguageFilterResult:
    # no-cost language detection
    try:
        detected_code = detect(job.description[:1500])
        
        # if it's a known language, check if the candidate speaks it
        if detected_code in LANGUAGE_CODE_MAP and detected_code != 'en':
            detected_lang = LANGUAGE_CODE_MAP[detected_code]
            
            # substring match to handle cases like "English (C1)" vs "English" which would have been false negative
            if not any(detected_lang.lower() in lang.lower() for lang in candidate_profile.languages):
                logger.info(f"Langdetect: Rejected early. Written in {detected_lang}.")
                return LanguageFilterResult(
                    is_rejected=True, 
                    reason=f"Job posting is written in {detected_lang}, which is not in candidate's languages."
                )
    except Exception as e:
        logger.warning(f"Langdetect failed for job {job.id}: {e}")

    # switch to LLM if written in English (or undetectable) to check if a specific language is REQUIRED in the text.
    system_prompt = f"""You are an AI language filter evaluating a job posting for a candidate.

You MUST return a valid JSON object with EXACTLY the following keys:
{{
    "is_rejected": <true or false>,
    "reason": "<brief explanation>"
}}

CANDIDATE SPOKEN LANGUAGES:
{candidate_profile.languages}

RULES:
1. If the job description explicitly requires mandatory fluency/proficiency in a spoken language NOT listed in the candidate's spoken languages, set 'is_rejected' to true and explain in 1 sentence.
2. Do NOT reject if a language (e.g., Dutch or German) is described as "a plus", "nice to have", "an advantage", or if the company offers language classes. Only reject if it is a strict mandatory requirement.
3. Otherwise, set 'is_rejected' to false and leave 'reason' as an empty string."""

    user_prompt = f"Title: {job.title}\nCompany: {job.company}\nDescription:\n{job.description}"

    try:
        import re
        response = await router.acompletion(
            model="gpt-6-luna",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            reasoning_effort="none",
            max_tokens=1024
        )
        content = (response.choices[0].message.content or "").strip()
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            content = match.group(0)
        return LanguageFilterResult.model_validate_json(content)
    except Exception as e:
        logger.warning(f"Language filter failed for job {job.id}: {e}. Defaulting to not rejected.")
        return LanguageFilterResult(is_rejected=False, reason="")
