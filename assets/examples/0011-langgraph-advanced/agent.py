"""A multi-source research agent as a LangGraph fan-out / fan-in.

    START -> search_google ─┐
          -> search_bing   ─┼─> select_reddit_urls -> fetch_reddit -> analyze_reddit ─┐
          -> search_reddit ─┘                                                          │
                                                                                       ├─> synthesize -> END
    START -> search_google -> analyze_google ─────────────────────────────────────────┤
          -> search_bing   -> analyze_bing   ─────────────────────────────────────────┘

The default graph is the reference shape: three searches join, Reddit URLs are
selected and fetched, then three analyses run in parallel and join for
synthesis. `--critical` moves Google and Bing analyses off the Reddit branch;
`--loose-join` shows why that restructuring needs an explicit list-edge join.

Sources come from recorded snapshots by default. `--live` swaps in BrightData,
reading `BRIGHTDATA_API_KEY` from the environment or `.env`. `--provider NAME`
selects any provider registered in `sources.PROVIDERS`.

Reddit is off by default. Set `REDDIT_ENABLED=true` in `.env` (or the shell) to
add the Reddit branch: selector -> comment fetch -> analysis.

Run from this folder:

    uv sync
    uv run python agent.py
    REDDIT_ENABLED=true uv run python agent.py     # bash
    $env:REDDIT_ENABLED = "true"; uv run python agent.py   # PowerShell
    uv run python agent.py --live
    uv run python agent.py --provider snapshot
    uv run python agent.py --critical
    uv run python agent.py --critical --loose-join
    uv run python agent.py "your question"
    uv run python agent.py --fail bing
    uv run python agent.py --check
    uv run python agent.py --zones
    uv run python agent.py --mermaid
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

import prompts
import sources
from common import build_model

SAMPLE_QUESTION = (
    "Should a small support team build its agent on LangGraph or a plain tool loop?"
)
TRUE_VALUES = {"1", "true", "yes", "on"}


def reddit_enabled() -> bool:
    """Reddit is opt-in: set REDDIT_ENABLED=true in .env or the shell."""
    return os.getenv("REDDIT_ENABLED", "false").strip().lower() in TRUE_VALUES


class RedditURLs(BaseModel):
    """The selector's output: only threads worth reading in full."""

    selected_urls: list[str] = Field(
        description="At most three Reddit URLs copied from the supplied list"
    )


