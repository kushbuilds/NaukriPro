"""AI-powered scoring and resume tailoring using Google Gemini (free tier)."""
import google.generativeai as genai

class AIEngine:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")
    
    def score_job(self, resume_text: str, job_title: str, job_description: str) -> dict:
        """Score a job 0-100 based on resume match. Returns {score, reason}."""
        prompt = f"""Score how well this candidate matches the job (0-100).
Return ONLY a JSON object: {{"score": <number>, "reason": "<one line>"}}

RESUME:
{resume_text[:3000]}

JOB TITLE: {job_title}
JOB DESCRIPTION:
{job_description[:2000]}"""
        
        resp = self.model.generate_content(prompt)
        text = resp.text.strip()
        # Parse JSON from response
        import json, re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"score": 50, "reason": "Could not parse score"}
    
    def tailor_resume(self, resume_text: str, job_title: str, job_description: str) -> str:
        """Return tailored resume content for a specific job."""
        prompt = f"""Tailor this resume for the job below. Keep it truthful but emphasize relevant skills.
Return the improved resume text only, no commentary.

ORIGINAL RESUME:
{resume_text[:4000]}

TARGET JOB: {job_title}
DESCRIPTION:
{job_description[:2000]}"""
        
        resp = self.model.generate_content(prompt)
        return resp.text.strip()
    
    def answer_question(self, resume_text: str, question: str) -> str:
        """Generate an answer to an application question based on resume."""
        prompt = f"""Based on this resume, answer the application question concisely and professionally.
If you cannot determine the answer from the resume, respond with "ASK_USER".

RESUME:
{resume_text[:3000]}

QUESTION: {question}"""
        
        resp = self.model.generate_content(prompt)
        return resp.text.strip()
