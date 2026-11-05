# 0010 — LangGraph: one node, then one branch

Two scripts, one idea: **a node is a function that returns a delta; an edge decides who runs next.**

- `simple.py` — the smallest useful graph: `START -> chatbot -> END`. Four nouns, no branch.
- `main.py` — a classifier reads the message, a conditional edge picks one of two specialists, and the run ends. Same four nouns, now with a decision.

The model is **DeepSeek** through `ChatDeepSeek`, and the two routes are NimbusDesk **billing** and **technical**, so the branch carries facts from lessons 7–9.

## Run

```powershell
cd assets\examples\0010-langgraph
uv sync

$env:DEEPSEEK_API_KEY = "sk-..."

uv run python simple.py
uv run python main.py "How long is the refund window on an annual plan?"
uv run python main.py "Outlook sync fails with E-311" --trace
uv run python main.py                  # interactive, keeps history
uv run python main.py --mermaid        # print the diagram source
```

The key comes from https://platform.deepseek.com. Without it, both scripts print the exact PowerShell lines and exit 1 — they never guess.

## What you should see

`uv run python simple.py`:

```
question: In one sentence, what does a router do in a LangGraph?
reply:    A router in LangGraph directs the flow of execution by conditionally selecting which node(s) to run next based on the current state, enabling branching and dynamic control flow in the graph.

state: 2 messages (human, ai)
edges:
  __start__ -> chatbot
  chatbot -> __end__
```

`uv run python main.py "How long is the refund window on an annual plan?"`:

```
route:  billing
answer: A full refund is available within 14 days of the initial charge. After day 14, annual plans are refunded pro rata minus the months used.
```

`uv run python main.py "Outlook sync keeps failing with error E-311. What do I do?" --trace`:

```
question: Outlook sync keeps failing with error E-311. What do I do?
step 1  classify   route=technical
step 2  technical  replied (123 chars)

answer: Error E-311 means the mailbox storage quota was exceeded. To fix it, archive conversations or raise the seat storage limit.
```

`main.py --mermaid` prints the branch as data:

```
graph TD;
	__start__ --> classify;
	classify -.-> billing;
	classify -.-> technical;
	billing --> __end__;
	technical --> __end__;
```

Dotted arrows are conditional edges. There is no line from `billing` back to `classify`: this graph runs once per turn.

Rendered as images: `output1.png` is the one-node graph, `output.png` is the branch.

## The graph, in four nouns

| declaration | in `simple.py` | in `main.py` |
|---|---|---|
| **State** | `TypedDict` with `messages` | adds `route: str \| None` |
| **reducer** | `Annotated[list, add_messages]` — nodes append | same |
| **node** | `chatbot` calls the model | `classify`, `billing`, `technical` |
| **edge** | `START -> chatbot -> END` | `START -> classify`, then a conditional edge |
| **compile** | `graph.compile()` | same |

A node never returns the new state. It returns only its change:

```python
def billing(state: State) -> dict:
    reply = model.invoke([SystemMessage(content=BILLING_PROMPT), *state["messages"]])
    return {"messages": [reply]}          # a delta, merged by add_messages
```

`add_messages` is the reducer. Without it, `messages: list` means last-write-wins: each node replaces the list, and history collapses. Try it: the graph still runs, and the final state holds one message instead of two.

## Why there is no `router` node

A common first version has three graph nodes before the specialists: `classifier -> router -> billing/technical`. The extra `router` node writes `{"next": ...}` into state, and the conditional edge is a lambda that reads `state["next"]`.

That works, but the decision is not work. It does not call a model, read a file, or mutate anything a user would see. It is the edge function wearing a node's clothes. This lab puts it where it belongs:

```python
def pick_specialist(state: State) -> str:
    return state["route"] or "technical"

graph.add_conditional_edges(
    "classify",
    pick_specialist,
    {"billing": "billing", "technical": "technical"},
)
```

Three consequences:

1. **One fewer superstep per turn.** The classifier's delta is routed directly.
2. **No stale field.** `next` is not persisted in state, so it cannot disagree with the route a later turn computed.
3. **The contract is explicit.** The returned string must be a key in that map.

`classify` still writes `route` to state — that is *data* the run can be inspected for, not a control signal the edge has to look up.

## Break it: an edge returns a key, not a delta

Two failures worth causing once. Both were run against this graph with the conditional edge changed:

**Return a name that is not in the map** (`return "refunds"`):

```
KeyError: 'refunds'
During task with name 'classify'
```

**Return a dict from the edge function** (`return {"next": "billing"}`):

```
TypeError: unhashable type: 'dict'
```

The second one is the node/edge split-brain case: a *node* may return `{"next": ...}`, because nodes return deltas. An *edge function* must return a node name (or `END`, or a list of names). If you move the router's body into the edge without dropping the dict, LangGraph tries to hash it as a key. Reading the error tells you which of the two roles you are in.

## Multi-turn: state is not memory

`chat_loop()` keeps the returned state and feeds it into the next turn:

```python
state = app.invoke(
    {**state, "messages": state["messages"] + [HumanMessage(content=text)]}
)
```

Without a checkpointer, that is the only memory there is: exit the process and the conversation is gone. A checkpointer plus a `thread_id` makes the graph read its own history back — the next step in the LangGraph arc, and the reason production agents can resume after a crash.

## Files

| file | role |
|---|---|
| `simple.py` | one node, two edges, `add_messages`; prints the compiled edges |
| `main.py` | classifier + conditional edge + two specialists; `--trace`, `--mermaid`, REPL |
| `common.py` | one `ChatDeepSeek` builder and the missing-key message |
| `output1.png` | rendered one-node graph (`START -> chatbot -> END`) |
| `output.png` | rendered branch (`classify` -> `billing` / `technical`) |
| `pyproject.toml` | uv project: `langgraph`, `langchain`, `langchain-deepseek`, `pydantic` |

## If it fails

- **`DEEPSEEK_API_KEY is not set`** — the script prints the three PowerShell lines. Copy them, then run again in the same terminal.
- **401 / 402 / timeout** — the wrapper prints the exception type and reminds you to check the key, balance, and network. The graph itself never sees the error.
- **Wrong route** — the classifier is a model call, so this is an eval problem, not a graph problem. Grow a small set of messages with expected routes and score it the way lesson 5 scores answers; the graph only obeys the label it was given.
- **`KeyError: '<name>'`** — a conditional edge returned a node name that is not a key in its map. Add the node and the map entry, or return an existing one.
- **`TypeError: unhashable type: 'dict'`** — you returned a state delta from an edge function. Return a node name; deltas belong in nodes.
