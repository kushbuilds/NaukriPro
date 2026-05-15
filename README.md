# NaukriPro 🤖

Auto-apply for jobs on LinkedIn and Naukri.com — AI-powered, with human confirmation before every submission.

## Features

- 🔍 **Job Search** — Scrapes LinkedIn & Naukri.com for matching roles
- 📊 **AI Scoring** — Scores each job (0–100) against your resume
- ✍️ **Resume Tailoring** — Generates a custom .docx resume per job
- 📝 **Auto-Fill** — Fills every application field in a real browser
- 🔄 **Multi-Step Forms** — Handles Next/Continue multi-page applications
- 🔐 **Login Persistence** — Saves cookies so you only log in once
- 📋 **Application Tracker** — Logs all applications, skips duplicates
- ⛔ **Never submits without your GO**

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
4. Copy it — you'll paste it when the tool asks (or set `GEMINI_API_KEY` env var)

## Run

### Web UI (recommended)
```bash
source venv/bin/activate
python app.py
```
Then open **http://localhost:5000** in your browser.

### CLI mode
```bash
source venv/bin/activate
python main.py
```

## What It Asks You

- Your name, email, phone, LinkedIn URL
- Job titles to search (comma-separated)
- Location preference
- Which boards to search (LinkedIn, Naukri, or both)
- Path to your resume (.pdf or .docx)
- Gemini API key

## During Use

| Situation | What to do |
|-----------|------------|
| CAPTCHA appears | Solve it, type `done` |
| Login required | Log in manually, type `done` |
| Unknown field | Type the answer when asked |
| Pre-submission review | Type `GO` to submit, `SKIP` to skip, or `EDIT` to make manual changes |
| Resume upload fails | Upload manually, type `done` |

## Project Structure

```
NaukriPro/
├── app.py               # Web UI server (Flask) — run this
├── main.py              # CLI mode alternative
├── config.py            # Interactive user input (CLI)
├── resume_parser.py     # PDF/DOCX text extraction
├── ai_engine.py         # Gemini AI (scoring, tailoring, Q&A)
├── scraper.py           # LinkedIn & Naukri job scraping
├── applicator.py        # Form filling & multi-step navigation
├── auth.py              # Login & cookie persistence
├── tracker.py           # Application history & dedup
├── resume_generator.py  # Tailored .docx generation
├── templates/index.html # Web UI frontend
├── static/style.css     # UI styling
├── requirements.txt     # Dependencies
├── .gitignore
├── applied_jobs.json    # (generated) application log
├── tailored_resumes/    # (generated) per-job resumes
└── .cookies/            # (generated) saved login sessions
```

## Tips

- Run during the day so you're available for prompts
- Keep your resume file updated
- One session can handle multiple applications back-to-back
- Type `all` when asked which jobs to apply to
- Cookies persist between sessions — login once per platform
- Check `applied_jobs.json` to see your application history
