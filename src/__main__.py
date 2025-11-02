import asyncio
import re
from typing import Any, Dict, List, Optional, Set

from apify import Actor
from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright
from playwright_stealth import stealth_async

LISTING_SEL = 'a[href*="/marketplace/item/"]'


def extract_listing_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    match = re.search(r"/item/(\d+)", url)
    return match.group(1) if match else None


def parse_price(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    match = re.search(r"([\d,]+(?:\.\d{2})?)", text)
    return float(match.group(1).replace(",", "")) if match else None


async def snapshot_cards(page: Page) -> List[Dict[str, Any]]:
    anchors = page.locator(LISTING_SEL)
    count = await anchors.count()
    records: List[Dict[str, Any]] = []
    for index in range(count):
        anchor = anchors.nth(index)
        href = await anchor.get_attribute("href")
        url = (
            href
            if href and href.startswith("http")
            else f"https://www.facebook.com{href}" if href else None
        )
        listing_id = extract_listing_id(url)
        card = anchor.locator("xpath=ancestor::div[1]")

        price_text = None
        try:
            price_text = await card.locator('span:has-text("$")').first.text_content()
        except Exception:
            pass

        title = await anchor.get_attribute("aria-label")

        image = None
        try:
            image = await card.locator("img").first.get_attribute("src")
        except Exception:
            pass

        records.append(
            {
                "listing_id": listing_id,
                "title": title,
                "price": parse_price(price_text),
                "image": image,
                "url": url,
            }
        )

    unique_records: Dict[str, Dict[str, Any]] = {}
    for record in records:
        lid = record.get("listing_id")
        if lid and lid not in unique_records:
            unique_records[lid] = record
    return list(unique_records.values())


async def scroll_results(page: Page, max_scrolls: int = 10, delay_ms: int = 1200) -> None:
    seen = 0
    for _ in range(max_scrolls):
        await page.wait_for_timeout(delay_ms)
        await page.mouse.wheel(0, 2400)
        await page.wait_for_load_state("networkidle")
        current = await page.locator(LISTING_SEL).count()
        if current <= seen:
            break
        seen = current


async def fetch_details(context, item_url: str) -> Dict[str, Any]:
    page = await context.new_page()
    try:
        await page.goto(item_url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        description = None
        selectors = [
            "div[role=main]",
            "div.x1ja2u2z",
            "div.x126k92a",
        ]
        for selector in selectors:
            node = soup.select_one(selector)
            if node and node.get_text(strip=True):
                description = node.get_text(separator="\n", strip=True)
                break
        return {"description": description}
    finally:
        await page.close()


async def run() -> None:
    async with Actor:
        input_data = await Actor.get_input() or {}

        urls: List[str] = input_data.get("urls", [])
        fetch_item_details: bool = bool(input_data.get("fetch_item_details", False))
        dedupe_across_runs: bool = bool(input_data.get("deduplicate_across_runs", True))
        stop_on_all_dupes: bool = bool(input_data.get("stop_on_first_page_all_duplicates", False))
        max_items: Optional[int] = input_data.get("max_items")
        if max_items in ("", None):
            max_items = None

        proxy_input: Dict[str, Any] = input_data.get("proxy", {}) or {}
        proxy_configuration = None
        if proxy_input.get("useApifyProxy"):
            proxy_configuration = await Actor.create_proxy_configuration(
                {
                    "groups": proxy_input.get("apifyProxyGroups"),
                    "countryCode": proxy_input.get("apifyProxyCountry"),
                }
            )
        elif proxy_input.get("proxyUrls"):
            proxy_configuration = await Actor.create_proxy_configuration(
                {"proxyUrls": proxy_input["proxyUrls"]}
            )

        proxy_url = (
            await proxy_configuration.new_url() if proxy_configuration else None
        )

        async with async_playwright() as playwright:
            launch_kwargs: Dict[str, Any] = {}
            if proxy_url:
                launch_kwargs["proxy"] = {"server": proxy_url}

            browser = await playwright.chromium.launch(headless=True, **launch_kwargs)
            context = await browser.new_context(
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = await context.new_page()
            await stealth_async(page)

            seen_store = await Actor.open_key_value_store("facebook-marketplace-seen")
            seen_ids: Set[str] = set(await seen_store.get_value("ids") or [])

            pushed = 0
            for url in urls:
                await Actor.log.info(f"Scraping: {url}")
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle")

                first_batch = await snapshot_cards(page)
                if dedupe_across_runs and stop_on_all_dupes and first_batch:
                    first_dupes_only = all(
                        item.get("listing_id") in seen_ids
                        for item in first_batch
                        if item.get("listing_id")
                    )
                    if first_dupes_only:
                        await Actor.log.info(
                            "First page is all duplicates; stopping early for this URL."
                        )
                        continue

                await scroll_results(page, max_scrolls=10, delay_ms=1200)
                items = await snapshot_cards(page)

                for item in items:
                    listing_id = item.get("listing_id")
                    if not listing_id:
                        continue
                    if dedupe_across_runs and listing_id in seen_ids:
                        continue

                    if fetch_item_details and item.get("url"):
                        try:
                            details = await fetch_details(context, item["url"])
                            item.update(details or {})
                        except Exception as exc:
                            await Actor.log.warning(
                                f"Detail fetch failed for {listing_id}: {exc}"
                            )

                    item["source_url"] = url
                    await Actor.push_data(item)
                    if dedupe_across_runs:
                        seen_ids.add(listing_id)
                    pushed += 1

                    if max_items and pushed >= max_items:
                        break

                if max_items and pushed >= max_items:
                    break

            if dedupe_across_runs:
                await seen_store.set_value("ids", list(seen_ids))

            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
