from resume_intelligence.resume_parser import extract_text
from resume_intelligence.llm_parser import parse_resume
from resume_intelligence.resume_rag import build_resume_index
from resume_intelligence.embeddings.embedder import generate_embedding

# extract resume text
text = extract_text("sample_resume.pdf")

# parse resume into structured object
resume_profile = parse_resume(text)

# build vector index
vector_store = build_resume_index(resume_profile)

# test query
query = "website for recommending recipes"

query_embedding = generate_embedding(query)

results = vector_store.search(query_embedding)

print("\nSemantic Search Results:\n")

for r in results:
    print(r)