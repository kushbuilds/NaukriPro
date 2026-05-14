"""Job scraping from LinkedIn and Naukri.com using Playwright."""
import asyncio
from playwright.async_api import Page

async def scrape_linkedin(page: Page, job_titles: list, location: str, limit: int = 20) -> list:
    """Scrape LinkedIn job listings."""
    jobs = []
    for title in job_titles:
        query = title.replace(" ", "%20")
        loc = location.replace(" ", "%20")
        url = f"https://www.linkedin.com/jobs/search/?keywords={query}&location={loc}"
        
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Get job cards
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
        query = title.replace(" ", "-")
        loc = location.replace(" ", "-").lower()
        url = f"https://www.naukri.com/{query}-jobs-in-{loc}"
        
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        cards = await page.query_selector_all(".srp-jobtuple-wrapper, .jobTuple")
        if not cards:
            cards = await page.query_selector_all("article.jobTuple")
        
        for card in cards[:limit]:
            try:
                title_el = await card.query_selector(".title, a.title")
                company_el = await card.query_selector(".comp-name, .subTitle a")
                location_el = await card.query_selector(".loc-wrap .loc, .locWrap .ellipsis")
                link_el = await card.query_selector("a.title, a[href*='job-listings']")
                
                job_title = (await title_el.inner_text()).strip() if title_el else "Unknown"
                company = (await company_el.inner_text()).strip() if company_el else "Unknown"
                job_loc = (await location_el.inner_text()).strip() if location_el else ""
                link = await link_el.get_attribute("href") if link_el else ""
                
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
        
        # Try common selectors for job descriptions
        selectors = [
            ".description__text",
            ".show-more-less-html__markup",
            ".job-description",
            ".jd-container",
            "#job_description",
            ".JDContainer",
            "[class*='description']",
        ]
        for sel in selectors:
            el = await page.query_selector(sel)
            if el:
                return (await el.inner_text()).strip()
        
        # Fallback: get main content
        body = await page.query_selector("main, article, .content")
        if body:
            return (await body.inner_text()).strip()[:3000]
    except Exception:
        pass
    return ""
