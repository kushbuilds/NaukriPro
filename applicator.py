"""Browser automation for filling job applications with multi-step support."""
import asyncio
from playwright.async_api import Page
from rich.console import Console
from rich.prompt import Prompt

console = Console()


async def detect_blockers(page: Page) -> str | None:
    """Check for CAPTCHA or login walls. Returns blocker type or None."""
    try:
        page_text = (await page.inner_text("body")).lower()
    except Exception:
        return None

    if any(kw in page_text for kw in ["captcha", "verify you're human", "i'm not a robot", "recaptcha"]):
        return "captcha"
    if any(kw in page_text for kw in ["sign in to", "log in to", "create an account to apply", "register to apply"]):
        return "login"
    return None


async def handle_blocker(blocker: str):
    """Pause and ask user to handle blocker."""
    if blocker == "captcha":
        console.print("[yellow]⚠️  CAPTCHA detected! Please solve it manually.[/yellow]")
    elif blocker == "login":
        console.print("[yellow]⚠️  Login/account required! Please log in manually.[/yellow]")
    Prompt.ask("Type [bold]done[/bold] when ready")


async def click_apply_button(page: Page) -> bool:
    """Find and click the Apply/Easy Apply button."""
    apply_keywords = ["apply now", "apply", "easy apply", "apply on company site", "i'm interested"]
    buttons = await page.query_selector_all("button, a[role='button'], a[class*='apply']")

    for btn in buttons:
        try:
            text = (await btn.inner_text()).strip().lower()
            if any(kw == text or kw in text for kw in apply_keywords):
                await btn.click()
                await page.wait_for_timeout(3000)
                return True
        except Exception:
            continue
    return False


async def click_next_button(page: Page) -> bool:
    """Click Next/Continue button for multi-step forms."""
    next_keywords = ["next", "continue", "save & next", "save and next", "proceed"]
    buttons = await page.query_selector_all("button, input[type='submit']")

    for btn in buttons:
        try:
            text = (await btn.inner_text()).strip().lower()
            if any(kw in text for kw in next_keywords):
                await btn.click()
                await page.wait_for_timeout(2000)
                return True
        except Exception:
            continue
    return False


async def fill_inputs(page: Page, config: dict, ai_engine, resume_text: str) -> dict:
    """Fill all visible text inputs on the current page/step."""
    filled = {}

    inputs = await page.query_selector_all(
        "input[type='text'], input[type='email'], input[type='tel'], "
        "input[type='url'], input:not([type='hidden']):not([type='file'])"
        ":not([type='checkbox']):not([type='radio']):not([type='submit'])"
        ":not([type='button']):not([type='password'])"
    )

    for inp in inputs:
        try:
            # Skip if already filled
            current_val = await inp.input_value()
            if current_val.strip():
                continue

            if not await inp.is_visible():
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

            field_hint = label or aria_label or placeholder or name
            if not field_hint:
                continue

            hint_lower = field_hint.lower()
            value = ""

            # Map common fields
            if any(k in hint_lower for k in ["full name", "your name"]):
                value = config["name"]
            elif any(k in hint_lower for k in ["first name", "fname", "given name"]):
                value = config["name"].split()[0]
            elif any(k in hint_lower for k in ["last name", "lname", "surname", "family name"]):
                parts = config["name"].split()
                value = parts[-1] if len(parts) > 1 else ""
            elif "name" in hint_lower and "company" not in hint_lower:
                value = config["name"]
            elif any(k in hint_lower for k in ["email", "e-mail"]):
                value = config["email"]
            elif any(k in hint_lower for k in ["phone", "mobile", "contact number", "cell"]):
                value = config["phone"]
            elif "linkedin" in hint_lower:
                value = config["linkedin"]
            elif any(k in hint_lower for k in ["city", "location", "current location"]):
                value = config["location"]
            else:
                answer = ai_engine.answer_question(resume_text, field_hint)
                if "ASK_USER" in answer:
                    console.print(f"[yellow]❓ Cannot determine: {field_hint}[/yellow]")
                    value = Prompt.ask(f"  Please provide: [bold]{field_hint}[/bold]")
                else:
                    value = answer

            if value:
                await inp.fill(value)
                filled[field_hint] = value
        except Exception:
            continue

    return filled


async def fill_textareas(page: Page, ai_engine, resume_text: str) -> dict:
    """Fill all visible textareas."""
    filled = {}
    textareas = await page.query_selector_all("textarea")

    for ta in textareas:
        try:
            if not await ta.is_visible():
                continue
            current_val = await ta.input_value()
            if current_val.strip():
                continue

            ta_id = await ta.get_attribute("id") or ""
            name = await ta.get_attribute("name") or ""
            placeholder = await ta.get_attribute("placeholder") or ""

            label = ""
            if ta_id:
                label_el = await page.query_selector(f"label[for='{ta_id}']")
                if label_el:
                    label = (await label_el.inner_text()).strip()

            field_hint = label or placeholder or name
            if not field_hint:
                field_hint = "Additional information"

            answer = ai_engine.answer_question(resume_text, field_hint)
            if "ASK_USER" in answer:
                console.print(f"[yellow]❓ Cannot determine: {field_hint}[/yellow]")
                answer = Prompt.ask(f"  Please provide: [bold]{field_hint}[/bold]")

            await ta.fill(answer)
            filled[field_hint] = answer[:80] + ("..." if len(answer) > 80 else "")
        except Exception:
            continue

    return filled


