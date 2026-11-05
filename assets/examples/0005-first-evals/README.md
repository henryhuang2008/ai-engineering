# 0005 — Your first evals: dataset, scorer, runner, gate

Four parts, one comparison. The harness is plain Python — a JSONL file, a loop, a
counter — and the model call is the lesson-2 stack: one `ChatDeepSeek` handle,
`with_structured_output(SupportTicket)`, `temperature=0`. Nothing here is a
framework; everything here is a habit you will use on every change for the rest
of the course.

| part | what it is | in this lab |
|---|---|---|
| dataset | fixed cases with expected answers | `dataset.jsonl`, 12 curated tickets |
| scorer | a function that judges one output | `got == expected` — classification has a right answer |
| runner | loops cases, collects outputs, prints a number | `run()` -> `Result(accuracy, failures)` |
| gate | an exit code CI can act on | `--threshold 0.9` -> exit 1 below the line |

`dataset.jsonl` is read as `utf-8-sig`, so a case file saved by Windows PowerShell
(which prepends a BOM) still loads instead of failing on line 1.

## Run

```powershell
cd assets\examples\0005-first-evals
uv sync
$env:DEEPSEEK_API_KEY = "sk-..."          # this terminal only
uv run python eval.py                     # accuracy on the 12 cases
uv run python eval.py --threshold 1.0     # gate: any miss exits 1
```

Real output:

```
prompt: Classify the support ticket into billing, bug, or question.
accuracy: 12/12 = 100%
gate: 100% vs threshold 90% -> pass
```

Write that number down. It is your **baseline**, and it only means something
compared with the next run.

## Break it on purpose

A harness you have not seen fail is a harness you cannot trust. Three experiments,
each one variable:

| experiment | command | what actually happens |
|---|---|---|
| weak prompt | `$env:CLASSIFIER_PROMPT = "Answer question for every ticket."` | often **100% anyway** — with function calling the enum + ticket text decide the label, so the system prompt has less leverage than you expect. A null result is a result: the change did not matter. |
| retired model | `$env:DEEPSEEK_MODEL = "deepseek-retired"` | **0/12**, every case prints `ERROR: OpenAIInvalidRequestError ...`, gate exits 1. The gate catches outages, not only quality. |
| wrong label | change one `expected` in `dataset.jsonl` | **11/12** — a bad label is indistinguishable from a model failure until you read the case. |

Restore after each (`Remove-Item Env:CLASSIFIER_PROMPT`, `Remove-Item Env:DEEPSEEK_MODEL`)
and re-run to confirm you are back at the baseline. One variable per experiment is
the whole discipline.

## The gate

`eval.py` returns 0 when accuracy is at or above `--threshold`, 1 otherwise. That
is all CI needs:

```powershell
uv run python eval.py --threshold 0.9
if ($LASTEXITCODE -ne 0) { throw "eval gate failed" }
```

Wire that into Jenkins, GitHub Actions, or a pre-push hook and a prompt change can
no longer merge on vibes. The default threshold is 0.9; `--threshold 1.0` is the
strict mode while a suite is small.

## Checking your work

The lab is its own check: a correct harness prints `12/12 = 100%` and exits 0. If
the number differs, the `FAIL` lines tell you which moved — the model (errors), the
labels (one case), or the wiring (everything).

## DeepSeek notes

- `with_structured_output(SupportTicket, method="function_calling")` uses DeepSeek's
  tool calling. The pydantic model becomes the tool schema, so the label enum is
  enforced by the API, not by string parsing.
- `temperature=0` makes runs comparable. DeepSeek still does not promise identical
  text across runs, which is why the scorer compares **labels**, not prose.
- Thinking is disabled (`extra_body={"thinking": {"type": "disabled"}}`): this lab
  measures the classifier, not the reasoning trace.
- Overrides: `DEEPSEEK_MODEL` (default `deepseek-flash`), `DEEPSEEK_BASE_URL`,
  `CLASSIFIER_PROMPT` (the system prompt under test).

## Files

| file | role |
|---|---|
| `eval.py` | the whole harness: schema, model wiring, runner, gate, CLI |
| `dataset.jsonl` | 12 cases, one `{"ticket", "expected"}` per line |
| `pyproject.toml` | dependencies and Python floor — the single source of truth |
| `uv.lock` | the pinned dependency graph `uv sync` installs |
| `index.html` | this page, generated for the course — not needed to run the lab |

Generated, safe to delete and recreate: `.venv\` (`uv sync`).

Versions pinned by `uv.lock`: `langchain 1.4.8`, `langchain-core 1.7.4`,
`langchain-deepseek 1.1.1`, `pydantic 2.14.2` (Python 3.12).

Lesson: [lessons/0005-your-first-evals.html](../../../lessons/0005-your-first-evals.html)
