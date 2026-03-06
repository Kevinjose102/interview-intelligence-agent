from resume_intelligence.resume_parser import extract_text
from resume_intelligence.llm_parser import parse_resume

# path to resume pdf
resume_path = "sample_resume.pdf"

text = extract_text(resume_path)

print("----- RAW TEXT -----")
print(text[:500])

structured_resume = parse_resume(text)

print("\n----- STRUCTURED OUTPUT -----")
print(structured_resume)