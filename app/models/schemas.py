from pydantic import BaseModel, Field
from typing import List, Optional

class JobPosting(BaseModel):
    id: str
    title: str
    company: str
    description: str
    url: str

class LanguageFilterResult(BaseModel):
    is_rejected: bool = Field(..., description="True if the job is written in a language the candidate doesn't speak, or requires a language they don't have.")
    reason: str = Field(..., description="Explanation for the decision.")

class ExperienceFilterResult(BaseModel):
    is_rejected: bool = Field(..., description="True if the job requires Senior/Lead/Manager or more corporate experience than the target.")
    reason: str = Field(..., description="Explanation for the decision.")

class MatchResult(BaseModel):
    chain_of_thought: str = Field(..., description="Step-by-step reasoning evaluating technical skills and projects.")
    score: int = Field(..., description="Match score from 0 to 100")
    reasoning: str = Field(..., description="1-2 sentences on why this fits.")
    missing_skills: List[str] = Field(..., description="Critical skills in the JD the candidate lacks.")
    upskill_action: str = Field(..., description="One concrete action to bridge the gap.")
    auto_reject: bool = Field(..., description="True if the skills/tech stack are a complete mismatch.")
    is_skills_evaluated: bool = Field(False, description="Internal flag to track if the skills agent processed this job")

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
    academic_level: str = Field(default="BSc", description="The highest academic degree obtained by the candidate (e.g., BSc, MSc, PhD).")
    target_job_titles: List[str] = Field(
        ..., 
        description="List of 3 to 5 highly specific job titles that perfectly match this candidate's unique blend of skills and projects."
    )
