from .embeddings.embedder import generate_embedding
from .embeddings.chunker import chunk_resume
from .embeddings.vector_store import ResumeVectorStore

def build_resume_index(resume_profile):

    chunks = chunk_resume(resume_profile)

    first_embedding = generate_embedding(chunks[0])

    dimension = len(first_embedding)

    store = ResumeVectorStore(dimension)

    for chunk in chunks:

        emb = generate_embedding(chunk)

        store.add(emb, chunk)

    return store