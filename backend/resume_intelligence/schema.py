from pydantic import BaseModel, field_validator
from typing import List, Optional, Union


class Project(BaseModel):
    name: str
    technologies: List[str] = []
    description: Optional[str] = None


class Experience(BaseModel):
    company: str = ""
    role: str = ""
    duration: str = ""
    description: str = ""


class ResumeProfile(BaseModel):
    skills: List[str] = []
    projects: List[Project] = []
    experience: list = []

    @field_validator("experience", mode="before")
    @classmethod
    def normalize_experience(cls, v):
        """Accept experience as list of strings OR list of dicts."""
        if not v:
            return []
        result = []
        for item in v:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                # Convert dict to a readable string
                parts = []
                if item.get("role"):
                    parts.append(item["role"])
                if item.get("company"):
                    parts.append(f"at {item['company']}")
                if item.get("duration"):
                    parts.append(f"({item['duration']})")
                if item.get("description"):
                    parts.append(f"— {item['description']}")
                result.append(" ".join(parts) if parts else str(item))
            else:
                result.append(str(item))
        return result