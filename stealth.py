"""Human-like browser interaction to avoid bot detection."""
import asyncio
import random
from playwright.async_api import Page


async def human_type(page: Page, selector: str, text: str):
    """Type text with human-like delays between keystrokes."""
    el = await page.query_selector(selector)
    if not el:
        return
    await el.click()
    await asyncio.sleep(random.uniform(0.1, 0.3))
    for char in text:
        await el.type(char, delay=random.randint(30, 120))
        if random.random() < 0.05:  # occasional pause
            await asyncio.sleep(random.uniform(0.2, 0.5))


async def human_fill(element, text: str):
    """Fill an input element with human-like behavior."""
    await element.click()
    await asyncio.sleep(random.uniform(0.2, 0.5))
    # Clear existing content
    await element.fill("")
    await asyncio.sleep(random.uniform(0.1, 0.2))
    # Type with delays
    for char in text:
        await element.type(char, delay=random.randint(25, 100))
    await asyncio.sleep(random.uniform(0.1, 0.3))


async def random_scroll(page: Page):
    """Scroll randomly like a human browsing."""
    scroll_amount = random.randint(200, 500)
    await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
    await asyncio.sleep(random.uniform(0.5, 1.5))


async def human_delay():
    """Random delay between actions."""
    await asyncio.sleep(random.uniform(0.5, 2.0))


async def move_mouse_randomly(page: Page):
    """Move mouse to random position."""
    x = random.randint(100, 800)
    y = random.randint(100, 600)
    await page.mouse.move(x, y)
    await asyncio.sleep(random.uniform(0.1, 0.3))
