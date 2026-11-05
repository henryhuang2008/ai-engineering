# 0011 — LangGraph, advanced: fan-out, fan-in, and a join that fires early

A multi-source research agent as a graph:

```
START -> search_google ─┐
      -> search_bing   ─┼─> select_reddit_urls -> fetch_reddit -> analyze_reddit ─┐
      -> search_reddit ─┘                                                         │
                                                                                   ├─> synthesize -> END
START -> search_google -> analyze_google ──────────────────────────────────────────┤
      -> search_bing   -> analyze_bing   ──────────────────────────────────────────┘
```

By default **two searches** fan out (Google, Bing); setting `REDDIT_ENABLED=true` adds a third, Reddit branch — a structured-output selector, a comment fetch, and a third analysis. The analyses run in parallel and one synthesis writes the answer. The model is **DeepSeek** through `ChatDeepSeek`. The source layer reads recorded snapshots by default, or calls **BrightData** with `--live`.

The default graph is the reference shape: all three searches join before selection, and all three analyses wait for the Reddit fetch. `--critical` moves Google and Bing analyses off the Reddit branch. `--loose-join` reproduces the bug that restructuring exposes: **separate edges from different supersteps are not a barrier**, so `synthesize` runs twice.

## Run

```powershell
cd assets\examples\0011-langgraph-advanced
Copy-Item .env.example .env      # first time only; fill DEEPSEEK_API_KEY (+ BRIGHTDATA_API_KEY for --live)
uv sync

uv run python agent.py                          # two sources (Reddit off by default)
uv run python agent.py --provider snapshot      # local JSON, same as default
uv run python agent.py --live                   # BrightData (needs key + zone)
uv run python agent.py --critical               # with Reddit on: move Google/Bing earlier
uv run python agent.py --critical --loose-join  # with Reddit on: break the join
uv run python agent.py --fail bing              # one source returns nothing
uv run python agent.py --check                  # test the provider, no model calls
uv run python agent.py --zones                  # list active BrightData zones
uv run python agent.py --mermaid                # print the graph source
```

`REDDIT_ENABLED=true` in `.env` (or the shell) turns on the Reddit branch. `DEEPSEEK_API_KEY` can live in `.env` or in the shell. A full run makes five live DeepSeek calls (selector, three analyses, synthesis); the default two-source run makes three (two analyses, synthesis).

## What you should see

Default, two sources (Reddit off), one real run:

```
question: Should a small support team build its agent on LangGraph or a plain tool loop?
graph:    reference (fan-out, fan-in)
source:   snapshot
reddit:   off (REDDIT_ENABLED=false)

[   0.0s] search_bing          5 results
[   0.0s] search_google        5 results
[   2.5s] analyze_bing         analyses += bing
[   2.5s] analyze_google       analyses += google
[   4.8s] synthesize           173 words

sources: google=5 bing=5 reddit=0 | urls=0 | threads=0
graph: bing, google | nodes=5 | 4.8s
```

With `REDDIT_ENABLED=true`, the Reddit selector and third branch join the graph:

```
question: Should a small support team build its agent on LangGraph or a plain tool loop?
graph:    reference (fan-out, fan-in)
source:   snapshot
reddit:   on

[   0.0s] search_bing          5 results
[   0.0s] search_google        5 results
[   0.0s] search_reddit        5 results
[   1.6s] select_reddit_urls   3 urls
[   1.6s] fetch_reddit         3 threads / 9 comments
[   4.1s] analyze_bing         analyses += bing
[   4.4s] analyze_google       analyses += google
[   4.4s] analyze_reddit       analyses += reddit
[   6.6s] synthesize           180 words

answer: **Recommendation:** Start with a plain tool loop; migrate to LangGraph only
when a concrete operational requirement forces it.

sources: google=5 bing=5 reddit=5 | urls=3 | threads=3
graph: bing, google, reddit | nodes=9 | 6.6s
```

The three searches complete together because they are one superstep. The three analyses also complete together, after the fetch. Nine node executions, one synthesis.

## The join that fires early

The rest of this section assumes `REDDIT_ENABLED=true` — without it there is no third branch to arrive late. `--critical` is the tempting edit: Google and Bing analyses do not need Reddit, so start them as soon as their searches finish. If you wire the analyses to `synthesize` with separate `add_edge` calls, the join is **not** a barrier when its predecessors live in different supersteps:

