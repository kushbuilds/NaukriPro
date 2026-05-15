"""NaukriPro Web UI — Flask server with SSE for live updates."""
import os
import json
import asyncio
import threading
import queue
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response
from werkzeug.utils import secure_filename

from resume_parser import parse_resume
from ai_engine import AIEngine
from scraper import scrape_linkedin, scrape_naukri, get_job_description
from applicator import fill_application, show_summary_and_submit
from tracker import is_already_applied, log_application
from resume_generator import save_tailored_resume
from auth import ensure_naukri_login, ensure_linkedin_login

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / "uploads"
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)

# Shared state
state = {
    "config": None,
    "resume_text": "",
    "jobs": [],
    "ai": None,
    "event_queue": queue.Queue(),
    "response_queue": queue.Queue(),
}


def emit(msg_type, **kwargs):
    """Push an event to the SSE stream."""
    state["event_queue"].put(json.dumps({"type": msg_type, **kwargs}))


def ask_user(question: str) -> str:
    """Ask user a question via UI and wait for response."""
    emit("ask_user", question=question)
    return state["response_queue"].get()  # blocks until user responds


def confirm_submission(summary: str) -> str:
    """Ask user GO/SKIP via UI."""
    emit("confirm", summary=summary)
    return state["response_queue"].get()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/search', methods=['POST'])
def search_jobs():
    """Handle job search form submission."""
    try:
        # Save resume file
        resume_file = request.files.get('resume')
        if not resume_file:
            return jsonify({"error": "Resume file required"}), 400

        filename = secure_filename(resume_file.filename)
        resume_path = str(app.config['UPLOAD_FOLDER'] / filename)
        resume_file.save(resume_path)

        # Build config
        boards = request.form.getlist('boards')
        gemini_key = request.form.get('gemini_key') or os.environ.get('GEMINI_API_KEY', '')

        if not gemini_key:
            return jsonify({"error": "Gemini API key required"}), 400

        config = {
            "name": request.form['name'],
            "email": request.form['email'],
            "phone": request.form['phone'],
            "linkedin": request.form.get('linkedin', ''),
            "job_titles": [t.strip() for t in request.form['job_titles'].split(',')],
            "location": request.form['location'],
            "boards": boards,
            "resume_path": resume_path,
            "gemini_key": gemini_key,
        }

        state["config"] = config
        state["resume_text"] = parse_resume(resume_path)
        state["ai"] = AIEngine(gemini_key)

        # Run scraping in async
        jobs = asyncio.run(scrape_and_score(config, state["ai"], state["resume_text"]))
        state["jobs"] = jobs

        return jsonify({"jobs": jobs})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


async def scrape_and_score(config, ai, resume_text):
    """Scrape jobs and score them."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        all_jobs = []
        if "linkedin" in config["boards"]:
            jobs = await scrape_linkedin(page, config["job_titles"], config["location"])
            all_jobs.extend(jobs)
        if "naukri" in config["boards"]:
            jobs = await scrape_naukri(page, config["job_titles"], config["location"])
            all_jobs.extend(jobs)

        # Filter already applied
        all_jobs = [j for j in all_jobs if not is_already_applied(j.get("url", ""))]

        # Score top 10 (faster)
        scored = []
        for job in all_jobs[:10]:
            desc = await get_job_description(page, job["url"])
            job["description"] = desc
            try:
                result = ai.score_job(resume_text, job["title"], desc)
                job["score"] = result.get("score", 50)
                job["reason"] = result.get("reason", "")
            except Exception:
                job["score"] = 50
                job["reason"] = ""
            scored.append(job)

        await browser.close()

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:10]


@app.route('/api/apply')
def apply_stream():
    """SSE endpoint — streams live application progress."""
    indices = [int(i) for i in request.args.get('indices', '').split(',') if i]
    selected = [state["jobs"][i] for i in indices if i < len(state["jobs"])]

    def run_applications():
        asyncio.run(apply_to_jobs(selected))

    thread = threading.Thread(target=run_applications, daemon=True)
    thread.start()

    def event_stream():
        while True:
            try:
                msg = state["event_queue"].get(timeout=120)
                yield f"data: {msg}\n\n"
                if '"type": "done"' in msg:
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type':'log','message':'Waiting...','level':'info'})}\n\n"

    return Response(event_stream(), mimetype='text/event-stream')


@app.route('/api/respond', methods=['POST'])
def respond():
    """Receive user's answer to a question or GO/SKIP."""
    data = request.get_json()
    state["response_queue"].put(data.get("answer", ""))
    return jsonify({"ok": True})


