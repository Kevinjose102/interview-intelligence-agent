from .resume_parser import extract_text
from .llm_parser import parse_resume
from .embedding_engine import generate_embeddings
from .vector_store import store_embeddings

def process_resume(file_path):

    text = extract_text(file_path)

    structured_resume = parse_resume(text)

    embeddings = generate_embeddings(structured_resume)

    store_embeddings(embeddings)

    return structured_resume