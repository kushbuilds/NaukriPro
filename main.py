"""NaukriPro — Automated Job Application Tool.

Searches LinkedIn and Naukri.com, scores jobs against your resume,
tailors your resume, and auto-fills applications with human confirmation.
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
    
    # Step 4: Launch browser and scrape jobs
    console.print("[cyan]🌐 Launching browser...[/cyan]")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
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
            console.print("[red]No jobs found. Try different search terms.[/red]")
            await browser.close()
            return
        
        # Step 5: Get descriptions and score jobs
        console.print(f"\n[cyan]📊 Scoring {len(all_jobs)} jobs against your resume...[/cyan]")
        scored_jobs = []
        for i, job in enumerate(all_jobs[:20]):  # Limit to top 20
            console.print(f"  Scoring {i+1}/{min(len(all_jobs), 20)}: {job['title']} @ {job['company']}", end="\r")
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
        
        # Sort by score
        scored_jobs.sort(key=lambda x: x["score"], reverse=True)
        top_jobs = scored_jobs[:10]
        
        # Step 6: Display top jobs
        console.print("\n")
        table = Table(title="🏆 Top Job Matches")
        table.add_column("#", style="bold")
        table.add_column("Score", style="green")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Location")
        table.add_column("Source")
        table.add_column("Reason")
        
        for i, job in enumerate(top_jobs, 1):
            table.add_row(
                str(i),
                str(job["score"]),
                job["title"],
                job["company"],
                job["location"],
                job["source"],
                job.get("reason", "")[:40],
            )
        
        console.print(table)
        
        # Step 7: User picks jobs
        picks = Prompt.ask("\n[bold]Which jobs to apply to?[/bold] (comma-separated numbers, e.g. 1,3,5)")
        selected_indices = [int(x.strip()) - 1 for x in picks.split(",") if x.strip().isdigit()]
        selected_jobs = [top_jobs[i] for i in selected_indices if i < len(top_jobs)]
        
        if not selected_jobs:
            console.print("[red]No valid jobs selected.[/red]")
            await browser.close()
            return
        
        # Step 8: Apply to each selected job
        for i, job in enumerate(selected_jobs, 1):
            console.print(f"\n[bold cyan]═══ Applying {i}/{len(selected_jobs)}: {job['title']} @ {job['company']} ═══[/bold cyan]")
            
            # Tailor resume
            console.print("[cyan]✍️  Tailoring resume...[/cyan]")
            try:
                tailored = ai.tailor_resume(resume_text, job["title"], job["description"])
                console.print("[green]✓ Resume tailored[/green]")
            except Exception:
                tailored = resume_text
                console.print("[yellow]⚠ Using original resume[/yellow]")
            
            # Fill application
            console.print("[cyan]📝 Filling application...[/cyan]")
            filled_fields = await fill_application(page, job, config, ai, resume_text)
            
            if filled_fields:
                # Show summary and wait for GO
                submitted = await show_summary_and_submit(page, job, filled_fields)
                if submitted:
                    console.print(f"[bold green]✅ Done: {job['title']} @ {job['company']}[/bold green]")
            else:
                console.print("[yellow]Could not fill application. Skipping.[/yellow]")
        
        console.print("\n[bold green]🎉 All done! Good luck with your applications![/bold green]")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
