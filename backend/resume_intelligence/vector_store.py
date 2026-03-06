import faiss
import numpy as np

index = faiss.IndexFlatL2(1536)

def store_embeddings(embeddings):

    vectors = np.array(embeddings).astype("float32")

    index.add(vectors)