async def apply_to_jobs(jobs):
    """Apply to selected jobs with live updates."""
    from playwright.async_api import async_playwright

    config = state["config"]
    ai = state["ai"]
    resume_text = state["resume_text"]
    applied = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()

        # Login if needed
        if "naukri" in config["boards"]:
            emit("log", message="Logging into Naukri.com...", level="info")
            await ensure_naukri_login(page, context)
        if "linkedin" in config["boards"]:
            emit("log", message="Logging into LinkedIn...", level="info")
            await ensure_linkedin_login(page, context)

        for i, job in enumerate(jobs, 1):
            emit("log", message=f"[{i}/{len(jobs)}] {job['title']} @ {job['company']}", level="info")

            # Tailor resume
            emit("log", message="Tailoring resume...", level="info")
            tailored_path = ""
            try:
                tailored_text = ai.tailor_resume(resume_text, job["title"], job["description"])
                tailored_path = save_tailored_resume(tailored_text, job["company"], job["title"])
                emit("log", message="✓ Resume tailored", level="success")
            except Exception:
                emit("log", message="Using original resume", level="warning")

            # Fill application
            emit("log", message="Filling application form...", level="info")
            filled = await fill_application_web(page, job, config, ai, resume_text, tailored_path)

            if filled:
                # Ask for confirmation
                summary = f"{job['title']} @ {job['company']} | Fields: {len(filled)}"
                choice = confirm_submission(summary)

                if choice.upper() == "GO":
                    # Submit
                    submit_keywords = ["submit", "submit application", "apply", "send"]
                    buttons = await page.query_selector_all("button[type='submit'], button")
                    submitted = False
                    for btn in buttons:
                        try:
                            text = (await btn.inner_text()).strip().lower()
                            if any(kw in text for kw in submit_keywords):
                                await btn.click()
                                await page.wait_for_timeout(3000)
                                submitted = True
                                break
                        except Exception:
                            continue

                    if submitted:
                        log_application(job, "submitted")
                        applied += 1
                        emit("log", message=f"✅ Submitted: {job['title']} @ {job['company']}", level="success")
                    else:
                        emit("log", message="Could not find submit button — please submit manually in browser", level="warning")
                        ask_user("Type 'done' after submitting manually")
                        log_application(job, "submitted")
                        applied += 1
                else:
                    log_application(job, "skipped")
                    emit("log", message="Skipped", level="warning")
            else:
                emit("log", message="Could not fill form, skipping", level="error")
                log_application(job, "failed")

        await browser.close()

    emit("done", message=f"Done! Applied to {applied}/{len(jobs)} jobs.")


async def fill_application_web(page, job, config, ai, resume_text, tailored_path):
    """Fill application — web version that uses emit/ask_user instead of console."""
    from applicator import detect_blockers, click_apply_button, click_next_button

    url = job.get("url", "")
    if not url:
        return {}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        emit("log", message=f"Failed to load: {e}", level="error")
        return {}

    blocker = await detect_blockers(page)
    if blocker:
        ask_user(f"{'CAPTCHA' if blocker == 'captcha' else 'Login'} detected — handle it in the browser, then type 'done'")
        await page.wait_for_timeout(2000)

    await click_apply_button(page)

    blocker = await detect_blockers(page)
    if blocker:
        ask_user(f"{'CAPTCHA' if blocker == 'captcha' else 'Login'} detected — handle it, then type 'done'")
        await page.wait_for_timeout(2000)

    # Fill fields across steps
    all_filled = {}
    for step in range(10):
        inputs = await page.query_selector_all(
            "input[type='text'], input[type='email'], input[type='tel'], input[type='url'], "
            "input:not([type='hidden']):not([type='file']):not([type='checkbox'])"
            ":not([type='radio']):not([type='submit']):not([type='button']):not([type='password'])"
        )

        for inp in inputs:
            try:
                if not await inp.is_visible():
                    continue
                current = await inp.input_value()
                if current.strip():
                    continue

                inp_id = await inp.get_attribute("id") or ""
                name = await inp.get_attribute("name") or ""
                placeholder = await inp.get_attribute("placeholder") or ""
                aria_label = await inp.get_attribute("aria-label") or ""

                label = ""
                if inp_id:
                    label_el = await page.query_selector(f"label[for='{inp_id}']")
                    if label_el:
                        label = (await label_el.inner_text()).strip()

                hint = label or aria_label or placeholder or name
                if not hint:
                    continue

                h = hint.lower()
                value = ""
                if any(k in h for k in ["full name", "your name"]):
                    value = config["name"]
                elif any(k in h for k in ["first name", "fname"]):
                    value = config["name"].split()[0]
                elif any(k in h for k in ["last name", "lname", "surname"]):
                    parts = config["name"].split()
                    value = parts[-1] if len(parts) > 1 else ""
                elif "name" in h and "company" not in h:
                    value = config["name"]
                elif any(k in h for k in ["email", "e-mail"]):
                    value = config["email"]
                elif any(k in h for k in ["phone", "mobile", "contact"]):
                    value = config["phone"]
                elif "linkedin" in h:
                    value = config["linkedin"]
                elif any(k in h for k in ["city", "location"]):
                    value = config["location"]
                else:
                    answer = ai.answer_question(resume_text, hint)
                    if "ASK_USER" in answer:
                        value = ask_user(f"Please provide: {hint}")
                    else:
                        value = answer

                if value:
                    await inp.fill(value)
                    all_filled[hint] = value
            except Exception:
                continue

        # Textareas
        for ta in await page.query_selector_all("textarea"):
            try:
                if not await ta.is_visible():
                    continue
                if (await ta.input_value()).strip():
                    continue
                ta_id = await ta.get_attribute("id") or ""
                placeholder = await ta.get_attribute("placeholder") or ""
                label = ""
                if ta_id:
                    lbl = await page.query_selector(f"label[for='{ta_id}']")
                    if lbl:
                        label = (await lbl.inner_text()).strip()
                hint = label or placeholder or "Additional info"
                answer = ai.answer_question(resume_text, hint)
                if "ASK_USER" in answer:
                    answer = ask_user(f"Please provide: {hint}")
                await ta.fill(answer)
                all_filled[hint] = answer[:60] + "..."
            except Exception:
                continue

        # File upload
        for fi in await page.query_selector_all("input[type='file']"):
            try:
                upload = tailored_path if tailored_path else config["resume_path"]
                await fi.set_input_files(upload)
                all_filled["Resume"] = upload
            except Exception:
                ask_user("Could not upload resume — please upload manually, then type 'done'")

        # Next step?
        has_next = await click_next_button(page)
        if not has_next:
            break
        await page.wait_for_timeout(2000)

    emit("log", message=f"Filled {len(all_filled)} fields", level="success")
    return all_filled


if __name__ == '__main__':
    print("\n🤖 NaukriPro running at: http://localhost:8080\n")
    app.run(debug=False, port=8080, host="127.0.0.1")
