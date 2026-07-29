from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SUPPORTED_HOSTS = {
    "amazon.sa",
    "www.amazon.sa",
}

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class ScrapeError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProductSnapshot:
    url: str
    asin: str | None
    marketplace: str
    title: str
    price: float
    currency: str


def validate_amazon_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("The URL must start with http or https.")
    if parsed.hostname not in SUPPORTED_HOSTS:
        raise ValueError("This version supports Amazon.sa URLs only.")
    return url.strip()


def extract_asin(url: str) -> str | None:
    parsed = urlparse(url)
    patterns = [
        r"/dp/([A-Z0-9]{10})(?:[/?]|$)",
        r"/gp/product/([A-Z0-9]{10})(?:[/?]|$)",
        r"/product/([A-Z0-9]{10})(?:[/?]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, parsed.path, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    query = parse_qs(parsed.query)
    for key in ("asin", "ASIN"):
        values = query.get(key)
        if values and re.fullmatch(r"[A-Z0-9]{10}", values[0], re.IGNORECASE):
            return values[0].upper()
    return None


def parse_price(raw: str | None) -> float | None:
    if not raw:
        return None

    value = raw.translate(ARABIC_DIGITS)
    value = value.replace("\u066c", ",").replace("\u066b", ".")
    value = value.replace("\xa0", " ").strip()

    match = re.search(r"(\d[\d,.\s]*)", value)
    if not match:
        return None

    number = re.sub(r"\s+", "", match.group(1))

    if "," in number and "." in number:
        if number.rfind(".") > number.rfind(","):
            number = number.replace(",", "")
        else:
            number = number.replace(".", "").replace(",", ".")
    elif "," in number:
        tail = number.split(",")[-1]
        if len(tail) in {1, 2}:
            number = number.replace(",", ".")
        else:
            number = number.replace(",", "")

    try:
        parsed = float(number)
    except ValueError:
        return None

    return parsed if parsed > 0 else None


def _extract_json_ld(page) -> tuple[str | None, float | None]:
    scripts = page.locator('script[type="application/ld+json"]')
    for index in range(scripts.count()):
        text = scripts.nth(index).text_content() or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue

        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            title = node.get("name")
            offers = node.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict):
                price = parse_price(str(offers.get("price", "")))
                if price:
                    return str(title or "").strip() or None, price
    return None, None


def scrape_product(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45_000,
) -> ProductSnapshot:
    url = validate_amazon_url(url)
    asin = extract_asin(url)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="ar-SA",
            timezone_id="Asia/Riyadh",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2500)

            page_title = (page.title() or "").lower()
            body_text = (page.locator("body").inner_text(timeout=10_000) or "").lower()
            captcha_markers = (
                "robot check",
                "enter the characters you see below",
                "أدخل الأحرف التي تراها",
                "sorry, we just need to make sure you're not a robot",
            )
            if any(marker in page_title or marker in body_text for marker in captcha_markers):
                raise ScrapeError(
                    "Amazon displayed a verification/CAPTCHA page. No bypass was attempted; try again later."
                )

            title = None
            title_selectors = [
                "#productTitle",
                'meta[property="og:title"]',
                "h1 span",
            ]
            for selector in title_selectors:
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                if selector.startswith("meta"):
                    candidate = locator.get_attribute("content")
                else:
                    candidate = locator.text_content()
                if candidate and candidate.strip():
                    title = candidate.strip()
                    break

            json_title, json_price = _extract_json_ld(page)
            if not title:
                title = json_title

            price = None
            price_selectors = [
                "#corePrice_feature_div .priceToPay .a-offscreen",
                "#corePrice_feature_div .a-price .a-offscreen",
                "#corePriceDisplay_desktop_feature_div .priceToPay .a-offscreen",
                "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
                "#apex_desktop .priceToPay .a-offscreen",
                "#apex_desktop .a-price .a-offscreen",
                "#priceblock_dealprice",
                "#priceblock_ourprice",
                "#priceblock_saleprice",
                'meta[itemprop="price"]',
            ]
            for selector in price_selectors:
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                if selector.startswith("meta"):
                    candidate = locator.get_attribute("content")
                else:
                    candidate = locator.text_content()
                parsed_price = parse_price(candidate)
                if parsed_price is not None:
                    price = parsed_price
                    break

            if price is None:
                price = json_price

            if not title:
                raise ScrapeError("Could not extract the product title from the page.")
            if price is None:
                raise ScrapeError(
                    "Could not extract the price. The product may be unavailable or the page layout may have changed."
                )

            return ProductSnapshot(
                url=page.url,
                asin=asin or extract_asin(page.url),
                marketplace="amazon.sa",
                title=title,
                price=price,
                currency="SAR",
            )

        except PlaywrightTimeoutError as exc:
            raise ScrapeError("The Amazon page load timed out.") from exc
        finally:
            context.close()
            browser.close()