```
[   2.4s] analyze_bing         analyses += bing
[   2.7s] analyze_google       analyses += google
[   5.2s] synthesize           179 words     <- fires with two analyses
[   7.6s] analyze_reddit       analyses += reddit
[   9.9s] synthesize           180 words     <- fires again with all three
...
nodes=10 | 9.9s
```

The first answer was thrown away, and the run paid for an extra synthesis call. LangGraph triggered `synthesize` when the reachable predecessors finished, then triggered it again when Reddit arrived. The fix is an explicit list edge:

```python
graph.add_edge(
    ["analyze_google", "analyze_bing", "analyze_reddit"], "synthesize"
)
```

The same thing happens in a small graph with no model at all: a fast branch reaches the join, which runs, then the slow branch reaches it and it runs again. A list edge (or a dedicated join node with a counter) is what makes "wait for all" true.

## Failure is a branch too

`--fail bing` injects an empty result for one source (the trace uses `REDDIT_ENABLED=true`):

```
[   0.0s] search_bing          0 results
[   1.6s] analyze_bing         analyses += bing
...
**Missing/empty sources:** Bing returned no results.
sources: google=5 bing=0 reddit=5 | urls=3 | threads=3 | nodes=9 | 6.3s
```

The join still completes and the answer names the gap. The source node returns `[]`; the analyzer writes a placeholder instead of calling the model; synthesis sees the hole. A provider error that raised inside a node would fail the whole superstep, so the source layer normalizes failure at the boundary.

## The critical path, measured

With `REDDIT_ENABLED=true`, `--critical` looks faster — Google and Bing analyses finish at ~2.3s instead of ~3.5s. But the final synthesis still waits for the Reddit branch, which finished at ~4.7s:

```
[   1.4s] select_reddit_urls   3 urls
[   2.1s] analyze_google       analyses += google
[   2.3s] analyze_bing         analyses += bing
[   2.3s] fetch_reddit         3 threads / 9 comments
[   4.7s] analyze_reddit       analyses += reddit
[   6.7s] synthesize           167 words
```

In our runs the reference shape took 5.9–6.6s and the critical-path shape 6.7s. Moving work earlier only helps when the branch you move is the long pole; here Reddit is. The structural fix is still right — Google and Bing genuinely do not depend on Reddit — but the stopwatch is the judge, not the arrow count. Timestamps are emitted when a superstep finishes, so a fast node that shares a superstep with a slow one appears late.

## One provider interface, two implementations

The graph never touches a search API. It calls four members of a provider object:

```python
class SourceProvider(Protocol):
    name: str
    def search(self, engine, question, limit=5) -> list[dict]: ...
    def reddit_search(self, question, limit=5) -> list[dict]: ...
    def reddit_threads(self, urls) -> list[dict]: ...
    def check(self) -> None: ...
```

Two implementations ship in `sources.py`:

| provider | where the data comes from | needs |
|---|---|---|
| `snapshot` (default) | `data/google.json`, `data/bing.json`, `data/reddit.json`, ranked by query overlap | nothing |
| `brightdata` | SERP `/request` (zone, `brd_json=1`) + Reddit datasets (trigger → poll → download) | `BRIGHTDATA_API_KEY` and a SERP zone |

Pick one, in this order of precedence:

1. `--provider NAME` on the command line
2. `--live` (shorthand for `--provider brightdata`)
3. `SEARCH_PROVIDER` in `.env`
4. default `snapshot`

```powershell
uv run python agent.py                      # local JSON
uv run python agent.py --live               # BrightData
uv run python agent.py --provider snapshot  # same as the default
```

Keys go in `.env` next to the script (copy `.env.example`):

```
DEEPSEEK_API_KEY=...
BRIGHTDATA_API_KEY=...
BRIGHTDATA_ZONE=ai_agent2
```

Live Reddit calls are asynchronous snapshots, so they are slower; any provider error inside a node becomes an empty source and synthesis names the gap. The Reddit dataset ids default to BrightData's public ones; override them with `BRIGHTDATA_REDDIT_DATASET` and `BRIGHTDATA_COMMENTS_DATASET` if your account uses different datasets.

### BrightData setup

The lab does not ship a zone. `BRIGHTDATA_ZONE` must name a **SERP / Web Scraper API** zone in *your* BrightData account that can fetch a full Google/Bing URL with `brd_json=1`. The reference's `ai_agent2` is somebody else's zone; leaving it in `.env` produces:

```
HTTP 400: zone "ai_agent2" not found
```

