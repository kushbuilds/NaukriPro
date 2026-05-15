"""Job scraping from LinkedIn and Naukri.com using Playwright."""
from playwright.async_api import Page
from rich.console import Console

console = Console()


async def scrape_linkedin(page: Page, job_titles: list, location: str, limit: int = 20) -> list:
    """Scrape LinkedIn job listings."""
    jobs = []
    for title in job_titles:
        query = title.replace(" ", "%20")
        loc = location.replace(" ", "%20")
        url = f"https://www.linkedin.com/jobs/search/?keywords={query}&location={loc}"

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            console.print(f"[yellow]  LinkedIn timeout for '{title}': {e}[/yellow]")
            continue

        cards = await page.query_selector_all(".base-card")
        for card in cards[:limit]:
            try:
                title_el = await card.query_selector(".base-search-card__title")
                company_el = await card.query_selector(".base-search-card__subtitle")
                link_el = await card.query_selector("a")
                location_el = await card.query_selector(".job-search-card__location")

                job_title = (await title_el.inner_text()).strip() if title_el else "Unknown"
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                link = await link_el.get_attribute("href") if link_el else ""
                job_loc = (await location_el.inner_text()).strip() if location_el else ""

                jobs.append({
                    "title": job_title,
                    "company": company,
                    "location": job_loc,
                    "url": link,
                    "source": "LinkedIn",
                    "description": "",
                })
            except Exception:
                continue
    return jobs


async def scrape_naukri(page: Page, job_titles: list, location: str, limit: int = 20) -> list:
    """Scrape Naukri.com job listings."""
    jobs = []
    for title in job_titles:
        query = title.replace(" ", "-").lower()
        loc = location.replace(" ", "-").lower()
        url = f"https://www.naukri.com/{query}-jobs-in-{loc}"

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
        except Exception as e:
            console.print(f"[yellow]  Naukri timeout for '{title}': {e}[/yellow]")
            continue

        cards = await page.query_selector_all(".srp-jobtuple-wrapper, .cust-job-tuple")
        if not cards:
            cards = await page.query_selector_all("div[data-job-id]")

        for card in cards[:limit]:
            try:
                title_el = await card.query_selector("a.title")
                company_el = await card.query_selector("a.comp-name, .comp-name")
                location_el = await card.query_selector("span.loc, .loc-wrap .loc, .locWrap .ellipsis")

                job_title = (await title_el.inner_text()).strip() if title_el else "Unknown"
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                job_loc = (await location_el.inner_text()).strip() if location_el else ""
                link = await title_el.get_attribute("href") if title_el else ""

                jobs.append({
                    "title": job_title,
                    "company": company,
                    "location": job_loc,
                    "url": link,
                    "source": "Naukri",
                    "description": "",
                })
            except Exception:
                continue
    return jobs


async def get_job_description(page: Page, url: str) -> str:
    """Navigate to a job page and extract the description."""
    if not url:
        return ""
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        selectors = [
            ".description__text",
            ".show-more-less-html__markup",
            ".job-description",
            ".jd-container",
            "#job_description",
            ".JDContainer",
            "[class*='description']",
            "[class*='jobDesc']",
        ]
        for sel in selectors:
            el = await page.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if len(text) > 50:
                    return text[:3000]

        body = await page.query_selector("main, article, .content")
        if body:
            return (await body.inner_text()).strip()[:3000]
    except Exception:
        pass
    return ""
