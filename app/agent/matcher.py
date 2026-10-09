from app.models.schemas import JobPosting, MatchResult, CandidateProfile
from app.agent.language_agent import evaluate_language
from app.agent.experience_agent import evaluate_experience
from app.agent.skills_agent import evaluate_skills

async def evaluate_job(
    candidate_profile: CandidateProfile, 
    job: JobPosting, 
    target_yoe: int = 0
) -> MatchResult:
    
    # Language agent
    lang_result = await evaluate_language(candidate_profile, job)
    if lang_result.is_rejected:
        return MatchResult(
            chain_of_thought=f"Language filter rejected: {lang_result.reason}",
            score=0,
            reasoning=lang_result.reason,
            missing_skills=[],
            upskill_action="Learn the required language.",
            auto_reject=True
        )
        
    # Experience agent
    exp_result = await evaluate_experience(job, target_yoe)
    if exp_result.is_rejected:
        return MatchResult(
            chain_of_thought=f"Experience filter rejected: {exp_result.reason}",
            score=0,
            reasoning=exp_result.reason,
            missing_skills=[],
            upskill_action="Gain more corporate experience.",
            auto_reject=True
        )
        
    # Skills agent
    result = await evaluate_skills(candidate_profile, job)
    result.is_skills_evaluated = True
    return result
