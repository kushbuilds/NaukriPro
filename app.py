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
    "stop_flag": False,
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


@app.route('/api/signin', methods=['POST'])
def signin():
    """Open browser for user to sign in, save config."""
    try:
        resume_file = request.files.get('resume')
        if not resume_file:
            return jsonify({"error": "Resume file required"}), 400

        filename = secure_filename(resume_file.filename)
        resume_path = str(app.config['UPLOAD_FOLDER'] / filename)
        resume_file.save(resume_path)

        boards = request.form.getlist('boards')
        gemini_key = os.environ.get('GEMINI_API_KEY', '')
        if not gemini_key:
            return jsonify({"error": "Set GEMINI_API_KEY environment variable"}), 400

        auto_apply = request.form.get('auto_apply') == 'on'

        config = {
            "name": "",
            "email": "",
            "phone": "",
            "linkedin": "",
            "job_titles": [t.strip() for t in request.form['job_titles'].split(',')],
            "location": request.form['location'],
            "boards": boards,
            "resume_path": resume_path,
            "gemini_key": gemini_key,
            "auto_apply": auto_apply,
        }

        state["config"] = config
        state["resume_text"] = parse_resume(resume_path)
        state["ai"] = AIEngine(gemini_key)

        # Extract info from resume
        try:
            import re
            info = state["ai"]._call(f"Extract from this resume and return ONLY JSON: {{\"name\":\"\",\"email\":\"\",\"phone\":\"\",\"linkedin\":\"\"}}\n\nRESUME:\n{state['resume_text'][:2000]}")
            match = re.search(r'\{.*\}', info, re.DOTALL)
            if match:
                parsed = json.loads(match.group())
                config["name"] = parsed.get("name", "")
                config["email"] = parsed.get("email", "")
                config["phone"] = parsed.get("phone", "")
                config["linkedin"] = parsed.get("linkedin", "")
        except Exception:
            pass

        # Open browser with login pages
        def open_signin():
            asyncio.run(open_signin_pages(boards))
        thread = threading.Thread(target=open_signin, daemon=True)
        thread.start()

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


async def open_signin_pages(boards):
    """Open browser with login pages for user to sign in."""
    from playwright.async_api import async_playwright
    import os

    browser = await (await async_playwright().start()).chromium.launch_persistent_context(
        user_data_dir=os.path.expanduser("~/.naukripro_chrome_profile"),
        headless=False,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
    )

    if "naukri" in boards:
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=15000)

    if "linkedin" in boards:
        page = await browser.new_page()
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=15000)

    # Keep browser open — will be closed when search starts
    state["signin_browser"] = browser


