from __future__ import annotations

from html import unescape
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

SEARCH_COLUMNS = ["query", "title", "url", "snippet", "rank", "domain"]
SCRAPE_DEFAULTS = {
    "url": "",
    "domain": "",
    "status": "unavailable",
    "page_title": "",
    "meta_description": "",
    "text_excerpt": "",
    "social_links": 0,
    "contact_signals": 0,
    "capability_mentions": 0,
    "name_match_score": 0.0,
}
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(\+\d{1,3}[\s-]?)?(\d[\s-]?){8,14}")
_SOCIAL_DOMAINS = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com")


def _empty_search_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=SEARCH_COLUMNS)


def _extract_result_url(raw_url: str) -> str:
    if not raw_url:
        return ""

    parsed = urlparse(raw_url)
    if parsed.netloc.endswith("duckduckgo.com"):
        encoded = parse_qs(parsed.query).get("uddg", [""])
        return unescape(encoded[0]).strip()
    if raw_url.startswith("//"):
        return f"https:{raw_url}"
    return raw_url.strip()


def search_public_web(query: str, limit: int = 5, timeout_seconds: int = 4) -> pd.DataFrame:
    if not query.strip():
        return _empty_search_frame()

    try:
        response = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException:
        return _empty_search_frame()

    soup = BeautifulSoup(response.text, "html.parser")
    rows: list[dict[str, Any]] = []
    for rank, anchor in enumerate(soup.select("a.result__a, a.result-link"), start=1):
        url = _extract_result_url(anchor.get("href", ""))
        domain = urlparse(url).netloc.lower()
        if not url or not domain:
            continue

        container = anchor.find_parent(class_="result") or anchor.parent
        snippet_node = None
        if container is not None:
            snippet_node = container.select_one(".result__snippet, .result-snippet")
        rows.append(
            {
                "query": query,
                "title": anchor.get_text(" ", strip=True),
                "url": url,
                "snippet": snippet_node.get_text(" ", strip=True) if snippet_node else "",
                "rank": rank,
                "domain": domain,
            }
        )
        if len(rows) >= limit:
            break

    if not rows:
        return _empty_search_frame()
    return pd.DataFrame(rows, columns=SEARCH_COLUMNS)


def scrape_public_page(url: str, timeout_seconds: int = 4) -> dict[str, Any]:
    if not url.strip():
        return dict(SCRAPE_DEFAULTS)

    try:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException:
        return {**SCRAPE_DEFAULTS, "url": url, "domain": urlparse(url).netloc.lower()}

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type:
        return {
            **SCRAPE_DEFAULTS,
            "url": url,
            "domain": urlparse(url).netloc.lower(),
            "status": "non_html",
        }

    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    meta_description = ""
    meta_node = soup.find("meta", attrs={"name": "description"}) or soup.find(
        "meta", attrs={"property": "og:description"}
    )
    if meta_node is not None:
        meta_description = meta_node.get("content", "").strip()

    text = " ".join(soup.stripped_strings)
    excerpt = text[:900]
    social_links = 0
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "").lower()
        if any(domain in href for domain in _SOCIAL_DOMAINS):
            social_links += 1

    contact_signals = len(_EMAIL_PATTERN.findall(text)) + len(_PHONE_PATTERN.findall(text))

    return {
        "url": url,
        "domain": urlparse(url).netloc.lower(),
        "status": "ok",
        "page_title": title,
        "meta_description": meta_description,
        "text_excerpt": excerpt,
        "social_links": social_links,
        "contact_signals": contact_signals,
        "capability_mentions": 0,
        "name_match_score": 0.0,
    }
