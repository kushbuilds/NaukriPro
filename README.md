# NaukriPro 🤖

Auto-apply for jobs on LinkedIn and Naukri.com — AI-powered, with human confirmation before every submission.

## What It Does

1. **Searches** LinkedIn & Naukri.com for jobs matching your criteria
2. **Scores** each job (0–100) against your resume using AI
3. **Shows** you the top matches — you pick which to apply to
4. **Tailors** your resume for each selected job
5. **Auto-fills** every application field in a real browser
6. **STOPS** before submitting — shows a summary and waits for your `GO`

## Hard Rules

- ❌ NEVER submits without your explicit `GO`
- ❌ NEVER guesses unknown fields — asks you instead
- ⚠️ STOPS on CAPTCHA or login screens and alerts you

## Setup

```bash
cd /Users/kushmittal/Documents/Projects/NaukriPro

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Get a Free Gemini API Key

1. Go to https://aistudio.google.com/apikey
2. Sign in with Google
3. Click "Create API Key"
4. Copy it — you'll paste it when the tool asks

## Run

```bash
source venv/bin/activate
python main.py
```

The tool will ask for:
- Your name, email, phone, LinkedIn
- Job titles to search
- Location preference
- Path to your resume (.pdf or .docx)
- Gemini API key (or set `GEMINI_API_KEY` env var)

## During Use

| Situation | What to do |
|-----------|------------|
| CAPTCHA appears | Solve it, type `done` |
| Login required | Log in manually, type `done` |
| Unknown field | Type the answer when asked |
| Pre-submission review | Type `GO` to submit or `SKIP` to skip |
| Resume upload fails | Upload manually, type `done` |

## Tips

- Run during the day so you're available for prompts
- Keep your resume file updated
- One session can handle multiple applications back-to-back
- The browser is visible — you can watch everything happening
