from typing import TypedDict, Optional, Any
from langgraph.graph import StateGraph, END
from app.models.schemas import JobPosting, CandidateProfile, MatchResult
from app.agent.language_agent import evaluate_language
from app.agent.experience_agent import evaluate_experience
from app.agent.skills_agent import evaluate_skills
from app.agent.llm_router import router
import json
import logging

logger = logging.getLogger(__name__)

class JobState(TypedDict):
    job: JobPosting
    candidate_profile: CandidateProfile
    target_yoe: int
    
    # intermediate states
    is_rejected: bool
    reject_reason: str
    strategy: str
    final_match_result: Optional[MatchResult]

#antibot and correct jobs scraping node
async def scraper_validation_node(state: JobState):
    job = state["job"]
    text = job.description.lower()
    anti_bot_phrases = ["enable cookies", "verify you are a human", "access denied", "security check", "captcha"]
    for phrase in anti_bot_phrases:
        if phrase in text and len(text) < 1500:
            logger.info(f"Scraper validation rejected job {job.id}: Anti-bot detected.")
            return {"is_rejected": True, "reject_reason": "Anti-bot/Scraper blocked text detected."}
    return {"is_rejected": False, "reject_reason": ""}

import asyncio

# concurrent experience and language filters in order to reduce the latency
async def parallel_agents_node(state: JobState):
    lang_task = evaluate_language(state["candidate_profile"], state["job"])
    exp_task = evaluate_experience(state["job"], state["target_yoe"], state["candidate_profile"].academic_level)
    
    lang_res, exp_res = await asyncio.gather(lang_task, exp_task)
    
    if lang_res.is_rejected:
        return {"is_rejected": True, "reject_reason": f"Language filter rejected: {lang_res.reason}"}
    if exp_res.is_rejected:
        return {"is_rejected": True, "reject_reason": f"Experience filter rejected: {exp_res.reason}"}
        
    return {}

async def strategy_node(state: JobState):
    prompt = f"""You are a recruiter strategist. Read the Job Description and the Candidate's profile summary.
Generate a single-sentence evaluation strategy for the skills agent agent. Tell it what exactly to focus on when comparing this candidate to this specific job.

Job Title: {state["job"].title}
Job Desc: {state["job"].description[:1500]}
Candidate Summary: {state["candidate_profile"].experience_summary}

Strategy (1 sentence):"""
    try:
        response = await router.acompletion(
            model="gpt-6-luna",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50
        )
        strategy = response.choices[0].message.content.strip()
        return {"strategy": strategy}
    except Exception as e:
        logger.warning(f"Strategy generation failed: {e}")
        return {"strategy": ""}

async def skills_agent_node(state: JobState):
    res = await evaluate_skills(state["candidate_profile"], state["job"], state.get("strategy"))
    res.is_skills_evaluated = True
    return {"final_match_result": res}

async def devils_advocate_node(state: JobState):
    match_result = state.get("final_match_result")
    if not match_result or match_result.score <= 85:
        return {}
        
    prompt = f"""You are the Devil's Advocate for technical hiring.
The previous AI agent gave this candidate a very high match score ({match_result.score}/100).
Your job is to find the single biggest reason this candidate should actually be REJECTED or why the score is too optimistic.

Job Title: {state["job"].title}
Job Desc: {state["job"].description[:1500]}
Candidate Skills: {state["candidate_profile"].skills}
Agent's Reasoning: {match_result.reasoning}

If you find a critical flaw, return a JSON object: {{"found_flaw": true, "reason": "<flaw description>"}}
If it genuinely looks like a perfect match with no obvious flaws, return: {{"found_flaw": false, "reason": ""}}
"""
    try:
        response = await router.acompletion(
            model="gpt-6-luna",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=100
        )
        data = json.loads(response.choices[0].message.content)
        if data.get("found_flaw"):
            match_result.score = max(0, match_result.score - 15) # penalize additionally so that it goes below the threshold
            match_result.reasoning = f"{match_result.reasoning} | [Devil's Advocate Penalty]: {data.get('reason')}"
            return {"final_match_result": match_result}
    except Exception as e:
        logger.warning(f"Devil's Advocate failed: {e}")
    
    return {}

# langgraph setup
def check_rejection(state: JobState):
    return "end" if state.get("is_rejected") else "next"

workflow = StateGraph(JobState)

workflow.add_node("scraper_validation", scraper_validation_node)
workflow.add_node("parallel_agents", parallel_agents_node)
workflow.add_node("strategy", strategy_node)
workflow.add_node("skills_agent", skills_agent_node)
workflow.add_node("devils_advocate", devils_advocate_node)

workflow.set_entry_point("scraper_validation")

# scraper -> parallel agents
workflow.add_conditional_edges(
    "scraper_validation",
    check_rejection,
    {"end": END, "next": "parallel_agents"}
)

# parallel agents -> strategy
workflow.add_conditional_edges(
    "parallel_agents",
    check_rejection,
    {"end": END, "next": "strategy"}
)

# strategy -> skills agent
workflow.add_edge("strategy", "skills_agent")

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
        "strategy": "",
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
