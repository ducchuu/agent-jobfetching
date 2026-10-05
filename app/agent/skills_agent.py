import json
from app.agent.llm_router import router
from app.models.schemas import JobPosting, MatchResult, CandidateProfile

async def evaluate_skills(candidate_profile: CandidateProfile, job: JobPosting) -> MatchResult:
    candidate_data = {
        "skills": candidate_profile.skills,
        "projects": [p.model_dump() for p in candidate_profile.projects],
        "experience_summary": candidate_profile.experience_summary
    }
    
    prompt = f"""
    You are an extremely strict AI engineering manager evaluating a candidate for a role.
    This job has already passed language and experience filters. Your job is ONLY to evaluate skill and project match.
    
    You MUST return a valid JSON object with EXACTLY the following keys (do not return the schema itself, return the populated data):
    {{
        "chain_of_thought": "<step-by-step reasoning evaluating skills and projects>",
        "score": <integer between 0 and 100>,
        "reasoning": "<brief explanation of score>",
        "missing_skills": ["<missing skill>"],
        "upskill_action": "<concrete weekend action>",
        "auto_reject": false
    }}

    CANDIDATE PROFILE:
    {json.dumps(candidate_data, indent=2)}

    JOB POSTING:
    Title: {job.title}
    Company: {job.company}
    Description: {job.description}

    EVALUATION RULES:
    1. Treat the candidate's complex technical 'projects' as entirely valid experience.
    2. STRICT SCORING RUBRIC:
       - Base score is 100.
       - Deduct -15 points for every mandatory core technology in the job description that the candidate completely lacks.
       - Deduct -10 points if the job domain is completely unrelated to the candidate's projects (e.g., front-end web dev vs robotics).
       - Ensure the final score never exceeds 100 or drops below 0.
    """
    
    # We use a highly capable model here because it only runs on the filtered top 10% of jobs
    response = await router.acompletion(
        model="claude-3-5-sonnet-20240620", 
        messages=[{"role": "user", "content": prompt}],
        # Note: Depending on litellm version, response_format={"type": "json_object"} might not be supported for Claude natively. 
        # If it fails, we may need to remove it or use "gpt-4o". Assuming router handles it.
    )
    
    # Simple JSON extraction logic to handle potential markdown wrappers from Claude
    content = response.choices[0].message.content.strip()
    if content.startswith("```json"):
        content = content[7:-3].strip()
    elif content.startswith("```"):
        content = content[3:-3].strip()
        
    return MatchResult.model_validate_json(content)
