import faiss
import numpy as np

class ResumeVectorStore:

    def __init__(self, dimension):

        self.index = faiss.IndexFlatL2(dimension)
        self.text_chunks = []

    def add(self, embedding, text):

        vector = np.array([embedding]).astype("float32")

        self.index.add(vector)

        self.text_chunks.append(text)

    def search(self, query_embedding, k=3):

        query_vector = np.array([query_embedding]).astype("float32")

        distances, indices = self.index.search(query_vector, k)

        results = []

        for idx in indices[0]:
            results.append(self.text_chunks[idx])

        return results