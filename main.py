"""NaukriPro — Automated Job Application Tool.

Searches LinkedIn and Naukri.com, scores jobs against your resume,
tailors your resume, generates a .docx, and auto-fills applications
with human confirmation before every submission.
"""
import asyncio
from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from config import get_user_config
from resume_parser import parse_resume
from ai_engine import AIEngine
from scraper import scrape_linkedin, scrape_naukri, get_job_description
from applicator import fill_application, show_summary_and_submit
from tracker import is_already_applied, log_application
from resume_generator import save_tailored_resume
from auth import ensure_naukri_login, ensure_linkedin_login

console = Console()


async def main():
    # Step 1: Gather user info
    config = get_user_config()

    # Step 2: Parse resume
    console.print("\n[cyan]📄 Parsing resume...[/cyan]")
    resume_text = parse_resume(config["resume_path"])
    console.print(f"[green]✓ Resume parsed ({len(resume_text)} chars)[/green]")

    # Step 3: Initialize AI
    console.print("[cyan]🧠 Initializing AI engine...[/cyan]")
    ai = AIEngine(config["gemini_key"])
    console.print("[green]✓ AI ready (Gemini Flash — free tier)[/green]")

    # Step 4: Launch browser and handle logins
    console.print("[cyan]🌐 Launching browser...[/cyan]")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Login to platforms
        if "naukri" in config["boards"]:
            await ensure_naukri_login(page, context)
        if "linkedin" in config["boards"]:
            await ensure_linkedin_login(page, context)

        # Step 5: Scrape jobs
        all_jobs = []

        if "linkedin" in config["boards"]:
            console.print("[cyan]🔍 Searching LinkedIn...[/cyan]")
            jobs = await scrape_linkedin(page, config["job_titles"], config["location"])
            all_jobs.extend(jobs)
            console.print(f"[green]✓ Found {len(jobs)} jobs on LinkedIn[/green]")

        if "naukri" in config["boards"]:
            console.print("[cyan]🔍 Searching Naukri.com...[/cyan]")
            jobs = await scrape_naukri(page, config["job_titles"], config["location"])
            all_jobs.extend(jobs)
            console.print(f"[green]✓ Found {len(jobs)} jobs on Naukri[/green]")

        if not all_jobs:
            console.print("[red]No jobs found. Try different search terms or check your internet.[/red]")
            await browser.close()
            return

        # Filter out already-applied jobs
        before = len(all_jobs)
        all_jobs = [j for j in all_jobs if not is_already_applied(j.get("url", ""))]
        skipped = before - len(all_jobs)
        if skipped:
            console.print(f"[dim]  Skipped {skipped} jobs you already applied to.[/dim]")

        if not all_jobs:
            console.print("[green]You've already applied to all found jobs! Try new search terms.[/green]")
            await browser.close()
            return

        # Step 6: Get descriptions and score jobs
        console.print(f"\n[cyan]📊 Scoring {min(len(all_jobs), 20)} jobs against your resume...[/cyan]")
        scored_jobs = []
        for i, job in enumerate(all_jobs[:20]):
            console.print(f"  Scoring {i+1}/{min(len(all_jobs), 20)}: {job['title'][:40]} @ {job['company'][:20]}", end="\r")
            desc = await get_job_description(page, job["url"])
            job["description"] = desc
            try:
                result = ai.score_job(resume_text, job["title"], desc)
                job["score"] = result.get("score", 50)
                job["reason"] = result.get("reason", "")
            except Exception:
                job["score"] = 50
                job["reason"] = "Could not score"
            scored_jobs.append(job)

        console.print("")  # Clear the \r line

        # Sort by score
        scored_jobs.sort(key=lambda x: x["score"], reverse=True)
        top_jobs = scored_jobs[:10]

        # Step 7: Display top jobs
        table = Table(title="🏆 Top Job Matches")
        table.add_column("#", style="bold", width=3)
        table.add_column("Score", style="green", width=5)
        table.add_column("Title", max_width=30)
        table.add_column("Company", max_width=20)
        table.add_column("Location", max_width=15)
        table.add_column("Source", width=8)
        table.add_column("Reason", max_width=35)

        for i, job in enumerate(top_jobs, 1):
            table.add_row(
                str(i),
                str(job["score"]),
                job["title"][:30],
                job["company"][:20],
                job["location"][:15],
                job["source"],
                job.get("reason", "")[:35],
            )

        console.print(table)

        # Step 8: User picks jobs
        picks = Prompt.ask("\n[bold]Which jobs to apply to?[/bold] (comma-separated numbers, e.g. 1,3,5 or 'all')")
        if picks.strip().lower() == "all":
            selected_jobs = top_jobs
        else:
            selected_indices = [int(x.strip()) - 1 for x in picks.split(",") if x.strip().isdigit()]
            selected_jobs = [top_jobs[i] for i in selected_indices if i < len(top_jobs)]

        if not selected_jobs:
            console.print("[red]No valid jobs selected.[/red]")
            await browser.close()
            return

        console.print(f"\n[bold]Applying to {len(selected_jobs)} jobs...[/bold]\n")

        # Step 9: Apply to each selected job
        applied_count = 0
        for i, job in enumerate(selected_jobs, 1):
            console.print(f"\n[bold cyan]═══ [{i}/{len(selected_jobs)}] {job['title']} @ {job['company']} ═══[/bold cyan]")

            # Tailor resume and save as .docx
            console.print("[cyan]✍️  Tailoring resume...[/cyan]")
            tailored_path = ""
            try:
                tailored_text = ai.tailor_resume(resume_text, job["title"], job["description"])
                tailored_path = save_tailored_resume(tailored_text, job["company"], job["title"])
                console.print(f"[green]✓ Tailored resume saved: {tailored_path}[/green]")
            except Exception as e:
                console.print(f"[yellow]⚠ Using original resume ({e})[/yellow]")

            # Fill application
            console.print("[cyan]📝 Filling application...[/cyan]")
            filled_fields = await fill_application(page, job, config, ai, resume_text, tailored_path)

            if filled_fields:
                submitted = await show_summary_and_submit(page, job, filled_fields)
                if submitted:
                    log_application(job, "submitted")
                    applied_count += 1
                    console.print(f"[bold green]✅ Done: {job['title']} @ {job['company']}[/bold green]")
                else:
                    log_application(job, "skipped")
            else:
                console.print("[yellow]Could not fill application. Skipping.[/yellow]")
                log_application(job, "failed")

        # Summary
        console.print(f"\n[bold green]🎉 Session complete! Applied to {applied_count}/{len(selected_jobs)} jobs.[/bold green]")
        console.print("[dim]Application history saved to applied_jobs.json[/dim]")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
