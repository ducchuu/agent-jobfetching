import pymupdf
import os
import re
import logging
from app.agent.llm_router import router
from app.models.schemas import CandidateProfile

logger = logging.getLogger(__name__)

CACHE_PATH = "data/candidate_profile.json"

async def extract_profile_from_text(text: str) -> CandidateProfile:
    prompt = f"""You are a data extraction pipeline tool. Your task is to extract structured JSON data from a provided text document representing a professional resume or portfolio.

DATA MAPPING RULES:
1. name: Candidate full name.
2. academic_level: Highest academic degree obtained (e.g., 'BSc', 'MSc', or 'PhD'). Defaults to 'BSc' if not specified.
3. projects: Extract all technical projects (academic, personal, thesis). For each project, list the specific technologies used.
4. skills: Extract all technical skills and tools mentioned across the entire document.
5. target_job_titles: Generate 3-5 specific technical roles matching the candidate's unique skills and projects (e.g., 'AI Engineer', 'Robotics Software Engineer', 'Embedded Systems Engineer'). Omit seniority prefixes like 'Junior' or 'Senior'.
6. experience_summary: Briefly summarize professional experience and internships.
7. languages: Extract spoken languages as a simple list of names (e.g., ["English", "Polish"]).

Output ONLY a raw, valid JSON object with the exact keys below:
{{
    "name": "extracted name",
    "academic_level": "BSc",
    "skills": ["Python", "PyTorch"],
    "languages": ["English", "Polish"],
    "projects": [
        {{"name": "Project 1", "technologies": ["Python", "PyTorch"], "description": "Project summary"}}
    ],
    "experience_summary": "brief summary of work experience",
    "target_job_titles": ["title 1", "title 2", "title 3"]
}}

DOCUMENT TEXT:
{text}
"""
    logger.info("Calling LLM to extract structured candidate profile...")
    response = await router.acompletion(
        model="claude-5-5-sonnet",
        messages=[{"role": "user", "content": prompt}]
    )
    
    raw_json = (response.choices[0].message.content or "").strip()
    match = re.search(r"\{[\s\S]*\}", raw_json)
    if match:
        raw_json = match.group(0)
        
    profile = CandidateProfile.model_validate_json(raw_json)
    
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        f.write(profile.model_dump_json(indent=2))
        
    logger.info("Successfully extracted and cached candidate profile.")
    return profile

async def extract_profile_from_pdf_bytes(pdf_bytes: bytes) -> CandidateProfile:
    logger.info("Extracting text from in-memory PDF stream...")
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
    except Exception as e:
        logger.error(f"Failed to read PDF stream: {e}")
        raise
    return await extract_profile_from_text(text)

async def extract_profile_from_pdf(pdf_path: str) -> CandidateProfile:
    logger.info(f"Extracting text from {pdf_path}...")
    try:
        with pymupdf.open(pdf_path) as doc:
            text = "\n".join(page.get_text() for page in doc)
    except Exception as e:
        logger.error(f"Failed to read PDF {pdf_path}: {e}")
        raise
    return await extract_profile_from_text(text)
