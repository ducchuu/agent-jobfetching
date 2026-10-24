import json
import re
import logging
from app.config import settings
from app.models.schemas import JobPosting, MatchResult, CandidateProfile, SkillsRubricOutput
from app.agent.llm_router import router, EvaluationTransientError, log_cache_metrics

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are an expert technical hiring screener helping an engineering team pre-screen candidates for software, AI, and robotics roles.
Your task is to analyze the candidate's skills and technical projects against the job description and output a structured rubric.
Arithmetic for final scoring is handled deterministically by the system based on your extracted rubric.

EVALUATION PRINCIPLES:
1. Treat deep technical projects (academic thesis, open-source, hardware deployments) as fully legitimate engineering experience.
2. Distinguish clearly between CORE mandatory skills (dealbreakers for day-1 functionality) and SECONDARY tooling (learnable on the job).
3. If the candidate has worked with closely related technologies (e.g., PyTorch vs TensorFlow, ROS vs autonomous control loops, FastAPI vs Flask), treat this as strong transferable capability.
4. Set "hard_dealbreaker_found" to true ONLY if the job is completely outside the candidate's engineering domain (e.g., pure front-end web UI, graphic design, sales, legacy enterprise Java/COBOL) or has non-negotiable security requirements.

OUTPUT FORMAT:
You MUST return a valid JSON object matching the following structure:
{{
    "chain_of_thought": "<2-3 sentence technical evaluation of project depth and stack alignment>",
    "matched_core_skills": ["<skill1>", "<skill2>"],
    "missing_core_skills": ["<mandatory core technology completely missing>"],
    "missing_secondary_skills": ["<nice-to-have or peripheral tool missing>"],
    "project_relevance_bonus": <integer 0 to 15 based on direct project applicability>,
    "hard_dealbreaker_found": <true or false>,
    "reasoning_summary": "<1-2 sentence executive assessment of fit>",
    "upskill_recommendation": "<one concrete weekend engineering action>"
}}

FEW-SHOT EVALUATION EXAMPLES:

--- Example 1: High Match (AI / Robotics Role with High Project Relevance) ---
Job: Autonomous Systems Engineer (Python, PyTorch, Reinforcement Learning, Docker, ROS2)
Candidate Highlights: Autonomous Drone with PPO, Hexacopter Co-Optimization with PyTorch/RL, Python.
Output:
{{
    "chain_of_thought": "The candidate has hands-on deployment of PPO reinforcement learning and flight controllers in hardware, directly matching the core autonomy needs. Lacks explicit ROS2 and production Docker in projects, but possesses foundational robotics control and Python expertise.",
    "matched_core_skills": ["Python", "PyTorch", "Reinforcement Learning", "Control Systems"],
    "missing_core_skills": [],
    "missing_secondary_skills": ["ROS2", "Docker"],
    "project_relevance_bonus": 12,
    "hard_dealbreaker_found": false,
    "reasoning_summary": "Exceptional alignment with autonomous robotics and RL algorithms; demonstrated physical hardware flight deployment.",
    "upskill_recommendation": "Package the drone PPO flight controller into a ROS2 package running in a Docker container."
}}

--- Example 2: Complete Domain Mismatch (Front-End Web Development) ---
Job: Senior React Developer (React, Next.js, TypeScript, Tailwind CSS, Figma to Code)
Candidate Highlights: Python, Embedded Systems, Reinforcement Learning, VHDL.
Output:
{{
    "chain_of_thought": "The position demands deep expertise in modern client-side JavaScript frameworks and web UI design systems. The candidate's background is entirely centered on robotics, embedded hardware, and AI algorithms.",
    "matched_core_skills": [],
    "missing_core_skills": ["React", "TypeScript", "Next.js", "Tailwind CSS"],
    "missing_secondary_skills": ["Figma"],
    "project_relevance_bonus": 0,
    "hard_dealbreaker_found": true,
    "reasoning_summary": "Fundamental domain mismatch: pure front-end web development role versus candidate's robotics and AI systems focus.",
    "upskill_recommendation": "Do not pursue unless pivoting careers into front-end UI engineering."
}}