async def upload_resume(page: Page, resume_path: str) -> dict:
    """Handle resume file upload."""
    filled = {}
    file_inputs = await page.query_selector_all("input[type='file']")

    for fi in file_inputs:
        try:
            accept = await fi.get_attribute("accept") or ""
            # Only upload to inputs that accept documents
            if accept and not any(ext in accept for ext in [".pdf", ".doc", ".docx", "application/"]):
                continue
            await fi.set_input_files(resume_path)
            filled["Resume Upload"] = resume_path
        except Exception:
            console.print("[yellow]⚠️  Could not auto-upload resume. Please upload manually.[/yellow]")
            Prompt.ask("Type [bold]done[/bold] when uploaded")
            filled["Resume Upload"] = "manual"

    return filled


async def fill_application(page: Page, job: dict, config: dict, ai_engine, resume_text: str, tailored_resume_path: str) -> dict:
    """Navigate to job application and fill all fields across multiple steps. STOPS before submit."""

    url = job.get("url", "")
    if not url:
        console.print("[red]No application URL available.[/red]")
        return {}

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception as e:
        console.print(f"[red]Failed to load page: {e}[/red]")
        return {}

    # Check for blockers
    blocker = await detect_blockers(page)
    if blocker:
        await handle_blocker(blocker)
        await page.wait_for_timeout(2000)

    # Click apply button
    await click_apply_button(page)

    # Check for blockers again after clicking apply
    blocker = await detect_blockers(page)
    if blocker:
        await handle_blocker(blocker)
        await page.wait_for_timeout(2000)

    # Fill form (handle multi-step)
    all_filled = {}
    max_steps = 10

    for step in range(max_steps):
        console.print(f"[dim]  Filling step {step + 1}...[/dim]")

        # Fill fields on current step
        filled_inputs = await fill_inputs(page, config, ai_engine, resume_text)
        filled_ta = await fill_textareas(page, ai_engine, resume_text)

        # Upload resume (use tailored version)
        upload_path = tailored_resume_path if tailored_resume_path else config["resume_path"]
        filled_upload = await upload_resume(page, upload_path)

        all_filled.update(filled_inputs)
        all_filled.update(filled_ta)
        all_filled.update(filled_upload)

        # Check for blockers mid-form
        blocker = await detect_blockers(page)
        if blocker:
            await handle_blocker(blocker)

        # Try to go to next step
        has_next = await click_next_button(page)
        if not has_next:
            break  # We're on the final step

        await page.wait_for_timeout(2000)

    return all_filled


async def show_summary_and_submit(page: Page, job: dict, filled_fields: dict) -> bool:
    """Show pre-submission summary and wait for GO."""
    console.print("\n[bold green]═══ PRE-SUBMISSION SUMMARY ═══[/bold green]")
    console.print(f"[bold]Company:[/bold] {job['company']}")
    console.print(f"[bold]Position:[/bold] {job['title']}")
    console.print(f"[bold]Source:[/bold] {job['source']}")
    console.print(f"[bold]Score:[/bold] {job.get('score', 'N/A')}")
    console.print("\n[bold]Fields filled:[/bold]")
    for field, value in filled_fields.items():
        console.print(f"  • {field}: {value}")

    console.print("\n[bold yellow]Type GO to submit, SKIP to skip, or EDIT to make manual changes.[/bold yellow]")
    choice = Prompt.ask("", choices=["GO", "go", "SKIP", "skip", "EDIT", "edit"])

    if choice.lower() == "edit":
        console.print("[cyan]Make your edits in the browser, then come back here.[/cyan]")
        Prompt.ask("Type [bold]done[/bold] when ready to submit")
        choice = Prompt.ask("Now type [bold]GO[/bold] to submit or [bold]SKIP[/bold]", choices=["GO", "go", "SKIP", "skip"])

    if choice.lower() == "go":
        submit_keywords = ["submit", "submit application", "apply", "send application", "send", "confirm"]
        buttons = await page.query_selector_all("button[type='submit'], button, input[type='submit']")
        for btn in buttons:
            try:
                text = (await btn.inner_text()).strip().lower()
                if any(kw in text for kw in submit_keywords):
                    await btn.click()
                    await page.wait_for_timeout(3000)
                    console.print("[bold green]✅ Application submitted![/bold green]")
                    return True
            except Exception:
                continue
        console.print("[yellow]Could not find submit button. Please submit manually.[/yellow]")
        Prompt.ask("Type [bold]done[/bold] after submitting")
        return True
    else:
        console.print("[dim]Skipped.[/dim]")
        return False
