import asyncio
import json
import logging
import re
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from app.config import settings
from app.models.schemas import JobPosting, CandidateProfile, MatchResult
from app.agent.language_agent import evaluate_language
from app.agent.experience_agent import evaluate_experience
from app.agent.skills_agent import evaluate_skills
from app.agent.llm_router import router

logger = logging.getLogger(__name__)

class JobState(TypedDict):
    job: JobPosting
    candidate_profile: CandidateProfile
    target_yoe: int
    is_rejected: bool
    reject_reason: str
    final_match_result: Optional[MatchResult]

# anti-bot and corrupted jobs scraping check
async def scraper_validation_node(state: JobState):
    job = state["job"]
    text = job.description.lower()
    anti_bot_phrases = ["enable cookies", "verify you are a human", "access denied", "security check", "captcha"]
    for phrase in anti_bot_phrases:
        if phrase in text and len(text) < 1500:
            logger.info(f"Scraper validation rejected job {job.id}: Anti-bot detected.")
            return {"is_rejected": True, "reject_reason": "Anti-bot/Scraper blocked text detected."}
    return {"is_rejected": False, "reject_reason": ""}

# concurrent experience and language filters in order to reduce latency
async def parallel_agents_node(state: JobState):
    lang_task = evaluate_language(state["candidate_profile"], state["job"])
    exp_task = evaluate_experience(state["job"], state["target_yoe"], state["candidate_profile"].academic_level)
    
    lang_res, exp_res = await asyncio.gather(lang_task, exp_task)
    
    if lang_res.is_rejected:
        return {"is_rejected": True, "reject_reason": f"Language filter: {lang_res.reason}"}
    if exp_res.is_rejected:
        return {"is_rejected": True, "reject_reason": f"Experience filter: {exp_res.reason}"}
        
    return {"is_rejected": False, "reject_reason": ""}

async def skills_agent_node(state: JobState):
    res = await evaluate_skills(state["candidate_profile"], state["job"])
    return {"final_match_result": res}

async def devils_advocate_node(state: JobState):
    match_result = state.get("final_match_result")
    if not match_result or match_result.score < settings.MATCH_THRESHOLD:
        return {}
        
    candidate = state["candidate_profile"]
    projects_summary = "\n".join(
        f"- {p.name}: Technologies: {', '.join(p.technologies)} | {p.description}"
        for p in candidate.projects
    )
    matched_skills = (
        ", ".join(match_result.rubric.matched_core_skills)
        if match_result.rubric
        else "None listed"
    )
    
    system_prompt = """You are an independent technical hiring auditor.
Your job is to audit the skills evaluation report and verify whether the score is genuinely justified, or if the screening agent hallucinated skills or overlooked hard dealbreakers.

AUDIT RULES:
1. Verify if the screening agent credited the candidate in "Matched Core Skills" for technologies NOT supported by their skills or projects.
2. Check if the job description contains strict non-technical dealbreakers (e.g. required active security clearance, mandatory relocation outside candidate's region, specific legal certifications).
3. If a strict non-technical dealbreaker exists, set "hard_dealbreaker": true.
4. If the agent overstated or hallucinated a skill match, set "critical_flaw_found": true and specify calibrated "penalty_points" (integer between 1 and 15).
5. If the high score is legitimately backed up by the candidate's projects and skills, set both flags to false and "penalty_points": 0.

OUTPUT FORMAT:
Return ONLY a valid JSON object:
{
    "audit_passed": <true or false>,
    "hard_dealbreaker": <true or false>,
    "critical_flaw_found": <true or false>,
    "reason": "<explanation or empty string>",
    "penalty_points": <integer from 0 to 15>
}"""

    user_prompt = f"""CANDIDATE:
- Academic Level: {candidate.academic_level}
- Skills: {', '.join(candidate.skills)}
- Projects:
{projects_summary}

EVALUATED JOB:
Title: {state["job"].title}
Company: {state["job"].company}
Description:
{state["job"].description}

PREVIOUS EVALUATION:
Score: {match_result.score}/100
Reasoning: {match_result.reasoning}
Chain of Thought: {match_result.chain_of_thought}
Matched Core Skills identified: {matched_skills}
Missing Skills identified: {', '.join(match_result.missing_skills)}
"""

    try:
        response = await router.acompletion(
            model="gpt-6-luna",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"},
            reasoning_effort="low",
            max_tokens=1024
        )
        content = (response.choices[0].message.content or "").strip()
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            content = match.group(0)
        data = json.loads(content)
        
        if data.get("hard_dealbreaker"):
            flaw_reason = data.get("reason", "Hard dealbreaker identified during audit.")
            match_result.score = 0
            match_result.auto_reject = True
            match_result.reasoning = f"{match_result.reasoning} | [Auditor REJECT]: {flaw_reason}"
            return {"final_match_result": match_result}

        if data.get("critical_flaw_found"):
            raw_penalty = int(data.get("penalty_points", 10))
            penalty = max(0, min(15, raw_penalty))
            match_result.score = max(0, match_result.score - penalty)
            flaw_reason = data.get("reason", "Audit identified discrepancies in skill match.")
            match_result.reasoning = f"{match_result.reasoning} | [Auditor -{penalty}pts]: {flaw_reason}"
            return {"final_match_result": match_result}
    except Exception as e:
        logger.warning(f"Devil's Advocate audit failed: {e}")
    
    return {}

def check_rejection(state: JobState):
    return "end" if state.get("is_rejected") else "next"

workflow = StateGraph(JobState)

workflow.add_node("scraper_validation", scraper_validation_node)
workflow.add_node("parallel_agents", parallel_agents_node)
workflow.add_node("skills_agent", skills_agent_node)
workflow.add_node("devils_advocate", devils_advocate_node)

workflow.set_entry_point("scraper_validation")

# scraper -> parallel agents
workflow.add_conditional_edges(
    "scraper_validation",
    check_rejection,
    {"end": END, "next": "parallel_agents"}
)

# parallel agents -> skills agent
workflow.add_conditional_edges(
    "parallel_agents",
    check_rejection,
    {"end": END, "next": "skills_agent"}
)

# skills agent -> devils advocate
workflow.add_edge("skills_agent", "devils_advocate")

# devils advocate -> END
workflow.add_edge("devils_advocate", END)

job_graph = workflow.compile()

async def evaluate_job(
    candidate_profile: CandidateProfile, 
    job: JobPosting, 
    target_yoe: int = 0
) -> MatchResult:
    
    initial_state = {
        "job": job,
        "candidate_profile": candidate_profile,
        "target_yoe": target_yoe,
        "is_rejected": False,
        "reject_reason": "",
        "final_match_result": None
    }
    
    final_state = await job_graph.ainvoke(initial_state)
    
    if final_state.get("is_rejected"):
        return MatchResult(
            chain_of_thought=f"Early Rejection: {final_state.get('reject_reason')}",
            score=0,
            reasoning=final_state.get("reject_reason"),
            missing_skills=[],
            upskill_action="",
            auto_reject=True,
            is_skills_evaluated=False
        )
        
    return final_state["final_match_result"]
