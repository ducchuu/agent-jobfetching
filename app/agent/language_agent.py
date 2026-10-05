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
    # Step 1: Zero-cost language detection
    try:
        detected_code = detect(job.description[:1500])
        
        # If it's a known language, check if the candidate speaks it
        if detected_code in LANGUAGE_CODE_MAP and detected_code != 'en':
            detected_lang = LANGUAGE_CODE_MAP[detected_code]
            candidate_langs = [l.lower() for l in candidate_profile.languages]
            
            if detected_lang.lower() not in candidate_langs:
                logger.info(f"Langdetect: Rejected early. Written in {detected_lang}.")
                return LanguageFilterResult(
                    is_rejected=True, 
                    reason=f"Job posting is written in {detected_lang}, which is not in candidate's languages."
                )
    except Exception as e:
        logger.warning(f"Langdetect failed for job {job.id}: {e}")

    # Step 2: Fallback to gpt-4o-mini if written in English (or undetectable)
    # to check if a specific language is REQUIRED in the text.
    prompt = f"""
    You are an AI language filter evaluating a job posting for a candidate.
    
    You MUST return a valid JSON object with EXACTLY the following keys:
    {{
        "is_rejected": <true or false>,
        "reason": "<brief explanation>"
    }}

    CANDIDATE LANGUAGES:
    {candidate_profile.languages}

    JOB POSTING:
    Title: {job.title}
    Company: {job.company}
    Description: {job.description}

    RULES:
    1. If the job description explicitly requires fluency in a specific spoken language that is NOT listed in the candidate's languages, set 'is_rejected' to true.
    2. Otherwise, set 'is_rejected' to false.
    """
    response = await router.acompletion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return LanguageFilterResult.model_validate_json(response.choices[0].message.content)