1. Create (or pick) a SERP zone in the BrightData dashboard. `uv run python agent.py --zones` lists your active zones; if it prints `no active zones`, none exists yet.
2. Put its name in `.env`: `BRIGHTDATA_ZONE=your_zone_name`.
3. Reddit uses the datasets API, only when `REDDIT_ENABLED=true`. The public dataset ids in `.env.example` work if your account has access; otherwise set `BRIGHTDATA_REDDIT_DATASET` / `BRIGHTDATA_COMMENTS_DATASET`, or stay on `snapshot`.
4. Verify without spending model calls:

```powershell
uv run python agent.py --check
```

Expected: `check: ok`, result counts for Google and Bing, then either `reddit disabled (REDDIT_ENABLED=false)` or `reddit trigger accepted (snapshot ...); polling skipped` when `REDDIT_ENABLED=true`. Any `400` now prints the API's own message.

### Adding another provider (e.g. Oxylabs)

No third adapter is implemented yet — the interface is the extension point. A provider is a small class in `sources.py`:

1. Implement the four members. `search` and `reddit_search` return `{title, url, snippet}`; `reddit_threads` returns `{title, url, comments}` and must drop URLs it does not recognize; `check` raises a clear error when a key or config is missing; `name` is what users pass to `--provider`.
2. Register it once:

```python
from oxylabs_provider import OxylabsProvider

PROVIDERS["oxylabs"] = OxylabsProvider
```

3. Run it:

```powershell
uv run python agent.py --provider oxylabs
```

The graph, prompts and state do not change. This is the whole seam — BrightData, Oxylabs, SerpAPI, Tavily or your own index are interchangeable behind it.

## Files

| file | role |
|---|---|
| `agent.py` | state, nodes, both graph shapes, trace runner, CLI |
| `sources.py` | the provider seam; snapshot default, BrightData dispatch |
| `brightdata.py` | live SERP + Reddit datasets: trigger, poll, download |
| `settings.py` | loads `.env` once before anything reads `os.environ` |
| `.env.example` | copy to `.env`; keys and provider settings |
| `prompts.py` | one analyzer prompt, one selector, one synthesis |
| `common.py` | one `ChatDeepSeek` builder and the missing-key message |
| `data/google.json` | recorded Google results |
| `data/bing.json` | recorded Bing results |
| `data/reddit.json` | recorded Reddit threads and comments |
| `graph.png` | rendered reference graph |
| `graph-critical.png` | rendered critical-path graph |
| `pyproject.toml` | uv project: `langgraph`, `langchain`, `langchain-deepseek`, `python-dotenv`, `requests` |

## If it fails

- **`DEEPSEEK_API_KEY is not set`** — copy `.env.example` to `.env` and fill it, or set the shell variable. The script prints the exact lines and exits 1.
- **`BRIGHTDATA_API_KEY is not set, and this run asked for --live`** — add it to `.env`, or run without `--live` to use the recorded snapshots.
- **BrightData `401` / `403`** — the key is wrong.
- **`HTTP 400: zone "…" not found`** — `BRIGHTDATA_ZONE` is not a SERP zone in your account. Run `uv run python agent.py --zones`; `no active zones` means you must create one. `ai_agent2` belongs to the reference author.
- **`HTTP 400` on `/datasets/v3/trigger`** — the Reddit dataset is not available on your account, or the trigger was rejected; the response body is printed. Set `BRIGHTDATA_REDDIT_DATASET` / `BRIGHTDATA_COMMENTS_DATASET` to datasets you have, or use `snapshot`.
- **BrightData snapshot timeout** — Reddit datasets are asynchronous; raise `BRIGHTDATA_POLL_SECONDS` in `.env` and retry.
- **Anything BrightData** — run `uv run python agent.py --check` first: it tests the key, zone and dataset trigger without any DeepSeek calls.
- **`.env` seems ignored** — run from this folder (`load_dotenv()` looks here), and remember shell variables win over `.env`.
- **`InvalidUpdateError: At key 'analyses': Can receive only one value per step`** — you removed `Annotated[dict, merge_analyses]`. Three parallel analyzers write the same key; without a reducer LangGraph refuses the concurrent update.
- **`synthesize` ran twice** — you used separate edges for a join whose predecessors start in different supersteps. Use the list edge.
- **A wrong or invented Reddit URL** — the selector can only return URLs from the supplied list; `select_reddit_urls` filters against `reddit_results` before fetching.
- **A source is empty** — expected under `--fail` or a provider failure; synthesis names it. Do not "fix" it by hiding the gap.
