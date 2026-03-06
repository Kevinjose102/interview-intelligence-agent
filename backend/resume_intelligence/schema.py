from pydantic import BaseModel
from typing import List, Optional

class Project(BaseModel):
    name: str
    technologies: List[str]
    description: Optional[str]

class ResumeProfile(BaseModel):
    skills: List[str]
    projects: List[Project]
    experience: List[str]