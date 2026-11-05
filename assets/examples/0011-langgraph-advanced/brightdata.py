"""BrightData adapters: live Google/Bing results and Reddit threads.

The lab's default provider is the recorded snapshot in `data/`. `--live` swaps
in these functions. BrightData is a paid scraping API; the pieces used here are:

  SERP        POST https://api.brightdata.com/request   (a SERP zone, brd_json=1)
  Reddit      POST https://api.brightdata.com/datasets/v3/trigger
              GET  .../progress/{snapshot_id}
              GET  .../snapshot/{snapshot_id}?format=json

The Reddit dataset ids below are the public ones used by the reference agent.
Override them with env vars if your account uses different datasets.

Credentials come from `.env` (or the environment):

  BRIGHTDATA_API_KEY       required
  BRIGHTDATA_ZONE          SERP zone, default ai_agent2
  BRIGHTDATA_POLL_SECONDS  snapshot budget, default 300

This module never prints the key and never includes it in an exception message.
"""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import quote_plus

import requests

import settings  # noqa: F401  (loads .env before os.environ is read)

BASE = "https://api.brightdata.com"
REDDIT_DISCOVERY_DATASET = os.getenv(
    "BRIGHTDATA_REDDIT_DATASET", "gd_lvz8ah06191smkebj4"
)
REDDIT_COMMENTS_DATASET = os.getenv(
    "BRIGHTDATA_COMMENTS_DATASET", "gd_lvzdpsdlw09j6t702"
)


class BrightDataError(RuntimeError):
    """A live source failed. The graph treats this as an empty source."""


def missing_key_message() -> str:
    return (
        "BRIGHTDATA_API_KEY is not set, and this run asked for --live.\n"
        "  .env (this folder):  BRIGHTDATA_API_KEY=...\n"
        "  or:                  $env:BRIGHTDATA_API_KEY = \"...\"\n"
        "  Copy .env.example to .env first if you have not.\n"
        "Without it, run the recorded snapshots: uv run python agent.py"
    )


def list_zones() -> list[dict]:
    """Active zones on the account. Empty means no SERP zone exists yet."""
    data = _request("GET", f"{BASE}/zone/get_active_zones")
    if not isinstance(data, list):
        raise BrightDataError(f"zone list was not a list: {data!r}")
    return data


def _key() -> str:
    key = os.getenv("BRIGHTDATA_API_KEY")
    if not key:
        raise BrightDataError(missing_key_message())
    return key


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
    }


def _request(method: str, url: str, **kwargs: Any) -> Any:
    try:
        response = requests.request(
            method, url, headers=_headers(), timeout=60, **kwargs
        )
    except requests.RequestException as error:
        # Do not echo headers: they contain the bearer token.
        raise BrightDataError(f"{method} {url} failed: {error}") from error

    if response.status_code >= 400:
        # BrightData puts the actionable reason in the body (bad zone, dataset
        # not available, malformed payload). Show it instead of just "400".
        detail = " ".join(response.text.split())[:500] or "(empty body)"
        raise BrightDataError(
            f"{method} {url} -> HTTP {response.status_code}: {detail}"
        )

    try:
        return response.json()
    except ValueError as error:
        raise BrightDataError(f"{method} {url} returned non-JSON data") from error


def _wait_for_snapshot(snapshot_id: str) -> None:
    budget = float(os.getenv("BRIGHTDATA_POLL_SECONDS", "300"))
    deadline = time.monotonic() + budget
    delay = 5.0
    progress_url = f"{BASE}/datasets/v3/progress/{snapshot_id}"

    while time.monotonic() < deadline:
        progress = _request("GET", progress_url)
        status = progress.get("status") if isinstance(progress, dict) else None
        if status == "ready":
            return
        if status == "failed":
            raise BrightDataError(f"snapshot {snapshot_id} failed")
        time.sleep(delay)

    raise BrightDataError(
        f"snapshot {snapshot_id} did not finish within {budget:.0f}s; "
        "raise BRIGHTDATA_POLL_SECONDS if the dataset is slow"
    )


def _trigger(params: dict[str, str], data: list[dict]) -> str:
    trigger = _request(
        "POST", f"{BASE}/datasets/v3/trigger", params=params, json=data
    )
    snapshot_id = trigger.get("snapshot_id") if isinstance(trigger, dict) else None
    if not snapshot_id:
        raise BrightDataError(f"trigger returned no snapshot_id: {trigger!r}")
    return snapshot_id


