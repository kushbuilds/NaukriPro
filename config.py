"""Configuration and user input gathering."""
import os
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt

console = Console()

def get_user_config():
    """Gather all required info from user interactively."""
    console.print("\n[bold cyan]🤖 NaukriPro — Auto Job Application Tool[/bold cyan]\n")
    
    name = Prompt.ask("[bold]Your full name[/bold]")
    email = Prompt.ask("[bold]Your email[/bold]")
    phone = Prompt.ask("[bold]Your phone number[/bold]")
    linkedin = Prompt.ask("[bold]Your LinkedIn URL[/bold]", default="")
    
    job_titles = Prompt.ask("[bold]Job titles to search[/bold] (comma-separated, e.g. Data Analyst, BI Developer)")
    location = Prompt.ask("[bold]Preferred location[/bold] (city or 'remote')")
    
    boards = []
    use_linkedin = Prompt.ask("[bold]Search LinkedIn?[/bold]", choices=["y", "n"], default="y")
    if use_linkedin == "y":
        boards.append("linkedin")
    use_naukri = Prompt.ask("[bold]Search Naukri.com?[/bold]", choices=["y", "n"], default="y")
    if use_naukri == "y":
        boards.append("naukri")
    
    resume_path = Prompt.ask("[bold]Path to your resume (.pdf or .docx)[/bold]")
    resume_path = os.path.expanduser(resume_path.strip())
    
    if not Path(resume_path).exists():
        console.print(f"[red]File not found: {resume_path}[/red]")
        raise SystemExit(1)
    
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if not gemini_key:
        gemini_key = Prompt.ask("[bold]Gemini API key[/bold] (free at https://aistudio.google.com/apikey)")
    
    return {
        "name": name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
        "job_titles": [t.strip() for t in job_titles.split(",")],
        "location": location,
        "boards": boards,
        "resume_path": resume_path,
        "gemini_key": gemini_key,
    }
