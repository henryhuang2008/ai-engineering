# 0003 — Function calling: the model asks, your code acts

One LangChain handle (`ChatDeepSeek`), five stages. The model never runs anything: it
returns a **request** (`AIMessage.tool_calls`), your code decides whether to run it,
executes the real function, and reports back with a `ToolMessage`. Repeat until the
model answers in plain text — that loop is the atom of agency.

| stage | what it shows | stable result |
|---|---|---|
| 1. catalog | two `@tool` functions → name, description, parameter schema. The model never sees the bodies | 2 tools; `required` is `['ticket_id']` and `['ticket_id', 'amount_usd']` |
| 2. one call | `bind_tools()` → `AIMessage.tool_calls` → `execute()` → `ToolMessage` → one more call | thread **3 → 5** messages; the tool result carries the call id |
| 3. the loop | a refund needs two rounds (look up, then refund); the loop ends when `tool_calls` is empty | iterations **2–3**, `stopped: answer` |
| 4. the guard | `T-1002` is not refundable → the tool returns `{"error": "ticket not refundable"}` and the model must read it | `stopped: answer`, no invented success |
| 5. the cap | `max_iterations=1` on the same refund task | `stopped: budget`, 1 iteration, empty answer |

Model *wording* varies between runs. Message counts, call ids, and the loop's stop
reason are structural — `evals.py` asserts those, not the sentences.

## Run

The lab calls the live DeepSeek API. There is no fake model and no offline mode.

```powershell
# key, this terminal only
$env:DEEPSEEK_API_KEY = "sk-..."

# or persist for future terminals, then reopen the terminal
setx DEEPSEEK_API_KEY "sk-..."
```

```powershell
cd assets\examples\0003-function-calling
uv sync                              # create .venv from pyproject.toml + uv.lock
uv run python function_calling_lab.py # five stages against DeepSeek
uv run python evals.py                # 54 offline checks; +3 live with a key
```

`uv sync` is the install step: `pyproject.toml` declares the dependencies and
`uv.lock` pins the exact graph, so no `venv` + `pip` dance and no drift between
machines. No uv yet: `winget install --id=astral-sh.uv`, or `pip install uv`.

Get a key at <https://platform.deepseek.com/api_keys>; the account needs a small
prepaid balance. Without a key the lab prints the two key commands and exits 1 — no
silent fallback.

Optional overrides:

| variable | default |
|---|---|
| `DEEPSEEK_MODEL` | `deepseek-flash` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |
| `MAX_ITERATIONS` | `10` |

## What the self-tests cover

Everything that does not need the network: the fixture, both tool contracts
(required arguments, description text), the tool bodies (refund allowed / refused /
unknown ticket), the catalog the model receives, `execute()` for good calls, unknown
tools and invalid arguments, the loop's control flow (answer vs budget, message
shapes, call-id pairing) driven by a test double defined **in `evals.py`**, the
missing-key instructions, the model wiring, and the uv project. With a key, three
more checks fire: one live call must return an `AIMessage` that requests
`get_ticket_status`.

## DeepSeek notes

- `deepseek-flash` supports tool calls; `deepseek-v4-pro` is the larger option. Same
  key, same base URL.
- The lab disables DeepSeek thinking for speed. If you turn thinking on
  (`extra_body={"thinking": {"type": "enabled"}}`), tool turns require every earlier
  `reasoning_content` to be echoed back or the API answers 400 — which is why the
  loop keeps the raw `AIMessage` instead of rebuilding messages by hand.
- `strict` mode (Beta) pins argument shapes to your JSON schema: use the
  `https://api.deepseek.com/beta` base URL and set `strict: true` per function.
- LangChain maps `AIMessage.tool_calls` and `ToolMessage` onto DeepSeek's OpenAI-shaped
  wire format, so the same loop runs unchanged on other providers.

## Files

| file | role |
|---|---|
| `function_calling_lab.py` | the five stages, the hand-written loop, and the live `ChatDeepSeek` wiring |
| `evals.py` | 54 offline checks (fixture, tool contracts, catalog, execution, loop control flow, budget, model config, missing-key message, no fake model, uv project) plus a conditional live smoke |
| `pyproject.toml` | dependencies and Python floor — the single source of truth |
| `uv.lock` | the pinned dependency graph `uv sync` installs |
| `index.html` | this lab rendered for the course |

Versions pinned by `uv.lock`: `langchain 1.4.8`, `langchain-core 1.7.4`,
`langchain-deepseek 1.1.1`, `pydantic 2.14.2` (Python 3.12).

Lesson: [lessons/0003-function-calling.html](../../../lessons/0003-function-calling.html)