def _reddit_request(question: str, num_of_posts: int = 75) -> tuple[dict, list[dict]]:
    params = {
        "dataset_id": REDDIT_DISCOVERY_DATASET,
        "include_errors": "true",
        "type": "discover_new",
        "discover_by": "keyword",
    }
    data = [
        {
            "keyword": question,
            "date": "All time",
            "sort_by": "Hot",
            "num_of_posts": num_of_posts,
        }
    ]
    return params, data


def trigger_reddit(question: str, num_of_posts: int = 75) -> str:
    """Start a Reddit discovery snapshot and return its id without polling.

    Used by `agent.py --check`: it validates the key and dataset access without
    waiting minutes for the snapshot to finish.
    """
    params, data = _reddit_request(question, num_of_posts)
    return _trigger(params, data)


def _trigger_and_download(params: dict[str, str], data: list[dict]) -> list[dict]:
    snapshot_id = _trigger(params, data)
    _wait_for_snapshot(snapshot_id)
    rows = _request(
        "GET",
        f"{BASE}/datasets/v3/snapshot/{snapshot_id}",
        params={"format": "json"},
    )
    if not isinstance(rows, list):
        raise BrightDataError("snapshot download did not return a list")
    return rows


def search(engine: str, question: str, limit: int = 5) -> list[dict]:
    """Live SERP results, normalized to the shape the graph expects."""
    if engine not in {"google", "bing"}:
        raise ValueError(f"unknown engine: {engine}")

    base = {
        "google": "https://www.google.com/search",
        "bing": "https://www.bing.com/search",
    }[engine]
    zone = os.getenv("BRIGHTDATA_ZONE", "").strip()
    if not zone:
        raise BrightDataError(
            "BRIGHTDATA_ZONE is not set. Create a SERP / Web Scraper API zone in "
            "BrightData and put its name in .env. The reference's ai_agent2 is "
            "not your account's zone."
        )
    payload = {
        "zone": zone,
        "url": f"{base}?q={quote_plus(question)}&brd_json=1",
        "format": "raw",
    }
    data = _request("POST", f"{BASE}/request", json=payload)
    organic = data.get("organic", []) if isinstance(data, dict) else []

    results = []
    for item in organic[:limit]:
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("link") or item.get("url") or "",
                "snippet": item.get("description") or item.get("snippet") or "",
            }
        )
    return results


def reddit_search(question: str, limit: int = 5) -> list[dict]:
    """Live Reddit discovery, normalized to {title, url, snippet}."""
    params, data = _reddit_request(question)
    rows = _trigger_and_download(params, data)

    results = []
    for row in rows[:limit]:
        title = row.get("title") or ""
        results.append(
            {
                "title": title,
                "url": row.get("url") or "",
                "snippet": (row.get("description") or title)[:280],
            }
        )
    return results


def reddit_threads(urls: list[str]) -> list[dict]:
    """Live comments for the selected posts, grouped by URL."""
    if not urls:
        return []

    params = {
        "dataset_id": REDDIT_COMMENTS_DATASET,
        "include_errors": "true",
    }
    data = [
        {
            "url": url,
            "days_back": 10,
            "load_all_replies": False,
            "comment_limit": "",
        }
        for url in urls
    ]
    rows = _trigger_and_download(params, data)

    threads: dict[str, dict] = {
        url: {"url": url, "title": "", "comments": []} for url in urls
    }
    stray: list[str] = []
    for row in rows:
        url = row.get("url") or row.get("post_url") or ""
        comment = row.get("comment") or row.get("content") or ""
        if not comment:
            continue
        if not url:
            stray.append(comment)
            continue
        thread = threads.setdefault(
            url, {"url": url, "title": "", "comments": []}
        )
        if not thread["title"]:
            thread["title"] = row.get("post_title") or row.get("title") or ""
        thread["comments"].append(comment)

    # Some dataset versions omit the input URL. Keep the comments instead of
    # silently returning nothing: attach them to the first selected thread.
    if stray and not any(thread["comments"] for thread in threads.values()):
        threads[urls[0]]["comments"] = stray

    # Keep the caller's order and drop threads that produced no comments.
    return [threads[url] for url in urls if threads[url]["comments"]]
