from .resume_parser import extract_text
from .llm_parser import parse_resume


def process_resume(file_path):
    """
    Extract text from PDF, parse with LLM, return structured profile.
    Returns (profile, raw_text) so the caller can run deep analysis.
    """
    text = extract_text(file_path)
    structured_resume = parse_resume(text)
    return structured_resume, text