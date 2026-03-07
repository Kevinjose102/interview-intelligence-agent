def chunk_resume(resume_profile):

    chunks = []

    # skills
    for skill in resume_profile.skills:
        chunks.append(f"Skill: {skill}")

    # projects
    for project in resume_profile.projects:
        text = f"Project {project.name}. Technologies: {', '.join(project.technologies)}. {project.description}"
        chunks.append(text)

    # experience
    for exp in resume_profile.experience:
        chunks.append(f"Experience: {exp}")

    return chunks