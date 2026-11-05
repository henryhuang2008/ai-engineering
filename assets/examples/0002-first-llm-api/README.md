# 0002 — First LLM call: messages, streaming, tools, structured output

One LangChain model handle (`ChatDeepSeek`), four stages. The point is the **shape of
the conversation**, not the vendor: every stage is messages in, messages out.

| stage | what it shows | stable result |
|---|---|---|
| 1. chat | `SystemMessage` + `HumanMessage` → `AIMessage`; turn 2 re-sends the whole history | 2 messages, then **4** |
| 2. streaming | `model.stream()` yields `AIMessageChunk` pieces; join them and you get the `invoke()` text | join == `invoke()`; the final chunk is often empty |
| 3. tools | `bind_tools()` → `AIMessage.tool_calls` → your code runs the tool → `ToolMessage` → one more call | thread grows **4 → 5** (one round trip) |
| 4. structured | `with_structured_output(SupportTicket, method="function_calling")` returns a validated pydantic instance | a `SupportTicket` object, not a dict |

Stage 3 is **one round trip, not an agent**. The model asks; your code executes; the
model answers. An agent is this loop repeated until no tool calls remain — that is
Lesson 3, by hand.

Model *wording* varies between runs. The counts above are structural (messages you
constructed), and `evals.py` asserts the contract, not the sentences.

## Run

The lab calls the live DeepSeek API. There is no fake model and no offline mode.

```powershell
# key, this terminal only
$env:DEEPSEEK_API_KEY = "sk-..."

# or persist for future terminals, then reopen the terminal
setx DEEPSEEK_API_KEY "sk-..."
```

```powershell
cd assets\examples\0002-first-llm-api
uv sync                        # create .venv from pyproject.toml + uv.lock
uv run python langchain_lab.py # four stages against DeepSeek
uv run python evals.py         # 32 offline checks; +2 live with a key
```

`uv sync` is the install step: `pyproject.toml` declares the dependencies and
`uv.lock` pins the exact graph, so no `venv` + `pip` dance and no drift between
machines. No uv yet: `winget install --id=astral-sh.uv`, or `pip install uv`.

Get a key at <https://platform.deepseek.com/api_keys>; the account needs a small
prepaid balance. Without a key the lab prints the two key commands and exits 1 — no
silent fallback to canned text.

Optional overrides:

| variable | default |
|---|---|
| `DEEPSEEK_MODEL` | `deepseek-flash` |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |

## DeepSeek notes

- `deepseek-flash` is the current model name (DeepSeek-V4.1-Flash-1017) and supports
  tool calls and JSON output; `deepseek-v4-pro` is the larger option.
- The API is OpenAI-compatible, which is why `langchain-deepseek` can reuse the
  OpenAI transport. The key is `DEEPSEEK_API_KEY`.
- DeepSeek thinks by default; the lab passes
  `extra_body={"thinking": {"type": "disabled"}}` because this lesson is about
  plumbing. Remove it to watch the reasoning tokens (and pay for them).
- DeepSeek has no OpenAI-style `json_schema` response format, so structured output
  uses tool calling: `with_structured_output(SupportTicket, method="function_calling")`

## Files

| file | role |
|---|---|
| `langchain_lab.py` | the four stages and the live `ChatDeepSeek` wiring |
| `evals.py` | 32 offline checks (schema, tool contract, message shapes, model config, missing-key message, no fake model, uv project) plus a conditional live smoke |
| `pyproject.toml` | dependencies and Python floor — the single source of truth |
| `uv.lock` | the pinned dependency graph `uv sync` installs |
| `index.html` | this lab rendered for the course |

Versions pinned by `uv.lock`: `langchain 1.4.8`, `langchain-core 1.7.4`,
`langchain-deepseek 1.1.1`, `pydantic 2.14.2` (Python 3.12).

Lesson: [lessons/0002-your-first-llm-api-call.html](../../../lessons/0002-your-first-llm-api-call.html)
