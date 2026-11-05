"""The source layer and its provider interface.

The graph talks to a provider object, never to a search API directly. A provider
implements four members:

    name                                      # what the trace prints
    search(engine, question, limit)           -> [{title, url, snippet}, ...]
    reddit_search(question, limit)            -> [{title, url, snippet}, ...]
    reddit_threads(urls)                      -> [{title, url, comments}, ...]
    check()                                   # raise if it is not ready to run

Two providers ship with the lab:

    snapshot    reads data/*.json, ranked by query overlap. No key, no network.
    brightdata  live SERP + Reddit datasets (see brightdata.py).

Pick one with `--live` (brightdata), `SEARCH_PROVIDER` in `.env`, or the default
`snapshot`. To add another provider (Oxylabs, SerpAPI, Tavily, your own index),
implement the four members in a class and add one line to PROVIDERS:

    class OxylabsProvider:
        name = "oxylabs"
        def check(self) -> None: ...
        def search(...): ...
        def reddit_search(...): ...
        def reddit_threads(...): ...

    PROVIDERS["oxylabs"] = OxylabsProvider

Then set SEARCH_PROVIDER=oxylabs. The graph, prompts and state do not change.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Protocol

import brightdata
import settings  # noqa: F401  (loads .env before os.environ is read)

DATA = Path(__file__).resolve().parent / "data"
SourceError = brightdata.BrightDataError
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "build", "by", "for", "from",
    "how", "in", "is", "it", "its", "of", "on", "or", "should", "small",
    "that", "the", "their", "this", "to", "use", "what", "when", "with",
}


class SourceProvider(Protocol):
    """The only contract the graph depends on."""

    name: str

    def search(
        self, engine: str, question: str, limit: int = 5
    ) -> list[dict]: ...

    def reddit_search(self, question: str, limit: int = 5) -> list[dict]: ...

    def reddit_threads(self, urls: list[str]) -> list[dict]: ...

    def check(self) -> None: ...


def _load(name: str) -> list[dict]:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _tokens(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9]+", text.lower()) if word not in STOPWORDS]


def _score(question: str, document: dict) -> int:
    query = set(_tokens(question))
    title = _tokens(document.get("title", ""))
    snippet = _tokens(document.get("snippet", ""))
    return 3 * sum(1 for word in title if word in query) + sum(
        1 for word in snippet if word in query
    )


class SnapshotProvider:
    """Recorded results from data/*.json. Deterministic and offline."""

    name = "snapshot"

    def check(self) -> None:
        return None

    def search(self, engine: str, question: str, limit: int = 5) -> list[dict]:
        if engine not in {"google", "bing"}:
            raise ValueError(f"unknown engine: {engine}")
        documents = _load(f"{engine}.json")
        # sorted() is stable, so equal scores keep the recorded order.
        ranked = sorted(
            documents, key=lambda document: _score(question, document), reverse=True
        )
        return [
            {
                "title": document["title"],
                "url": document["url"],
                "snippet": document["snippet"],
            }
            for document in ranked[:limit]
        ]

    def reddit_search(self, question: str, limit: int = 5) -> list[dict]:
        posts = _load("reddit.json")
        ranked = sorted(posts, key=lambda post: _score(question, post), reverse=True)
        return [
            {
                "title": post["title"],
                "url": post["url"],
                "snippet": post["snippet"],
            }
            for post in ranked[:limit]
        ]

    def reddit_threads(self, urls: list[str]) -> list[dict]:
        if not urls:
            return []

        by_url = {post["url"]: post for post in _load("reddit.json")}
        threads = []
        for url in urls:
            post = by_url.get(url)
            if post is None:
                # The model may invent a URL; never fetch or trust it.
                continue
            threads.append(
                {
                    "url": url,
                    "title": post["title"],
                    "comments": post["comments"],
                }
            )
        return threads


class BrightDataProvider:
    """Live provider: BrightData SERP + Reddit datasets."""

    name = "brightdata"

    def check(self) -> None:
        if not os.getenv("BRIGHTDATA_API_KEY"):
            raise SourceError(brightdata.missing_key_message())

        zone = os.getenv("BRIGHTDATA_ZONE", "").strip()
        if not zone:
            raise SourceError(
                "BRIGHTDATA_ZONE is not set. Run `uv run python agent.py --zones`; "
                "if the list is empty, create a SERP / Web Scraper API zone in "
                "BrightData, then put its name in .env."
            )

        try:
            zones = brightdata.list_zones()
        except Exception as error:  # noqa: BLE001 - turn the API error into one line
            raise SourceError(f"could not list BrightData zones: {error}") from error

        names = {
            zone_info.get("name") or zone_info.get("zone")
            for zone_info in zones
            if isinstance(zone_info, dict)
        }
        if zone not in names:
            active = ", ".join(sorted(name for name in names if name)) or "none"
            raise SourceError(
                f"BRIGHTDATA_ZONE={zone!r} is not an active zone (active: {active}). "
                "Run `uv run python agent.py --zones`, create a SERP zone if the "
                "list is empty, then set BRIGHTDATA_ZONE in .env."
            )

    def search(self, engine: str, question: str, limit: int = 5) -> list[dict]:
        return brightdata.search(engine, question, limit=limit)

    def reddit_search(self, question: str, limit: int = 5) -> list[dict]:
        return brightdata.reddit_search(question, limit=limit)

    def reddit_threads(self, urls: list[str]) -> list[dict]:
        return brightdata.reddit_threads(urls)


PROVIDERS: dict[str, type[SourceProvider]] = {
    "snapshot": SnapshotProvider,
    "brightdata": BrightDataProvider,
}


def get_provider(explicit: str | None = None) -> SourceProvider:
    """CLI wins, then SEARCH_PROVIDER, then the recorded snapshot."""
    name = (explicit or os.getenv("SEARCH_PROVIDER", "snapshot")).strip().lower()
    try:
        factory = PROVIDERS[name]
    except KeyError as error:
        choices = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown provider {name!r}; use one of {choices}") from error
    return factory()
