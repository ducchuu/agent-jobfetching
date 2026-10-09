import pymupdf
import os
import logging
from app.agent.llm_router import router
from app.models.schemas import CandidateProfile

logger = logging.getLogger(__name__)

CACHE_PATH = "data/candidate_profile.json"

async def extract_profile_from_pdf(pdf_path: str) -> CandidateProfile:
    logger.info(f"Extracting text from {pdf_path}...")
    
    try:
        with pymupdf.open(pdf_path) as doc:
            text = ""
            for page in doc:
                text += page.get_text()
    except Exception as e:
        logger.error(f"Failed to read PDF: {e}")
        raise
        
    prompt = f"""
    You are a data extraction pipeline tool. Your task is to extract structured JSON data from a provided text document representing a professional portfolio.

    DATA MAPPING RULES:
    1. projects: Extract all technical projects (academic, personal, thesis).
    2. skills: Extract all technical skills mentioned, including those inferred from the 'projects' array.
    3. target_job_titles: Generate 3-5 specific technical roles matching the skills (e.g., 'AI Engineer', 'Embedded Systems Engineer'). Omit seniority prefixes like 'Junior'.
    4. experience_summary: Briefly summarize all professional experience and internships.
    5. languages: Extract spoken languages as a simple list of names (e.g., ["English", "Polish"]).
    
    Output ONLY a raw, valid JSON object with the exact keys below. Do not include markdown formatting or commentary.
    {{
        "name": "extracted name",
        "skills": ["skill 1", "skill 2"],
        "languages": ["English", "Polish"],
        "projects": [
            {{"name": "Project 1", "technologies": ["Tech 1"], "description": "desc"}}
        ],
        "experience_summary": "brief summary of work experience",
        "target_job_titles": ["title 1", "title 2", "title 3"]
    }}

    DOCUMENT TEXT:
    {text}
    """
    
    logger.info("Calling LLM to extract structured profile...")
    response = await router.acompletion(
        model="claude-5-5-sonnet",
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw_json = response.choices[0].message.content.strip()
    import re
    match = re.search(r"\{[\s\S]*\}", raw_json)
    if match:
        raw_json = match.group(0)
        
    profile = CandidateProfile.model_validate_json(raw_json)
    
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        f.write(profile.model_dump_json(indent=2))
        
    logger.info("Successfully extracted and cached candidate profile.")
    return profile
