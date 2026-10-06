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
    You are an expert technical recruiter analyzing a junior engineer's CV.
    Your goal is to extract a structured profile.

    CRITICAL INSTRUCTIONS:
    1. Extract all technical projects (academic, thesis, personal) into the 'projects' array. From the 'projects' array extract relevant skills and add them to skills array, if not present yet.
    2. Generate 3 to 5 highly specific 'target_job_titles' based on the intersection of their skills. Do NOT use prefixes like 'Junior', 'Entry-level', or 'Graduate'. Just output the core role (e.g., 'AI Engineer', 'Robotics Software Engineer', 'Embedded Systems Engineer'). The pipeline will filter for experience later.
    3. The 'experience_summary' should summarize all work experience (including technical internships or roles alongside non-technical work).
    4. Extract all languages spoken by the candidate (e.g. English, Polish) into the 'languages' array as bare language names without proficiency levels.
    
    You MUST return a valid JSON object with EXACTLY the following keys (do not return the schema itself, return the populated data):
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

    CANDIDATE CV TEXT:
    {text}
    """
    
    logger.info("Calling LLM to extract structured profile...")
    response = await router.acompletion(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    
    raw_json = response.choices[0].message.content
    profile = CandidateProfile.model_validate_json(raw_json)
    
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        f.write(profile.model_dump_json(indent=2))
        
    logger.info("Successfully extracted and cached candidate profile.")
    return profile
