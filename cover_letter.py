"""Cover letter generation using AI."""


def generate_cover_letter(ai_engine, resume_text: str, job_title: str, company: str, job_description: str) -> str:
    """Generate a tailored cover letter."""
    prompt = f"""Write a concise, professional cover letter (150-200 words) for this job application.

Rules:
- Be specific to the company and role
- Highlight 2-3 most relevant experiences from the resume
- Show enthusiasm without being generic
- Do NOT use clichés like "I am writing to express my interest"
- Keep it natural and confident
- End with a clear call to action

RESUME:
{resume_text[:3000]}

JOB: {job_title} at {company}
DESCRIPTION:
{job_description[:1500]}

Return ONLY the cover letter text, no subject line or headers."""

    return ai_engine._call(prompt)
