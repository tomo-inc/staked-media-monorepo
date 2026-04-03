from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree

import defusedxml.ElementTree as DefusedET
import requests

TOKEN_RE = re.compile(r"[$]?[A-Za-z][A-Za-z0-9_']+|[\u4e00-\u9fff]{2,12}")


@dataclass(frozen=True)
class WebItem:
    title: str
    summary: str
    url: str
    source: str
    published_at: str


class WebEnricher:
    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_items: int = 12,
        recency_hours: int = 24,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_items = max_items
        self.recency_hours = recency_hours

    def search_recent_topic_signals(self, topic: str, keywords: list[str]) -> dict[str, Any]:
        query_terms = [topic] + keywords
        query_terms = [term.strip() for term in query_terms if term and term.strip()]
        if not query_terms:
            return {"items": [], "keywords": [], "facts": []}

        query = " ".join(query_terms[:6])
        items = self._fetch_google_news_rss(query)
        extracted_keywords = self._extract_keywords(items, query_terms)
        facts = [
            {
                "title": item.title,
                "summary": item.summary,
                "source": item.source,
                "url": item.url,
                "published_at": item.published_at,
            }
            for item in items
        ]
        return {
            "items": facts,
            "keywords": extracted_keywords,
            "facts": facts[:5],
        }

    def _fetch_google_news_rss(self, query: str) -> list[WebItem]:
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}+when:1d&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        try:
            response = requests.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException:
            return []

        try:
            root = DefusedET.fromstring(response.content)
        except ElementTree.ParseError:
            return []

        cutoff = datetime.now(UTC) - timedelta(hours=self.recency_hours)
        results: list[WebItem] = []
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            description = (item.findtext("description") or "").strip()
            link = (item.findtext("link") or "").strip()
            source = (item.findtext("source") or "").strip()
            pub_date_raw = (item.findtext("pubDate") or "").strip()
            published_at = ""
            if pub_date_raw:
                try:
                    parsed = parsedate_to_datetime(pub_date_raw).astimezone(UTC)
                    if parsed < cutoff:
                        continue
                    published_at = parsed.replace(microsecond=0).isoformat()
                except Exception:
                    published_at = pub_date_raw
            results.append(
                WebItem(
                    title=title,
                    summary=_strip_html(description),
                    url=link,
                    source=source,
                    published_at=published_at,
                )
            )
            if len(results) >= self.max_items:
                break
        return results

    def _extract_keywords(self, items: list[WebItem], base_terms: list[str], *, limit: int = 15) -> list[str]:
        seen: set[str] = set()
        keywords: list[str] = []
        blocked = {term.lower() for term in base_terms}

        for term in base_terms:
            normalized = term.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            keywords.append(term.strip())

        for item in items:
            text = f"{item.title} {item.summary}"
            for token in TOKEN_RE.findall(text):
                normalized = token.lower().strip("$")
                if len(normalized) < 2 or normalized in seen or normalized in blocked:
                    continue
                seen.add(normalized)
                keywords.append(token)
                if len(keywords) >= limit:
                    return keywords
        return keywords


def _strip_html(text: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", without_tags).strip()
