"""Browser automation for filling job applications."""
import asyncio
from playwright.async_api import Page
from rich.console import Console
from rich.prompt import Prompt

console = Console()


async def fill_application(page: Page, job: dict, config: dict, ai_engine, resume_text: str):
    """Navigate to job application and fill all fields. STOPS before submit."""
    
    url = job.get("url", "")
    if not url:
        console.print("[red]No application URL available.[/red]")
        return False
    
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    
    # Check for login/CAPTCHA
    page_text = await page.inner_text("body")
    if any(kw in page_text.lower() for kw in ["captcha", "verify you're human", "i'm not a robot"]):
        console.print("[yellow]⚠️  CAPTCHA detected! Please solve it manually, then type 'done'.[/yellow]")
        Prompt.ask("Type [bold]done[/bold] when ready")
    
    if any(kw in page_text.lower() for kw in ["sign in", "log in", "create account", "register"]):
        console.print("[yellow]⚠️  Login required! Please log in manually, then type 'done'.[/yellow]")
        Prompt.ask("Type [bold]done[/bold] when ready")
        await page.wait_for_timeout(2000)
    
    # Look for "Apply" button and click it
    apply_btns = await page.query_selector_all("button, a")
    for btn in apply_btns:
        text = (await btn.inner_text()).strip().lower()
        if text in ["apply", "apply now", "easy apply", "apply on company site"]:
            await btn.click()
            await page.wait_for_timeout(3000)
            break
    
    # Fill form fields
    filled_fields = {}
    
    # Fill text inputs
    inputs = await page.query_selector_all("input[type='text'], input[type='email'], input[type='tel'], input:not([type])")
    for inp in inputs:
        try:
            label = ""
            inp_id = await inp.get_attribute("id") or ""
            name = await inp.get_attribute("name") or ""
            placeholder = await inp.get_attribute("placeholder") or ""
            aria_label = await inp.get_attribute("aria-label") or ""
            
            # Try to find associated label
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
            if any(k in hint_lower for k in ["name", "full name"]):
                value = config["name"]
            elif any(k in hint_lower for k in ["first name", "fname"]):
                value = config["name"].split()[0]
            elif any(k in hint_lower for k in ["last name", "lname", "surname"]):
                parts = config["name"].split()
                value = parts[-1] if len(parts) > 1 else ""
            elif any(k in hint_lower for k in ["email", "e-mail"]):
                value = config["email"]
            elif any(k in hint_lower for k in ["phone", "mobile", "contact"]):
                value = config["phone"]
            elif "linkedin" in hint_lower:
                value = config["linkedin"]
            elif any(k in hint_lower for k in ["city", "location"]):
                value = config["location"]
            else:
                # Ask AI or user
                answer = ai_engine.answer_question(resume_text, field_hint)
                if "ASK_USER" in answer:
                    console.print(f"[yellow]❓ Cannot determine: {field_hint}[/yellow]")
                    value = Prompt.ask(f"  Please provide: [bold]{field_hint}[/bold]")
                else:
                    value = answer
            
            if value:
                await inp.fill(value)
                filled_fields[field_hint] = value
        except Exception:
            continue
    
    # Fill textareas (cover letter, additional info)
    textareas = await page.query_selector_all("textarea")
    for ta in textareas:
        try:
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
                continue
            
            answer = ai_engine.answer_question(resume_text, field_hint)
            if "ASK_USER" in answer:
                console.print(f"[yellow]❓ Cannot determine: {field_hint}[/yellow]")
                answer = Prompt.ask(f"  Please provide: [bold]{field_hint}[/bold]")
            
            await ta.fill(answer)
            filled_fields[field_hint] = answer[:100] + "..."
        except Exception:
            continue
    
    # Handle file upload (resume)
    file_inputs = await page.query_selector_all("input[type='file']")
    for fi in file_inputs:
        try:
            await fi.set_input_files(config["resume_path"])
            filled_fields["Resume Upload"] = config["resume_path"]
        except Exception:
            console.print("[yellow]⚠️  Could not auto-upload resume. Please upload manually.[/yellow]")
            Prompt.ask("Type [bold]done[/bold] when uploaded")
    
    return filled_fields


async def show_summary_and_submit(page: Page, job: dict, filled_fields: dict):
    """Show pre-submission summary and wait for GO."""
    console.print("\n[bold green]═══ PRE-SUBMISSION SUMMARY ═══[/bold green]")
    console.print(f"[bold]Company:[/bold] {job['company']}")
    console.print(f"[bold]Position:[/bold] {job['title']}")
    console.print(f"[bold]Source:[/bold] {job['source']}")
    console.print("\n[bold]Fields filled:[/bold]")
    for field, value in filled_fields.items():
        console.print(f"  • {field}: {value}")
    
    console.print("\n[bold yellow]Type GO to submit, or SKIP to skip this application.[/bold yellow]")
    choice = Prompt.ask("", choices=["GO", "go", "SKIP", "skip"])
    
    if choice.lower() == "go":
        # Find and click submit button
        buttons = await page.query_selector_all("button[type='submit'], button")
        for btn in buttons:
            text = (await btn.inner_text()).strip().lower()
            if text in ["submit", "submit application", "apply", "send application", "send"]:
                await btn.click()
                await page.wait_for_timeout(3000)
                console.print("[bold green]✅ Application submitted![/bold green]")
                return True
        console.print("[yellow]Could not find submit button. Please submit manually.[/yellow]")
        Prompt.ask("Type [bold]done[/bold] after submitting")
        return True
    else:
        console.print("[dim]Skipped.[/dim]")
        return False