@app.route('/api/search_after_signin')
def search_after_signin():
    """Search for jobs using the signed-in browser session."""
    try:
        config = state["config"]
        ai = state["ai"]
        resume_text = state["resume_text"]

        # Close the sign-in browser
        if "signin_browser" in state and state["signin_browser"]:
            asyncio.run(state["signin_browser"].close())
            state["signin_browser"] = None

        # Now scrape with the saved session
        jobs = asyncio.run(scrape_and_score(config, ai, resume_text))
        state["jobs"] = jobs

        return jsonify({"jobs": jobs, "auto_apply": config.get("auto_apply", False)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


async def scrape_and_score(config, ai, resume_text):
    """Scrape jobs and score them — fast mode using title-based scoring."""
    from playwright.async_api import async_playwright
    import os

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=os.path.expanduser("~/.naukripro_chrome_profile"),
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()

        all_jobs = []
        if "linkedin" in config["boards"]:
            jobs = await scrape_linkedin(page, config["job_titles"], config["location"])
            all_jobs.extend(jobs)
        if "naukri" in config["boards"]:
            jobs = await scrape_naukri(page, config["job_titles"], config["location"])
            all_jobs.extend(jobs)

        await browser.close()

        # Filter already applied
        all_jobs = [j for j in all_jobs if not is_already_applied(j.get("url", ""))]

        if not all_jobs:
            return []

        # Fast scoring: score all jobs in ONE batch API call using title + company only
        job_list_text = "\n".join(
            f"{i+1}. {j['title']} at {j['company']} ({j['location']})"
            for i, j in enumerate(all_jobs[:20])
        )

        prompt = f"""Score these jobs (0-100) based on how well this candidate matches.
Return ONLY a JSON array: [{{"index":1,"score":85,"reason":"..."}}, ...]

CANDIDATE RESUME (summary):
{resume_text[:2000]}

JOBS:
{job_list_text}"""

        try:
            import json, re
            resp = ai._call(prompt)
            match = re.search(r'\[.*\]', resp, re.DOTALL)
            if match:
                scores = json.loads(match.group())
                for item in scores:
                    idx = item.get("index", 0) - 1
                    if 0 <= idx < len(all_jobs):
                        all_jobs[idx]["score"] = item.get("score", 50)
                        all_jobs[idx]["reason"] = item.get("reason", "")
        except Exception:
            # Fallback: give all jobs score 50
            for j in all_jobs:
                j["score"] = 50
                j["reason"] = ""

        # Sort and return top 10
        all_jobs.sort(key=lambda x: x.get("score", 0), reverse=True)
        return all_jobs[:10]


@app.route('/api/apply')
def apply_stream():
    """SSE endpoint — streams live application progress."""
    indices = [int(i) for i in request.args.get('indices', '').split(',') if i]
    selected = [state["jobs"][i] for i in indices if i < len(state["jobs"])]

    def run_applications():
        state["stop_flag"] = False
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


@app.route('/api/stop', methods=['POST'])
def stop():
    """Stop the current operation."""
    state["stop_flag"] = True
    # Unblock any waiting response
    state["response_queue"].put("STOP")
    return jsonify({"ok": True})


async def apply_to_jobs(jobs):
    """Apply to selected jobs with live updates."""
    from playwright.async_api import async_playwright

    config = state["config"]
    ai = state["ai"]
    resume_text = state["resume_text"]
    applied = 0

    async with async_playwright() as p:
        import os
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=os.path.expanduser("~/.naukripro_chrome_profile"),
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser
        page = browser.pages[0] if browser.pages else await browser.new_page()

        # Close the initial blank tab — each job gets its own tab
        if browser.pages:
            await browser.pages[0].close()

        # Skip login — persistent profile keeps sessions
        emit("log", message="Using saved browser session (no login needed)", level="success")

        for i, job in enumerate(jobs, 1):
            if state["stop_flag"]:
                emit("log", message="⏹ Stopped by user", level="warning")
                break

            emit("log", message=f"[{i}/{len(jobs)}] {job['title']} @ {job['company']}", level="info")

            # Tailor resume to 90+ score
            emit("log", message="Fetching job details & tailoring resume...", level="info")
            tailored_path = ""
            try:
                # Fetch full description now (not during search for speed)
                if not job.get("description"):
                    from playwright.async_api import async_playwright
                    desc_page = await browser.new_page()
                    from scraper import get_job_description
                    job["description"] = await get_job_description(desc_page, job["url"])
                    await desc_page.close()

                tailored_text = ai.tailor_resume(resume_text, job["title"], job["description"])
                result = ai.score_job(tailored_text, job["title"], job["description"])
                score = result.get("score", 0)
                emit("log", message=f"Tailored resume score: {score}/100", level="info")
                
                if score < 90:
                    emit("log", message="Refining further...", level="info")
                    tailored_text = ai.tailor_resume(tailored_text, job["title"], job["description"])
                    result = ai.score_job(tailored_text, job["title"], job["description"])
                    score = result.get("score", 0)
                    emit("log", message=f"Final resume score: {score}/100", level="success")
                
                tailored_path = save_tailored_resume(tailored_text, job["company"], job["title"])
                emit("log", message=f"✓ Resume ready ({score}/100)", level="success")
            except Exception as e:
                emit("log", message=f"Using original resume ({e})", level="warning")

            # Open new tab for this job
            page = await browser.new_page()
            await page.bring_to_front()
            emit("log", message="Filling application form...", level="info")
            filled = await fill_application_web(page, job, config, ai, resume_text, tailored_path)

            if filled:
                # Auto-apply mode: submit directly. Manual mode: ask GO/SKIP
                if state["config"].get("auto_apply"):
                    emit("log", message=f"Auto-submitting: {job['title']} @ {job['company']}", level="info")
                    submit_keywords = ["submit", "submit application", "apply", "send", "confirm", "save and apply"]
                    buttons = await page.query_selector_all("button[type='submit'], button, input[type='submit']")
                    submitted = False
                    for btn in buttons:
                        try:
                            if not await btn.is_visible():
                                continue
                            text = (await btn.inner_text()).strip().lower()
                            if any(kw in text for kw in submit_keywords):
                                await btn.click()
                                await page.wait_for_timeout(3000)
                                submitted = True
                                break
                        except Exception:
                            continue
                    if not submitted:
                        # Try Naukri-specific: chatbot apply or direct apply success
                        page_text = ""
                        try:
                            page_text = (await page.inner_text("body")).lower()
                        except Exception:
                            pass
                        if "applied successfully" in page_text or "application submitted" in page_text:
                            submitted = True
                    if submitted:
                        log_application(job, "submitted")
                        applied += 1
                        emit("log", message=f"✅ Submitted: {job['title']} @ {job['company']}", level="success")
                    else:
                        emit("log", message="Could not find submit button — please submit manually", level="warning")
                        ask_user("Type 'done' after submitting manually")
                        log_application(job, "submitted")
                        applied += 1
                else:
                    summary = f"{job['title']} @ {job['company']} | Fields: {len(filled)}"
                    choice = confirm_submission(summary)

                    if choice.upper() == "GO":
                        submit_keywords = ["submit", "submit application", "apply", "send"]
                        buttons = await page.query_selector_all("button[type='submit'], button, input[type='submit']")
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
                            emit("log", message="Could not find submit button — please submit manually", level="warning")
                            ask_user("Type 'done' after submitting manually")
                            log_application(job, "submitted")
                            applied += 1
                    else:
                        log_application(job, "skipped")
                        emit("log", message="Skipped", level="warning")
            else:
                emit("log", message="Could not fill form, skipping", level="error")
                log_application(job, "failed")

            # Close this tab
            await page.close()

        await browser.close()

    emit("done", message=f"Done! Applied to {applied}/{len(jobs)} jobs.")


async def fill_application_web(page, job, config, ai, resume_text, tailored_path):
    """Fill application — web version with human-like behavior."""
    from applicator import detect_blockers, click_next_button
    from stealth import human_fill, human_delay, random_scroll, move_mouse_randomly
    from cover_letter import generate_cover_letter

    url = job.get("url", "")
    if not url:
        return {}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await human_delay()
        await random_scroll(page)
        await page.wait_for_timeout(2000)
    except Exception as e:
        emit("log", message=f"Failed to load: {e}", level="error")
        return {}

    # Click apply button (Naukri-specific + generic)
    apply_btn = await page.query_selector("#apply-button, button[class*='apply'], [class*='apply-button']")
    if not apply_btn:
        buttons = await page.query_selector_all("button, a[role='button']")
        for btn in buttons:
            try:
                text = (await btn.inner_text()).strip().lower()
                if text in ["apply", "apply now", "easy apply", "i'm interested"]:
                    apply_btn = btn
                    break
            except Exception:
                continue

    if apply_btn:
        await move_mouse_randomly(page)
        await human_delay()
        await apply_btn.click()
        await page.wait_for_timeout(4000)

    # Check if redirected to login/registration
    current_url = page.url.lower()
    if any(kw in current_url for kw in ["login", "registration", "createaccount", "signin", "authwall"]):
        emit("log", message="Login required — please log in on the browser", level="warning")
        ask_user("Log into your account in the browser, then type 'done'")
        await page.wait_for_timeout(3000)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        apply_btn = await page.query_selector("#apply-button, button[class*='apply'], [class*='apply-button']")
        if apply_btn:
            await apply_btn.click()
            await page.wait_for_timeout(4000)

    # Check for CAPTCHA
    blocker = await detect_blockers(page)
    if blocker:
        emit("log", message=f"{'CAPTCHA' if blocker == 'captcha' else 'Blocker'} detected", level="warning")
        ask_user("Handle it in the browser, then type 'done'")
        await page.wait_for_timeout(2000)

    # Check if already applied
    page_text = ""
    try:
        page_text = (await page.inner_text("body")).lower()
    except Exception:
        pass
    if "already applied" in page_text:
        emit("log", message="Already applied to this job — skipping", level="info")
        return {}

    # Generate cover letter for this job
    cover_letter = ""
    try:
        cover_letter = generate_cover_letter(ai, resume_text, job["title"], job["company"], job.get("description", ""))
    except Exception:
        pass

    # Fill fields across steps (with retry)
    all_filled = {}
    max_retries = 2

    for step in range(10):
        await human_delay()

        # --- Text inputs ---
        inputs = await page.query_selector_all(
            "input[type='text'], input[type='email'], input[type='tel'], input[type='url'], input[type='number'], "
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
                if any(k in h for k in ["full name", "your name", "what is your name"]):
                    value = config["name"]
                elif any(k in h for k in ["first name", "fname"]):
                    value = config["name"].split()[0] if config["name"] else ""
                elif any(k in h for k in ["last name", "lname", "surname"]):
                    parts = config["name"].split()
                    value = parts[-1] if len(parts) > 1 else ""
                elif "name" in h and "company" not in h:
                    value = config["name"]
                elif any(k in h for k in ["email", "e-mail", "email id"]):
                    value = config["email"]
                elif any(k in h for k in ["phone", "mobile", "contact", "mobile number"]):
                    value = config["phone"]
                elif "linkedin" in h:
                    value = config["linkedin"]
                elif any(k in h for k in ["city", "location", "current location"]):
                    value = config["location"]
                elif any(k in h for k in ["notice period", "current ctc", "expected ctc", "experience", "salary"]):
                    answer = ai.answer_question(resume_text, hint)
                    value = answer if "ASK_USER" not in answer else ""
                    if not value:
                        value = ask_user(f"Please provide: {hint}")
                else:
                    answer = ai.answer_question(resume_text, hint)
                    if "ASK_USER" in answer:
                        value = ask_user(f"Please provide: {hint}")
                    else:
                        value = answer

                if value:
                    await human_fill(inp, value)
                    all_filled[hint] = value
            except Exception:
                continue

        # --- Dropdowns/Select fields ---
        selects = await page.query_selector_all("select")
        for sel in selects:
            try:
                if not await sel.is_visible():
                    continue
                sel_id = await sel.get_attribute("id") or ""
                name = await sel.get_attribute("name") or ""
                label = ""
                if sel_id:
                    lbl = await page.query_selector(f"label[for='{sel_id}']")
                    if lbl:
                        label = (await lbl.inner_text()).strip()
                hint = label or name
                if not hint:
                    continue

                # Get options
                options = await sel.query_selector_all("option")
                option_texts = []
                for opt in options:
                    text = (await opt.inner_text()).strip()
                    val = await opt.get_attribute("value") or ""
                    if text and val:
                        option_texts.append(text)

                if not option_texts:
                    continue

                # Ask AI which option to pick
                answer = ai.answer_question(resume_text, f"For the field '{hint}', which option best fits? Options: {', '.join(option_texts[:20])}")
                if "ASK_USER" in answer:
                    answer = ask_user(f"Select for '{hint}': {', '.join(option_texts[:10])}")

                # Find best matching option
                for opt in options:
                    text = (await opt.inner_text()).strip()
                    if text.lower() in answer.lower() or answer.lower() in text.lower():
                        val = await opt.get_attribute("value")
                        if val:
                            await sel.select_option(value=val)
                            all_filled[hint] = text
                            break
            except Exception:
                continue

        # --- Radio buttons ---
        radio_groups = {}
        radios = await page.query_selector_all("input[type='radio']")
        for radio in radios:
            try:
                name = await radio.get_attribute("name") or ""
                if name and name not in radio_groups:
                    radio_groups[name] = []
                if name:
                    label_text = ""
                    radio_id = await radio.get_attribute("id") or ""
                    if radio_id:
                        lbl = await page.query_selector(f"label[for='{radio_id}']")
                        if lbl:
                            label_text = (await lbl.inner_text()).strip()
                    value = await radio.get_attribute("value") or ""
                    radio_groups[name].append({"element": radio, "label": label_text or value, "value": value})
            except Exception:
                continue

        for group_name, options in radio_groups.items():
            try:
                option_labels = [o["label"] for o in options if o["label"]]
                if not option_labels:
                    continue
                answer = ai.answer_question(resume_text, f"For '{group_name}', which option? Choices: {', '.join(option_labels)}")
                if "ASK_USER" in answer:
                    answer = ask_user(f"Select for '{group_name}': {', '.join(option_labels)}")
                for opt in options:
                    if opt["label"].lower() in answer.lower() or answer.lower() in opt["label"].lower():
                        await opt["element"].click()
                        all_filled[group_name] = opt["label"]
                        break
            except Exception:
                continue

        # --- Textareas (cover letter, additional info) ---
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

                # Use cover letter for cover letter fields
                h = hint.lower()
                if any(k in h for k in ["cover letter", "why do you want", "why should we hire", "tell us about"]):
                    text = cover_letter if cover_letter else ai.answer_question(resume_text, hint)
                else:
                    text = ai.answer_question(resume_text, hint)

                if "ASK_USER" in text:
                    text = ask_user(f"Please provide: {hint}")

                await human_fill(ta, text)
                all_filled[hint] = text[:60] + "..."
            except Exception:
                continue

        # --- File upload ---
        for fi in await page.query_selector_all("input[type='file']"):
            try:
                upload = tailored_path if tailored_path else config["resume_path"]
                await fi.set_input_files(upload)
                all_filled["Resume"] = upload
            except Exception:
                ask_user("Could not upload resume — please upload manually, then type 'done'")

        # Next step?
        await human_delay()
        has_next = await click_next_button(page)
        if not has_next:
            break
        await page.wait_for_timeout(2000)

    emit("log", message=f"Filled {len(all_filled)} fields", level="success")
    return all_filled


if __name__ == '__main__':
    print("\n🤖 NaukriPro running at: http://localhost:8080\n")
    app.run(debug=False, port=8080, host="127.0.0.1")