--- Example 3: Moderate Match (NLP / Conversational AI with Secondary Tooling Gap) ---
Job: NLP Engineer (Python, Transformers, Speech-to-Text, FastAPI, Databricks, Apache Spark)
Candidate Highlights: Voice-Driven Conversational AI with BERT and Whisper, Flask, SQLite.
Output:
{{
    "chain_of_thought": "Candidate built an end-to-end voice interactive pipeline using BERT and Whisper, proving hands-on NLP and speech capability. Lacks enterprise big-data infrastructure tools (Spark, Databricks), but core models and Python stack match.",
    "matched_core_skills": ["Python", "NLP", "BERT", "Speech-to-Text / Whisper"],
    "missing_core_skills": [],
    "missing_secondary_skills": ["Databricks", "Apache Spark"],
    "project_relevance_bonus": 8,
    "hard_dealbreaker_found": false,
    "reasoning_summary": "Strong core NLP and speech recognition implementation experience, with learnable secondary enterprise data pipeline gaps.",
    "upskill_recommendation": "Complete a practical tutorial processing audio datasets using PySpark on Databricks Community Edition."
}}

CANDIDATE PROFILE:
{candidate_json}"""

acompletion = router.acompletion

async def evaluate_skills(candidate_profile: CandidateProfile, job: JobPosting) -> MatchResult:
    candidate_data = {
        "name": candidate_profile.name,
        "academic_level": candidate_profile.academic_level,
        "skills": candidate_profile.skills,
        "languages": candidate_profile.languages,
        "projects": [p.model_dump() for p in candidate_profile.projects],
        "experience_summary": candidate_profile.experience_summary,
        "target_job_titles": candidate_profile.target_job_titles
    }
    
    static_system_content = SYSTEM_PROMPT_TEMPLATE.format(
        candidate_json=json.dumps(candidate_data, indent=2)
    )
    
    dynamic_job_content = (
        f"JOB POSTING:\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Description: {job.description}\n"
    )

    try:
        response = await acompletion(
            model="gpt-6.1-sol",
            messages=[
                {"role": "system", "content": static_system_content},
                {"role": "user", "content": dynamic_job_content}
            ],
            response_format={"type": "json_object"},
            reasoning_effort="low",
            max_tokens=4096
        )
        log_cache_metrics(response)
        
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise EvaluationTransientError("LLM returned empty content from skills agent.")

        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            content = match.group(0)
        
        data = json.loads(content)
        rubric = SkillsRubricOutput.model_validate(data)
        computed_score = rubric.computed_score

        return MatchResult(
            chain_of_thought=rubric.chain_of_thought,
            score=computed_score,
            reasoning=rubric.reasoning_summary,
            missing_skills=rubric.missing_core_skills + rubric.missing_secondary_skills,
            upskill_action=rubric.upskill_recommendation,
            auto_reject=rubric.hard_dealbreaker_found,
            is_skills_evaluated=True,
            rubric=rubric
        )
    except (json.JSONDecodeError, KeyError, ValueError) as parse_err:
        logger.error(f"Failed to parse SkillsRubricOutput for job {job.id}: {parse_err}")
        return MatchResult(
            chain_of_thought=f"Parse failure: {parse_err}",
            score=0,
            reasoning="Failed to parse structured rubric from model response.",
            missing_skills=[],
            upskill_action="",
            auto_reject=True,
            is_skills_evaluated=True
        )
    except EvaluationTransientError:
        raise
    except Exception as e:
        # Transient errors (network, timeout, 429) must not be treated as permanent rejections
        logger.error(f"Transient error during skills evaluation for job {job.id}: {e}")
        raise EvaluationTransientError(f"Skills evaluation transient failure: {e}") from e
