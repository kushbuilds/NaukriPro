"""Naukri.com login helper with cookie persistence."""
import json
from pathlib import Path
from playwright.async_api import BrowserContext, Page
from rich.console import Console
from rich.prompt import Prompt

console = Console()

COOKIES_DIR = Path(__file__).parent / ".cookies"


async def save_cookies(context: BrowserContext, name: str):
    """Save browser cookies to disk for reuse."""
    COOKIES_DIR.mkdir(exist_ok=True)
    cookies = await context.cookies()
    (COOKIES_DIR / f"{name}.json").write_text(json.dumps(cookies, indent=2))


async def load_cookies(context: BrowserContext, name: str) -> bool:
    """Load saved cookies into browser context. Returns True if loaded."""
    cookie_file = COOKIES_DIR / f"{name}.json"
    if cookie_file.exists():
        cookies = json.loads(cookie_file.read_text())
        await context.add_cookies(cookies)
        return True
    return False


async def ensure_naukri_login(page: Page, context: BrowserContext):
    """Ensure user is logged into Naukri.com, using saved cookies or manual login."""
    # Try loading saved cookies
    loaded = await load_cookies(context, "naukri")
    if loaded:
        await page.goto("https://www.naukri.com/mnjuser/profile", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        # Check if actually logged in
        if "login" not in page.url.lower():
            console.print("[green]✓ Naukri.com session restored from saved cookies[/green]")
            return

    # Manual login required
    console.print("[yellow]🔐 Naukri.com login required.[/yellow]")
    console.print("[dim]  Opening login page — please log in manually.[/dim]")
    await page.goto("https://www.naukri.com/nlogin/login", wait_until="domcontentloaded", timeout=15000)
    Prompt.ask("Type [bold]done[/bold] after logging in")
    await page.wait_for_timeout(2000)

    # Save cookies for next time
    await save_cookies(context, "naukri")
    console.print("[green]✓ Cookies saved — won't need to login again next time[/green]")


async def ensure_linkedin_login(page: Page, context: BrowserContext):
    """Ensure user is logged into LinkedIn if needed."""
    loaded = await load_cookies(context, "linkedin")
    if loaded:
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)
        if "login" not in page.url.lower() and "authwall" not in page.url.lower():
            console.print("[green]✓ LinkedIn session restored from saved cookies[/green]")
            return

    console.print("[yellow]🔐 LinkedIn login required for Easy Apply.[/yellow]")
    console.print("[dim]  Opening login page — please log in manually.[/dim]")
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=15000)
    Prompt.ask("Type [bold]done[/bold] after logging in")
    await page.wait_for_timeout(2000)

    await save_cookies(context, "linkedin")
    console.print("[green]✓ Cookies saved — won't need to login again next time[/green]")
