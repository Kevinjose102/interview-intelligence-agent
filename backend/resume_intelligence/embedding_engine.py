from openai import OpenAI

client = OpenAI()

def generate_embeddings(resume_profile):

    text_chunks = []

    text_chunks.extend(resume_profile.skills)

    for project in resume_profile.projects:
        text_chunks.append(project.name)
        text_chunks.append(project.description)

    embeddings = []

    for chunk in text_chunks:

        emb = client.embeddings.create(
            model="text-embedding-3-small",
            input=chunk
        )

        embeddings.append(emb.data[0].embedding)

    return embeddings