def merge_analyses(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    """Reducer: three parallel analyzers each write one key of the same dict."""
    return {**left, **right}


class State(TypedDict):
    question: str
    google_results: list[dict]
    bing_results: list[dict]
    reddit_results: list[dict]
    selected_urls: list[str]
    reddit_posts: list[dict]
    analyses: Annotated[dict[str, str], merge_analyses]
    answer: str


def initial_state(question: str) -> dict:
    return {
        "question": question,
        "google_results": [],
        "bing_results": [],
        "reddit_results": [],
        "selected_urls": [],
        "reddit_posts": [],
        "analyses": {},
        "answer": "",
    }


def build_graph(
    model,
    *,
    provider: sources.SourceProvider,
    reddit: bool,
    critical: bool = False,
    loose_join: bool = False,
    failures: frozenset[str] = frozenset(),
):
    def search_node(source: str):
        def node(state: State) -> dict:
            if source in failures:
                return {f"{source}_results": []}
            try:
                if source == "reddit":
                    results = provider.reddit_search(state["question"])
                    return {"reddit_results": results}
                results = provider.search(source, state["question"])
                return {f"{source}_results": results}
            except Exception as error:  # noqa: BLE001 - a dead source must not kill the join
                print(f"warning: {source} source failed: {error}", file=sys.stderr)
                return {f"{source}_results": []}

        return node

    def select_reddit_urls(state: State) -> dict:
        posts = state["reddit_results"]
        if not posts or model is None:
            return {"selected_urls": []}

        picker = model.with_structured_output(RedditURLs, method="function_calling")
        try:
            picked = picker.invoke(prompts.selector_messages(state["question"], posts))
        except Exception as error:  # noqa: BLE001 - a dead selector must not kill the join
            print(f"warning: URL selection failed: {error}", file=sys.stderr)
            return {"selected_urls": []}

        allowed = {post["url"] for post in posts}
        urls: list[str] = []
        for url in picked.selected_urls:
            if url in allowed and url not in urls:
                urls.append(url)
        return {"selected_urls": urls[:3]}

    def fetch_reddit(state: State) -> dict:
        try:
            return {"reddit_posts": provider.reddit_threads(state["selected_urls"])}
        except Exception as error:  # noqa: BLE001 - keep the join alive
            print(f"warning: Reddit fetch failed: {error}", file=sys.stderr)
            return {"reddit_posts": []}

    def analyzer(source: str):
        def node(state: State) -> dict:
            if source == "reddit":
                payload = {
                    "search_results": state["reddit_results"],
                    "threads": state["reddit_posts"],
                }
            else:
                payload = state[f"{source}_results"]

            if not payload or (isinstance(payload, dict) and not any(payload.values())):
                return {"analyses": {source: "(no results returned)"}}

            reply = model.invoke(
                prompts.analysis_messages(source, state["question"], payload)
            )
            return {"analyses": {source: reply.content}}

        return node

    def synthesize(state: State) -> dict:
        reply = model.invoke(
            prompts.synthesis_messages(state["question"], state["analyses"])
        )
        return {"answer": reply.content}

    active = ("google", "bing") + (("reddit",) if reddit else ())
    graph = StateGraph(State)
    for source in active:
        graph.add_node(f"search_{source}", search_node(source))
        graph.add_node(f"analyze_{source}", analyzer(source))
    if reddit:
        graph.add_node("select_reddit_urls", select_reddit_urls)
        graph.add_node("fetch_reddit", fetch_reddit)
    graph.add_node("synthesize", synthesize)

    for source in active:
        graph.add_edge(START, f"search_{source}")

    if not reddit:
        # Two independent sources, one analysis each.
        for source in active:
            graph.add_edge(f"search_{source}", f"analyze_{source}")
    elif critical:
        # Critical-path attempt: only Reddit waits for Reddit. Google and Bing
        # analyses run while the Reddit branch is still selecting and fetching.
        graph.add_edge("search_reddit", "select_reddit_urls")
        graph.add_edge("select_reddit_urls", "fetch_reddit")
        graph.add_edge("fetch_reddit", "analyze_reddit")
        graph.add_edge("search_google", "analyze_google")
        graph.add_edge("search_bing", "analyze_bing")
    else:
        # Reference shape: all three searches join before Reddit selection,
        # and every analysis waits for the Reddit fetch.
        graph.add_edge(
            ["search_google", "search_bing", "search_reddit"], "select_reddit_urls"
        )
        graph.add_edge("select_reddit_urls", "fetch_reddit")
        for source in ("google", "bing", "reddit"):
            graph.add_edge("fetch_reddit", f"analyze_{source}")

    analyzers = [f"analyze_{source}" for source in active]
    if loose_join:
        # The bug: separate edges from different supersteps are not a barrier.
        # synthesize can fire with only some of the analyses.
        for name in analyzers:
            graph.add_edge(name, "synthesize")
    else:
        graph.add_edge(analyzers, "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


def describe(delta: dict) -> str:
    for key, value in delta.items():
        if key == "analyses":
            return f"analyses += {', '.join(value)}"
        if key.endswith("_results"):
            return f"{len(value)} results"
        if key == "selected_urls":
            return f"{len(value)} urls"
        if key == "reddit_posts":
            comments = sum(len(thread["comments"]) for thread in value)
            return f"{len(value)} threads / {comments} comments"
        if key == "answer":
            return f"{len(value.split())} words"
    return ""


def run(
    question: str,
    model,
    *,
    provider: sources.SourceProvider,
    reddit: bool,
    critical: bool,
    loose_join: bool,
    failures: frozenset[str],
) -> int:
    app = build_graph(
        model,
        provider=provider,
        reddit=reddit,
        critical=critical,
        loose_join=loose_join,
        failures=failures,
    )
    inputs = initial_state(question)
    final = inputs
    nodes = 0
    started = time.perf_counter()

    print(f"question: {question}")
    shape = "critical-path" if critical else "reference"
    print(f"graph:    {shape} (fan-out, fan-in)")
    print(f"source:   {provider.name}")
    print(f"reddit:   {'on' if reddit else 'off (REDDIT_ENABLED=false)'}")
    if critical and not reddit:
        print("note:     --critical has no effect while Reddit is disabled")
    if loose_join:
        print("join:     loose (separate edges, no barrier)")
    if failures:
        print(f"failed:   {', '.join(sorted(failures))} (injected)")
    print()

    for mode, chunk in app.stream(inputs, stream_mode=["updates", "values"]):
        if mode == "values":
            final = chunk
            continue
        for node, delta in chunk.items():
            nodes += 1
            elapsed = time.perf_counter() - started
            print(f"[{elapsed:6.1f}s] {node:<20} {describe(delta)}")

    elapsed = time.perf_counter() - started
    print()
    print(f"answer: {final['answer']}")
    print()
    print(
        "sources: "
        f"google={len(final['google_results'])} "
        f"bing={len(final['bing_results'])} "
        f"reddit={len(final['reddit_results'])} | "
        f"urls={len(final['selected_urls'])} | "
        f"threads={len(final['reddit_posts'])}"
    )
    print(
        f"graph: {', '.join(final['analyses']) or 'none'} | "
        f"nodes={nodes} | {elapsed:.1f}s"
    )
    return 0


def check_provider(provider: sources.SourceProvider, reddit: bool) -> int:
    """Test the provider without running the graph (no DeepSeek calls)."""
    print(f"provider: {provider.name}")

    try:
        provider.check()
    except sources.SourceError as error:
        print(f"check:    {error}", file=sys.stderr)
        return 1
    print("check:    ok")

    failures = 0
    for label in ("google", "bing"):
        try:
            results = provider.search(label, "test query", limit=2)
            print(f"{label:9} {len(results)} results")
            if results:
                print(f"          first: {results[0].get('title', '')[:70]}")
        except Exception as error:  # noqa: BLE001 - report and keep checking
            failures += 1
            print(f"{label:9} failed: {error}", file=sys.stderr)

    if not reddit:
        print("reddit    disabled (REDDIT_ENABLED=false)")
    elif provider.name == "brightdata":
        import brightdata

        try:
            snapshot_id = brightdata.trigger_reddit("test query")
            print(
                f"reddit    trigger accepted (snapshot {snapshot_id}); "
                "polling skipped"
            )
        except Exception as error:  # noqa: BLE001 - report the API body
            failures += 1
            print(f"reddit    failed: {error}", file=sys.stderr)
    else:
        try:
            results = provider.reddit_search("test query", limit=2)
            print(f"reddit    {len(results)} results")
            if results:
                print(f"          first: {results[0].get('title', '')[:70]}")
        except Exception as error:  # noqa: BLE001
            failures += 1
            print(f"reddit    failed: {error}", file=sys.stderr)

    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="*", help="defaults to the sample question")
    parser.add_argument(
        "--critical", action="store_true", help="move Google/Bing analyses off the Reddit branch"
    )
    parser.add_argument(
        "--loose-join",
        action="store_true",
        help="join the analyses with separate edges (reproduces the early-fire bug)",
    )
    parser.add_argument(
        "--fail",
        action="append",
        choices=["google", "bing", "reddit"],
        default=[],
        metavar="SOURCE",
        help="inject an empty result for a source (repeatable)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="shorthand for --provider brightdata",
    )
    parser.add_argument(
        "--provider",
        metavar="NAME",
        help="provider registered in sources.PROVIDERS (default: snapshot)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="test the selected provider and exit (no DeepSeek calls)",
    )
    parser.add_argument(
        "--zones",
        action="store_true",
        help="list active BrightData zones and exit",
    )
    parser.add_argument("--mermaid", action="store_true", help="print the graph source")
    args = parser.parse_args()

    if args.zones:
        import brightdata

        try:
            zones = brightdata.list_zones()
        except Exception as error:  # noqa: BLE001 - the API body is the message
            print(f"error: {error}", file=sys.stderr)
            return 1
        if not zones:
            print("no active zones.")
            print("Create a SERP / Web Scraper API zone in BrightData, then set")
            print("BRIGHTDATA_ZONE to its name in .env.")
            return 1
        for zone in zones:
            name = zone.get("name") or zone.get("zone") or "?"
            kind = zone.get("type") or zone.get("zone_type") or ""
            print(f"{name}  {kind}".rstrip())
        print("\nSet BRIGHTDATA_ZONE to one of these names in .env.")
        return 0

    try:
        explicit = args.provider or ("brightdata" if args.live else None)
        provider = sources.get_provider(explicit)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    reddit = reddit_enabled()

    if args.check:
        return check_provider(provider, reddit)

    if args.mermaid:
        app = build_graph(
            None,
            provider=provider,
            reddit=reddit,
            critical=args.critical,
            loose_join=args.loose_join,
        )
        print(app.get_graph().draw_mermaid())
        return 0

    try:
        provider.check()
    except sources.SourceError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    question = " ".join(args.question) or SAMPLE_QUESTION
    try:
        model = build_model()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    failures = frozenset(args.fail) - (frozenset() if reddit else {"reddit"})
    try:
        return run(
            question,
            model,
            provider=provider,
            reddit=reddit,
            critical=args.critical,
            loose_join=args.loose_join,
            failures=failures,
        )
    except Exception as error:  # noqa: BLE001 - show the provider error, keep exit 1
        print(f"error: {type(error).__name__}: {error}", file=sys.stderr)
        print("check DEEPSEEK_API_KEY, account balance, and network access.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
