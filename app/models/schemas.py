from pydantic import BaseModel, Field, model_validator
from typing import List, Optional

class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    description: str
    url: str
    raw_description: str = ""
    location: str = ""

class LanguageFilterResult(BaseModel):
    is_rejected: bool = Field(..., description="True if the job is written in a language the candidate doesn't speak, or requires a language they don't have.")
    reason: str = Field(..., description="Explanation for the decision.")

class ExperienceFilterResult(BaseModel):
    is_rejected: bool = Field(..., description="True if the job requires Senior/Lead/Manager or more corporate experience than the target.")
    reason: str = Field(..., description="Explanation for the decision.")

class SkillsRubricOutput(BaseModel):
    chain_of_thought: str = Field(..., description="Step-by-step reasoning evaluating skills, projects, and fit.")
    matched_core_skills: List[str] = Field(default_factory=list, description="Core mandatory skills from JD the candidate has demonstrated.")
    missing_core_skills: List[str] = Field(default_factory=list, description="Mandatory core technologies in the JD the candidate completely lacks.")
    missing_secondary_skills: List[str] = Field(default_factory=list, description="Nice-to-have or secondary tooling skills missing.")
    project_relevance_bonus: int = Field(default=0, ge=0, le=15, description="Bonus (0-15) based on depth and direct relevance of candidate's technical projects to the role.")
    hard_dealbreaker_found: bool = Field(default=False, description="True if the role's core domain is fundamentally mismatched.")
    reasoning_summary: str = Field(..., description="1-2 sentence executive summary of why this fits or does not fit.")
    upskill_recommendation: str = Field(..., description="One concrete weekend action to bridge the most critical skill gap.")

    @model_validator(mode="after")
    def deduplicate_skill_lists(self) -> "SkillsRubricOutput":
        seen_core = {}
        for s in self.missing_core_skills:
            key = s.strip().lower()
            if key and key not in seen_core:
                seen_core[key] = s.strip()
        self.missing_core_skills = list(seen_core.values())

        seen_secondary = {}
        for s in self.missing_secondary_skills:
            key = s.strip().lower()
            if key and key not in seen_core and key not in seen_secondary:
                seen_secondary[key] = s.strip()
        self.missing_secondary_skills = list(seen_secondary.values())
        return self

    @property
    def computed_score(self) -> int:
        if self.hard_dealbreaker_found:
            return 0
        base = 85 + self.project_relevance_bonus
        penalty = (len(self.missing_core_skills) * 10) + (len(self.missing_secondary_skills) * 3)
        return max(0, min(100, base - penalty))


class AuditOutput(BaseModel):
    audit_passed: bool = False
    hard_dealbreaker: bool = False
    critical_flaw_found: bool = False
    reason: str = ""
    penalty_points: int = Field(default=0, ge=0, le=15)

class MatchResult(BaseModel):
    chain_of_thought: str = Field(..., description="Step-by-step reasoning evaluating technical skills and projects.")
    score: int = Field(..., description="Match score from 0 to 100")
    reasoning: str = Field(..., description="1-2 sentences on why this fits.")
    missing_skills: List[str] = Field(..., description="Critical skills in the JD the candidate lacks.")
    upskill_action: str = Field(..., description="One concrete action to bridge the gap.")
    auto_reject: bool = Field(..., description="True if the skills/tech stack are a complete mismatch.")
    is_skills_evaluated: bool = Field(False, description="Internal flag to track if the skills agent processed this job")
    rubric: Optional[SkillsRubricOutput] = Field(default=None, description="Detailed rubric breakdown")

class Project(BaseModel):
    name: str = Field(..., description="Name of the project")
    technologies: List[str] = Field(..., description="List of technologies used")
    description: str = Field(..., description="Summary of the project")

class CandidateProfile(BaseModel):
    name: str = Field(..., description="The name of the candidate")
    skills: List[str] = Field(..., description="List of technical and soft skills")
    languages: List[str] = Field(..., description="Languages spoken by the candidate")
    projects: List[Project] = Field(..., description="List of academic and personal technical projects")
    experience_summary: str = Field(..., description="A short summary of their work experience")
    academic_level: str = Field(default="BSc", description="Highest degree level: BSc, MSc, or PhD")
    target_job_titles: List[str] = Field(
        ..., 
        description="List of 3 to 5 highly specific job titles that perfectly match this candidate's unique blend of skills and projects."
    )

    @model_validator(mode="after")
    def merge_project_technologies_into_skills(self) -> "CandidateProfile":
        normalized_existing = {s.lower(): s for s in self.skills}
        for project in self.projects:
            for tech in project.technologies:
                if tech.lower() not in normalized_existing:
                    normalized_existing[tech.lower()] = tech
        self.skills = list(normalized_existing.values())
        return self
