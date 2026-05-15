"""AI-powered scoring and resume tailoring using Google Gemini (free tier)."""
import json
import re
import time
import google.generativeai as genai
from rich.console import Console

console = Console()


class AIEngine:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def _call(self, prompt: str, retries: int = 3) -> str:
        """Call Gemini with retry logic for rate limits."""
        for attempt in range(retries):
            try:
                resp = self.model.generate_content(prompt)
                return resp.text.strip()
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    wait = 2 ** (attempt + 1)
                    console.print(f"[yellow]  Rate limited, waiting {wait}s...[/yellow]")
                    time.sleep(wait)
                elif attempt == retries - 1:
                    console.print(f"[red]  AI error: {e}[/red]")
                    return ""
                else:
                    time.sleep(1)
        return ""

    def score_job(self, resume_text: str, job_title: str, job_description: str) -> dict:
        """Score a job 0-100 based on resume match."""
        prompt = f"""Score how well this candidate matches the job (0-100).
Return ONLY a JSON object: {{"score": <number>, "reason": "<one line>"}}

RESUME:
{resume_text[:3000]}

JOB TITLE: {job_title}
JOB DESCRIPTION:
{job_description[:2000]}"""

        text = self._call(prompt)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"score": 50, "reason": "Could not parse score"}

    def tailor_resume(self, resume_text: str, job_title: str, job_description: str) -> str:
        """Return tailored resume content optimized for 90-100 match score."""
        prompt = f"""You are an expert resume writer. Rewrite this resume to be a 95-100% match for the job below.

Rules:
- Keep all information TRUTHFUL — do not invent experience or skills the candidate doesn't have
- Reorder sections to highlight the most relevant experience first
- Use keywords and phrases from the job description naturally
- Quantify achievements where possible
- Remove irrelevant details that don't serve this application
- Match the tone and terminology of the job posting
- Ensure ATS (Applicant Tracking System) compatibility
- Keep it concise (1-2 pages worth of content)

Return ONLY the improved resume text, no commentary.

ORIGINAL RESUME:
{resume_text[:4000]}

TARGET JOB: {job_title}
DESCRIPTION:
{job_description[:2000]}"""

        return self._call(prompt)

    def answer_question(self, resume_text: str, question: str) -> str:
        """Generate an answer to an application question based on resume."""
        prompt = f"""Based on this resume, answer the application question concisely and professionally.
If you cannot determine the answer from the resume, respond with ONLY "ASK_USER".

RESUME:
{resume_text[:3000]}

QUESTION: {question}"""

        return self._call(prompt)
